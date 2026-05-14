#!/usr/bin/env python3
"""Validate Agent OS approval-file lifecycle without dispatching providers."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"
DEFAULT_APPROVAL_FILE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval.json"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-lifecycle.json"


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


def parse_utc(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if text:
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gate_errors(gate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if gate.get("verdict") != "PASS" or gate.get("approval_request_ready") is not True:
        errors.append("approval gate must be ready")
    if gate.get("dispatch_authorized") is not False:
        errors.append("approval gate dispatch_authorized must remain false")
    if gate.get("live_providers_run") is not False:
        errors.append("approval gate live_providers_run must remain false")
    if not gate.get("runspec_path"):
        errors.append("approval gate missing runspec_path")
    if not gate.get("runspec_sha256"):
        errors.append("approval gate missing runspec_sha256")
    return errors


def approval_errors(
    approval: dict[str, Any],
    *,
    gate: dict[str, Any],
    now: datetime,
    current_runspec_sha256: str,
) -> tuple[str, int, list[str]]:
    errors: list[str] = []
    if approval.get("schema") != "ao-operator/agent-os-runspec-execution-approval/v1":
        errors.append("approval file schema must be ao-operator/agent-os-runspec-execution-approval/v1")
    if approval.get("approved") is not True:
        errors.append("approval file approved must be true")
    if not str(approval.get("operator") or "").strip():
        errors.append("approval file operator is required")
    if not str(approval.get("accepted_risk") or "").strip():
        errors.append("approval file accepted_risk is required")
    if approval.get("runspec_path") != gate.get("runspec_path"):
        errors.append("approval file runspec_path must match approval gate")
    if approval.get("runspec_sha256") != gate.get("runspec_sha256"):
        errors.append("approval file runspec_sha256 must match approval gate")
    if current_runspec_sha256 != approval.get("runspec_sha256"):
        errors.append("current RunSpec sha256 must match approval file sha256")
    if approval.get("task_count") != gate.get("task_count"):
        errors.append("approval file task_count must match approval gate")

    expires_in_seconds = 0
    state = "APPROVED_ACTIVE"
    try:
        approved_at = parse_utc(approval.get("approved_at"))
        expires_at = parse_utc(approval.get("expires_at"))
        expires_in_seconds = int((expires_at - now).total_seconds())
        if approved_at > now:
            errors.append("approval file approved_at must not be in the future")
            state = "NOT_YET_ACTIVE"
        if expires_at <= now:
            errors.append("approval file is expired")
            state = "EXPIRED"
    except (TypeError, ValueError):
        errors.append("approval file approved_at and expires_at must be valid datetimes")
        state = "INVALID"

    if errors and state == "APPROVED_ACTIVE":
        state = "INVALID"
    return state, expires_in_seconds, errors


def check_lifecycle(
    *,
    root: Path = ROOT,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    gate_path = resolve_path(root, approval_gate)
    approval_path = resolve_path(root, approval_file)
    gate = load_json(gate_path)
    errors = gate_errors(gate)
    checked_at = parse_utc(now).replace(microsecond=0)
    runspec_path = resolve_path(root, str(gate.get("runspec_path") or ""))
    current_sha = sha256_file(runspec_path) if runspec_path.is_file() else ""
    if gate.get("runspec_path") and not current_sha:
        errors.append("current RunSpec file must exist")
    if gate.get("runspec_sha256") and current_sha and current_sha != gate.get("runspec_sha256"):
        errors.append("current RunSpec sha256 must match approval gate sha256")

    approval_present = approval_path.is_file()
    approval_state = "ABSENT"
    approval_usable = False
    expires_in_seconds = None
    approval_summary: dict[str, Any] = {}
    if approval_present:
        approval = load_json(approval_path)
        approval_state, expires_in_seconds, approval_file_errors = approval_errors(
            approval,
            gate=gate,
            now=checked_at,
            current_runspec_sha256=current_sha,
        )
        errors.extend(approval_file_errors)
        approval_usable = not approval_file_errors and not errors
        approval_summary = {
            "schema": approval.get("schema", ""),
            "approved": approval.get("approved"),
            "operator_present": bool(str(approval.get("operator") or "").strip()),
            "accepted_risk_present": bool(str(approval.get("accepted_risk") or "").strip()),
            "approved_at": approval.get("approved_at", ""),
            "expires_at": approval.get("expires_at", ""),
            "runspec_path": approval.get("runspec_path", ""),
            "runspec_sha256": approval.get("runspec_sha256", ""),
            "task_count": approval.get("task_count", 0),
        }

    return {
        "schema": "ao-operator/agent-os-approval-lifecycle/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checked_at": checked_at.isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_gate": relpath(root, gate_path),
        "approval_file": relpath(root, approval_path),
        "approval_file_present": approval_present,
        "approval_state": approval_state,
        "approval_usable": approval_usable,
        "approval": approval_summary,
        "expires_in_seconds": expires_in_seconds,
        "current_runspec_sha256": current_sha,
        "gate_runspec_sha256": gate.get("runspec_sha256", ""),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval is active; pass it to the approval-only execution launcher when explicit execution is intended."
            if approval_usable
            else "Keep Agent OS execution blocked until a fresh approval file is materialized."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS approval lifecycle")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--now", default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_lifecycle(
        root=args.root,
        approval_gate=args.approval_gate,
        approval_file=args.approval_file,
        now=args.now,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
