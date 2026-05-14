#!/usr/bin/env python3
"""Validate explicit Agent OS RunSpec execution approval without dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_APPROVAL_FILE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


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


def parse_utc(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def approval_errors(
    gate: dict[str, Any],
    approval: dict[str, Any],
    approval_present: bool,
    *,
    now: datetime,
) -> list[str]:
    errors: list[str] = []
    if gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if gate.get("verdict") != "PASS" or gate.get("approval_request_ready") is not True:
        errors.append("approval gate must be ready")
    if gate.get("dispatch_authorized") is not False:
        errors.append("approval gate dispatch_authorized must remain false")
    if gate.get("provider_profile_checked") is not True or gate.get("provider_profile_matches") is not True:
        errors.append("approval gate provider profile must be checked and match")
    if gate.get("provider_mismatches"):
        errors.append("approval gate must not contain provider mismatches")
    if not approval_present:
        return errors
    if approval.get("schema") != "ao-operator/agent-os-runspec-execution-approval/v1":
        errors.append("approval schema must be ao-operator/agent-os-runspec-execution-approval/v1")
    if approval.get("approved") is not True:
        errors.append("approval approved must be true")
    for field in ["operator", "approved_at", "expires_at", "accepted_risk"]:
        if not str(approval.get(field) or "").strip():
            errors.append(f"approval missing {field}")
    approved_at = parse_utc(str(approval.get("approved_at") or ""))
    expires_at = parse_utc(str(approval.get("expires_at") or ""))
    if approved_at is None:
        errors.append("approval approved_at must be a UTC timestamp")
    if expires_at is None:
        errors.append("approval expires_at must be a UTC timestamp")
    if approved_at is not None and expires_at is not None:
        if expires_at <= approved_at:
            errors.append("approval expires_at must be after approved_at")
        if now < approved_at:
            errors.append("approval is not active yet")
        if now >= expires_at:
            errors.append("approval has expired")
    if approval.get("runspec_path") != gate.get("runspec_path"):
        errors.append("approval runspec_path must match approval gate")
    if not str(gate.get("runspec_sha256") or "").strip():
        errors.append("approval gate missing runspec_sha256")
    if approval.get("runspec_sha256") != gate.get("runspec_sha256"):
        errors.append("approval runspec_sha256 must match approval gate")
    if approval.get("task_count") != gate.get("task_count"):
        errors.append("approval task_count must match approval gate")
    return errors


def validate_approval(
    *,
    root: Path = ROOT,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    gate_path = resolve_path(root, approval_gate)
    approval_path = resolve_path(root, approval_file)
    gate = load_json(gate_path)
    approval_present = approval_path.is_file()
    approval = load_json(approval_path) if approval_present else {}
    now_dt = parse_utc(now) if isinstance(now, str) else (now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc))
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    errors = approval_errors(gate, approval, approval_present, now=now_dt)
    valid = approval_present and not errors
    return {
        "schema": "ao-operator/agent-os-runspec-execution-approval-validation/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_gate": relpath(root, gate_path),
        "approval_file": relpath(root, approval_path),
        "approval_file_present": approval_present,
        "approval_valid": valid,
        "approval_state": "APPROVED" if valid else "NOT_APPROVED",
        "approval_time_checked": approval_present,
        "checked_at": now_dt.replace(microsecond=0).isoformat(),
        "runspec_path": gate.get("runspec_path", ""),
        "runspec_sha256": gate.get("runspec_sha256", ""),
        "approval_runspec_sha256": approval.get("runspec_sha256", "") if approval_present else "",
        "runspec_lock": gate.get("runspec_lock", {}),
        "task_count": gate.get("task_count", 0),
        "execution_command": gate.get("execution_command", []),
        "provider_profile": gate.get("provider_profile", ""),
        "provider_profile_checked": gate.get("provider_profile_checked") is True,
        "provider_profile_matches": gate.get("provider_profile_matches") is True,
        "provider_mismatches": gate.get("provider_mismatches", []),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": "Run approval-only execution slice." if valid else "Keep Agent OS execution blocked until explicit approval exists.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS RunSpec execution approval")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--now", default=None, help="UTC timestamp override for deterministic approval-window validation")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = validate_approval(root=args.root, approval_gate=args.approval_gate, approval_file=args.approval_file, now=args.now)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"approval_valid={str(payload['approval_valid']).lower()}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
