#!/usr/bin/env python3
"""Validate Agent OS RunSpec DAG edge coverage without provider dispatch."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_RENDERER_REPORT = f"{STATUS_ROOT}/agent-os-runspec-renderer.json"
DEFAULT_ROLE_GRAPH_REPORT = f"{STATUS_ROOT}/agent-os-role-graph.json"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-runspec-dag-edge-coverage.json"
SCHEMA = "ao-operator/agent-os-runspec-dag-edge-coverage/v1"


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


def runspec_tasks(report: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = report.get("runspec") if isinstance(report.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def task_id_for_role(role_id: str) -> str:
    return f"agent-os-{role_id}"


def role_id_for_task(task_id: str) -> str:
    return task_id.removeprefix("agent-os-")


def role_graph_edges(report: dict[str, Any]) -> set[tuple[str, str]]:
    edges = report.get("edges")
    result: set[tuple[str, str]] = set()
    if not isinstance(edges, list):
        return result
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source and target:
            result.add((task_id_for_role(source), task_id_for_role(target)))
    return result


def role_graph_roles(report: dict[str, Any]) -> list[str]:
    roles = report.get("roles")
    if not isinstance(roles, list):
        return []
    return [str(role.get("id") or "") for role in roles if isinstance(role, dict) and role.get("id")]


def task_edges(tasks: list[dict[str, Any]]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for task in tasks:
        task_id = str(task.get("id") or "")
        deps = task.get("deps") if isinstance(task.get("deps"), list) else []
        for dep in deps:
            edges.add((str(dep), task_id))
    return edges


def outgoing_by_task(edges: set[tuple[str, str]]) -> dict[str, list[str]]:
    outgoing: dict[str, list[str]] = {}
    for source, target in sorted(edges):
        outgoing.setdefault(source, []).append(target)
    return outgoing


def topological_sort(ids: list[str], edges: set[tuple[str, str]]) -> tuple[list[str], bool]:
    known = set(ids)
    incoming_count = {task_id: 0 for task_id in ids}
    outgoing = {task_id: [] for task_id in ids}
    for source, target in edges:
        if source in known and target in known:
            incoming_count[target] += 1
            outgoing[source].append(target)
    ready = sorted(task_id for task_id, count in incoming_count.items() if count == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current]):
            incoming_count[target] -= 1
            if incoming_count[target] == 0:
                ready.append(target)
                ready.sort()
    return ordered, len(ordered) == len(ids)


def analyze_graph(renderer: dict[str, Any], role_graph: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if renderer.get("schema") != "ao-operator/agent-os-runspec-renderer/v1":
        errors.append("renderer schema must be ao-operator/agent-os-runspec-renderer/v1")
    if renderer.get("verdict") != "PASS":
        errors.append("renderer verdict must be PASS")
    if renderer.get("dispatch_authorized") is not False:
        errors.append("renderer dispatch_authorized must remain false")
    if renderer.get("live_providers_run") is not False:
        errors.append("renderer live_providers_run must remain false")
    if role_graph.get("schema") != "ao-operator/agent-os-role-graph/v1":
        errors.append("role graph schema must be ao-operator/agent-os-role-graph/v1")
    if role_graph.get("verdict") != "PASS":
        errors.append("role graph verdict must be PASS")
    if role_graph.get("dispatch_authorized") is not False:
        errors.append("role graph dispatch_authorized must remain false")
    if role_graph.get("live_providers_run") is not False:
        errors.append("role graph live_providers_run must remain false")

    tasks = runspec_tasks(renderer)
    ids = [str(task.get("id") or "") for task in tasks]
    if not ids:
        errors.append("runspec tasks must be non-empty")
    if len(ids) != len(set(ids)):
        errors.append("runspec task ids must be unique")

    known = set(ids)
    edges = task_edges(tasks)
    for source, target in sorted(edges):
        if source not in known:
            errors.append(f"task {target} depends on unknown task {source}")
        if target not in known:
            errors.append(f"unknown dependency target {target}")

    role_edges = role_graph_edges(role_graph)
    role_task_ids = [task_id_for_role(role) for role in role_graph_roles(role_graph)]
    if role_task_ids and set(role_task_ids) != known:
        errors.append("runspec task ids must match role graph roles")
    role_graph_alignment = edges == role_edges
    if not role_graph_alignment:
        errors.append("runspec direct dependency edges must match role graph edges")

    topo, acyclic = topological_sort(ids, edges)
    if not acyclic:
        errors.append("runspec dependency graph must be acyclic; cycle detected")
    entry_task_ids = sorted(known - {target for _, target in edges})
    terminal_task_ids = sorted(known - {source for source, _ in edges})
    if len(entry_task_ids) != 1:
        errors.append("runspec DAG must have exactly one entry task")
    if len(terminal_task_ids) != 1:
        errors.append("runspec DAG must have exactly one terminal task")
    if role_task_ids and acyclic and topo != role_task_ids:
        errors.append("runspec topological task order must match role graph role order")

    index_by_id = {task_id: index for index, task_id in enumerate(ids)}
    for source, target in sorted(edges):
        if source in index_by_id and target in index_by_id and index_by_id[source] >= index_by_id[target]:
            errors.append(f"task order must place {source} before {target}")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "task_count": len(ids),
        "edge_count": len(edges),
        "role_graph_edge_count": len(role_edges),
        "entry_task_ids": entry_task_ids,
        "terminal_task_ids": terminal_task_ids,
        "topological_task_ids": topo,
        "role_graph_task_ids": role_task_ids,
        "role_graph_alignment": role_graph_alignment,
        "errors": errors,
    }


def mutate_renderer(renderer: dict[str, Any], case_id: str) -> dict[str, Any]:
    mutated = deepcopy(renderer)
    runspec = mutated.get("runspec") if isinstance(mutated.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks") if isinstance(spec.get("tasks"), list) else []
    by_id = {str(task.get("id") or ""): task for task in tasks}
    if case_id == "cycle_refused" and "agent-os-planner" in by_id and "agent-os-evaluator-closer" in by_id:
        by_id["agent-os-planner"]["deps"] = ["agent-os-evaluator-closer"]
    elif case_id == "missing_role_edge_refused":
        for task in tasks:
            if isinstance(task, dict) and task.get("deps"):
                task["deps"] = []
                break
    elif case_id == "unknown_dependency_refused" and "agent-os-implementer" in by_id:
        by_id["agent-os-implementer"]["deps"] = ["agent-os-missing-role"]
    elif case_id == "duplicate_entry_refused":
        for task in tasks[1:]:
            if isinstance(task, dict) and task.get("deps"):
                task["deps"] = []
                break
    elif case_id == "terminal_fork_refused":
        source = str(tasks[-2].get("id") or "") if len(tasks) >= 2 and isinstance(tasks[-2], dict) else "agent-os-planner"
        tasks.append(
            {
                "id": "agent-os-extra-terminal",
                "kind": "agent",
                "deps": [source],
                "spec": {
                    "provider": "codex",
                    "dispatchAuthorized": False,
                    "promptFile": "ao/prompts/agent-os-phase/99-extra-terminal.md",
                },
            }
        )
    return mutated


def mutation_cases(renderer: dict[str, Any], role_graph: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for case_id in [
        "cycle_refused",
        "missing_role_edge_refused",
        "unknown_dependency_refused",
        "duplicate_entry_refused",
        "terminal_fork_refused",
    ]:
        result = analyze_graph(mutate_renderer(renderer, case_id), role_graph)
        cases.append(
            {
                "id": case_id,
                "observed_verdict": result["verdict"],
                "error_count": len(result["errors"]),
                "dispatch_authorized": False,
                "live_providers_run": False,
            }
        )
    return cases


def build_report(
    *,
    root: Path = ROOT,
    renderer_report: str | Path = DEFAULT_RENDERER_REPORT,
    role_graph_report: str | Path = DEFAULT_ROLE_GRAPH_REPORT,
) -> dict[str, Any]:
    root = root.resolve()
    renderer_path = resolve_path(root, renderer_report)
    role_graph_path = resolve_path(root, role_graph_report)
    renderer = load_json(renderer_path)
    role_graph = load_json(role_graph_path)
    baseline = analyze_graph(renderer, role_graph)
    cases = mutation_cases(renderer, role_graph) if baseline["task_count"] else []
    errors = list(baseline["errors"])
    for case in cases:
        if case["observed_verdict"] != "FAIL":
            errors.append(f"{case['id']} must fail closed")
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case['id']} must keep dispatch/live flags false")
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "renderer_report": relpath(root, renderer_path),
        "role_graph_report": relpath(root, role_graph_path),
        "task_count": baseline["task_count"],
        "edge_count": baseline["edge_count"],
        "role_graph_edge_count": baseline["role_graph_edge_count"],
        "entry_task_ids": baseline["entry_task_ids"],
        "terminal_task_ids": baseline["terminal_task_ids"],
        "topological_task_ids": baseline["topological_task_ids"],
        "role_graph_task_ids": baseline["role_graph_task_ids"],
        "role_graph_alignment": baseline["role_graph_alignment"],
        "mutation_case_count": len(cases),
        "mutation_cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec DAG edge coverage passes; continue Agent OS architecture implementation behind no-provider gates."
            if not errors
            else "Fix RunSpec DAG edge coverage before changing role graph, router, or RunSpec generation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec DAG edge coverage")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--renderer-report", default=DEFAULT_RENDERER_REPORT)
    parser.add_argument("--role-graph-report", default=DEFAULT_ROLE_GRAPH_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_report(
        root=args.root,
        renderer_report=args.renderer_report,
        role_graph_report=args.role_graph_report,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = relpath(args.root.resolve(), output.resolve())
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
