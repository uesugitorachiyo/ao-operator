#!/usr/bin/env python3
"""Validate committed Agent OS RunSpec YAML semantic parity without provider dispatch."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_RENDERER_REPORT = f"{STATUS_ROOT}/agent-os-runspec-renderer.json"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-runspec-yaml-semantic-parity.json"
SCHEMA = "ao-operator/agent-os-runspec-yaml-semantic-parity/v1"

SEMANTIC_FIELDS = (
    "provider",
    "promptFile",
    "workspace",
    "policyProfile",
    "kind",
    "dispatchAuthorized",
)


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


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("\"") and text.endswith("\"") and len(text) >= 2:
            text = text[1:-1]
        elif text.startswith("'") and text.endswith("'") and len(text) >= 2:
            text = text[1:-1]
        if text == "true":
            return True
        if text == "false":
            return False
        return text
    return value


def parse_runspec_yaml_tasks(body: str) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_spec = False
    id_pattern = re.compile(r"^\s+- id:\s*([A-Za-z0-9_.-]+)\s*$")
    kind_pattern = re.compile(r"^(\s+)kind:\s*(.+?)\s*$")
    spec_open_pattern = re.compile(r"^\s+spec:\s*$")
    field_pattern = re.compile(r"^(\s+)([A-Za-z][A-Za-z0-9_]*):\s*(.+?)\s*$")

    for raw in body.splitlines():
        id_match = id_pattern.match(raw)
        if id_match:
            current = {"id": id_match.group(1), "spec": {}}
            tasks.append(current)
            in_spec = False
            continue
        if current is None:
            continue
        if spec_open_pattern.match(raw):
            in_spec = True
            continue
        kind_match = kind_pattern.match(raw)
        if kind_match and not in_spec and "kind" not in current:
            current["kind"] = normalize_scalar(kind_match.group(2))
            continue
        field_match = field_pattern.match(raw)
        if field_match and in_spec:
            key = field_match.group(2)
            value = normalize_scalar(field_match.group(3))
            current["spec"][key] = value

    if "kind: Run" not in body:
        errors.append("runspec YAML missing kind: Run")
    if "dispatchAuthorized: true" in body:
        errors.append("runspec YAML must not authorize dispatch")
    if not tasks:
        errors.append("runspec YAML tasks must be non-empty")
    return tasks, errors


def renderer_field_value(task: dict[str, Any], field: str) -> Any:
    if field == "kind":
        return task.get("kind")
    spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
    return spec.get(field)


def yaml_field_value(task: dict[str, Any], field: str) -> Any:
    if field == "kind":
        return task.get("kind")
    spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
    return spec.get(field)


def analyze_semantic_parity(
    *,
    renderer: dict[str, Any],
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

    renderer_task_list = renderer_tasks(renderer)
    renderer_by_id = {str(task.get("id") or ""): task for task in renderer_task_list}
    yaml_by_id = {str(task.get("id") or ""): task for task in yaml_tasks}

    renderer_ids = [str(task.get("id") or "") for task in renderer_task_list]
    yaml_ids = [str(task.get("id") or "") for task in yaml_tasks]
    if len(yaml_ids) != len(set(yaml_ids)):
        errors.append("runspec YAML task ids must be unique")
    if set(yaml_ids) != set(renderer_ids):
        errors.append("runspec YAML task ids must match renderer report")

    field_drift: dict[str, list[str]] = {field: [] for field in SEMANTIC_FIELDS}
    aligned_task_ids: list[str] = []
    drifted_task_ids: list[str] = []

    common_ids = sorted(set(yaml_ids) & set(renderer_ids))
    for task_id in common_ids:
        yaml_task = yaml_by_id[task_id]
        renderer_task = renderer_by_id[task_id]
        task_drifted = False
        for field in SEMANTIC_FIELDS:
            yaml_value = yaml_field_value(yaml_task, field)
            renderer_value = renderer_field_value(renderer_task, field)
            if yaml_value != renderer_value:
                field_drift[field].append(task_id)
                errors.append(
                    f"task {task_id} {field} must match renderer; "
                    f"yaml={yaml_value!r} renderer={renderer_value!r}"
                )
                task_drifted = True
            if field == "dispatchAuthorized" and yaml_value is not False:
                errors.append(f"task {task_id} dispatchAuthorized must remain false")
        if task_drifted:
            drifted_task_ids.append(task_id)
        else:
            aligned_task_ids.append(task_id)

    all_aligned = not drifted_task_ids and set(yaml_ids) == set(renderer_ids)

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "task_count": len(yaml_ids),
        "renderer_task_count": len(renderer_ids),
        "common_task_count": len(common_ids),
        "aligned_task_count": len(aligned_task_ids),
        "drifted_task_count": len(drifted_task_ids),
        "aligned_task_ids": aligned_task_ids,
        "drifted_task_ids": sorted(drifted_task_ids),
        "field_drift": {field: sorted(ids) for field, ids in field_drift.items()},
        "fields_checked": list(SEMANTIC_FIELDS),
        "all_aligned": all_aligned,
        "errors": errors,
    }


def mutate_yaml_tasks(yaml_tasks: list[dict[str, Any]], case_id: str) -> list[dict[str, Any]]:
    mutated = deepcopy(yaml_tasks)
    if not mutated:
        return mutated
    target = mutated[0]
    target_spec = target.setdefault("spec", {})
    if case_id == "yaml_provider_drift_refused":
        target_spec["provider"] = "anthropic"
    elif case_id == "yaml_prompt_drift_refused":
        target_spec["promptFile"] = "ao/prompts/agent-os-phase/99-drifted.md"
    elif case_id == "yaml_workspace_drift_refused":
        target_spec["workspace"] = "../elsewhere"
    elif case_id == "yaml_policy_drift_refused":
        target_spec["policyProfile"] = "ao/policy/elevated.yaml"
    elif case_id == "yaml_kind_drift_refused":
        target["kind"] = "shell"
    elif case_id == "yaml_dispatch_authorized_refused":
        target_spec["dispatchAuthorized"] = True
    return mutated


def mutation_cases(renderer: dict[str, Any], yaml_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = []
    for case_id in [
        "yaml_provider_drift_refused",
        "yaml_prompt_drift_refused",
        "yaml_workspace_drift_refused",
        "yaml_policy_drift_refused",
        "yaml_kind_drift_refused",
        "yaml_dispatch_authorized_refused",
    ]:
        result = analyze_semantic_parity(
            renderer=renderer,
            yaml_tasks=mutate_yaml_tasks(yaml_tasks, case_id),
        )
        cases.append(
            {
                "id": case_id,
                "observed_verdict": result["verdict"],
                "error_count": len(result["errors"]),
                "drifted_task_count": result["drifted_task_count"],
                "dispatch_authorized": False,
                "live_providers_run": False,
            }
        )
    return cases


def build_report(
    *,
    root: Path = ROOT,
    renderer_report: str | Path = DEFAULT_RENDERER_REPORT,
) -> dict[str, Any]:
    root = root.resolve()
    renderer_path = resolve_path(root, renderer_report)
    renderer = load_json(renderer_path)
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

    baseline = analyze_semantic_parity(
        renderer=renderer,
        yaml_tasks=yaml_tasks,
        yaml_errors=yaml_errors,
    )
    cases = mutation_cases(renderer, yaml_tasks) if yaml_tasks else []
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
        "runspec_path": relpath(root, runspec_path),
        "task_count": baseline["task_count"],
        "renderer_task_count": baseline["renderer_task_count"],
        "common_task_count": baseline["common_task_count"],
        "aligned_task_count": baseline["aligned_task_count"],
        "drifted_task_count": baseline["drifted_task_count"],
        "aligned_task_ids": baseline["aligned_task_ids"],
        "drifted_task_ids": baseline["drifted_task_ids"],
        "field_drift": baseline["field_drift"],
        "fields_checked": baseline["fields_checked"],
        "all_aligned": baseline["all_aligned"],
        "mutation_case_count": len(cases),
        "mutation_cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec YAML semantic parity passes; continue Agent OS architecture implementation behind no-provider gates."
            if not errors
            else "Fix RunSpec YAML semantic parity before changing role graph, router, or RunSpec generation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec YAML semantic parity")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--renderer-report", default=DEFAULT_RENDERER_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_report(
        root=args.root,
        renderer_report=args.renderer_report,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = relpath(args.root.resolve(), output.resolve())
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
