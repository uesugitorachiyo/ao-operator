#!/usr/bin/env python3
"""Compile an Agent OS phase plan and verification matrix without dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = "docs/contracts/ao-operator-agent-capabilities.json"
DEFAULT_STATE_V2 = "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json"
STATE_V2_SCHEMA = "ao-operator/agent-os-state/v2"
ROLE_GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
ROLE_ORDER = [
    "planner",
    "plan-hardener",
    "factory-manager",
    "implementer",
    "slice-reviewer",
    "integrator",
    "evaluator-closer",
]
HIGH_RISK_GATE = "closure evidence required for high-risk role"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    target = path.relative_to(root) if path.is_relative_to(root) else Path(path)
    return target.as_posix()


def load_contract(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def ordered_roles(core_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_by_id = {str(role.get("id")): role for role in core_roles if role.get("id")}
    ordered = [role_by_id[role_id] for role_id in ROLE_ORDER if role_id in role_by_id]
    extra = sorted(
        (role for role in core_roles if str(role.get("id")) not in ROLE_ORDER),
        key=lambda role: str(role.get("id")),
    )
    return ordered + extra


def build_phase_plan(roles: list[dict[str, Any]], *, lane: str, state_schema_version: str = STATE_V2_SCHEMA) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    previous: str | None = None
    for index, role in enumerate(roles, start=1):
        role_id = str(role.get("id"))
        exit_gate = "evaluator acceptance" if role_id == "evaluator-closer" else "role evidence accepted"
        steps.append(
            {
                "order": index,
                "role": role_id,
                "depends_on": [previous] if previous else [],
                "capabilities": string_list(role.get("capabilities")),
                "reads": string_list(role.get("reads")),
                "writes": string_list(role.get("writes")),
                "risk_level": role.get("risk_level"),
                "dispatch_mode": role.get("dispatch_mode"),
                "exit_gate": exit_gate,
            }
        )
        previous = role_id
    return {
        "lane": lane,
        "mode": "compiled-plan",
        "state_schema_version": state_schema_version,
        "steps": steps,
        "entry_gate": "validated capability contract",
        "final_gate": "evaluator acceptance",
    }


def build_verification_matrix(roles: list[dict[str, Any]], specialists: list[dict[str, Any]]) -> dict[str, Any]:
    required_commands: dict[str, list[str]] = {}
    risk_gates: dict[str, list[str]] = {}
    for role in roles:
        role_id = str(role.get("id"))
        verification = str(role.get("verification") or "").strip()
        required_commands[role_id] = [verification] if verification else []
        gates = ["role evidence artifact required"]
        if role.get("risk_level") == "high":
            gates.append(HIGH_RISK_GATE)
        risk_gates[role_id] = gates
    return {
        "required_commands": required_commands,
        "risk_gates": risk_gates,
        "specialist_gates": {
            str(specialist.get("id")): str(specialist.get("activation_gate") or "")
            for specialist in specialists
            if specialist.get("id")
        },
    }


def contract_errors(data: dict[str, Any], roles: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-capability-contract/v1":
        errors.append("schema must be ao-operator/agent-os-capability-contract/v1")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must remain false for phase compilation")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must remain false for phase compilation")
    if not roles:
        errors.append("core_roles must be a non-empty list")
    role_ids = [str(role.get("id")) for role in roles]
    missing = [role_id for role_id in ["planner", "plan-hardener", "factory-manager", "implementer", "evaluator-closer"] if role_id not in role_ids]
    if missing:
        errors.append("missing required phase roles: " + ", ".join(missing))
    for role in roles:
        role_id = str(role.get("id") or "<missing>")
        if not role.get("verification"):
            errors.append(f"role {role_id} missing verification command")
        if not string_list(role.get("reads")):
            errors.append(f"role {role_id} missing reads")
        if not string_list(role.get("writes")):
            errors.append(f"role {role_id} missing writes")
    return errors


def build_state_baseline(root: Path, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": relpath(root, path),
        "schema": str(payload.get("schema") or ""),
        "verdict": str(payload.get("verdict") or ""),
        "previous_schema": str(payload.get("previous_schema") or ""),
        "role_graph_schema": str(payload.get("role_graph_schema") or ""),
        "evidence_path_count": len(string_list(payload.get("evidence_paths"))),
    }


def state_v2_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != STATE_V2_SCHEMA:
        errors.append(f"state_v2 schema must be {STATE_V2_SCHEMA}")
    if payload.get("verdict") != "PASS":
        errors.append("state_v2 verdict must be PASS")
    if payload.get("role_graph_schema") != ROLE_GRAPH_SCHEMA:
        errors.append(f"state_v2 role_graph_schema must be {ROLE_GRAPH_SCHEMA}")
    if payload.get("dispatch_authorized") is not False:
        errors.append("state_v2 dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        errors.append("state_v2 live_providers_run must remain false")
    return errors


def compile_phase(
    *,
    root: Path = ROOT,
    contract: str | Path = DEFAULT_CONTRACT,
    state_v2: str | Path = DEFAULT_STATE_V2,
    lane: str = "agent-os-phase-compiler",
) -> dict[str, Any]:
    contract_path = resolve_path(root, contract)
    state_path = resolve_path(root, state_v2)
    data = load_contract(contract_path)
    state_payload = load_contract(state_path)
    core_roles = [item for item in data.get("core_roles", []) if isinstance(item, dict)] if isinstance(data.get("core_roles"), list) else []
    specialists = [item for item in data.get("specialists", []) if isinstance(item, dict)] if isinstance(data.get("specialists"), list) else []
    roles = ordered_roles(core_roles)
    errors = contract_errors(data, roles) + state_v2_errors(state_payload)
    return {
        "schema": "ao-operator/agent-os-phase-compiler/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "lane": lane,
        "contract": relpath(root, contract_path),
        "state_baseline": build_state_baseline(root, state_path, state_payload),
        "phase_plan": build_phase_plan(roles, lane=lane, state_schema_version=str(state_payload.get("schema") or "")),
        "verification_matrix": build_verification_matrix(roles, specialists),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Add the Agent OS phase execution handoff contract using this matrix."
            if not errors
            else "Fix phase compilation errors before producing executable handoff contracts."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a AO Operator Agent OS phase plan")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--state-v2", default=DEFAULT_STATE_V2)
    parser.add_argument("--lane", default="agent-os-phase-compiler")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = compile_phase(root=args.root, contract=args.contract, state_v2=args.state_v2, lane=args.lane)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
