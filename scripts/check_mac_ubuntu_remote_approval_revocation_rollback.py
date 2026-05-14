#!/usr/bin/env python3
"""Prove remote approval revocation rollback on Ubuntu in isolated staging."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import check_mac_ubuntu_signed_approval_bundle_transfer as signed_transfer
from redact_strict_public_artifacts import redact_text


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
SCHEMA = "ao-operator/mac-ubuntu-remote-approval-revocation-rollback/v1"
RETURN_SCHEMA = "ao-operator/remote-approval-revocation-rollback-return/v1"
VALIDATION_SCHEMA = "ao-operator/mac-ubuntu-remote-approval-revocation-rollback-validation/v1"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/mac-ubuntu-remote-approval-revocation-rollback.json"
DEFAULT_REMOTE_USER = signed_transfer.DEFAULT_REMOTE_USER
DEFAULT_REMOTE_REPO = signed_transfer.DEFAULT_REMOTE_REPO
DEFAULT_REMOTE_BASE = "/tmp/ao-operator-remote-approval-revocation-rollback"
DEFAULT_IDENTITY = signed_transfer.DEFAULT_IDENTITY
APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"

TRANSFER_ARTIFACTS = signed_transfer.TRANSFER_ARTIFACTS
APPROVAL_BUNDLE = signed_transfer.APPROVAL_BUNDLE
APPROVAL_BUNDLE_SIGNATURE = signed_transfer.APPROVAL_BUNDLE_SIGNATURE
APPROVAL_BUNDLE_SIGNATURE_REPORT = signed_transfer.APPROVAL_BUNDLE_SIGNATURE_REPORT
APPROVAL_IDENTITY_SIGNATURE = signed_transfer.APPROVAL_IDENTITY_SIGNATURE


@dataclass
class RunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., RunResult]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def canonical_sha256(payload: dict[str, Any]) -> str:
    return signed_transfer.canonical_sha256(payload)


def git_head(root: Path) -> str:
    return signed_transfer.git_head(root)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def resolve_env_placeholder(value: str) -> str:
    return signed_transfer.resolve_env_placeholder(value)


def ssh_base(remote_user: str, remote_host: str, identity: Path) -> list[str]:
    return signed_transfer.ssh_base(remote_user, remote_host, identity)


def scp_base(identity: Path) -> list[str]:
    return signed_transfer.scp_base(identity)


def run_checked(command: list[str], *, input_text: str | None = None, timeout: int = 120) -> RunResult:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return RunResult(command=command, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def remote_verify_revoke_and_restore_script() -> str:
    return f"""set -euo pipefail
ROOT="$1"
TRANSFER_ID="$2"
LOCAL_HEAD="$3"
BUNDLE="$ROOT/incoming/signed-approval-bundle-transfer.tgz"
EXTRACT="$ROOT/extracted"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
python3 - "$BUNDLE" "$EXTRACT" "$TRANSFER_ID" "$LOCAL_HEAD" <<'PY'
import hashlib, json, subprocess, sys, tarfile
from pathlib import Path

BUNDLE_PATH = "{APPROVAL_BUNDLE}"
SIDECAR_PATH = "{APPROVAL_BUNDLE_SIGNATURE}"
SIGNATURE_REPORT_PATH = "{APPROVAL_BUNDLE_SIGNATURE_REPORT}"
IDENTITY_REPORT_PATH = "{APPROVAL_IDENTITY_SIGNATURE}"
APPROVAL_GATE = "{APPROVAL_GATE}"
TRANSFER_ARTIFACTS = {json.dumps(TRANSFER_ARTIFACTS)}
RETURN_SCHEMA = "{RETURN_SCHEMA}"
MAX_FILES = 32
MAX_TOTAL_BYTES = 4 * 1024 * 1024
FORBIDDEN_TERMS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENSSH PRIVATE KEY", "BEGIN PRIVATE KEY"]

bundle = Path(sys.argv[1])
extract = Path(sys.argv[2])
transfer_id = sys.argv[3]
local_head = sys.argv[4]

