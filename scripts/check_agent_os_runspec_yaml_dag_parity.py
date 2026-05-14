#!/usr/bin/env python3
"""Validate committed Agent OS RunSpec YAML DAG parity without provider dispatch."""

from __future__ import annotations

import argparse
import ast
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_RENDERER_REPORT = f"{STATUS_ROOT}/agent-os-runspec-renderer.json"
DEFAULT_ROLE_GRAPH_REPORT = f"{STATUS_ROOT}/agent-os-role-graph.json"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-runspec-yaml-dag-parity.json"
SCHEMA = "ao-operator/agent-os-runspec-yaml-dag-parity/v1"


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


def renderer_tasks(report: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = report.get("runspec") if isinstance(report.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def task_id_for_role(role_id: str) -> str:
    return f"agent-os-{role_id}"


def role_graph_roles(report: dict[str, Any]) -> list[str]:
    roles = report.get("roles")
    if not isinstance(roles, list):
        return []
    return [str(role.get("id") or "") for role in roles if isinstance(role, dict) and role.get("id")]


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


def task_edges(tasks: list[dict[str, Any]]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for task in tasks:
        task_id = str(task.get("id") or "")
        deps = task.get("deps") if isinstance(task.get("deps"), list) else []
        for dep in deps:
            edges.add((str(dep), task_id))
    return edges


def parse_deps(raw: str) -> list[str]:
    value = raw.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, str) and item]
    if value.startswith("- "):
        return [value[2:].strip().strip('"').strip("'")]
    return []


def parse_runspec_yaml_tasks(body: str) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in body.splitlines():
        id_match = re.match(r"^\s+- id:\s*([A-Za-z0-9_.-]+)\s*$", raw)
        if id_match:
            current = {"id": id_match.group(1), "deps": []}
            tasks.append(current)
            continue
        deps_match = re.match(r"^\s+deps:\s*(.+?)\s*$", raw)
        if deps_match and current is not None:
            current["deps"] = parse_deps(deps_match.group(1))
    if "kind: Run" not in body:
        errors.append("runspec YAML missing kind: Run")
    if "dispatchAuthorized: true" in body:
        errors.append("runspec YAML must not authorize dispatch")
    if not tasks:
        errors.append("runspec YAML tasks must be non-empty")
    return tasks, errors


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


def analyze_yaml_parity(
    *,
    renderer: dict[str, Any],
    role_graph: dict[str, Any],
    yaml_tasks: list[dict[str, Any]],
    yaml_errors: list[str] | None = None,
) -> dict[str, Any]:
    errors = list(yaml_errors or [])
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

    renderer_ids = [str(task.get("id") or "") for task in renderer_tasks(renderer)]
    yaml_ids = [str(task.get("id") or "") for task in yaml_tasks]
    if len(yaml_ids) != len(set(yaml_ids)):
        errors.append("runspec YAML task ids must be unique")
    if set(yaml_ids) != set(renderer_ids):
        errors.append("runspec YAML task ids must match renderer report")

    yaml_known = set(yaml_ids)
    yaml_edges = task_edges(yaml_tasks)
    renderer_edges = task_edges(renderer_tasks(renderer))
    graph_edges = role_graph_edges(role_graph)
    role_task_ids = [task_id_for_role(role) for role in role_graph_roles(role_graph)]
    for source, target in sorted(yaml_edges):
        if source not in yaml_known:
            errors.append(f"YAML task {target} depends on unknown task {source}")
        if target not in yaml_known:
            errors.append(f"unknown YAML dependency target {target}")
    yaml_renderer_alignment = yaml_edges == renderer_edges
    yaml_role_graph_alignment = yaml_edges == graph_edges
    if not yaml_renderer_alignment:
        errors.append("yaml dependency edges must match renderer dependency edges")
    if not yaml_role_graph_alignment:
        errors.append("yaml dependency edges must match role graph edges")

    topo, acyclic = topological_sort(yaml_ids, yaml_edges)
    if not acyclic:
        errors.append("runspec YAML dependency graph must be acyclic; cycle detected")
    entry_task_ids = sorted(yaml_known - {target for _, target in yaml_edges})
    terminal_task_ids = sorted(yaml_known - {source for source, _ in yaml_edges})
    if len(entry_task_ids) != 1:
        errors.append("runspec YAML DAG must have exactly one entry task")
    if len(terminal_task_ids) != 1:
        errors.append("runspec YAML DAG must have exactly one terminal task")
    if role_task_ids and acyclic and topo != role_task_ids:
        errors.append("runspec YAML topological task order must match role graph role order")

    index_by_id = {task_id: index for index, task_id in enumerate(yaml_ids)}
    for source, target in sorted(yaml_edges):
        if source in index_by_id and target in index_by_id and index_by_id[source] >= index_by_id[target]:
            errors.append(f"YAML task order must place {source} before {target}")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "task_count": len(yaml_ids),
        "yaml_edge_count": len(yaml_edges),
        "renderer_edge_count": len(renderer_edges),
        "role_graph_edge_count": len(graph_edges),
        "entry_task_ids": entry_task_ids,
        "terminal_task_ids": terminal_task_ids,
        "topological_task_ids": topo,
        "renderer_task_ids": renderer_ids,
        "role_graph_task_ids": role_task_ids,
        "yaml_renderer_alignment": yaml_renderer_alignment,
        "yaml_role_graph_alignment": yaml_role_graph_alignment,
        "errors": errors,
    }


