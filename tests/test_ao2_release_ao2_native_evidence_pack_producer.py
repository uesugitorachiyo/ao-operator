from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_ao2_native_evidence_pack_producer.py"

PRODUCER_SCHEMA = (
    "ao-operator/ao2-release-ao2-native-evidence-pack-producer/v1"
)
AO2_PACK_EVIDENCE_SCHEMA = "ao2.ao-operator-compat-pack-evidence.v1"
AO2_EVIDENCE_PACK_SCHEMA = "ao2.evidence-pack.v1"


def _factory_queue_path(target: Path) -> Path:
    return target / ".ao2" / "factory-compat" / "queue.json"


def _seed_factory_queue(target: Path) -> Path:
    queue = _factory_queue_path(target)
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(
        json.dumps(
            {
                "schema_version": "ao2.ao-operator-compat-workbench-queue.v1",
                "entries": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return queue


def _empty_path_env() -> dict[str, str]:
    return {"PATH": ""}


def _default_unsigned_stdout(evidence_pack_out: Path) -> dict:
    return {
        "schema_version": AO2_PACK_EVIDENCE_SCHEMA,
        "status": "produced",
        "run_id": "fixture-run",
        "queue_path": "<test>",
        "entry_status": "accepted",
        "native_evaluator_verdict": "accepted",
        "evidence_pack_source": "<test-source>",
        "evidence_pack_source_sha256": "deadbeef",
        "evidence_pack_out": str(evidence_pack_out),
        "evidence_pack_sha256": "cafebabe",
        "evidence_pack_schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "evidence_pack_execution_owner": "ao2",
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "deterministic_replay": {
            "schema_version": (
                "ao2.ao-operator-compat-pack-evidence-deterministic-replay.v1"
            ),
            "verified": True,
            "replay_owner": "ao2-factory-pack-evidence",
            "replay_sha256": "cafebabe",
            "written_sha256": "cafebabe",
        },
        "signature": {
            "schema_version": (
                "ao2.ao-operator-compat-pack-evidence-signature.v1"
            ),
            "signed_payload": "evidence_pack_out",
            "signature_verified": False,
            "signature_status": "unsigned",
        },
    }


def _default_signed_stdout(
    evidence_pack_out: Path,
    *,
    signer_id: str = "ao2-factory-pack-evidence-signer",
) -> dict:
    payload = _default_unsigned_stdout(evidence_pack_out)
    payload["signature"] = {
        "schema_version": (
            "ao2.ao-operator-compat-pack-evidence-signature.v1"
        ),
        "signature_algorithm": "RSA/SHA-256",
        "signer_id": signer_id,
        "signed_payload": "evidence_pack_out",
        "signed_payload_path": str(evidence_pack_out),
        "signed_payload_sha256": "cafebabe",
        "signature_path": str(evidence_pack_out) + ".sig",
        "signature_sha256": "feed",
        "public_key_path": str(evidence_pack_out) + ".public.pem",
        "public_key_sha256": "f00d",
        "signature_verified": True,
    }
    return payload


def _write_fake_pack_evidence_binary(
    *,
    path: Path,
    evidence_pack_out: Path,
    pack_body: dict,
    stdout_payload: dict | None = None,
    exit_code: int = 0,
    write_pack_file: bool = True,
) -> Path:
    if stdout_payload is None:
        stdout_payload = _default_unsigned_stdout(evidence_pack_out)
    write_block = ""
    if write_pack_file:
        pack_text = json.dumps(pack_body, indent=2, sort_keys=True)
        write_block = (
            f"mkdir -p {evidence_pack_out.parent!s}\n"
            f"cat > {evidence_pack_out!s} << 'AO2_PACK_EOF'\n"
            f"{pack_text}\n"
            "AO2_PACK_EOF\n"
        )
    stdout_text = json.dumps(stdout_payload)
    script = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f"{write_block}"
        f"printf '%s' {stdout_text!r}\n"
        f"exit {exit_code}\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run_producer(
    *,
    write_json: Path,
    evidence_pack_out: Path,
    ao2_target: Path | None = None,
    run_id: str | None = None,
    ao2_binary: str | None = None,
    signing_key: Path | None = None,
    signer_id: str | None = None,
    require_signed_evidence: bool = False,
    extra_env: dict[str, str] | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--write-json",
        str(write_json),
        "--evidence-pack-out",
        str(evidence_pack_out),
        "--json",
    ]
    if ao2_binary is not None:
        args.extend(["--ao2-binary", ao2_binary])
    if ao2_target is not None:
        args.extend(["--ao2-target", str(ao2_target)])
    if run_id is not None:
        args.extend(["--run-id", run_id])
    if signing_key is not None:
        args.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        args.extend(["--signer-id", signer_id])
    if require_signed_evidence:
        args.append("--require-signed-evidence")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    payload = json.loads(result.stdout)
    on_disk = json.loads(write_json.read_text(encoding="utf-8"))
    assert payload == on_disk
    return payload, result


# ---------------------------------------------------------------------------
# missing-inputs paths
# ---------------------------------------------------------------------------


def test_missing_inputs_when_no_target_or_binary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    out = tmp_path / "pack.json"
    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["schema_version"] == PRODUCER_SCHEMA
    assert payload["status"] == "missing_inputs"
    assert "ao2_target" in payload["missing"]
    assert any(
        m.startswith("ao2_binary_not_on_path:ao2-not-installed")
        for m in payload["missing"]
    )
    assert payload["evidence_pack_emitted"] is False
    assert payload["evidence_pack_path"] is None
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-workbench-queue"
    assert payload["control_plane_role"] == "read_only_observer_after_signed_evidence"
    assert not out.exists(), "no evidence pack written when missing inputs"


def test_missing_inputs_when_target_directory_missing(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    out = tmp_path / "pack.json"
    missing_target = tmp_path / "no-such-target"
    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=missing_target,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith(f"ao2_target_not_found:{missing_target}")
        for m in payload["missing"]
    )


def test_missing_inputs_when_queue_file_absent(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    out = tmp_path / "pack.json"
    target = tmp_path / "ao2-target"
    target.mkdir()
    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("factory_queue_not_found:") for m in payload["missing"]
    )
    assert payload["inputs"]["queue_path"].endswith("queue.json")


# ---------------------------------------------------------------------------
# produced path with fake ao2 binary
# ---------------------------------------------------------------------------


def _setup_fake_target(tmp_path: Path) -> Path:
    target = tmp_path / "ao2-target"
    target.mkdir()
    _seed_factory_queue(target)
    return target


def test_produces_evidence_pack_with_fake_ao2_binary(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "runtime_contract": {
            "execution_owner": "ao2",
            "factory_v3_drives_workflow": False,
        },
        "workflow_tasks": [{"id": "intake"}],
    }
    _write_fake_pack_evidence_binary(
        path=fake_ao2,
        evidence_pack_out=out,
        pack_body=pack_body,
    )

    payload, result = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        run_id="fixture-run",
        ao2_binary=str(fake_ao2),
    )
    assert payload is not None
    assert payload["schema_version"] == PRODUCER_SCHEMA
    assert payload["status"] == "produced"
    assert payload["evidence_pack_emitted"] is True
    assert payload["evidence_pack_path"] == str(out)
    assert payload["evidence_pack_schema"] == AO2_EVIDENCE_PACK_SCHEMA
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-workbench-queue"
    assert (
        payload["control_plane_role"]
        == "read_only_observer_after_signed_evidence"
    )
    summary_body = payload["evidence_pack_summary"]
    assert summary_body["schema_version"] == AO2_PACK_EVIDENCE_SCHEMA
    assert summary_body["run_id"] == "fixture-run"
    assert summary_body["entry_status"] == "accepted"
    assert summary_body["evidence_pack_execution_owner"] == "ao2"
    assert summary_body["evidence_pack_sha256"]
    assert summary_body["evidence_pack_source"]
    assert out.is_file()
    pack_on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert pack_on_disk["schema_version"] == AO2_EVIDENCE_PACK_SCHEMA
    assert pack_on_disk["runtime_contract"]["execution_owner"] == "ao2"
    # AO2 always reports a deterministic_replay block; unsigned baseline.
    replay = payload["evidence_pack_deterministic_replay"]
    assert replay is not None
    assert replay["verified"] is True
    assert replay["replay_owner"] == "ao2-factory-pack-evidence"
    assert replay["written_sha256"] == replay["replay_sha256"]
    # Signature block surfaces verbatim; unsigned status forwarded.
    signature = payload["evidence_pack_signature"]
    assert signature is not None
    assert signature["signature_verified"] is False
    assert signature["signature_status"] == "unsigned"
    # Inputs surface the resolved binary and run_id with no secret leakage,
    # plus signing fields default to None when not requested.
    inputs = payload["inputs"]
    assert inputs["ao2_target"] == str(target)
    assert inputs["run_id"] == "fixture-run"
    assert inputs["ao2_binary_resolved"] == str(fake_ao2)
    assert inputs["queue_path"] == str(_factory_queue_path(target))
    assert inputs["signing_key"] is None
    assert inputs["signer_id"] is None


def test_rejects_pack_with_wrong_schema(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    bad_stdout = {
        "schema_version": AO2_PACK_EVIDENCE_SCHEMA,
        "status": "produced",
        "run_id": "fixture-run",
        "queue_path": "<test>",
        "entry_status": "accepted",
        "native_evaluator_verdict": "accepted",
        "evidence_pack_source": "<test-source>",
        "evidence_pack_source_sha256": "deadbeef",
        "evidence_pack_out": str(out),
        "evidence_pack_sha256": "cafebabe",
        "evidence_pack_schema_version": "not.evidence-pack",  # wrong
        "evidence_pack_execution_owner": "ao2",
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
        "control_plane_role": "read_only_observer_after_signed_evidence",
    }
    _write_fake_pack_evidence_binary(
        path=fake_ao2,
        evidence_pack_out=out,
        pack_body={"schema_version": "not.evidence-pack"},
        stdout_payload=bad_stdout,
    )
    payload, result = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        run_id="fixture-run",
        ao2_binary=str(fake_ao2),
        expect_returncode=1,
    )
    assert payload is None
    assert "schema_version" in (result.stderr or "")
    assert "ao2.evidence-pack.v1" in (result.stderr or "")


def test_rejects_when_ao2_pack_evidence_returns_nonzero(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    script = (
        "#!/usr/bin/env bash\n"
        "echo 'simulated AO2 failure' >&2\n"
        "exit 17\n"
    )
    fake_ao2.write_text(script, encoding="utf-8")
    fake_ao2.chmod(
        fake_ao2.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    payload, result = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        ao2_binary=str(fake_ao2),
        expect_returncode=1,
    )
    assert payload is None
    assert "simulated AO2 failure" in (result.stderr or "")
    assert "exit 17" in (result.stderr or "")


# ---------------------------------------------------------------------------
# signed-evidence passthrough (Phase 2 exit-gate item #4 / #5)
# ---------------------------------------------------------------------------


def _write_signing_key_passthrough_binary(
    *,
    path: Path,
    evidence_pack_out: Path,
    pack_body: dict,
    args_capture: Path,
    stdout_payload: dict,
) -> None:
    """Fake ao2 binary that records its argv to ``args_capture`` so tests can
    prove --signing-key / --signer-id flow from the producer to the AO2 CLI."""
    pack_text = json.dumps(pack_body, indent=2, sort_keys=True)
    stdout_text = json.dumps(stdout_payload)
    script = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f"printf '%s\\n' \"$@\" > {args_capture!s}\n"
        f"mkdir -p {evidence_pack_out.parent!s}\n"
        f"cat > {evidence_pack_out!s} << 'AO2_PACK_EOF'\n"
        f"{pack_text}\n"
        "AO2_PACK_EOF\n"
        f"printf '%s' {stdout_text!r}\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_forwards_signing_key_and_signer_id_to_ao2(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    args_capture = tmp_path / "ao2-argv.txt"
    signing_key = tmp_path / "ephemeral-signing-key.pem"
    signing_key.write_text("-----BEGIN FAKE KEY-----\n", encoding="utf-8")

    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "runtime_contract": {"execution_owner": "ao2"},
    }
    _write_signing_key_passthrough_binary(
        path=fake_ao2,
        evidence_pack_out=out,
        pack_body=pack_body,
        args_capture=args_capture,
        stdout_payload=_default_signed_stdout(
            out, signer_id="ao2-nightly-release-signer"
        ),
    )

    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        run_id="fixture-run",
        ao2_binary=str(fake_ao2),
        signing_key=signing_key,
        signer_id="ao2-nightly-release-signer",
    )
    assert payload is not None
    assert payload["status"] == "produced"

    # AO2 received the flags verbatim, including the signer-id.
    argv = args_capture.read_text(encoding="utf-8").splitlines()
    assert "--signing-key" in argv
    assert str(signing_key) in argv
    assert argv[argv.index("--signing-key") + 1] == str(signing_key)
    assert "--signer-id" in argv
    assert argv[argv.index("--signer-id") + 1] == "ao2-nightly-release-signer"

    # The signed AO2 result surfaces under evidence_pack_signature with all
    # fields the nightly evaluator-decision producer / release-gate needs.
    signature = payload["evidence_pack_signature"]
    assert signature["signature_verified"] is True
    assert signature["signer_id"] == "ao2-nightly-release-signer"
    assert signature["signature_algorithm"] == "RSA/SHA-256"
    assert signature["signed_payload"] == "evidence_pack_out"
    assert signature["signature_path"].endswith(".sig")
    assert signature["public_key_path"].endswith(".public.pem")

    # Inputs record the requested signing key + signer id so the artifact is
    # auditable without re-running AO2.
    inputs = payload["inputs"]
    assert inputs["signing_key"] == str(signing_key)
    assert inputs["signer_id"] == "ao2-nightly-release-signer"


