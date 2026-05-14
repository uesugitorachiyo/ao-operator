#!/usr/bin/env python3
"""Run a deterministic Mac-to-Ubuntu remote transfer smoke."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "ao-operator-remote-host.example"
DEFAULT_USER = "factory"
DEFAULT_IDENTITY = Path("~/.ssh/factory_v3_remote_ed25519").expanduser()
DEFAULT_REMOTE_BASE = "/tmp/ao-operator-remote-smoke"
DEFAULT_LOCAL_BASE = Path("/tmp")
SCHEMA = "ao-operator/mac-ubuntu-remote-smoke/v1"


class SmokeError(RuntimeError):
    """Raised when the smoke cannot produce accepted transfer evidence."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_bytes(size: int) -> bytes:
    """Generate deterministic non-secret bytes for payload sizing."""

    if size < 0:
        raise ValueError("extra bytes must be >= 0")
    out = bytearray()
    counter = 0
    while len(out) < size:
        out.extend(hashlib.sha256(f"ao-operator-smoke:{counter}".encode("utf-8")).digest())
        counter += 1
    return bytes(out[:size])


def safe_rel(path: str) -> bool:
    value = Path(path)
    return not value.is_absolute() and ".." not in value.parts


def build_payload(
    root: Path,
    *,
    smoke_id: str,
    source_commit: str,
    target: str,
    extra_bytes: int = 0,
) -> dict[str, Any]:
    workspace = root / "workspace"
    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "input.txt").write_text(
        "hello from ao-operator mac-to-ubuntu remote smoke\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "notes.md").write_text(
        "\n".join(
            [
                "# Mac Ubuntu Remote Smoke",
                "",
                f"- smoke_id: {smoke_id}",
                f"- source_commit: {source_commit}",
                f"- target: {target}",
                "- provider_dispatch: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if extra_bytes:
        (workspace / "large.bin").write_bytes(deterministic_bytes(extra_bytes))

    entries: list[dict[str, Any]] = []
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink():
            raise SmokeError(f"symlink is forbidden in smoke payload: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(workspace).as_posix()
        entries.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest = {
        "schema": SCHEMA,
        "smoke_id": smoke_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_commit": source_commit,
        "target": target,
        "provider_dispatch": False,
        "forbidden": {
            "provider_api_keys": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
            "absolute_paths": True,
            "symlinks": True,
        },
        "entries": entries,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def create_bundle(payload_root: Path, bundle_path: Path) -> str:
    with tarfile.open(bundle_path, "w:gz") as tar:
        tar.add(payload_root / "manifest.json", arcname="manifest.json", recursive=False)
        tar.add(payload_root / "workspace", arcname="workspace")
    return sha256_file(bundle_path)


def remote_script() -> str:
    return r"""set -euo pipefail
ROOT="$1"
BUNDLE="$ROOT/incoming/bundle.tgz"
EXTRACT="$ROOT/extracted"
RETURN="$ROOT/return-manifest.json"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
python3 - "$BUNDLE" "$EXTRACT" "$RETURN" <<'PY'
import base64
import hashlib
import json
import sys
import tarfile
from pathlib import Path

bundle = Path(sys.argv[1])
extract = Path(sys.argv[2])
return_manifest = Path(sys.argv[3])
MAX_FILES = 128
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def safe_target(base, name):
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe path: {name!r}")
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError(f"unsafe path: {name!r}")
    return target


def safe_extract_bundle(bundle_path, target_root):
    errors = []
    total = 0
    try:
        with tarfile.open(bundle_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_FILES:
                errors.append(f"too many archive entries: {len(members)}")
            for member in members:
                try:
                    target = safe_target(target_root, member.name)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    errors.append(f"symlink forbidden: {member.name}" if member.issym() or member.islnk() else f"special file forbidden: {member.name}")
                    continue
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    errors.append("archive total size exceeds limit")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    errors.append(f"missing archive file content: {member.name}")
                    continue
                with source, target.open("wb") as handle:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
    except (tarfile.TarError, OSError) as exc:
        errors.append(f"bundle unpack failed: {exc}")
    return errors


errors = safe_extract_bundle(bundle, extract)
manifest_path = extract / "manifest.json"
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError) as exc:
    manifest = {}
    errors.append(f"manifest unavailable: {exc}")
if manifest.get("provider_dispatch") is not False:
    errors.append("provider_dispatch must be false")
entries = manifest.get("entries", [])
if not isinstance(entries, list) or not entries:
    errors.append("manifest entries missing")

for entry in entries:
    rel = entry.get("path")
    if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts:
        errors.append(f"unsafe path: {rel!r}")
        continue
    path = extract / "workspace" / rel
    if path.is_symlink():
        errors.append(f"symlink forbidden: {rel}")
        continue
    if not path.is_file():
        errors.append(f"missing file: {rel}")
        continue
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        errors.append(f"sha256 mismatch: {rel}")
    if len(data) != entry.get("size_bytes"):
        errors.append(f"size mismatch: {rel}")

artifact_path = extract / "workspace" / "ubuntu-artifact.txt"
artifact_body = (
    "ubuntu remote smoke artifact\n"
    f"smoke_id={manifest.get('smoke_id')}\n"
    f"entries={len(entries)}\n"
).encode("utf-8")
artifact_path.write_bytes(artifact_body)
artifact = {
    "path": "ubuntu-artifact.txt",
    "size_bytes": len(artifact_body),
    "sha256": hashlib.sha256(artifact_body).hexdigest(),
    "contents_b64": base64.b64encode(artifact_body).decode("ascii"),
}
payload = {
    "schema": "ao-operator/mac-ubuntu-remote-smoke-return/v1",
    "verdict": "PASS" if not errors else "FAIL",
    "smoke_id": manifest.get("smoke_id"),
    "source_commit": manifest.get("source_commit"),
    "entries_checked": len(entries),
    "errors": errors,
    "artifact": artifact,
}
return_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if not errors else 2)
PY
"""


def run_checked(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def ssh_base(user: str, host: str, identity: Path) -> list[str]:
    return [
        "ssh",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        f"{user}@{host}",
    ]


def scp_base(identity: Path) -> list[str]:
    return [
        "scp",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
    ]


def validate_return_manifest(path: Path, *, smoke_id: str, source_commit: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = list(payload.get("errors") or [])
    artifact = payload.get("artifact") or {}
    if payload.get("verdict") != "PASS":
        errors.append("remote verdict is not PASS")
    if payload.get("smoke_id") != smoke_id:
        errors.append("smoke_id mismatch")
    if payload.get("source_commit") != source_commit:
        errors.append("source_commit mismatch")
    rel = artifact.get("path")
    if not isinstance(rel, str) or not safe_rel(rel):
        errors.append("artifact path is unsafe")
    try:
        contents = base64.b64decode(artifact.get("contents_b64", ""), validate=True)
    except Exception:
        contents = b""
        errors.append("artifact contents_b64 is invalid")
    if hashlib.sha256(contents).hexdigest() != artifact.get("sha256"):
        errors.append("artifact sha256 mismatch")
    if len(contents) != artifact.get("size_bytes"):
        errors.append("artifact size mismatch")
    payload["local_validation_errors"] = errors
    payload["local_validation"] = "PASS" if not errors else "FAIL"
    if errors:
        raise SmokeError("; ".join(errors))
    return payload


def write_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def run_smoke(
    *,
    root: Path = ROOT,
    host: str = DEFAULT_HOST,
    user: str = DEFAULT_USER,
    identity: Path = DEFAULT_IDENTITY,
    remote_base: str = DEFAULT_REMOTE_BASE,
    local_base: Path = DEFAULT_LOCAL_BASE,
    extra_bytes: int = 0,
    keep_local_temp: bool = False,
    keep_remote: bool = False,
) -> dict[str, Any]:
    if not identity.exists():
        raise SmokeError(f"identity key missing: {identity}")

    smoke_id = f"mac-ubuntu-remote-smoke-{utc_stamp()}"
    source_commit = git_head(root)
    target = f"{user}@{host}"
    local_parent = local_base / smoke_id
    remote_root = f"{remote_base}/{smoke_id}"
    return_manifest = local_parent / "return-manifest.json"
    bundle = local_parent / "bundle.tgz"
    cleanup_absent = False
    remote_created = False
    ssh = ssh_base(user, host, identity)
    local_parent.mkdir(parents=True, exist_ok=False)
    try:
        build_payload(
            local_parent,
            smoke_id=smoke_id,
            source_commit=source_commit,
            target=target,
            extra_bytes=extra_bytes,
        )
        bundle_sha = create_bundle(local_parent, bundle)
        scp = scp_base(identity)
        run_checked(ssh + [f"rm -rf {shlex.quote(remote_root)} && mkdir -p {shlex.quote(remote_root)}/incoming"])
        remote_created = True
        run_checked(scp + [str(bundle), f"{user}@{host}:{remote_root}/incoming/bundle.tgz"])
        run_checked(ssh + ["bash -s -- " + shlex.quote(remote_root)], input_text=remote_script())
        run_checked(scp + [f"{user}@{host}:{remote_root}/return-manifest.json", str(return_manifest)])
        returned = validate_return_manifest(return_manifest, smoke_id=smoke_id, source_commit=source_commit)
        if not keep_remote:
            run_checked(ssh + [f"rm -rf {shlex.quote(remote_root)} && test ! -e {shlex.quote(remote_root)}"])
            cleanup_absent = True
        report = {
            "schema": SCHEMA,
            "verdict": "PASS",
            "smoke_id": smoke_id,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_commit": source_commit,
            "target": target,
            "provider_dispatch": False,
            "extra_bytes": extra_bytes,
            "bundle_sha256": bundle_sha,
            "bundle_size_bytes": bundle.stat().st_size,
            "remote_root": remote_root,
            "remote_cleanup_absent": cleanup_absent,
            "return_manifest": returned,
        }
        return report
    finally:
        if remote_created and not keep_remote and not cleanup_absent:
            subprocess.run(
                ssh + [f"rm -rf {shlex.quote(remote_root)} && test ! -e {shlex.quote(remote_root)}"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if not keep_local_temp:
            shutil.rmtree(local_parent, ignore_errors=True)


def simulate_interrupted_upload_cleanup(
    *,
    root: Path = ROOT,
    host: str = DEFAULT_HOST,
    user: str = DEFAULT_USER,
    identity: Path = DEFAULT_IDENTITY,
    remote_base: str = DEFAULT_REMOTE_BASE,
    local_base: Path = DEFAULT_LOCAL_BASE,
    extra_bytes: int = 1024 * 1024,
    partial_bytes: int = 4096,
    keep_local_temp: bool = False,
    keep_remote: bool = False,
) -> dict[str, Any]:
    if not identity.exists():
        raise SmokeError(f"identity key missing: {identity}")
    if partial_bytes <= 0:
        raise SmokeError("partial_bytes must be greater than zero")

    smoke_id = f"mac-ubuntu-remote-interrupt-{utc_stamp()}"
    source_commit = git_head(root)
    target = f"{user}@{host}"
    local_parent = local_base / smoke_id
    remote_root = f"{remote_base}/{smoke_id}"
    bundle = local_parent / "bundle.tgz"
    partial = local_parent / "bundle.tgz.part"
    remote_created = False
    cleanup_absent = False
    ssh = ssh_base(user, host, identity)
    scp = scp_base(identity)
    local_parent.mkdir(parents=True, exist_ok=False)
    try:
        build_payload(
            local_parent,
            smoke_id=smoke_id,
            source_commit=source_commit,
            target=target,
            extra_bytes=extra_bytes,
        )
        bundle_sha = create_bundle(local_parent, bundle)
        with bundle.open("rb") as src, partial.open("wb") as dst:
            dst.write(src.read(partial_bytes))
        run_checked(ssh + [f"rm -rf {shlex.quote(remote_root)} && mkdir -p {shlex.quote(remote_root)}/incoming"])
        remote_created = True
        run_checked(scp + [str(partial), f"{user}@{host}:{remote_root}/incoming/bundle.tgz.part"])
        if not keep_remote:
            run_checked(ssh + [f"rm -rf {shlex.quote(remote_root)} && test ! -e {shlex.quote(remote_root)}"])
            cleanup_absent = True
        return {
            "schema": SCHEMA,
            "verdict": "PASS" if cleanup_absent or keep_remote else "FAIL",
            "mode": "interrupted-upload-cleanup",
            "smoke_id": smoke_id,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_commit": source_commit,
            "target": target,
            "provider_dispatch": False,
            "extra_bytes": extra_bytes,
            "partial_bytes": partial.stat().st_size,
            "bundle_sha256": bundle_sha,
            "bundle_size_bytes": bundle.stat().st_size,
            "remote_root": remote_root,
            "remote_cleanup_absent": cleanup_absent,
        }
    finally:
        if remote_created and not keep_remote and not cleanup_absent:
            subprocess.run(
                ssh + [f"rm -rf {shlex.quote(remote_root)} && test ! -e {shlex.quote(remote_root)}"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if not keep_local_temp:
            shutil.rmtree(local_parent, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Mac-to-Ubuntu deterministic transfer smoke")
    parser.add_argument("--host", default=os.environ.get("FACTORY_V3_REMOTE_HOST", DEFAULT_HOST))
    parser.add_argument("--user", default=os.environ.get("FACTORY_V3_REMOTE_USER", DEFAULT_USER))
    parser.add_argument("--identity", type=Path, default=Path(os.environ.get("FACTORY_V3_REMOTE_IDENTITY", str(DEFAULT_IDENTITY))).expanduser())
    parser.add_argument("--remote-base", default=os.environ.get("FACTORY_V3_REMOTE_SMOKE_BASE", DEFAULT_REMOTE_BASE))
    parser.add_argument("--local-base", type=Path, default=DEFAULT_LOCAL_BASE)
    parser.add_argument("--extra-bytes", type=int, default=0)
    parser.add_argument("--keep-local-temp", action="store_true")
    parser.add_argument("--keep-remote", action="store_true")
    parser.add_argument("--simulate-interrupted-upload", action="store_true")
    parser.add_argument("--partial-bytes", type=int, default=4096)
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--write-return-manifest", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.simulate_interrupted_upload:
            payload = simulate_interrupted_upload_cleanup(
                host=args.host,
                user=args.user,
                identity=args.identity,
                remote_base=args.remote_base,
                local_base=args.local_base,
                extra_bytes=args.extra_bytes,
                partial_bytes=args.partial_bytes,
                keep_local_temp=args.keep_local_temp,
                keep_remote=args.keep_remote,
            )
        else:
            payload = run_smoke(
                host=args.host,
                user=args.user,
                identity=args.identity,
                remote_base=args.remote_base,
                local_base=args.local_base,
                extra_bytes=args.extra_bytes,
                keep_local_temp=args.keep_local_temp,
                keep_remote=args.keep_remote,
            )
    except (subprocess.CalledProcessError, SmokeError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        if isinstance(exc, subprocess.CalledProcessError):
            if exc.stdout:
                print(exc.stdout)
            if exc.stderr:
                print(exc.stderr)
        return 1

    if args.write_report:
        write_report(args.write_report, payload)
    if args.write_return_manifest and "return_manifest" in payload:
        write_report(args.write_return_manifest, payload["return_manifest"])

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        for key in ("mode", "smoke_id", "bundle_sha256", "remote_cleanup_absent"):
            if key in payload:
                value = payload[key]
                if isinstance(value, bool):
                    value = str(value).lower()
                print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