def safe_target(base, name):
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe path: {{name!r}}")
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError(f"unsafe path: {{name!r}}")
    return target

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def canonical_sha256(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {{}}
    return data if isinstance(data, dict) else {{}}

def safe_extract_bundle(bundle_path, target_root):
    errors = []
    total = 0
    try:
        with tarfile.open(bundle_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_FILES:
                errors.append(f"too many archive entries: {{len(members)}}")
            for member in members:
                try:
                    target = safe_target(target_root, member.name)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if member.issym() or member.islnk():
                    errors.append(f"symlink forbidden: {{member.name}}")
                    continue
                if not member.isfile():
                    errors.append(f"special file forbidden: {{member.name}}")
                    continue
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    errors.append("archive total size exceeds limit")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    errors.append(f"missing archive content: {{member.name}}")
                    continue
                with source, target.open("wb") as handle:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
    except (tarfile.TarError, OSError) as exc:
        errors.append(f"bundle unpack failed: {{exc}}")
    return errors

def dispatch_errors(payload, label):
    errors = []
    if payload.get("dispatch_authorized") is not False:
        errors.append(f"{{label}} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        errors.append(f"{{label}} live_providers_run must remain false")
    return errors

errors = safe_extract_bundle(bundle, extract)
manifest = load_json(extract / "transfer-manifest.json")
if manifest.get("transfer_id") != transfer_id:
    errors.append("transfer_id mismatch")
if manifest.get("local_head") != local_head:
    errors.append("local_head mismatch")
if manifest.get("dispatch_authorized") is not False:
    errors.append("transfer manifest dispatch_authorized must remain false")
if manifest.get("live_providers_run") is not False:
    errors.append("transfer manifest live_providers_run must remain false")
artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {{}}
for rel in TRANSFER_ARTIFACTS:
    path = extract / "files" / rel
    item = artifacts.get(rel) if isinstance(artifacts.get(rel), dict) else {{}}
    if not path.is_file():
        errors.append(f"missing transferred artifact: {{rel}}")
        continue
    if path.is_symlink():
        errors.append(f"symlink forbidden: {{rel}}")
        continue
    if sha256_file(path) != item.get("sha256"):
        errors.append(f"sha256 mismatch: {{rel}}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if any(term in text for term in FORBIDDEN_TERMS):
        errors.append("provider credential material must be absent")

approval_bundle = load_json(extract / "files" / BUNDLE_PATH)
sidecar = load_json(extract / "files" / SIDECAR_PATH)
signature_report = load_json(extract / "files" / SIGNATURE_REPORT_PATH)
identity_report = load_json(extract / "files" / IDENTITY_REPORT_PATH)
errors.extend(dispatch_errors(approval_bundle, "approval bundle"))
errors.extend(dispatch_errors(sidecar, "approval bundle signature sidecar"))
errors.extend(dispatch_errors(signature_report, "approval bundle signature report"))
errors.extend(dispatch_errors(identity_report, "approval identity signature report"))
subject_sha = canonical_sha256(approval_bundle) if approval_bundle else ""
signed_bundle_verified = True
if approval_bundle.get("schema") != "ao-operator/agent-os-execution-approval-bundle/v1":
    errors.append("approval bundle schema mismatch")
    signed_bundle_verified = False
if approval_bundle.get("verdict") != "PASS":
    errors.append("approval bundle verdict must be PASS")
    signed_bundle_verified = False
template = approval_bundle.get("approval_template") if isinstance(approval_bundle.get("approval_template"), dict) else {{}}
if template.get("approved") is not False:
    errors.append("approval bundle template must remain unapproved")
    signed_bundle_verified = False
if sidecar.get("schema") != "ao-operator/agent-os-approval-bundle-signature-sidecar/v1":
    errors.append("approval bundle signature sidecar schema mismatch")
    signed_bundle_verified = False
if sidecar.get("subject") != BUNDLE_PATH:
    errors.append("approval bundle signature sidecar subject mismatch")
    signed_bundle_verified = False
if sidecar.get("subject_sha256") != subject_sha:
    errors.append("approval bundle signature sidecar subject sha mismatch")
    signed_bundle_verified = False
if signature_report.get("schema") != "ao-operator/agent-os-approval-bundle-signature/v1":
    errors.append("approval bundle signature report schema mismatch")
    signed_bundle_verified = False
if signature_report.get("verdict") != "PASS" or signature_report.get("signature_matches") is not True:
    errors.append("approval bundle signature report must pass")
    signed_bundle_verified = False
if identity_report.get("schema") != "ao-operator/agent-os-approval-identity-signature/v1":
    errors.append("approval identity signature report schema mismatch")
if identity_report.get("verdict") != "PASS":
    errors.append("approval identity signature report must pass")
if identity_report.get("identity_signature") is not True or identity_report.get("signature_verified") is not True:
    errors.append("approval identity signature must be verified")
if identity_report.get("private_key_committed") is not False:
    errors.append("approval identity private key must not be committed")

def write_fixture_file(fixture, rel, text):
    rel_path = Path(str(rel))
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"unsafe fixture path: {{rel}}")
    target = safe_target(fixture, rel_path.as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target

def revocation_log_sanitized(path):
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return "accepted_risk" not in text and '"approval"' not in text and "OPENAI_API_KEY" not in text and "ANTHROPIC_API_KEY" not in text

approval_target = approval_bundle.get("approval_file_target") or "{STATUS_ROOT}/agent-os-runspec-execution-approval.json"
approval_file_rel = Path(str(approval_target))
if approval_file_rel.is_absolute() or ".." in approval_file_rel.parts:
    errors.append("approval file target must be a safe repo-relative path")

fixture = extract / "remote-revocation-rollback-fixture"
materialization = {{}}
revocation = {{}}
fixture_approval_written = False
revocation_applied = False
approval_file_present_after_revocation = True
rollback_restore_verified = False
approval_file_restored_after = False
sanitized = False
if not errors:
    try:
        gate = load_json(Path(APPROVAL_GATE))
        runspec_path = Path(str(gate.get("runspec_path") or ""))
        if runspec_path.is_absolute() or ".." in runspec_path.parts:
            errors.append("approval gate runspec_path must be safe")
        else:
            write_fixture_file(fixture, APPROVAL_GATE, Path(APPROVAL_GATE).read_text(encoding="utf-8"))
            write_fixture_file(fixture, BUNDLE_PATH, (extract / "files" / BUNDLE_PATH).read_text(encoding="utf-8"))
            write_fixture_file(fixture, runspec_path.as_posix(), runspec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"fixture setup failed: {{exc}}")

if not errors:
    result = subprocess.run(
        [
            "python3",
            "scripts/materialize_agent_os_approval.py",
            "--root",
            str(fixture),
            "--approval-bundle",
            BUNDLE_PATH,
            "--approval-gate",
            APPROVAL_GATE,
            "--approved",
            "--operator",
            "ao-operator-remote-revocation-rollback",
            "--accepted-risk",
            "Remote isolated fixture approval used only to prove revocation rollback.",
            "--write-approval-file",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        materialization = json.loads(result.stdout)
    except json.JSONDecodeError:
        materialization = {{}}
    if result.returncode != 0:
        errors.append("remote approval fixture materialization failed")
    if materialization.get("schema") != "ao-operator/agent-os-approval-materialization/v1":
        errors.append("remote materialization schema mismatch")
    if materialization.get("verdict") != "PASS":
        errors.append("remote fixture materialization verdict must be PASS")
    if materialization.get("approval_file_written") is not True:
        errors.append("remote fixture materialization must write approval file")
    if materialization.get("approval_valid") is not True:
        errors.append("remote fixture approval must be valid before revocation")
    if materialization.get("dispatch_authorized") is not False:
        errors.append("remote materialization dispatch_authorized must remain false")
    if materialization.get("live_providers_run") is not False:
        errors.append("remote materialization live_providers_run must remain false")

fixture_approval = fixture / approval_file_rel
backup = fixture / "rollback-backup" / approval_file_rel.name
if not errors:
    fixture_approval_written = fixture_approval.is_file()
    if not fixture_approval_written:
        errors.append("fixture approval file missing before revocation")
    else:
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(fixture_approval.read_text(encoding="utf-8"), encoding="utf-8")
        revoke_result = subprocess.run(
            [
                "python3",
                "scripts/check_agent_os_approval_revocation.py",
                "--root",
                str(fixture),
                "--approval-file",
                approval_file_rel.as_posix(),
                "--revocation-log",
                "run-artifacts/live/remote-revocations.jsonl",
                "--operator",
                "ao-operator-remote-revocation-rollback",
                "--reason",
                "Remote isolated fixture revocation rollback proof.",
                "--apply",
                "--force",
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            revocation = json.loads(revoke_result.stdout)
        except json.JSONDecodeError:
            revocation = {{}}
        if revoke_result.returncode != 0:
            errors.append("remote fixture revocation apply failed")
        if revocation.get("verdict") != "PASS":
            errors.append("remote fixture revocation verdict must be PASS")
        if revocation.get("revocation_applied") is not True:
            errors.append("remote fixture revocation must be applied")
        approval_file_present_after_revocation = fixture_approval.is_file()
        if approval_file_present_after_revocation:
            errors.append("fixture approval file must be absent after revocation")
        log_path = fixture / "run-artifacts/live/remote-revocations.jsonl"
        sanitized = revocation_log_sanitized(log_path)
        if not sanitized:
            errors.append("remote fixture revocation log must be sanitized")
        fixture_approval.parent.mkdir(parents=True, exist_ok=True)
        fixture_approval.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        approval_file_restored_after = fixture_approval.is_file()
        rollback_restore_verified = approval_file_restored_after and fixture_approval.read_text(encoding="utf-8") == backup.read_text(encoding="utf-8")
        if not rollback_restore_verified:
            errors.append("remote fixture rollback restore must verify")

revocation_applied = revocation.get("revocation_applied") is True
head = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
remote_head = head.stdout.strip() if head.returncode == 0 else ""
payload = {{
    "schema": RETURN_SCHEMA,
    "verdict": "PASS" if not errors else "FAIL",
    "transfer_id": transfer_id,
    "local_head": local_head,
    "remote_head": remote_head,
    "artifact_count": len(artifacts),
    "signed_bundle_verified": signed_bundle_verified and not any("approval bundle" in item for item in errors),
    "signature_verified": sidecar.get("subject_sha256") == subject_sha and signature_report.get("signature_matches") is True,
    "identity_verified": identity_report.get("identity_signature") is True and identity_report.get("signature_verified") is True,
    "fixture_approval_written": fixture_approval_written,
    "revocation_applied": revocation_applied,
    "approval_file_present_after_revocation": approval_file_present_after_revocation,
    "rollback_restore_verified": rollback_restore_verified,
    "approval_file_restored_after": approval_file_restored_after,
    "revocation_log_sanitized": sanitized,
    "dispatch_authorized": False,
    "live_providers_run": False,
    "provider_dispatch": False,
    "remote_cleanup_absent": False,
    "errors": errors,
}}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if not errors else 2)
PY
"""


def validate_remote_return(
    payload: dict[str, Any],
    *,
    transfer_id: str,
    local_head: str,
    expected_artifact_count: int,
) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != RETURN_SCHEMA:
        errors.append(f"remote return schema must be {RETURN_SCHEMA}")
    if payload.get("verdict") != "PASS":
        errors.append("remote verdict must be PASS")
    if payload.get("transfer_id") != transfer_id:
        errors.append("remote transfer_id mismatch")
    if payload.get("remote_head") != local_head:
        errors.append("remote git head must match local head")
    if int(payload.get("artifact_count") or 0) != expected_artifact_count:
        errors.append("remote artifact count mismatch")
    for key in (
        "signed_bundle_verified",
        "signature_verified",
        "identity_verified",
        "fixture_approval_written",
        "revocation_applied",
        "rollback_restore_verified",
        "approval_file_restored_after",
        "revocation_log_sanitized",
    ):
        if payload.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ("approval_file_present_after_revocation",):
        if payload.get(key) is not False:
            errors.append(f"{key} must remain false")
    for key in ("dispatch_authorized", "live_providers_run", "provider_dispatch"):
        if payload.get(key) is not False:
            errors.append(f"{key} must remain false")
    if payload.get("remote_cleanup_absent") is not True:
        errors.append("remote cleanup must be absent")
    for item in payload.get("errors") or []:
        errors.append(f"remote error: {item}")
    return errors


def build_report(
    *,
    root: Path = ROOT,
    remote_host: str,
    remote_user: str = DEFAULT_REMOTE_USER,
    remote_repo: str = DEFAULT_REMOTE_REPO,
    identity: Path = DEFAULT_IDENTITY,
    remote_base: str = DEFAULT_REMOTE_BASE,
    transfer_id: str | None = None,
    timeout: int = 120,
    runner: Runner = run_checked,
) -> dict[str, Any]:
    root = root.resolve()
    transfer_id = transfer_id or f"remote-approval-revocation-rollback-{utc_stamp()}"
    local_head = git_head(root)
    local_manifest = signed_transfer.build_local_manifest(root=root)
    errors = list(local_manifest.get("missing") or []) + list(local_manifest.get("errors") or [])
    remote_payload: dict[str, Any] = {}
    remote_root = f"{remote_base}/{transfer_id}"
    cleanup_absent = False
    ssh = ssh_base(remote_user, remote_host, identity)

    if not errors:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ao-operator-remote-approval-rollback-") as temp:
            bundle = signed_transfer.create_transfer_package(root, Path(temp), transfer_id=transfer_id, local_head=local_head)
            head_result = runner(ssh + [f"cd {shlex.quote(remote_repo)} && git rev-parse --short=8 HEAD"], timeout=timeout)
            if head_result.returncode != 0:
                errors.append("remote git head probe failed")
            elif head_result.stdout.strip() != local_head:
                errors.append("remote git head must match local head")
            mkdir_result = runner(
                ssh + [f"rm -rf {shlex.quote(remote_root)} && mkdir -p {shlex.quote(remote_root)}/incoming"],
                timeout=timeout,
            )
            if mkdir_result.returncode != 0:
                errors.append("remote staging setup failed")
            if not errors:
                scp_result = runner(
                    scp_base(identity) + [str(bundle), f"{remote_user}@{remote_host}:{remote_root}/incoming/signed-approval-bundle-transfer.tgz"],
                    timeout=timeout,
                )
                if scp_result.returncode != 0:
                    errors.append("remote bundle copy failed")
            if not errors:
                verify_result = runner(
                    ssh
                    + [
                        f"cd {shlex.quote(remote_repo)} && bash -s -- {shlex.quote(remote_root)} {shlex.quote(transfer_id)} {shlex.quote(local_head)}"
                    ],
                    input_text=remote_verify_revoke_and_restore_script(),
                    timeout=timeout,
                )
                try:
                    remote_payload = json.loads(verify_result.stdout)
                except json.JSONDecodeError:
                    remote_payload = {}
                if verify_result.returncode != 0:
                    errors.append("remote approval revocation rollback failed")
            cleanup_result = runner(ssh + [f"rm -rf {shlex.quote(remote_root)} && test ! -e {shlex.quote(remote_root)}"], timeout=timeout)
            cleanup_absent = cleanup_result.returncode == 0
            if remote_payload:
                remote_payload["remote_cleanup_absent"] = cleanup_absent
                errors.extend(
                    validate_remote_return(
                        remote_payload,
                        transfer_id=transfer_id,
                        local_head=local_head,
                        expected_artifact_count=len(TRANSFER_ARTIFACTS),
                    )
                )
            elif not errors:
                errors.append("remote rollback return manifest missing")

    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "transfer_id": transfer_id,
        "local": {
            "repo": str(root),
            "head": local_head,
            "manifest": local_manifest,
        },
        "remote": {
            "target": f"{remote_user}@{remote_host}",
            "repo": remote_repo,
            "head": remote_payload.get("remote_head", ""),
            "return_manifest": remote_payload,
            "staging_root": remote_root,
        },
        "remote_git_synced": remote_payload.get("remote_head") == local_head,
        "signed_bundle_verified": remote_payload.get("signed_bundle_verified") is True,
        "signature_verified": remote_payload.get("signature_verified") is True,
        "identity_verified": remote_payload.get("identity_verified") is True,
        "fixture_approval_written": remote_payload.get("fixture_approval_written") is True,
        "revocation_applied": remote_payload.get("revocation_applied") is True,
        "approval_file_present_after_revocation": remote_payload.get("approval_file_present_after_revocation", True),
        "rollback_restore_verified": remote_payload.get("rollback_restore_verified") is True,
        "approval_file_restored_after": remote_payload.get("approval_file_restored_after") is True,
        "revocation_log_sanitized": remote_payload.get("revocation_log_sanitized") is True,
        "remote_cleanup_absent": cleanup_absent,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "provider_dispatch": False,
        "errors": errors,
        "next_safe_command": (
            "Remote approval revocation rollback passes; continue with the operator runbook lane."
            if not errors
            else "Fix remote approval revocation rollback before any remote approval write path."
        ),
    }
    return sanitize(payload)


def validate_committed_report(*, root: Path = ROOT, report_path: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = root.resolve()
    report = load_json(resolve_path(root, report_path))
    errors: list[str] = []
    if report.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if report.get("verdict") != "PASS":
        errors.append("report verdict must be PASS")
    for key in (
        "remote_git_synced",
        "signed_bundle_verified",
        "signature_verified",
        "identity_verified",
        "fixture_approval_written",
        "revocation_applied",
        "rollback_restore_verified",
        "approval_file_restored_after",
        "revocation_log_sanitized",
        "remote_cleanup_absent",
    ):
        if report.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ("approval_file_present_after_revocation", "dispatch_authorized", "live_providers_run", "provider_dispatch"):
        if report.get(key) is not False:
            errors.append(f"{key} must remain false")
    return {
        "schema": VALIDATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "report": relpath(root, resolve_path(root, report_path)),
        "report_verdict": report.get("verdict", "MISSING"),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Committed remote approval revocation rollback report passes."
            if not errors
            else "Refresh remote approval revocation rollback evidence before continuing."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Mac-to-Ubuntu remote approval revocation rollback")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--remote-host", default=os.environ.get("FACTORY_V3_REMOTE_HOST", ""))
    parser.add_argument("--remote-user", default=os.environ.get("FACTORY_V3_REMOTE_USER", DEFAULT_REMOTE_USER))
    parser.add_argument("--remote-repo", default=os.environ.get("FACTORY_V3_REMOTE_REPO", DEFAULT_REMOTE_REPO))
    parser.add_argument("--remote-base", default=os.environ.get("FACTORY_V3_REMOTE_APPROVAL_REVOCATION_ROLLBACK_BASE", DEFAULT_REMOTE_BASE))
    parser.add_argument("--identity", type=Path, default=Path(os.environ.get("FACTORY_V3_REMOTE_IDENTITY", str(DEFAULT_IDENTITY))).expanduser())
    parser.add_argument("--transfer-id")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    remote_host = resolve_env_placeholder(args.remote_host)
    if remote_host:
        payload = build_report(
            root=args.root,
            remote_host=remote_host,
            remote_user=args.remote_user,
            remote_repo=args.remote_repo,
            identity=args.identity,
            remote_base=args.remote_base,
            transfer_id=args.transfer_id,
            timeout=args.timeout,
        )
        if args.write_output is not None:
            output = resolve_path(args.root, args.write_output)
            write_json(output, payload)
            payload["output"] = relpath(args.root.resolve(), output.resolve())
    else:
        payload = validate_committed_report(root=args.root, report_path=args.write_output or DEFAULT_OUTPUT)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
