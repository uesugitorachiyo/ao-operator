#!/usr/bin/env python3
"""Validate the non-dispatching Agent OS RunSpec draft and prompt packets."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RENDERER_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json"
VALID_PROVIDERS = {"codex", "claude", "antigravity"}
ROLE_PROVIDER_KEYS = {
    "planner": "FACTORY_V3_PLANNER_PROVIDER",
    "spec-forge": "FACTORY_V3_SPEC_FORGE_PROVIDER",
    "ralph-loop": "FACTORY_V3_RALPH_LOOP_PROVIDER",
    "plan-hardener": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
    "factory-manager": "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
    "implementer": "FACTORY_V3_IMPLEMENTER_PROVIDER",
    "slice-reviewer": "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
    "integrator": "FACTORY_V3_INTEGRATOR_PROVIDER",
    "evaluator-closer": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
}
PROMPT_REQUIRED_TEXT = [
    "Use only the scoped context below. Do not use full conversation history.",
    "## Reads",
    "## Writes",
    "## Verification Commands",
    "## Required Status Fields",
    "Dispatch is not authorized by this rendered draft.",
]


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


def parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}, [f"provider profile missing: {path}"]
    values: dict[str, str] = {}
    errors: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"provider profile line is not KEY=VALUE: {line}")
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    for key, value in sorted(values.items()):
        if key == "FACTORY_V3_DEFAULT_PROVIDER" or (key.startswith("FACTORY_V3_") and key.endswith("_PROVIDER")):
            if value not in VALID_PROVIDERS:
                errors.append(f"{key} resolved to unsupported provider {value!r}")
    return values, errors


def role_for_task_id(task_id: str) -> str:
    return task_id.removeprefix("agent-os-")


def expected_provider_for_role(env: dict[str, str], role: str) -> str:
    key = ROLE_PROVIDER_KEYS.get(role)
    if key and env.get(key):
        return env[key]
    return env.get("FACTORY_V3_DEFAULT_PROVIDER", "codex")


def validate_provider_profile(
    root: Path,
    provider_profile: str | Path | None,
    tasks: list[dict[str, Any]],
) -> tuple[str, bool, bool, list[dict[str, str]], list[str]]:
    if provider_profile is None:
        return "", False, True, [], []
    profile_path = resolve_path(root, provider_profile)
    env, errors = parse_env(profile_path)
    mismatches: list[dict[str, str]] = []
    if errors:
        return relpath(root, profile_path), True, False, mismatches, errors
    for task in tasks:
        task_id = str(task.get("id") or "")
        role = role_for_task_id(task_id)
        spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
        actual = str(spec.get("provider") or "")
        expected = expected_provider_for_role(env, role)
        if expected not in VALID_PROVIDERS:
            continue
        if actual != expected:
            mismatches.append(
                {
                    "role": role,
                    "task_id": task_id,
                    "expected": expected,
                    "actual": actual,
                }
            )
            errors.append(f"provider mismatch for {role}: expected {expected}, got {actual}")
    return relpath(root, profile_path), True, not mismatches and not errors, mismatches, errors


def task_list(report: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = report.get("runspec") if isinstance(report.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def prompt_files(report: dict[str, Any]) -> list[str]:
    files = report.get("prompt_files")
    return [item for item in files if isinstance(item, str) and item.strip()] if isinstance(files, list) else []


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema") != "ao-operator/agent-os-runspec-renderer/v1":
        errors.append("renderer schema must be ao-operator/agent-os-runspec-renderer/v1")
    if report.get("verdict") != "PASS":
        errors.append("renderer verdict must be PASS")
    if report.get("dispatch_authorized") is not False:
        errors.append("renderer dispatch_authorized must remain false")
    if report.get("live_providers_run") is not False:
        errors.append("renderer live_providers_run must remain false")
    if not task_list(report):
        errors.append("renderer runspec tasks must be non-empty")
    return errors


def parse_yaml_task_ids(body: str) -> list[str]:
    return re.findall(r"^\s+- id:\s*([A-Za-z0-9_.-]+)\s*$", body, flags=re.MULTILINE)


def validate_runspec_file(root: Path, report: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    runspec_value = str(report.get("runspec_path") or "")
    if not runspec_value:
        return ["renderer report missing runspec_path"]
    path = resolve_path(root, runspec_value)
    if not path.is_file():
        return [f"runspec file missing: {relpath(root, path)}"]
    body = path.read_text(encoding="utf-8")
    if "kind: Run" not in body:
        errors.append("runspec file missing kind: Run")
    if "dispatchAuthorized: true" in body:
        errors.append("runspec must not authorize dispatch")
    yaml_task_ids = parse_yaml_task_ids(body)
    report_task_ids = [str(task.get("id")) for task in tasks if task.get("id")]
    if len(yaml_task_ids) != len(report_task_ids):
        errors.append(f"runspec task count mismatch: yaml={len(yaml_task_ids)} report={len(report_task_ids)}")
    if set(yaml_task_ids) != set(report_task_ids):
        errors.append("runspec YAML task ids must match renderer report")
    return errors


def validate_task_graph(tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids = [str(task.get("id")) for task in tasks if task.get("id")]
    if len(ids) != len(set(ids)):
        errors.append("runspec task ids must be unique")
    known = set(ids)
    for task in tasks:
        task_id = str(task.get("id") or "<missing>")
        spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
        deps = task.get("deps") if isinstance(task.get("deps"), list) else []
        for dep in deps:
            if dep not in known:
                errors.append(f"task {task_id} depends on unknown task {dep}")
        provider = spec.get("provider")
        if provider not in VALID_PROVIDERS:
            errors.append(f"task {task_id} provider must be codex or claude")
        if spec.get("dispatchAuthorized") is not False:
            errors.append(f"task {task_id} dispatchAuthorized must be false")
        if not spec.get("promptFile"):
            errors.append(f"task {task_id} missing promptFile")
        if not spec.get("policyProfile"):
            errors.append(f"task {task_id} missing policyProfile")
    return errors


def validate_prompt_files(root: Path, files: list[str], tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    task_prompt_files = {
        str(task.get("spec", {}).get("promptFile"))
        for task in tasks
        if isinstance(task.get("spec"), dict) and task.get("spec", {}).get("promptFile")
    }
    if set(files) != task_prompt_files:
        errors.append("prompt file list must match task promptFile entries")
    for prompt in files:
        path = resolve_path(root, prompt)
        if not path.is_file():
            errors.append(f"prompt file missing: {prompt}")
            continue
        body = path.read_text(encoding="utf-8")
        for required in PROMPT_REQUIRED_TEXT:
            if required not in body:
                if required.startswith("Use only"):
                    errors.append(f"prompt {prompt} missing scoped context warning")
                else:
                    errors.append(f"prompt {prompt} missing required section: {required}")
    return errors


def validate_agent_os_runspec(
    *,
    root: Path = ROOT,
    renderer_report: str | Path = DEFAULT_RENDERER_REPORT,
    provider_profile: str | Path | None = None,
) -> dict[str, Any]:
    report_path = resolve_path(root, renderer_report)
    report = load_json(report_path)
    tasks = task_list(report)
    files = prompt_files(report)
    errors: list[str] = []
    errors.extend(validate_report(report))
    errors.extend(validate_runspec_file(root, report, tasks))
    errors.extend(validate_task_graph(tasks))
    errors.extend(validate_prompt_files(root, files, tasks))
    profile, profile_checked, profile_matches, provider_mismatches, profile_errors = validate_provider_profile(
        root,
        provider_profile,
        tasks,
    )
    errors.extend(profile_errors)
    valid = not errors
    return {
        "schema": "ao-operator/agent-os-runspec-validation/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if valid else "FAIL",
        "renderer_report": relpath(root, report_path),
        "runspec_path": str(report.get("runspec_path") or ""),
        "task_count": len(tasks),
        "prompt_files_checked": len(files),
        "runspec_valid": valid,
        "provider_profile": profile,
        "provider_profile_checked": profile_checked,
        "provider_profile_matches": profile_matches,
        "provider_mismatches": provider_mismatches,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Review Agent OS RunSpec validation or choose the next gated SDD lane."
            if valid
            else "Fix Agent OS RunSpec validation errors before any execution slice."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a AO Operator Agent OS RunSpec draft")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--renderer-report", default=DEFAULT_RENDERER_REPORT)
    parser.add_argument("--provider-profile")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = validate_agent_os_runspec(
        root=args.root,
        renderer_report=args.renderer_report,
        provider_profile=args.provider_profile,
    )
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_json(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
