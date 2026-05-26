#!/usr/bin/env python3
"""Check Agent OS RunSpec provider boundary fixtures without dispatch."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_runspec_renderer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-provider-boundary-matrix.json"
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
MATRIX_ROLES = ["planner", "factory-manager", "implementer", "slice-reviewer", "integrator", "evaluator-closer"]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def provider_for(env: dict[str, str], role: str) -> str:
    key = ROLE_PROVIDER_KEYS[role]
    provider = env.get(key) or env.get("FACTORY_V3_DEFAULT_PROVIDER") or "codex"
    return provider if provider in VALID_PROVIDERS else ""


def renderer_fixture(env: dict[str, str], *, substitute_role: str | None = None, substitute_provider: str = "codex") -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for index, role in enumerate(MATRIX_ROLES):
        provider = provider_for(env, role)
        if role == substitute_role:
            provider = substitute_provider
        task_id = f"agent-os-{role}"
        tasks.append(
            {
                "id": task_id,
                "kind": "agent",
                "deps": [] if index == 0 else [f"agent-os-{MATRIX_ROLES[index - 1]}"],
                "spec": {
                    "provider": provider,
                    "agent": f"{provider}-default",
                    "promptFile": f"ao/prompts/agent-os-phase/{index + 1:02d}-{role}.md",
                    "workspace": ".",
                    "policyProfile": "ao/policy/local-dev.yaml",
                    "dispatchAuthorized": False,
                },
            }
        )
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "verdict": "PASS",
        "task_count": len(tasks),
        "prompt_files": [task["spec"]["promptFile"] for task in tasks],
        "runspec": {
            "apiVersion": "ao.dev/v1",
            "kind": "Run",
            "metadata": {
                "name": "agent-os-phase-draft",
                "description": "Non-dispatching Agent OS RunSpec draft rendered from scoped handoff packets.",
            },
            "spec": {"tasks": tasks},
        },
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def tasks_from(report: dict[str, Any]) -> list[dict[str, Any]]:
    runspec = report.get("runspec") if isinstance(report.get("runspec"), dict) else {}
    spec = runspec.get("spec") if isinstance(runspec.get("spec"), dict) else {}
    tasks = spec.get("tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def role_for_task(task: dict[str, Any]) -> str:
    task_id = str(task.get("id") or "")
    return task_id.removeprefix("agent-os-")


def yaml_provider_set(report: dict[str, Any]) -> tuple[list[str], bool, list[str]]:
    yaml_body = agent_os_runspec_renderer.render_runspec_yaml(report["runspec"])
    task_ids = re.findall(r"^\s+- id:\s*([A-Za-z0-9_.-]+)\s*$", yaml_body, flags=re.MULTILINE)
    providers = re.findall(r"^\s+provider:\s*([A-Za-z0-9_.-]+)\s*$", yaml_body, flags=re.MULTILINE)
    report_task_count = len(tasks_from(report))
    errors: list[str] = []
    if len(task_ids) != report_task_count:
        errors.append(f"yaml task count mismatch: yaml={len(task_ids)} report={report_task_count}")
    if len(providers) != report_task_count:
        errors.append(f"yaml provider count mismatch: yaml={len(providers)} report={report_task_count}")
    return sorted(set(providers)), not errors, errors


def validate_case(
    case_id: str,
    env: dict[str, str],
    report: dict[str, Any],
    *,
    profile_path: str,
    expect_pass: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    providers: list[str] = []
    yaml_providers, yaml_verified, yaml_errors = yaml_provider_set(report)
    errors.extend(yaml_errors)
    if report.get("schema") != "ao-operator/agent-os-runspec-renderer/v1":
        errors.append("renderer schema must be ao-operator/agent-os-runspec-renderer/v1")
    if report.get("dispatch_authorized") is not False:
        errors.append("renderer dispatch_authorized must remain false")
    if report.get("live_providers_run") is not False:
        errors.append("renderer live_providers_run must remain false")
    for task in tasks_from(report):
        role = role_for_task(task)
        spec = task.get("spec") if isinstance(task.get("spec"), dict) else {}
        provider = str(spec.get("provider") or "")
        providers.append(provider)
        expected = provider_for(env, role) if role in ROLE_PROVIDER_KEYS else ""
        if provider not in VALID_PROVIDERS:
            errors.append(f"provider for {role} must be codex, claude, or antigravity")
        if expected and provider != expected:
            errors.append(f"provider mismatch for {role}: expected {expected}, got {provider}")
        if spec.get("agent") != f"{provider}-default":
            errors.append(f"agent mismatch for {role}")
        if spec.get("dispatchAuthorized") is not False:
            errors.append(f"task {role} dispatchAuthorized must remain false")
    verdict = "PASS" if not errors else "FAIL"
    return {
        "id": case_id,
        "verdict": verdict,
        "expected_verdict": "PASS" if expect_pass else "FAIL",
        "profile_path": profile_path,
        "provider_set": sorted(set(providers)),
        "yaml_provider_set": yaml_providers,
        "yaml_verified": yaml_verified,
        "task_count": len(tasks_from(report)),
        "substitution_refused": not expect_pass and verdict == "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
    }


def build_matrix(*, root: Path = ROOT) -> dict[str, Any]:
    profile_root = root if (root / "examples/provider-profiles/all-codex.env").is_file() else ROOT
    profile_paths = {
        "codex_only": "examples/provider-profiles/all-codex.env",
        "claude_only": "examples/provider-profiles/all-claude.env",
        "antigravity_only": "examples/provider-profiles/all-antigravity.env",
        "mixed_profile": "examples/provider-profiles/mixed-throughput.env",
    }
    profiles = {
        profile_id: parse_env(profile_root / path)
        for profile_id, path in profile_paths.items()
    }
    codex_case = validate_case(
        "codex_only",
        profiles["codex_only"],
        renderer_fixture(profiles["codex_only"]),
        profile_path=profile_paths["codex_only"],
    )
    claude_case = validate_case(
        "claude_only",
        profiles["claude_only"],
        renderer_fixture(profiles["claude_only"]),
        profile_path=profile_paths["claude_only"],
    )
    antigravity_case = validate_case(
        "antigravity_only",
        profiles["antigravity_only"],
        renderer_fixture(profiles["antigravity_only"]),
        profile_path=profile_paths["antigravity_only"],
    )
    mixed_case = validate_case(
        "mixed_profile",
        profiles["mixed_profile"],
        renderer_fixture(profiles["mixed_profile"]),
        profile_path=profile_paths["mixed_profile"],
    )
    substituted = renderer_fixture(profiles["claude_only"], substitute_role="planner", substitute_provider="codex")
    refusal_case = validate_case(
        "provider_substitution_refusal",
        profiles["claude_only"],
        substituted,
        profile_path=profile_paths["claude_only"],
        expect_pass=False,
    )
    cases = [codex_case, claude_case, antigravity_case, mixed_case, refusal_case]

    errors: list[str] = []
    for case in cases:
        if case["verdict"] != case["expected_verdict"]:
            errors.append(f"{case['id']} expected {case['expected_verdict']} got {case['verdict']}")
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case['id']} must remain non-dispatching")
        if case["yaml_verified"] is not True:
            errors.append(f"{case['id']} YAML verification must pass")
    if refusal_case["substitution_refused"] is not True:
        errors.append("provider substitution refusal case must fail closed")

    return {
        "schema": "ao-operator/agent-os-runspec-provider-boundary-matrix/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec provider boundary matrix passes; keep provider substitution explicit."
            if not errors
            else "Fix RunSpec provider boundary failures before provider-aware renderer changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec provider boundary matrix")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_matrix(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
