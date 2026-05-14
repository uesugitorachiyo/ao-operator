#!/usr/bin/env python3
"""Check Agent OS RunSpec compatibility before router architecture changes."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RENDERER_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json"
SCHEMA = "ao-operator/agent-os-runspec-compatibility-matrix/v1"
RENDERER_SCHEMA = "ao-operator/agent-os-runspec-renderer/v1"


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


def tasks_from(report: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = report.get("runspec") if isinstance(report.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def prompt_files_from(report: dict[str, Any]) -> list[str]:
    files = report.get("prompt_files")
    return [item for item in files if isinstance(item, str) and item.strip()] if isinstance(files, list) else []


def task_ids(tasks: list[dict[str, Any]]) -> list[str]:
    return [str(task.get("id")) for task in tasks if task.get("id")]


def parse_yaml_task_ids(body: str) -> list[str]:
    return re.findall(r"^\s+- id:\s*([A-Za-z0-9_.-]+)\s*$", body, flags=re.MULTILINE)


def validate_renderer_case(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    tasks = tasks_from(report)
    prompts = prompt_files_from(report)
    ids = task_ids(tasks)
    if report.get("schema") != RENDERER_SCHEMA:
        errors.append(f"renderer schema must be {RENDERER_SCHEMA}")
    if report.get("verdict") != "PASS":
        errors.append("renderer verdict must be PASS")
    if report.get("dispatch_authorized") is not False:
        errors.append("renderer dispatch_authorized must remain false")
    if report.get("live_providers_run") is not False:
        errors.append("renderer live_providers_run must remain false")
    if not tasks:
        errors.append("renderer tasks must be non-empty")
    if len(ids) != len(set(ids)):
        errors.append("renderer task ids must be unique")
    if len(prompts) != len(tasks):
        errors.append("renderer prompt file count must match task count")
    for task in tasks:
        spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
        task_id = str(task.get("id") or "<missing>")
        if spec.get("dispatchAuthorized") is not False:
            errors.append(f"task {task_id} dispatchAuthorized must be false")
        if not spec.get("promptFile"):
            errors.append(f"task {task_id} missing promptFile")
    return {
        "id": "current_renderer_report",
        "verdict": "PASS" if not errors else "FAIL",
        "task_count": len(tasks),
        "prompt_count": len(prompts),
        "errors": errors,
    }


def validate_yaml_case(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    runspec_value = str(report.get("runspec_path") or "")
    report_ids = set(task_ids(tasks_from(report)))
    path = resolve_path(root, runspec_value) if runspec_value else root / "__missing_runspec__"
    if not runspec_value:
        errors.append("renderer report missing runspec_path")
        body = ""
    elif not path.is_file():
        errors.append(f"runspec file missing: {relpath(root, path)}")
        body = ""
    else:
        body = path.read_text(encoding="utf-8")
    if body:
        if "kind: Run" not in body:
            errors.append("yaml runspec missing kind: Run")
        if "dispatchAuthorized: true" in body:
            errors.append("yaml runspec must not authorize dispatch")
        yaml_ids = set(parse_yaml_task_ids(body))
        if yaml_ids != report_ids:
            errors.append("yaml task ids must match renderer task ids")
    else:
        yaml_ids = set()
    return {
        "id": "current_yaml_draft",
        "verdict": "PASS" if not errors else "FAIL",
        "runspec_path": runspec_value,
        "task_count": len(yaml_ids),
        "errors": errors,
    }


def legacy_renderer_fixture() -> dict[str, Any]:
    return {
        "schema": RENDERER_SCHEMA,
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "prompt_files": [
            "ao/prompts/agent-os-phase/01-planner.md",
            "ao/prompts/agent-os-phase/02-implementer.md",
        ],
        "runspec": {
            "apiVersion": "ao.dev/v1",
            "kind": "Run",
            "metadata": {"name": "agent-os-phase-draft"},
            "spec": {
                "tasks": [
                    {
                        "id": "agent-os-planner",
                        "kind": "agent",
                        "deps": [],
                        "spec": {
                            "provider": "codex",
                            "promptFile": "ao/prompts/agent-os-phase/01-planner.md",
                            "dispatchAuthorized": False,
                        },
                    },
                    {
                        "id": "agent-os-implementer",
                        "kind": "agent",
                        "deps": ["agent-os-planner"],
                        "spec": {
                            "provider": "codex",
                            "promptFile": "ao/prompts/agent-os-phase/02-implementer.md",
                            "dispatchAuthorized": False,
                        },
                    },
                ]
            },
        },
    }


def validate_legacy_case() -> dict[str, Any]:
    current = validate_renderer_case(legacy_renderer_fixture())
    return {
        "id": "legacy_renderer_v1_fixture",
        "verdict": current["verdict"],
        "task_count": current["task_count"],
        "prompt_count": current["prompt_count"],
        "errors": current["errors"],
    }


def check_matrix(
    *,
    root: Path = ROOT,
    renderer_report: str | Path = DEFAULT_RENDERER_REPORT,
) -> dict[str, Any]:
    report_path = resolve_path(root, renderer_report)
    report = load_json(report_path)
    cases = [
        validate_renderer_case(report),
        validate_yaml_case(root, report),
        validate_legacy_case(),
    ]
    errors = [error for case in cases for error in case["errors"]]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "renderer_report": relpath(root, report_path),
        "case_count": len(cases),
        "cases": cases,
        "verdict": "PASS" if not errors else "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "RunSpec compatibility passes; router architecture can preserve this baseline."
            if not errors
            else "Fix RunSpec compatibility errors before router architecture implementation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec compatibility matrix")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--renderer-report", default=DEFAULT_RENDERER_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_matrix(root=args.root, renderer_report=args.renderer_report)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
