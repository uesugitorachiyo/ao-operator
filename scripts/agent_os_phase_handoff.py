#!/usr/bin/env python3
"""Build scoped Agent OS phase handoff packets without provider dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHASE_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json"
STATUS_FIELDS = ["Result", "Artifact", "Evidence", "Concerns", "Blocker"]


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


def step_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    phase_plan = data.get("phase_plan")
    if not isinstance(phase_plan, dict):
        return []
    steps = phase_plan.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def verification_matrix(data: dict[str, Any]) -> dict[str, Any]:
    matrix = data.get("verification_matrix")
    return matrix if isinstance(matrix, dict) else {}


def packet_id(step: dict[str, Any]) -> str:
    order = int(step.get("order") or 0)
    role = str(step.get("role") or "unknown")
    return f"{order:02d}-{role}"


def build_packets(steps: list[dict[str, Any]], matrix: dict[str, Any]) -> list[dict[str, Any]]:
    commands = matrix.get("required_commands") if isinstance(matrix.get("required_commands"), dict) else {}
    risk_gates = matrix.get("risk_gates") if isinstance(matrix.get("risk_gates"), dict) else {}
    packets: list[dict[str, Any]] = []
    for step in steps:
        role = str(step.get("role") or "")
        packets.append(
            {
                "packet_id": packet_id(step),
                "role": role,
                "depends_on": string_list(step.get("depends_on")),
                "scoped_context": {
                    "capabilities": string_list(step.get("capabilities")),
                    "reads": string_list(step.get("reads")),
                    "writes": string_list(step.get("writes")),
                },
                "risk_level": step.get("risk_level"),
                "dispatch_mode": step.get("dispatch_mode"),
                "exit_gate": step.get("exit_gate"),
                "required_status_fields": STATUS_FIELDS,
                "verification_commands": string_list(commands.get(role)) if isinstance(commands, dict) else [],
                "risk_gates": string_list(risk_gates.get(role)) if isinstance(risk_gates, dict) else [],
                "full_transcript_allowed": False,
            }
        )
    return packets


def validate_handoff_source(data: dict[str, Any], packets: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-phase-compiler/v1":
        errors.append("phase report schema must be ao-operator/agent-os-phase-compiler/v1")
    if data.get("verdict") != "PASS":
        errors.append("phase report verdict must be PASS")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must remain false for phase handoff")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must remain false for phase handoff")
    if not packets:
        errors.append("handoff packets must be non-empty")
    for packet in packets:
        role = str(packet.get("role") or "<missing>")
        context = packet.get("scoped_context") if isinstance(packet.get("scoped_context"), dict) else {}
        if not string_list(context.get("reads")):
            errors.append(f"packet {role} missing scoped reads")
        if not string_list(context.get("writes")):
            errors.append(f"packet {role} missing scoped writes")
        if not string_list(packet.get("verification_commands")):
            errors.append(f"packet {role} missing verification commands")
        if packet.get("full_transcript_allowed") is not False:
            errors.append(f"packet {role} must forbid full transcripts")
    return errors


def build_handoff(
    *,
    root: Path = ROOT,
    phase_report: str | Path = DEFAULT_PHASE_REPORT,
) -> dict[str, Any]:
    report_path = resolve_path(root, phase_report)
    data = load_json(report_path)
    steps = step_list(data)
    matrix = verification_matrix(data)
    packets = build_packets(steps, matrix)
    errors = validate_handoff_source(data, packets)
    specialist_gates = matrix.get("specialist_gates") if isinstance(matrix.get("specialist_gates"), dict) else {}
    return {
        "schema": "ao-operator/agent-os-phase-handoff/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "phase_report": relpath(root, report_path),
        "handoff_packets": packets,
        "specialist_activation": {str(key): str(value) for key, value in specialist_gates.items()},
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Add UAT acceptance state using scoped handoff packets."
            if not errors
            else "Fix phase handoff errors before any AO RunSpec rendering."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AO Operator Agent OS phase handoff packets")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--phase-report", default=DEFAULT_PHASE_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_handoff(root=args.root, phase_report=args.phase_report)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
