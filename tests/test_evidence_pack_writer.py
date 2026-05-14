from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import subprocess
import tarfile
import tempfile
import builtins
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import evidence_pack_verify
import evidence_pack_writer


def _inputs(tmp_path: Path, *, run_id: str = "0123456789abcdef", created_at: str = "2026-05-11T18:00:00+00:00") -> evidence_pack_writer.RunInputs:
    artifact = tmp_path / "report.md"
    artifact.write_text("evidence\n", encoding="utf-8")
    return evidence_pack_writer.RunInputs(
        run_id=run_id,
        factory_version="v0.7.0",
        ao_runtime_version="v0.2.0",
        created_at=created_at,
        completed_at="2026-05-11T18:14:32+00:00",
        operator=evidence_pack_writer.OperatorRecord(
            host_fingerprint="sha256:host",
            user_label="operator-host-mac",
        ),
        profile=evidence_pack_writer.ProfileRecord(
            name="evidence",
            version="v1",
            policy_digest="sha256:policy",
        ),
        providers=[
            evidence_pack_writer.ProviderRecord(
                role="planner-intake",
                name="codex",
                version="0.42.1",
            ),
        ],
        tasks=[
            evidence_pack_writer.TaskRecord(
                task_id="intake",
                role="planner-intake",
                status="completed",
                started_at="2026-05-11T18:00:01+00:00",
                completed_at="2026-05-11T18:01:00+00:00",
            ),
        ],
        events=[
            {
                "ts": "2026-05-11T18:00:01+00:00",
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "span_id": "b7ad6b7169203331",
                "type": "task.started",
                "task_id": "intake",
                "attrs": {},
            },
            {
                "ts": "2026-05-11T18:01:00+00:00",
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "span_id": "b7ad6b7169203332",
                "type": "task.completed",
                "task_id": "intake",
                "attrs": {},
            },
        ],
        transcripts={
            "intake": [
                {"role": "user", "content": "brief", "ts": "2026-05-11T18:00:02+00:00"},
                {"role": "assistant", "content": "done", "ts": "2026-05-11T18:00:03+00:00"},
            ],
        },
        artifact_paths={"intake": [artifact]},
    )


def _write_input_json(tmp_path: Path) -> Path:
    inputs = _inputs(tmp_path)
    raw = asdict(inputs)
    raw["artifact_paths"] = {
        task_id: [str(path) for path in paths]
        for task_id, paths in inputs.artifact_paths.items()
    }
    input_json = tmp_path / "input.json"
    input_json.write_text(json.dumps(raw), encoding="utf-8")
    return input_json


def _force_missing_cryptography(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("cryptography"):
            raise ImportError("cryptography intentionally unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_merkle_root_empty():
    assert evidence_pack_writer.merkle_root([]) == hashlib.sha256(b"").hexdigest()


def test_merkle_root_single_leaf():
    leaf = hashlib.sha256(b"leaf").hexdigest()

    assert evidence_pack_writer.merkle_root([leaf]) == leaf


def test_merkle_root_two_leaves():
    left, right = sorted([hashlib.sha256(b"a").hexdigest(), hashlib.sha256(b"b").hexdigest()])
    expected = hashlib.sha256(bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()

    assert evidence_pack_writer.merkle_root([right, left]) == expected


def test_merkle_root_odd_count_duplicates_last():
    leaves = sorted([hashlib.sha256(value).hexdigest() for value in (b"a", b"b", b"c")])
    ab = hashlib.sha256(bytes.fromhex(leaves[0]) + bytes.fromhex(leaves[1])).hexdigest()
    cc = hashlib.sha256(bytes.fromhex(leaves[2]) + bytes.fromhex(leaves[2])).hexdigest()
    expected = hashlib.sha256(bytes.fromhex(ab) + bytes.fromhex(cc)).hexdigest()

    assert evidence_pack_writer.merkle_root(list(reversed(leaves))) == expected


def test_hmac_signer_short_key_raises():
    with pytest.raises(ValueError, match="at least 16 bytes"):
        evidence_pack_writer.HMACSigner(b"too-short")


def test_hmac_signer_sign_round_trip():
    key = b"0123456789abcdef"
    signer = evidence_pack_writer.HMACSigner(key)

    assert signer.sign(b"payload") == hmac.new(key, b"payload", hashlib.sha256).digest()


def test_write_pack_creates_expected_layout(tmp_path):
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(b"0123456789abcdef"),
    )

    assert (pack / "manifest.json").is_file()
    assert (pack / "events.ndjson").is_file()
    assert (pack / "transcripts" / "intake.ndjson").is_file()
    assert (pack / "artifacts").is_dir()
    assert (pack / "signatures" / "pack.sig").is_file()
    assert (pack / "signatures" / "pubkey").is_file()


def test_write_pack_manifest_round_trip(tmp_path):
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(b"0123456789abcdef"),
    )

    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_pack_version"] == "ao-operator/evidence-pack/v1"
    assert manifest["run_id"] == "0123456789abcdef"
    assert manifest["merkle_root"].startswith("sha256:")
    assert manifest["signature_algo"] == "HMAC-SHA256"


def test_write_pack_manifest_includes_deterministic_replay_declaration(tmp_path):
    inputs = replace(
        _inputs(tmp_path),
        tasks=[
            evidence_pack_writer.TaskRecord(
                task_id="intake",
                role="planner-intake",
                status="completed",
                started_at="2026-05-11T18:00:01+00:00",
                completed_at="2026-05-11T18:01:00+00:00",
                deterministic=True,
                replay_command=["python3", "scripts/replay_intake.py"],
                replay_outputs=["report.md"],
            ),
        ],
    )

    pack = evidence_pack_writer.write_pack(
        inputs,
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(b"0123456789abcdef"),
    )

    task = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))["tasks"][0]
    assert task["deterministic"] is True
    assert task["replay_command"] == ["python3", "scripts/replay_intake.py"]
    assert task["replay_outputs"] == ["report.md"]


