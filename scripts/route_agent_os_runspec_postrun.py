#!/usr/bin/env python3
"""Route future Agent OS RunSpec execution outcomes without dispatching providers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_EXECUTION_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json"


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


def route(
    *,
    root: Path = ROOT,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    execution_report: str | Path = DEFAULT_EXECUTION_REPORT,
) -> dict[str, Any]:
    gate_path = resolve_path(root, approval_gate)
    execution_path = resolve_path(root, execution_report)
    gate = load_json(gate_path)
    execution = load_json(execution_path)
    errors: list[str] = []
    if gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if gate.get("verdict") != "PASS":
        errors.append("approval gate must be PASS before postrun routing")
    if gate.get("dispatch_authorized") is not False:
        errors.append("approval gate dispatch_authorized must remain false")

    if errors:
        route_name = "BLOCKED"
        diagnostics_required = False
        commit_allowed = False
    elif not execution_path.is_file():
        route_name = "PENDING_RUN"
        diagnostics_required = False
        commit_allowed = False
    elif execution.get("verdict") == "PASS" and execution.get("ao_completed") is True and execution.get("evaluator_accepted") is True:
        route_name = "ACCEPTED"
        diagnostics_required = False
        commit_allowed = True
    elif execution.get("verdict") == "BLOCKED":
        route_name = "BLOCKED"
        diagnostics_required = False
        commit_allowed = False
    else:
        route_name = "DIAGNOSTIC_REQUIRED"
        diagnostics_required = True
        commit_allowed = False

    return {
        "schema": "ao-operator/agent-os-runspec-postrun-route/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_gate": relpath(root, gate_path),
        "execution_report": relpath(root, execution_path),
        "execution_report_present": execution_path.is_file(),
        "route": route_name,
        "diagnostics_required": diagnostics_required,
        "commit_success_evidence_allowed": commit_allowed,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": {
            "PENDING_RUN": "Keep waiting; no Agent OS execution evidence exists yet.",
            "ACCEPTED": "Run Agent OS evaluator closure contract before committing success evidence.",
            "DIAGNOSTIC_REQUIRED": "Preserve Agent OS execution diagnostics before rerun.",
            "BLOCKED": "Resolve the Agent OS execution blocker before rerun.",
        }[route_name],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route Agent OS RunSpec postrun state")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--execution-report", default=DEFAULT_EXECUTION_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = route(root=args.root, approval_gate=args.approval_gate, execution_report=args.execution_report)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"route={payload['route']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
