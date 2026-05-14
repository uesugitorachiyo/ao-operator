#!/usr/bin/env python3
"""Check Agent OS architecture implementation surfaces before deeper changes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-architecture-implementation-gate.json"

ROLE_ORDER = [
    "planner",
    "plan-hardener",
    "factory-manager",
    "implementer",
    "slice-reviewer",
    "integrator",
    "evaluator-closer",
]

REPORTS = {
    "architecture_readiness": {
        "path": f"{STATUS_ROOT}/agent-os-architecture-readiness.json",
        "schema": "ao-operator/agent-os-architecture-readiness/v1",
    },
    "role_graph": {
        "path": f"{STATUS_ROOT}/agent-os-role-graph.json",
        "schema": "ao-operator/agent-os-role-graph/v1",
    },
    "router_v2_state": {
        "path": f"{STATUS_ROOT}/agent-os-router-v2-state.json",
        "schema": "ao-operator/agent-os-state/v2",
    },
    "state_v2": {
        "path": f"{STATUS_ROOT}/agent-os-state-v2.json",
        "schema": "ao-operator/agent-os-state/v2",
    },
    "phase_handoff": {
        "path": f"{STATUS_ROOT}/agent-os-phase-handoff.json",
        "schema": "ao-operator/agent-os-phase-handoff/v1",
    },
    "runspec_renderer": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-renderer.json",
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
    },
    "runspec_validation": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-validation.json",
        "schema": "ao-operator/agent-os-runspec-validation/v1",
    },
    "provider_boundary_matrix": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-provider-boundary-matrix.json",
        "schema": "ao-operator/agent-os-runspec-provider-boundary-matrix/v1",
    },
    "execution_hygiene": {
        "path": f"{STATUS_ROOT}/agent-os-execution-hygiene.json",
        "schema": "ao-operator/agent-os-execution-hygiene/v1",
    },
}

IMPLEMENTATION_SURFACES = [
    "scripts/agent_os_role_graph.py",
    "scripts/agent_os_router.py",
    "scripts/agent_os_state_v2.py",
    "scripts/agent_os_runspec_renderer.py",
    "scripts/agent_os_runspec_validator.py",
    "scripts/run_agent_os_runspec_execution.py",
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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def common_errors(report_id: str, payload: dict[str, Any], expected_schema: str) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != expected_schema:
        errors.append(f"{report_id} schema must be {expected_schema}")
    if payload.get("verdict") != "PASS":
        errors.append(f"{report_id} verdict must be PASS")
    if payload.get("dispatch_authorized") is not False:
        errors.append(f"{report_id} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        errors.append(f"{report_id} live_providers_run must remain false")
    return errors


def role_ids(role_graph: dict[str, Any]) -> list[str]:
    roles = role_graph.get("roles")
    if not isinstance(roles, list):
        return []
    return [str(role.get("id") or "") for role in roles if isinstance(role, dict) and role.get("id")]


def handoff_roles(handoff: dict[str, Any]) -> list[str]:
    packets = handoff.get("handoff_packets")
    if not isinstance(packets, list):
        return []
    return [str(packet.get("role") or "") for packet in packets if isinstance(packet, dict) and packet.get("role")]


def runspec_tasks(renderer: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = renderer.get("runspec") if isinstance(renderer.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def expected_task_ids(roles: list[str]) -> list[str]:
    return [f"agent-os-{role}" for role in roles]


def alignment_errors(
    *,
    role_graph: dict[str, Any],
    handoff: dict[str, Any],
    renderer: dict[str, Any],
    validation: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    roles = role_ids(role_graph)
    packets = handoff_roles(handoff)
    tasks = runspec_tasks(renderer)
    task_ids = [str(task.get("id") or "") for task in tasks]

    if roles != ROLE_ORDER:
        errors.append("role graph roles must match the canonical Agent OS role order")
    if roles != packets:
        errors.append("role graph roles must match handoff packet roles")
    if task_ids != expected_task_ids(roles):
        errors.append("RunSpec task ids must match role graph roles")
    if int(role_graph.get("role_count") or 0) != len(ROLE_ORDER):
        errors.append("role graph role_count must be 7")
    if int(renderer.get("task_count") or 0) != len(roles):
        errors.append("renderer task_count must match role graph role_count")
    if int(validation.get("task_count") or 0) != len(roles):
        errors.append("validation task_count must match role graph role_count")
    if int(validation.get("prompt_files_checked") or 0) != len(roles):
        errors.append("validation prompt_files_checked must match role graph role_count")

    for task in tasks:
        task_id = str(task.get("id") or "<missing>")
        spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
        if spec.get("dispatchAuthorized") is not False:
            errors.append(f"runspec task {task_id} dispatchAuthorized must be false")
        if not spec.get("promptFile"):
            errors.append(f"runspec task {task_id} promptFile is required")
        if spec.get("provider") not in {"codex", "claude"}:
            errors.append(f"runspec task {task_id} provider must be codex or claude")
    return errors


def specific_errors(reports: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    architecture = reports["architecture_readiness"]
    role_graph = reports["role_graph"]
    router_v2 = reports["router_v2_state"]
    state_v2 = reports["state_v2"]
    renderer = reports["runspec_renderer"]
    validation = reports["runspec_validation"]
    boundary = reports["provider_boundary_matrix"]
    handoff = reports["phase_handoff"]

    if architecture.get("architecture_ready") is not True:
        errors.append("architecture readiness must be ready")
    if role_graph.get("state_schema_version") != "ao-operator/agent-os-state/v2":
        errors.append("role graph must point to state v2")
    for report_id, payload in (("router_v2_state", router_v2), ("state_v2", state_v2)):
        if payload.get("role_graph_schema") != "ao-operator/agent-os-role-graph/v1":
            errors.append(f"{report_id} must point to role graph schema")
        blockers = payload.get("blockers")
        if isinstance(blockers, list) and blockers:
            errors.append(f"{report_id} blockers must be empty")
    if router_v2.get("architecture_ready") is not True:
        errors.append("router_v2_state architecture_ready must be true")
    if renderer.get("state_baseline_checked") is not True:
        errors.append("renderer must check state baseline")
    if renderer.get("state_schema_version") != "ao-operator/agent-os-state/v2":
        errors.append("renderer state_schema_version must be ao-operator/agent-os-state/v2")
    if renderer.get("role_graph_schema") != "ao-operator/agent-os-role-graph/v1":
        errors.append("renderer role_graph_schema must be ao-operator/agent-os-role-graph/v1")
    if renderer.get("architecture_ready") is not True:
        errors.append("renderer architecture_ready must be true")
    if validation.get("provider_profile_matches") is not True:
        errors.append("runspec validation provider_profile_matches must be true")
    if int(boundary.get("case_count") or 0) < 4:
        errors.append("provider boundary matrix must include at least 4 cases")
    errors.extend(
        alignment_errors(
            role_graph=role_graph,
            handoff=handoff,
            renderer=renderer,
            validation=validation,
        )
    )
    return errors


def summarize(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    reports: dict[str, dict[str, Any]] = {}
    evidence_paths: dict[str, str] = {}
    blockers: list[str] = []
    checks: dict[str, str] = {}

    for report_id, config in REPORTS.items():
        path = resolve_path(root, config["path"])
        evidence_paths[report_id] = relpath(root, path)
        payload = load_json(path)
        reports[report_id] = payload
        if not path.is_file():
            blockers.append(f"{report_id} evidence file is missing: {relpath(root, path)}")
            checks[report_id] = "MISSING"
            continue
        errors = common_errors(report_id, payload, config["schema"])
        blockers.extend(errors)
        checks[report_id] = "PASS" if not errors else "FAIL"

    missing_surfaces = [
        rel
        for rel in IMPLEMENTATION_SURFACES
        if not resolve_path(root, rel).is_file()
    ]
    blockers.extend(f"implementation surface missing: {rel}" for rel in missing_surfaces)
    checks["implementation_surfaces"] = "PASS" if not missing_surfaces else "FAIL"

    if all(report_id in reports for report_id in REPORTS):
        semantic_errors = specific_errors(reports)
        blockers.extend(semantic_errors)
        checks["role_handoff_runspec_alignment"] = (
            "PASS"
            if not any(
                "role graph" in item or "RunSpec" in item or "runspec task" in item or "task_count" in item
                or "prompt_files_checked" in item
                for item in semantic_errors
            )
            else "FAIL"
        )
        checks["state_v2_bridge"] = (
            "PASS"
            if not any("state" in item or "architecture_ready" in item or "baseline" in item for item in semantic_errors)
            else "FAIL"
        )

    roles = role_ids(reports.get("role_graph", {}))
    packets = handoff_roles(reports.get("phase_handoff", {}))
    tasks = runspec_tasks(reports.get("runspec_renderer", {}))
    implementation_ready = not blockers
    return {
        "schema": "ao-operator/agent-os-architecture-implementation-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if implementation_ready else "FAIL",
        "implementation_ready": implementation_ready,
        "role_count": len(roles),
        "handoff_packet_count": len(packets),
        "runspec_task_count": len(tasks),
        "checks": checks,
        "evidence_paths": evidence_paths,
        "implementation_surfaces": IMPLEMENTATION_SURFACES,
        "blockers": blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Proceed with the next Agent OS architecture implementation slice behind no-provider gates."
            if implementation_ready
            else "Fix Agent OS architecture implementation blockers before router or RunSpec changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS architecture implementation gate")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