def test_write_pack_artifact_cas_dedup(tmp_path):
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")
    inputs = replace(_inputs(tmp_path), artifact_paths={"intake": [first, second]})

    pack = evidence_pack_writer.write_pack(
        inputs,
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(b"0123456789abcdef"),
    )

    assert len([path for path in (pack / "artifacts").iterdir() if path.is_dir()]) == 1


def test_write_pack_deterministic_modulo_timestamps(tmp_path):
    key = b"0123456789abcdef"
    first = evidence_pack_writer.write_pack(
        _inputs(tmp_path, run_id="aaaaaaaaaaaaaaaa", created_at="2026-05-11T18:00:00+00:00"),
        tmp_path / "packs-a",
        evidence_pack_writer.HMACSigner(key),
    )
    second = evidence_pack_writer.write_pack(
        _inputs(tmp_path, run_id="bbbbbbbbbbbbbbbb", created_at="2026-05-11T19:00:00+00:00"),
        tmp_path / "packs-b",
        evidence_pack_writer.HMACSigner(key),
    )

    left = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    right = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    for variable in ("created_at", "run_id"):
        left.pop(variable)
        right.pop(variable)
    assert left == right


def test_write_pack_signature_verifies(tmp_path):
    key = b"0123456789abcdef"
    signer = evidence_pack_writer.HMACSigner(key)
    pack = evidence_pack_writer.write_pack(_inputs(tmp_path), tmp_path / "packs", signer)
    manifest_bytes = (pack / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    sig_input = hashlib.sha256(manifest_bytes).digest() + bytes.fromhex(
        manifest["merkle_root"].removeprefix("sha256:")
    )

    assert hmac.compare_digest((pack / "signatures" / "pack.sig").read_bytes(), signer.sign(sig_input))


def test_write_pack_refuses_to_overwrite(tmp_path):
    inputs = _inputs(tmp_path)
    signer = evidence_pack_writer.HMACSigner(b"0123456789abcdef")
    evidence_pack_writer.write_pack(inputs, tmp_path / "packs", signer)

    with pytest.raises(FileExistsError):
        evidence_pack_writer.write_pack(inputs, tmp_path / "packs", signer)


def test_try_ed25519_signer_missing_crypto_raises_helpful_error(tmp_path, monkeypatch):
    _force_missing_cryptography(monkeypatch)

    with pytest.raises(ImportError, match="install cryptography"):
        evidence_pack_writer.try_ed25519_signer(tmp_path / "missing.pem")


def test_writer_cli_accepts_ed25519_private_key_flag(tmp_path, monkeypatch):
    _force_missing_cryptography(monkeypatch)
    input_json = _write_input_json(tmp_path)

    with pytest.raises(ImportError, match="install cryptography"):
        evidence_pack_writer.main(
            [
                str(input_json),
                str(tmp_path / "packs"),
                "--ed25519-private-key",
                str(tmp_path / "operator-ed25519.pem"),
            ]
        )


def test_ed25519_signer_round_trips_when_cryptography_available(tmp_path):
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    key_path = tmp_path / "operator-ed25519.pem"
    key = ed25519.Ed25519PrivateKey.generate()
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.try_ed25519_signer(key_path),
    )

    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["signature_algo"] == "Ed25519"
    assert evidence_pack_verify.verify_pack(pack)["verdict"] == "PASS"


def test_write_tar_zst_creates_archive_with_manifest_first(tmp_path):
    if shutil.which("zstd") is None:
        pytest.skip("zstd CLI not installed")
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(b"0123456789abcdef"),
    )

    archive = evidence_pack_writer.write_tar_zst(pack, tmp_path / "archives")

    assert archive.name == "evidence-pack-0123456789abcdef.tar.zst"
    assert archive.is_file()
    with tempfile.TemporaryDirectory() as temp:
        tar_path = Path(temp) / "pack.tar"
        subprocess.run(["zstd", "-q", "-d", "-o", str(tar_path), str(archive)], check=True)
        with tarfile.open(tar_path) as tf:
            assert tf.getnames()[0] == "evidence-pack-0123456789abcdef/manifest.json"
