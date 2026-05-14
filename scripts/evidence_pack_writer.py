#!/usr/bin/env python3
"""Write AO Operator evidence packs in the frozen v1 wire format.

This module is stdlib-only at import time. It writes the directory layout for
``ao-operator/evidence-pack/v1``. Production tar.zst packaging uses the optional
``zstd`` CLI, and production Ed25519 signing uses an optional lazy
``cryptography`` import.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

EVIDENCE_PACK_VERSION = "ao-operator/evidence-pack/v1"


@dataclass(frozen=True, slots=True)
class OperatorRecord:
    host_fingerprint: str
    user_label: str


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    name: str
    version: str
    policy_digest: str


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    role: str
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    role: str
    status: str
    started_at: str
    completed_at: str
    deterministic: bool = False
    replay_command: list[str] | None = None
    replay_outputs: list[str] | None = None


@dataclass(frozen=True, slots=True)
class RunInputs:
    run_id: str
    factory_version: str
    ao_runtime_version: str
    created_at: str
    completed_at: str
    operator: OperatorRecord
    profile: ProfileRecord
    providers: list[ProviderRecord]
    tasks: list[TaskRecord]
    events: list[dict[str, object]]
    transcripts: dict[str, list[dict[str, object]]]
    artifact_paths: dict[str, list[Path]]


class Signer(Protocol):
    algo: str

    def sign(self, data: bytes) -> bytes:
        ...

    def public_material(self) -> bytes:
        ...


class HMACSigner:
    algo = "HMAC-SHA256"

    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise ValueError("HMAC key must be at least 16 bytes")
        self._key = key

    def sign(self, data: bytes) -> bytes:
        return hmac.new(self._key, data, hashlib.sha256).digest()

    def public_material(self) -> bytes:
        return hashlib.sha256(self._key).digest()


def try_ed25519_signer(privkey_pem_path: Path) -> Signer:
    """Return an Ed25519 signer when optional production crypto is enabled."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise ImportError(
            "install cryptography for production Ed25519 signing; "
            f"{privkey_pem_path} was not loaded in this stdlib-only runtime"
        ) from exc

    key = serialization.load_pem_private_key(privkey_pem_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must be Ed25519")

    class Ed25519Signer:
        algo = "Ed25519"

        def sign(self, data: bytes) -> bytes:
            return key.sign(data)

        def public_material(self) -> bytes:
            return key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

    return Ed25519Signer()


def signer_from_options(
    *,
    hmac_key_hex: str | None = None,
    ed25519_private_key: Path | None = None,
) -> tuple[Signer, bytes | None]:
    """Build exactly one evidence-pack signer from operator CLI options.

    Returns ``(signer, hmac_key)``. ``hmac_key`` is only returned for HMAC so
    the verifier can replay-check HMAC packs without re-reading operator input.
    """
    hmac_key_hex = hmac_key_hex or None
    if bool(hmac_key_hex) == bool(ed25519_private_key):
        raise ValueError("exactly one evidence-pack signer is required")
    if hmac_key_hex:
        hmac_key = bytes.fromhex(hmac_key_hex)
        return HMACSigner(hmac_key), hmac_key
    if ed25519_private_key is None:
        raise ValueError("exactly one evidence-pack signer is required")
    return try_ed25519_signer(ed25519_private_key), None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    """Compute SDD 131 §3 paired SHA-256 over sorted hex leaves."""
    if not leaves:
        return _sha256_bytes(b"")
    level = sorted(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: list[str] = []
        for index in range(0, len(level), 2):
            next_level.append(
                _sha256_bytes(bytes.fromhex(level[index]) + bytes.fromhex(level[index + 1]))
            )
        level = next_level
    return level[0]


def _sort_event(record: dict[str, object]) -> tuple[str, str]:
    return (str(record.get("ts", "")), str(record.get("span_id", "")))


def _write_ndjson(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            fh.write("\n")


def _relative_file_hashes(root: Path) -> list[str]:
    leaves: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts[0] == "signatures" or rel.name == "manifest.json":
            continue
        leaves.append(_sha256_file(path))
    return leaves


def build_manifest(
    inputs: RunInputs,
    transcript_paths: dict[str, str],
    artifact_shas: dict[str, list[str]],
    merkle_root_value: str,
    signature_algo: str,
) -> dict[str, object]:
    tasks: list[dict[str, object]] = []
    for task in inputs.tasks:
        body = asdict(task)
        if not body["deterministic"]:
            body.pop("deterministic")
        if body["replay_command"] is None:
            body.pop("replay_command")
        if body["replay_outputs"] is None:
            body.pop("replay_outputs")
        body["transcript_path"] = transcript_paths.get(task.task_id, "")
        body["artifact_shas"] = artifact_shas.get(task.task_id, [])
        tasks.append(body)
    return {
        "evidence_pack_version": EVIDENCE_PACK_VERSION,
        "run_id": inputs.run_id,
        "factory_version": inputs.factory_version,
        "ao_runtime_version": inputs.ao_runtime_version,
        "created_at": inputs.created_at,
        "completed_at": inputs.completed_at,
        "operator": asdict(inputs.operator),
        "profile": asdict(inputs.profile),
        "providers": [asdict(provider) for provider in inputs.providers],
        "tasks": tasks,
        "merkle_root": f"sha256:{merkle_root_value}",
        "signature_algo": signature_algo,
        "schema_version": 1,
    }


def write_pack(inputs: RunInputs, dest_dir: Path, signer: Signer) -> Path:
    pack_root = dest_dir / f"evidence-pack-{inputs.run_id}"
    if pack_root.exists():
        raise FileExistsError(str(pack_root))
    pack_root.mkdir(parents=True)

    _write_ndjson(pack_root / "events.ndjson", sorted(inputs.events, key=_sort_event))

    transcript_paths: dict[str, str] = {}
    for task_id, records in sorted(inputs.transcripts.items()):
        rel_path = Path("transcripts") / f"{task_id}.ndjson"
        _write_ndjson(
            pack_root / rel_path,
            sorted(records, key=lambda record: str(record.get("ts", ""))),
        )
        transcript_paths[task_id] = rel_path.as_posix()

    artifact_shas: dict[str, list[str]] = {}
    for task_id, paths in sorted(inputs.artifact_paths.items()):
        task_shas: list[str] = []
        for source in paths:
            sha = _sha256_file(source)
            sha_dir = pack_root / "artifacts" / sha
            sha_dir.mkdir(parents=True, exist_ok=True)
            target = sha_dir / source.name
            if not target.exists():
                shutil.copyfile(source, target)
            task_shas.append(f"sha256:{sha}")
        artifact_shas[task_id] = sorted(set(task_shas))

    root = merkle_root(_relative_file_hashes(pack_root))
    manifest = build_manifest(inputs, transcript_paths, artifact_shas, root, signer.algo)
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    (pack_root / "manifest.json").write_bytes(manifest_bytes)

    sig_input = hashlib.sha256(manifest_bytes).digest() + bytes.fromhex(root)
    signatures = pack_root / "signatures"
    signatures.mkdir()
    (signatures / "pack.sig").write_bytes(signer.sign(sig_input))
    (signatures / "pubkey").write_bytes(signer.public_material())
    return pack_root


def _canonical_pack_members(pack_root: Path) -> list[Path]:
    manifest = pack_root / "manifest.json"
    rest = sorted(
        path
        for path in pack_root.rglob("*")
        if path.is_file() and path != manifest
    )
    return [manifest, *rest]


def write_tar_zst(pack_root: Path, dest_dir: Path) -> Path:
    """Write canonical evidence-pack-<run_id>.tar.zst using optional zstd CLI."""
    zstd = shutil.which("zstd")
    if zstd is None:
        raise ImportError("install zstandard or zstd CLI for production .tar.zst packaging")
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"{pack_root.name}.tar.zst"
    if archive.exists():
        raise FileExistsError(str(archive))
    with tempfile.TemporaryDirectory(prefix="ao-operator-evidence-pack-tar-") as tmp:
        tar_path = Path(tmp) / f"{pack_root.name}.tar"
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tf:
            for path in _canonical_pack_members(pack_root):
                tf.add(path, arcname=(Path(pack_root.name) / path.relative_to(pack_root)).as_posix())
        result = subprocess.run(
            [zstd, "-q", "-T0", "-o", str(archive), str(tar_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "zstd compression failed")
    return archive


def _record(cls: type, value: object) -> object:
    if not isinstance(value, dict):
        raise ValueError(f"{cls.__name__} input must be an object")
    return cls(**value)


def _load_inputs(path: Path) -> RunInputs:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RunInputs(
        run_id=raw["run_id"],
        factory_version=raw["factory_version"],
        ao_runtime_version=raw["ao_runtime_version"],
        created_at=raw["created_at"],
        completed_at=raw["completed_at"],
        operator=_record(OperatorRecord, raw["operator"]),
        profile=_record(ProfileRecord, raw["profile"]),
        providers=[_record(ProviderRecord, item) for item in raw.get("providers", [])],
        tasks=[_record(TaskRecord, item) for item in raw.get("tasks", [])],
        events=list(raw.get("events", [])),
        transcripts=dict(raw.get("transcripts", {})),
        artifact_paths={
            str(task_id): [Path(value) for value in values]
            for task_id, values in raw.get("artifact_paths", {}).items()
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a AO Operator evidence pack directory")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("dest_dir", type=Path)
    signer_group = parser.add_mutually_exclusive_group(required=True)
    signer_group.add_argument("--hmac-key-hex")
    signer_group.add_argument("--ed25519-private-key", type=Path)
    parser.add_argument("--tar-zst", action="store_true", help="also write evidence-pack-<run_id>.tar.zst")
    args = parser.parse_args(argv)

    inputs = _load_inputs(args.input_json)
    signer, _ = signer_from_options(
        hmac_key_hex=args.hmac_key_hex,
        ed25519_private_key=args.ed25519_private_key,
    )
    pack = write_pack(inputs, args.dest_dir, signer)
    output = write_tar_zst(pack, args.dest_dir) if args.tar_zst else pack
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
