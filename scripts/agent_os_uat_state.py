#!/usr/bin/env python3
"""Build Agent OS UAT acceptance state without authorizing closure."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HANDOFF_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
PENDING_BLOCKER = "human UAT acceptance is pending"


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


def packet_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    packets = data.get("handoff_packets")
    if not isinstance(packets, list):
        return []
    return [packet for packet in packets if isinstance(packet, dict)]


def uat_item(packet: dict[str, Any]) -> dict[str, Any]:
    role = str(packet.get("role") or "unknown")
    return {
        "id": f"uat-{packet.get('packet_id') or role}",
        "packet_id": str(packet.get("packet_id") or ""),
        "role": role,
        "question": f"Does {role} satisfy its exit gate with acceptable evidence?",
        "requires_human_response": True,
        "status": "pending-human-acceptance",
        "accepted": False,
        "evidence_required": string_list(packet.get("required_status_fields")),
        "verification_commands": string_list(packet.get("verification_commands")),
        "risk_gates": string_list(packet.get("risk_gates")),
    }


def validate_source(data: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-phase-handoff/v1":
        errors.append("handoff report schema must be ao-operator/agent-os-phase-handoff/v1")
    if data.get("verdict") != "PASS":
        errors.append("handoff report verdict must be PASS")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must remain false for UAT state")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must remain false for UAT state")
    if not items:
        errors.append("UAT items must be non-empty")
    for item in items:
        role = str(item.get("role") or "<missing>")
        if item.get("requires_human_response") is not True:
            errors.append(f"UAT item {role} must require a human response")
        if item.get("accepted") is not False:
            errors.append(f"UAT item {role} must start unaccepted")
        if not string_list(item.get("evidence_required")):
            errors.append(f"UAT item {role} missing evidence requirements")
        if not string_list(item.get("verification_commands")):
            errors.append(f"UAT item {role} missing verification commands")
    return errors


def build_uat_state(
    *,
    root: Path = ROOT,
    handoff_report: str | Path = DEFAULT_HANDOFF_REPORT,
) -> dict[str, Any]:
    report_path = resolve_path(root, handoff_report)
    data = load_json(report_path)
    packets = packet_list(data)
    items = [uat_item(packet) for packet in packets]
    errors = validate_source(data, items)
    return {
        "schema": "ao-operator/agent-os-uat-state/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "handoff_report": relpath(root, report_path),
        "uat_required": True,
        "uat_items": items,
        "blockers": [PENDING_BLOCKER] if not errors else errors,
        "closure_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Collect and record human UAT responses before closure authorization."
            if not errors
            else "Fix UAT state source errors before recording acceptance."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AO Operator Agent OS UAT state")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--handoff-report", default=DEFAULT_HANDOFF_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_uat_state(root=args.root, handoff_report=args.handoff_report)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
