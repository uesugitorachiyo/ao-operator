#!/usr/bin/env python3
"""Extract Agent OS learnings from pending UAT state without closing the phase."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UAT_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json"


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


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def uat_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("uat_items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def role_learning(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    learning: dict[str, dict[str, Any]] = {}
    for item in items:
        role = str(item.get("role") or "unknown")
        risk_gates = string_list(item.get("risk_gates"))
        learning[role] = {
            "status": str(item.get("status") or ""),
            "accepted": item.get("accepted") is True,
            "high_risk": any("high-risk" in gate for gate in risk_gates),
            "verification_commands": string_list(item.get("verification_commands")),
        }
    return learning


def validate_source(data: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-uat-state/v1":
        errors.append("UAT report schema must be ao-operator/agent-os-uat-state/v1")
    if data.get("verdict") != "PASS":
        errors.append("UAT report verdict must be PASS")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must remain false for learning extraction")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must remain false for learning extraction")
    if data.get("closure_authorized") is not False:
        errors.append("closure_authorized must remain false until human UAT is accepted")
    if not items:
        errors.append("UAT items must be non-empty")
    return errors


def extract_learning(
    *,
    root: Path = ROOT,
    uat_report: str | Path = DEFAULT_UAT_REPORT,
) -> dict[str, Any]:
    report_path = resolve_path(root, uat_report)
    data = load_json(report_path)
    items = uat_items(data)
    errors = validate_source(data, items)
    pending = [item for item in items if item.get("status") == "pending-human-acceptance"]
    return {
        "schema": "ao-operator/agent-os-learning-extract/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "uat_report": relpath(root, report_path),
        "pending_uat_count": len(pending),
        "open_blockers": string_list(data.get("blockers")),
        "lessons": [
            "Keep generated UAT state separate from human acceptance.",
            "Use role-level verification commands as the durable UAT evidence checklist.",
        ],
        "negative_learnings": [
            "Do not authorize closure while UAT items remain pending.",
            "Do not treat local validation as a substitute for human acceptance.",
        ],
        "role_learning": role_learning(items),
        "next_actions": [
            "Record human UAT responses or continue with operator cockpit visibility."
        ],
        "closure_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Add operator cockpit visibility for UAT, dispatch, readiness, and blockers."
            if not errors
            else "Fix learning extraction source errors before operator cockpit planning."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract AO Operator Agent OS learnings")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--uat-report", default=DEFAULT_UAT_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = extract_learning(root=args.root, uat_report=args.uat_report)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
