#!/usr/bin/env python3
"""Rehearse Agent OS RunSpec execution refusal without providers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-rehearsal.json"


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


def rehearse(*, root: Path = ROOT, approval_gate: str | Path = DEFAULT_APPROVAL_GATE) -> dict[str, Any]:
    gate_path = resolve_path(root, approval_gate)
    gate = load_json(gate_path)
    errors: list[str] = []
    if gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if gate.get("verdict") != "PASS" or gate.get("approval_request_ready") is not True:
        errors.append("approval gate must be ready before rehearsal")
    if gate.get("dispatch_authorized") is not False:
        errors.append("approval gate dispatch_authorized must remain false")
    if gate.get("live_providers_run") is not False:
        errors.append("approval gate live_providers_run must remain false")
    approval_file_present = gate.get("approval_file_present") is True
    refused_without_approval = not approval_file_present
    if approval_file_present:
        errors.append("no-provider rehearsal expects approval file to be absent")
    ready = not errors and refused_without_approval
    return {
        "schema": "ao-operator/agent-os-runspec-execution-rehearsal/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "approval_gate": relpath(root, gate_path),
        "refused_without_approval": refused_without_approval,
        "would_run_provider": False,
        "execution_command": gate.get("execution_command", []),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Route Agent OS postrun state; do not execute providers."
            if ready
            else "Fix Agent OS no-provider rehearsal errors before any execution slice."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rehearse Agent OS RunSpec execution refusal")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = rehearse(root=args.root, approval_gate=args.approval_gate)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
