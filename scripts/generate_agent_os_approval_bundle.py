#!/usr/bin/env python3
"""Generate a template-only Agent OS execution approval bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_APPROVAL_TARGET = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json"


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
    if gate.get("provider_profile_checked") is not True or gate.get("provider_profile_matches") is not True:
        errors.append("approval gate provider profile must be checked and match")
    if gate.get("provider_mismatches"):
        errors.append("approval gate must not contain provider mismatches")
    lock = gate.get("runspec_lock")
    lock_ok = (
        isinstance(lock, dict)
        and lock.get("algorithm") == "sha256"
        and lock.get("path") == gate.get("runspec_path")
        and bool(gate.get("runspec_sha256"))
        and lock.get("sha256") == gate.get("runspec_sha256")
    )
    if not lock_ok:
        errors.append("approval gate must include sha256 RunSpec lock")
    if not isinstance(gate.get("task_count"), int) or gate.get("task_count", 0) <= 0:
        errors.append("approval gate task_count must be positive")
    return errors


def generate_bundle(
    *,
    root: Path = ROOT,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    approval_target: str | Path = DEFAULT_APPROVAL_TARGET,
    now: str | datetime | None = None,
    expires_in_hours: int = 4,
) -> dict[str, Any]:
    root = root.resolve()
    gate_path = resolve_path(root, approval_gate)
    target_path = resolve_path(root, approval_target)
    gate = load_json(gate_path)
    errors = gate_errors(gate)
    approved_at = parse_utc(now).replace(microsecond=0)
    expires_at = approved_at + timedelta(hours=expires_in_hours)
    template = {
        "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
        "approved": False,
        "operator": "",
        "approved_at": approved_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "accepted_risk": "",
        "runspec_path": gate.get("runspec_path", ""),
        "runspec_sha256": gate.get("runspec_sha256", ""),
        "task_count": gate.get("task_count", 0),
    }
    return {
        "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_gate": relpath(root, gate_path),
        "approval_file_target": relpath(root, target_path),
        "approval_template": template,
        "runspec_lock": gate.get("runspec_lock", {}),
        "execution_command": gate.get("execution_command", []),
        "instructions": [
            "Review the approval gate and RunSpec hash before editing the approval file.",
            "Copy approval_template to approval_file_target only when execution is intentionally approved.",
            "Set approved=true, operator, and accepted_risk before validation.",
            "Do not run AO from this generator.",
        ],
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Review and fill the approval template only when explicit execution approval is intended."
            if not errors
            else "Fix approval gate blockers before generating an operator approval."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Agent OS execution approval template bundle")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--approval-target", default=DEFAULT_APPROVAL_TARGET)
    parser.add_argument("--now", default=None)
    parser.add_argument("--expires-in-hours", type=int, default=4)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = generate_bundle(
        root=args.root,
        approval_gate=args.approval_gate,
        approval_target=args.approval_target,
        now=args.now,
        expires_in_hours=args.expires_in_hours,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