def test_require_signed_evidence_accepts_verified_ao2_result(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    args_capture = tmp_path / "ao2-argv.txt"
    signing_key = tmp_path / "key.pem"
    signing_key.write_text("-----BEGIN FAKE KEY-----\n", encoding="utf-8")

    _write_signing_key_passthrough_binary(
        path=fake_ao2,
        evidence_pack_out=out,
        pack_body={
            "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
            "runtime_contract": {"execution_owner": "ao2"},
        },
        args_capture=args_capture,
        stdout_payload=_default_signed_stdout(out),
    )
    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        ao2_binary=str(fake_ao2),
        signing_key=signing_key,
        require_signed_evidence=True,
    )
    assert payload is not None
    assert payload["status"] == "produced"
    assert payload["evidence_pack_signature"]["signature_verified"] is True
    assert payload["evidence_pack_deterministic_replay"]["verified"] is True


def test_require_signed_evidence_rejects_unsigned_result(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    # AO2 returns the unsigned default — no signing-key forwarded — so the
    # producer must refuse to accept the artifact.
    _write_fake_pack_evidence_binary(
        path=fake_ao2,
        evidence_pack_out=out,
        pack_body={
            "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
            "runtime_contract": {"execution_owner": "ao2"},
        },
    )
    payload, result = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        ao2_binary=str(fake_ao2),
        require_signed_evidence=True,
        expect_returncode=1,
    )
    assert payload is None
    assert "--require-signed-evidence" in (result.stderr or "")
    assert "signature_verified" in (result.stderr or "")


def test_signer_id_without_signing_key_is_rejected(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    out = tmp_path / "pack.json"
    _, result = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        signer_id="ao2-nightly-release-signer",
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
        expect_returncode=1,
    )
    assert "--signer-id requires --signing-key" in (result.stderr or "")


def test_missing_signing_key_file_reported_in_missing_inputs(tmp_path: Path) -> None:
    target = _setup_fake_target(tmp_path)
    out = tmp_path / "packed-evidence.json"
    summary = tmp_path / "evidence-pack-summary.json"
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_ao2 = fake_bin_dir / "ao2"
    fake_ao2.write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    fake_ao2.chmod(
        fake_ao2.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    missing_key = tmp_path / "no-such-key.pem"

    payload, _ = run_producer(
        write_json=summary,
        evidence_pack_out=out,
        ao2_target=target,
        ao2_binary=str(fake_ao2),
        signing_key=missing_key,
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith(f"signing_key_not_found:{missing_key}")
        for m in payload["missing"]
    )
    assert payload["inputs"]["signing_key"] == str(missing_key)
    assert payload["evidence_pack_signature"] is None
    assert payload["evidence_pack_deterministic_replay"] is None
    assert not out.exists()
