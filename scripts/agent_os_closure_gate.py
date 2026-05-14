#!/usr/bin/env python3
"""Close the local Agent OS lane after human UAT and readiness gates pass."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESPONSE_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json"
DEFAULT_READINESS_REPORT = "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-closure-gate.json"
UAT_BLOCKER = "UAT response gate has not authorized closure"
READINESS_BLOCKER = "release readiness is not ship-ready"


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


def validate_sources(response: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if response.get("schema") != "ao-operator/agent-os-uat-response-gate/v1":
        errors.append("response gate schema must be ao-operator/agent-os-uat-response-gate/v1")
    if response.get("verdict") != "PASS":
        errors.append("response gate verdict must be PASS")
    if response.get("dispatch_authorized") is not False:
        errors.append("response dispatch_authorized must remain false")
    if response.get("live_providers_run") is not False:
        errors.append("response live_providers_run must remain false")
    if readiness.get("schema") != "ao-operator/release-readiness-gate/v1":
        errors.append("readiness report schema must be ao-operator/release-readiness-gate/v1")
    if readiness.get("verdict") != "PASS":
        errors.append("readiness report verdict must be PASS")
    if readiness.get("dispatch_authorized") is not False:
        errors.append("readiness dispatch_authorized must remain false")
    if readiness.get("live_providers_run") is not False:
        errors.append("readiness live_providers_run must remain false")
    return errors


def closure_blockers(response: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if response.get("closure_authorized") is not True:
        blockers.append(UAT_BLOCKER)
    if readiness.get("ship_ready") is not True:
        blockers.append(READINESS_BLOCKER)
    return blockers


def evaluate_closure(
    *,
    root: Path = ROOT,
    response_gate: str | Path = DEFAULT_RESPONSE_GATE,
    readiness_report: str | Path = DEFAULT_READINESS_REPORT,
) -> dict[str, Any]:
    response_path = resolve_path(root, response_gate)
    readiness_path = resolve_path(root, readiness_report)
    response = load_json(response_path)
    readiness = load_json(readiness_path)
    errors = validate_sources(response, readiness)
    blockers = closure_blockers(response, readiness)
    closed = not errors and not blockers
    return {
        "schema": "ao-operator/agent-os-closure-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "response_gate": relpath(root, response_path),
        "readiness_report": relpath(root, readiness_path),
        "response_summary": response.get("response_summary", {}),
        "ship_ready": readiness.get("ship_ready") is True,
        "agent_os_closed": closed,
        "closure_authorized": closed,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "blockers": blockers,
        "errors": errors,
        "next_safe_command": (
            "Agent OS lane is closed; choose a separate gated SDD lane."
            if closed
            else "Resolve closure blockers before closing Agent OS lane."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate AO Operator Agent OS closure")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--response-gate", default=DEFAULT_RESPONSE_GATE)
    parser.add_argument("--readiness-report", default=DEFAULT_READINESS_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = evaluate_closure(root=args.root, response_gate=args.response_gate, readiness_report=args.readiness_report)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"agent_os_closed={str(payload['agent_os_closed']).lower()}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
