#!/usr/bin/env python3
"""Summarize Agent OS architecture readiness from committed safety baselines."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json"
DEFAULT_ROLE_GRAPH = "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json"
DEFAULT_STATE_V2 = "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json"
DEFAULT_COMMIT_GUARD = "run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json"
DEFAULT_ROUTE_MATRIX = "run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json"
DEFAULT_RUNSPEC_MATRIX = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json"

EXPECTED_SCHEMAS = {
    "role_graph": "ao-operator/agent-os-role-graph/v1",
    "state_v2": "ao-operator/agent-os-state/v2",
    "commit_guard": "ao-operator/agent-os-accepted-execution-commit-guard/v1",
    "route_matrix": "ao-operator/agent-os-postrun-route-matrix/v1",
    "runspec_matrix": "ao-operator/agent-os-runspec-compatibility-matrix/v1",
}


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


def check_common(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    expected = EXPECTED_SCHEMAS[name]
    if payload.get("schema") != expected:
        blockers.append(f"{name} schema must be {expected}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"{name} verdict must be PASS")
    if payload.get("dispatch_authorized") is not False:
        blockers.append(f"{name} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        blockers.append(f"{name} live_providers_run must remain false")
    return blockers


def check_specific(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if name == "role_graph":
        if payload.get("role_count") != 7:
            blockers.append("role_graph role_count must be 7")
        if payload.get("state_schema_version") != EXPECTED_SCHEMAS["state_v2"]:
            blockers.append("role_graph must point to state v2 schema")
    elif name == "state_v2":
        if payload.get("role_graph_schema") != EXPECTED_SCHEMAS["role_graph"]:
            blockers.append("state_v2 must point to role graph schema")
    elif name == "commit_guard":
        if payload.get("commit_success_evidence_allowed") is not False:
            blockers.append("commit_guard must not allow success evidence commits before accepted execution")
        if payload.get("raw_snapshot_commit_allowed") is not False:
            blockers.append("commit_guard must not allow raw snapshot commits")
    elif name == "route_matrix":
        if payload.get("case_count") != 6:
            blockers.append("route_matrix case_count must be 6")
    elif name == "runspec_matrix":
        if payload.get("case_count") != 3:
            blockers.append("runspec_matrix case_count must be 3")
    return blockers


def summarize(
    *,
    root: Path = ROOT,
    role_graph: str | Path = DEFAULT_ROLE_GRAPH,
    state_v2: str | Path = DEFAULT_STATE_V2,
    commit_guard: str | Path = DEFAULT_COMMIT_GUARD,
    route_matrix: str | Path = DEFAULT_ROUTE_MATRIX,
    runspec_matrix: str | Path = DEFAULT_RUNSPEC_MATRIX,
) -> dict[str, Any]:
    paths = {
        "role_graph": resolve_path(root, role_graph),
        "state_v2": resolve_path(root, state_v2),
        "commit_guard": resolve_path(root, commit_guard),
        "route_matrix": resolve_path(root, route_matrix),
        "runspec_matrix": resolve_path(root, runspec_matrix),
    }
    baselines: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    checks: dict[str, str] = {}
    for name, path in paths.items():
        payload = load_json(path)
        baselines[name] = payload
        missing = not path.is_file()
        if missing:
            blockers.append(f"{name} evidence file is missing: {relpath(root, path)}")
            checks[name] = "MISSING"
            continue
        baseline_blockers = check_common(name, payload) + check_specific(name, payload)
        blockers.extend(baseline_blockers)
        checks[name] = "PASS" if not baseline_blockers else "FAIL"

    architecture_ready = not blockers
    return {
        "schema": "ao-operator/agent-os-architecture-readiness/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if architecture_ready else "FAIL",
        "architecture_ready": architecture_ready,
        "baseline_count": len(paths),
        "checks": checks,
        "evidence_paths": {name: relpath(root, path) for name, path in paths.items()},
        "blockers": blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Start router architecture implementation behind these compatibility baselines."
            if architecture_ready
            else "Fix Agent OS architecture readiness blockers before implementation."
        ),
    }


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"architecture_ready={str(payload['architecture_ready']).lower()}",
        f"baseline_count={payload['baseline_count']}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"next_safe_command={payload['next_safe_command']}",
    ]
    lines.extend(f"blocker={blocker}" for blocker in payload["blockers"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Agent OS architecture readiness")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--role-graph", default=DEFAULT_ROLE_GRAPH)
    parser.add_argument("--state-v2", default=DEFAULT_STATE_V2)
    parser.add_argument("--commit-guard", default=DEFAULT_COMMIT_GUARD)
    parser.add_argument("--route-matrix", default=DEFAULT_ROUTE_MATRIX)
    parser.add_argument("--runspec-matrix", default=DEFAULT_RUNSPEC_MATRIX)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(
        root=args.root,
        role_graph=args.role_graph,
        state_v2=args.state_v2,
        commit_guard=args.commit_guard,
        route_matrix=args.route_matrix,
        runspec_matrix=args.runspec_matrix,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
