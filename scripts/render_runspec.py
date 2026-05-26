#!/usr/bin/env python3
"""Render a AO Operator smoke RunSpec from .env provider selection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_PROVIDERS = {"claude", "codex", "antigravity"}

TASKS = [
    ("planner-intake", "FACTORY_V3_PLANNER_PROVIDER", "ao/prompts/planner-intake.md", []),
    ("plan-hardener", "FACTORY_V3_PLAN_HARDENER_PROVIDER", "ao/prompts/plan-hardener.md", ["planner-intake"]),
    ("factory-manager", "FACTORY_V3_FACTORY_MANAGER_PROVIDER", "ao/prompts/factory-manager.md", ["plan-hardener"]),
    ("implementer-slice", "FACTORY_V3_IMPLEMENTER_PROVIDER", "ao/prompts/implementer-slice.md", ["factory-manager"]),
    ("reviewer-slice", "FACTORY_V3_SLICE_REVIEWER_PROVIDER", "ao/prompts/reviewer-slice.md", ["implementer-slice"]),
    ("integrator", "FACTORY_V3_INTEGRATOR_PROVIDER", "ao/prompts/integrator.md", ["reviewer-slice"]),
    ("evaluator-closer", "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER", "ao/prompts/evaluator-closer.md", ["integrator"]),
]


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def provider_for(env: dict[str, str], role_key: str) -> str:
    default = env.get("FACTORY_V3_DEFAULT_PROVIDER", "codex")
    value = env.get(role_key, default)
    if value not in VALID_PROVIDERS:
        raise ValueError(f"{role_key} resolved to unsupported provider {value!r}")
    return value


def deps_yaml(deps: list[str]) -> str:
    if not deps:
        return "[]"
    return "[" + ", ".join(f'"{dep}"' for dep in deps) + "]"


def render(env: dict[str, str]) -> str:
    lines: list[str] = [
        "apiVersion: ao.dev/v1",
        "kind: Run",
        "metadata:",
        "  name: ao-operator-smoke",
        "  description: AO Operator provider-aware smoke DAG rendered from .env.",
        "spec:",
        "  tasks:",
    ]

    for task_id, role_key, prompt_file, deps in TASKS:
        provider = provider_for(env, role_key)
        agent = f"{provider}-default"
        lines.extend(
            [
                f"    - id: {task_id}",
                "      kind: agent",
                f"      deps: {deps_yaml(deps)}",
                "      spec:",
                f"        provider: {provider}",
                f"        agent: {agent}",
                f"        promptFile: {prompt_file}",
                "        workspace: .",
                "        policyProfile: ao/policy/local-dev.yaml",
            ]
        )

    return "\n".join(lines) + "\n"


def render_full(env: dict[str, str], slug: str, prompts_dir: str, workspace: str) -> str:
    lines: list[str] = [
        "apiVersion: ao.dev/v1",
        "kind: Run",
        "metadata:",
        f"  name: {slug}",
        f"  description: AO Operator full provider-aware DAG for {slug}.",
        "spec:",
        "  tasks:",
    ]

    for task_id, role_key, _prompt_file, deps in TASKS:
        provider = provider_for(env, role_key)
        agent = f"{provider}-default"
        lines.extend(
            [
                f"    - id: {task_id}",
                "      kind: agent",
                f"      deps: {deps_yaml(deps)}",
                "      spec:",
                f"        provider: {provider}",
                f"        agent: {agent}",
                f"        promptFile: {prompts_dir.rstrip('/')}/{task_id}.md",
                f"        workspace: {workspace}",
                "        policyProfile: ao/policy/local-dev.yaml",
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=str(ROOT / ".env"), help="Path to .env file")
    parser.add_argument("--plan", help="Full-factory plan path; enables full RunSpec mode")
    parser.add_argument("--prompts", help="Prompt directory for full RunSpec mode")
    parser.add_argument("--workspace", default=".", help="Workspace path for full RunSpec mode")
    parser.add_argument("--output", help="Output path; stdout when omitted")
    args = parser.parse_args()

    env = parse_env(Path(args.env))
    try:
        if args.plan:
            if not args.prompts:
                print("render_runspec.py: --prompts is required with --plan", file=sys.stderr)
                return 2
            plan_path = Path(args.plan)
            slug = plan_path.name.removesuffix("-plan.md")
            body = render_full(env, slug, args.prompts, args.workspace)
        else:
            body = render(env)
    except ValueError as exc:
        print(f"render_runspec.py: {exc}", file=sys.stderr)
        return 2

    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
