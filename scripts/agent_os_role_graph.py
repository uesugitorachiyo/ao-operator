#!/usr/bin/env python3
"""Build a versioned Agent OS role graph without dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = "docs/contracts/ao-operator-agent-capabilities.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json"
GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"
CORE_ROLE_ORDER = [
    "planner",
    "plan-hardener",
    "factory-manager",
    "implementer",
    "slice-reviewer",
    "integrator",
    "evaluator-closer",
]


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


def role_node(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(role.get("id") or ""),
        "risk_level": str(role.get("risk_level") or ""),
        "dispatch_mode": str(role.get("dispatch_mode") or ""),
        "provider_boundary": str(role.get("provider_boundary") or ""),
        "capabilities": [str(item) for item in role.get("capabilities", []) if isinstance(item, str)],
        "reads": [str(item) for item in role.get("reads", []) if isinstance(item, str)],
        "writes": [str(item) for item in role.get("writes", []) if isinstance(item, str)],
        "verification": str(role.get("verification") or ""),
    }


def default_edges(role_ids: set[str]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for source, target in zip(CORE_ROLE_ORDER, CORE_ROLE_ORDER[1:]):
        if source in role_ids and target in role_ids:
            edges.append({"from": source, "to": target})
    return edges


def migrate_state_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    previous_schema = str(snapshot.get("schema") or "")
    return {
        "schema": STATE_SCHEMA_V2,
        "previous_schema": previous_schema,
        "role_graph_schema": GRAPH_SCHEMA,
        "lane": snapshot.get("lane", ""),
        "route": snapshot.get("route", {}),
        "blockers": snapshot.get("blockers", []),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "migration_notes": [
            "v2 state adds an explicit role_graph_schema pointer.",
            "dispatch remains false until an approval-specific execution gate authorizes it.",
        ],
    }


def build_role_graph(
    *,
    root: Path = ROOT,
    contract: str | Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract_path = resolve_path(root, contract)
    data = load_json(contract_path)
    core_roles = [item for item in data.get("core_roles", []) if isinstance(item, dict)] if isinstance(data.get("core_roles"), list) else []
    role_by_id = {str(role.get("id") or ""): role for role in core_roles}
    errors: list[str] = []

    if data.get("schema") != "ao-operator/agent-os-capability-contract/v1":
        errors.append("capability contract schema must be ao-operator/agent-os-capability-contract/v1")
    if data.get("dispatch_authorized") is not False:
        errors.append("capability contract dispatch_authorized must be false")
    if data.get("live_providers_run") is not False:
        errors.append("capability contract live_providers_run must be false")
    for role_id in CORE_ROLE_ORDER:
        if role_id not in role_by_id:
            errors.append(f"missing core role: {role_id}")

    nodes = [role_node(role_by_id[role_id]) for role_id in CORE_ROLE_ORDER if role_id in role_by_id]
    edges = default_edges(set(role_by_id))
    return {
        "schema": GRAPH_SCHEMA,
        "state_schema_version": STATE_SCHEMA_V2,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "contract": relpath(root, contract_path),
        "role_count": len(nodes),
        "roles": nodes,
        "edges": edges,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Use this role graph as the compatibility baseline for router and RunSpec architecture changes."
            if not errors
            else "Fix Agent OS role graph blockers before changing router or RunSpec architecture."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AO Operator Agent OS role graph")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_role_graph(root=args.root, contract=args.contract)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