def mutate_yaml_tasks(yaml_tasks: list[dict[str, Any]], case_id: str) -> list[dict[str, Any]]:
    mutated = deepcopy(yaml_tasks)
    by_id = {str(task.get("id") or ""): task for task in mutated}
    if case_id == "yaml_cycle_refused" and "agent-os-planner" in by_id and "agent-os-evaluator-closer" in by_id:
        by_id["agent-os-planner"]["deps"] = ["agent-os-evaluator-closer"]
    elif case_id == "yaml_renderer_edge_drift_refused":
        for task in mutated:
            if task.get("deps"):
                task["deps"] = []
                break
    elif case_id == "yaml_unknown_dependency_refused" and "agent-os-implementer" in by_id:
        by_id["agent-os-implementer"]["deps"] = ["agent-os-missing-role"]
    elif case_id == "yaml_terminal_fork_refused" and len(mutated) >= 2:
        mutated.append({"id": "agent-os-extra-terminal", "deps": [str(mutated[-2].get("id") or "")]})
    return mutated


def mutation_cases(renderer: dict[str, Any], role_graph: dict[str, Any], yaml_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = []
    for case_id in [
        "yaml_cycle_refused",
        "yaml_renderer_edge_drift_refused",
        "yaml_unknown_dependency_refused",
        "yaml_terminal_fork_refused",
    ]:
        result = analyze_yaml_parity(
            renderer=renderer,
            role_graph=role_graph,
            yaml_tasks=mutate_yaml_tasks(yaml_tasks, case_id),
        )
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
    runspec_value = str(renderer.get("runspec_path") or "")
    runspec_path = resolve_path(root, runspec_value) if runspec_value else root / "ao/runspecs/agent-os-phase-draft.yaml"
    try:
        yaml_body = runspec_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        yaml_body = ""
        yaml_tasks: list[dict[str, Any]] = []
        yaml_errors = [f"runspec YAML missing: {relpath(root, runspec_path)}"]
    else:
        yaml_tasks, yaml_errors = parse_runspec_yaml_tasks(yaml_body)
    baseline = analyze_yaml_parity(
        renderer=renderer,
        role_graph=role_graph,
        yaml_tasks=yaml_tasks,
        yaml_errors=yaml_errors,
    )
    cases = mutation_cases(renderer, role_graph, yaml_tasks) if yaml_tasks else []
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
        "runspec_path": relpath(root, runspec_path),
        "task_count": baseline["task_count"],
        "yaml_edge_count": baseline["yaml_edge_count"],
        "renderer_edge_count": baseline["renderer_edge_count"],
        "role_graph_edge_count": baseline["role_graph_edge_count"],
        "entry_task_ids": baseline["entry_task_ids"],
        "terminal_task_ids": baseline["terminal_task_ids"],
        "topological_task_ids": baseline["topological_task_ids"],
        "renderer_task_ids": baseline["renderer_task_ids"],
        "role_graph_task_ids": baseline["role_graph_task_ids"],
        "yaml_renderer_alignment": baseline["yaml_renderer_alignment"],
        "yaml_role_graph_alignment": baseline["yaml_role_graph_alignment"],
        "mutation_case_count": len(cases),
        "mutation_cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec YAML DAG parity passes; continue Agent OS architecture implementation behind no-provider gates."
            if not errors
            else "Fix RunSpec YAML DAG parity before changing role graph, router, or RunSpec generation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec YAML DAG parity")
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
