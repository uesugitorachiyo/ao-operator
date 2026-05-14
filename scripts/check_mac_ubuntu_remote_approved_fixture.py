#!/usr/bin/env python3
"""Prove Ubuntu can materialize an isolated approved fixture and stop at launcher PLAN."""

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
SCHEMA = "ao-operator/mac-ubuntu-remote-approved-fixture/v1"
RETURN_SCHEMA = "ao-operator/remote-approved-fixture-return/v1"
VALIDATION_SCHEMA = "ao-operator/mac-ubuntu-remote-approved-fixture-validation/v1"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/mac-ubuntu-remote-approved-fixture.json"
DEFAULT_REMOTE_USER = signed_transfer.DEFAULT_REMOTE_USER
DEFAULT_REMOTE_REPO = signed_transfer.DEFAULT_REMOTE_REPO
DEFAULT_REMOTE_BASE = "/tmp/ao-operator-remote-approved-fixture"
DEFAULT_IDENTITY = signed_transfer.DEFAULT_IDENTITY
APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"
RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"

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


def remote_approved_fixture_script() -> str:
    return f"""set -euo pipefail
ROOT="$1"
TRANSFER_ID="$2"
LOCAL_HEAD="$3"
BUNDLE="$ROOT/incoming/signed-approval-bundle-transfer.tgz"
EXTRACT="$ROOT/extracted"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
python3 - "$BUNDLE" "$EXTRACT" "$TRANSFER_ID" "$LOCAL_HEAD" <<'PY'
import hashlib, json, shutil, subprocess, sys, tarfile
from pathlib import Path

BUNDLE_PATH = "{APPROVAL_BUNDLE}"
SIDECAR_PATH = "{APPROVAL_BUNDLE_SIGNATURE}"
SIGNATURE_REPORT_PATH = "{APPROVAL_BUNDLE_SIGNATURE_REPORT}"
IDENTITY_REPORT_PATH = "{APPROVAL_IDENTITY_SIGNATURE}"
APPROVAL_GATE = "{APPROVAL_GATE}"
RUNSPEC = "{RUNSPEC}"
TRANSFER_ARTIFACTS = {json.dumps(TRANSFER_ARTIFACTS)}
RETURN_SCHEMA = "{RETURN_SCHEMA}"
MAX_FILES = 32
MAX_TOTAL_BYTES = 4 * 1024 * 1024
FORBIDDEN_TERMS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENSSH PRIVATE KEY", "BEGIN PRIVATE KEY"]

bundle = Path(sys.argv[1])
extract = Path(sys.argv[2])
transfer_id = sys.argv[3]
local_head = sys.argv[4]
repo = Path.cwd()
fixture = extract / "remote-approved-fixture"

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

def run_json(command):
    completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {{}}
    return completed, payload

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
if approval_bundle.get("schema") != "ao-operator/agent-os-execution-approval-bundle/v1":
    errors.append("approval bundle schema mismatch")
if approval_bundle.get("verdict") != "PASS":
    errors.append("approval bundle verdict must pass")
if sidecar.get("subject") != BUNDLE_PATH:
    errors.append("signature sidecar subject mismatch")
if sidecar.get("subject_sha256") != canonical_sha256(approval_bundle):
    errors.append("signature sidecar subject sha mismatch")
if signature_report.get("signature_matches") is not True:
    errors.append("signature report must match")
if identity_report.get("identity_signature") is not True or identity_report.get("signature_verified") is not True:
    errors.append("identity signature must be verified")
if identity_report.get("private_key_committed") is not False:
    errors.append("private key must not be committed")

fixture_approval_written = False
approval_valid = False
launcher_plan_verified = False
would_run_provider = True
approval_file_present_after = False

if not errors:
    (fixture / Path(BUNDLE_PATH).parent).mkdir(parents=True, exist_ok=True)
    (fixture / Path(APPROVAL_GATE).parent).mkdir(parents=True, exist_ok=True)
    (fixture / Path(RUNSPEC).parent).mkdir(parents=True, exist_ok=True)
    shutil.copy2(extract / "files" / BUNDLE_PATH, fixture / BUNDLE_PATH)
    shutil.copy2(repo / APPROVAL_GATE, fixture / APPROVAL_GATE)
    shutil.copy2(repo / RUNSPEC, fixture / RUNSPEC)
    materialize, materialize_payload = run_json([
        sys.executable,
        str(repo / "scripts/materialize_agent_os_approval.py"),
        "--root",
        str(fixture),
        "--approved",
        "--operator",
        "ao-operator-remote-approved-fixture",
        "--accepted-risk",
        "Remote isolated fixture validates launcher planning only.",
        "--write-approval-file",
        "--write-output",
        "--json",
    ])
    if materialize.returncode != 0:
        errors.append("remote fixture approval materialization failed")
    fixture_approval_written = materialize_payload.get("approval_file_written") is True
    if not fixture_approval_written:
        errors.append("fixture approval must be written")
    approval_file = fixture / str(materialize_payload.get("approval_file") or "")
    approval_file_present_after = approval_file.is_file()
    validation, validation_payload = run_json([
        sys.executable,
        str(repo / "scripts/validate_agent_os_runspec_execution_approval.py"),
        "--root",
        str(fixture),
        "--write-output",
        "--json",
    ])
    approval_valid = validation_payload.get("approval_valid") is True
    if validation.returncode != 0 or not approval_valid:
        errors.append("fixture approval validation must pass")
    launcher, launcher_payload = run_json([
        sys.executable,
        str(repo / "scripts/run_agent_os_runspec_execution.py"),
        "--root",
        str(fixture),
        "--json",
    ])
    launcher_plan_verified = launcher_payload.get("verdict") == "PLAN"
    would_run_provider = launcher_payload.get("would_run_provider") is True
    if launcher.returncode != 0 or not launcher_plan_verified:
        errors.append("launcher must stop at PLAN")
    if launcher_payload.get("would_run_provider") is not False:
        errors.append("launcher must not run providers")
    if launcher_payload.get("dispatch_authorized") is not False:
        errors.append("launcher dispatch_authorized must remain false")
    if launcher_payload.get("live_providers_run") is not False:
        errors.append("launcher live_providers_run must remain false")

remote_head = subprocess.check_output(["git", "rev-parse", "--short=8", "HEAD"], cwd=repo, text=True).strip()
print(json.dumps({{
    "schema": RETURN_SCHEMA,
    "verdict": "PASS" if not errors else "FAIL",
    "transfer_id": transfer_id,
    "local_head": local_head,
    "remote_head": remote_head,
    "artifact_count": len(TRANSFER_ARTIFACTS),
    "signed_bundle_verified": not errors and bool(approval_bundle),
    "signature_verified": signature_report.get("signature_matches") is True,
    "identity_verified": identity_report.get("identity_signature") is True and identity_report.get("signature_verified") is True,
    "fixture_approval_written": fixture_approval_written,
    "approval_valid": approval_valid,
    "launcher_plan_verified": launcher_plan_verified,
    "would_run_provider": would_run_provider,
    "approval_file_present_after": approval_file_present_after,
    "remote_cleanup_absent": False,
    "dispatch_authorized": False,
    "live_providers_run": False,
    "provider_dispatch": False,
    "errors": errors,
}}, sort_keys=True))
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
    if payload.get("transfer_id") != transfer_id:
        errors.append("transfer_id mismatch")
    if payload.get("local_head") != local_head or payload.get("remote_head") != local_head:
        errors.append("remote git head must match local head")
    if int(payload.get("artifact_count") or 0) != expected_artifact_count:
        errors.append("artifact count mismatch")
    for key in [
        "signed_bundle_verified",
        "signature_verified",
        "identity_verified",
        "fixture_approval_written",
        "approval_valid",
        "launcher_plan_verified",
        "approval_file_present_after",
        "remote_cleanup_absent",
    ]:
        if payload.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ["would_run_provider", "dispatch_authorized", "live_providers_run", "provider_dispatch"]:
        if payload.get(key) is not False:
            errors.append(f"{key} must remain false")
    errors.extend(str(error) for error in payload.get("errors", []))
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
    transfer_id = transfer_id or f"remote-approved-fixture-{utc_stamp()}"
    local_head = git_head(root)
    local_manifest = signed_transfer.build_local_manifest(root=root)
    errors = list(local_manifest.get("missing") or []) + list(local_manifest.get("errors") or [])
    remote_payload: dict[str, Any] = {}
    remote_root = f"{remote_base}/{transfer_id}"
    cleanup_absent = False
    ssh = ssh_base(remote_user, remote_host, identity)

    if not errors:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ao-operator-remote-approved-fixture-") as temp:
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
                    input_text=remote_approved_fixture_script(),
                    timeout=timeout,
                )
                try:
                    remote_payload = json.loads(verify_result.stdout)
                except json.JSONDecodeError:
                    remote_payload = {}
                if verify_result.returncode != 0:
                    errors.append("remote approved fixture failed")
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
                errors.append("remote approved fixture return manifest missing")

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
        "approval_valid": remote_payload.get("approval_valid") is True,
        "launcher_plan_verified": remote_payload.get("launcher_plan_verified") is True,
        "would_run_provider": remote_payload.get("would_run_provider") is True,
        "approval_file_present_after": remote_payload.get("approval_file_present_after") is True,
        "remote_cleanup_absent": cleanup_absent,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "provider_dispatch": False,
        "errors": errors,
        "next_safe_command": (
            "Remote approved fixture reaches launcher PLAN without provider dispatch."
            if not errors
            else "Fix remote approved fixture before remote approval execution planning."
        ),
    }
    return sanitize(payload)


def committed_report_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if report.get("verdict") != "PASS":
        errors.append("verdict must be PASS")
    for key in [
        "remote_git_synced",
        "signed_bundle_verified",
        "signature_verified",
        "identity_verified",
        "fixture_approval_written",
        "approval_valid",
        "launcher_plan_verified",
        "approval_file_present_after",
        "remote_cleanup_absent",
    ]:
        if report.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ["would_run_provider", "dispatch_authorized", "live_providers_run", "provider_dispatch"]:
        if report.get(key) is not False:
            errors.append(f"{key} must remain false")
    return errors


def validate_committed_report(*, root: Path = ROOT, report_path: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = root.resolve()
    path = resolve_path(root, report_path)
    report = load_json(path)
    errors = committed_report_errors(report)
    return {
        "schema": VALIDATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "report": relpath(root, path),
        "report_verdict": report.get("verdict", "MISSING"),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Committed remote approved fixture report passes."
            if not errors
            else "Refresh remote approved fixture evidence before continuing."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Mac-to-Ubuntu remote approved fixture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--remote-host", default=os.environ.get("FACTORY_V3_REMOTE_HOST", ""))
    parser.add_argument("--remote-user", default=DEFAULT_REMOTE_USER)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    parser.add_argument("--remote-base", default=DEFAULT_REMOTE_BASE)
    parser.add_argument("--transfer-id", default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.remote_host:
        payload = build_report(
            root=args.root,
            remote_host=resolve_env_placeholder(args.remote_host),
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
