#!/usr/bin/env python3
"""Validate the AO Operator scaffold contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "AGENTS.md",
    "ao-operator.md",
    "SETUP.md",
    "PROMPT_SAMPLES.md",
    ".env.example",
    "skills.toml",
    "images/README.md",
    "images/ao-operator-architecture.svg",
    "images/ao-operator-run-lifecycle.svg",
    "images/ao-operator-artifact-flow.svg",
    "ao/runspecs/README.md",
    "ao/runspecs/ao-operator-smoke.yaml",
    "ao/prompts/README.md",
    "ao/prompts/planner-intake.md",
    "ao/prompts/plan-hardener.md",
    "ao/prompts/factory-manager.md",
    "ao/prompts/implementer-slice.md",
    "ao/prompts/reviewer-slice.md",
    "ao/prompts/integrator.md",
    "ao/prompts/evaluator-closer.md",
    "ao/policy/local-dev.yaml",
    "agents/README.md",
    "agents/planner.toml",
    "agents/plan-hardener.toml",
    "agents/factory-manager.toml",
    "agents/implementer.toml",
    "agents/slice-reviewer.toml",
    "agents/integrator.toml",
    "agents/evaluator-closer.toml",
    "skills/README.md",
    "skills/factory-intake/SKILL.md",
    "skills/context-offload/SKILL.md",
    "skills/closure-verification/SKILL.md",
    "skills/mission-monitor-ops/SKILL.md",
    "skills/spec-forge-contracting/SKILL.md",
    "skills/llm-wiki-lookup/SKILL.md",
    "docs/specs/README.md",
    "docs/plans/README.md",
    "docs/contracts/README.md",
    "docs/knowledge/README.md",
    "run-artifacts/README.md",
    "docs/evaluations/README.md",
    "docs/sdd/README.md",
    "docs/sdd/01-architecture.md",
    "docs/sdd/02-implementation-plan.md",
    "docs/sdd/03-interfaces-and-contracts.md",
    "docs/sdd/04-verification-plan.md",
    "docs/sdd/05-rollout-and-risks.md",
    "docs/sdd/06-implementation-checklist.md",
    "scripts/factory_doctor.py",
    "scripts/factory_run.py",
    "scripts/validate_factory.py",
    "scripts/validate_scaffold.py",
    "scripts/render_runspec.py",
    "scripts/validate.py",
    "scripts/validate_intake.py",
    "scripts/verify_closure.py",
    "scripts/artifact_hygiene.py",
    "scripts/pr_ready.py",
    "scripts/validate_provider_profiles.py",
    "scripts/prepare_ao_runtime_big_task.py",
    "scripts/factory_queue.py",
    "scripts/worker_pool.py",
    "scripts/code_smell_analyzer.py",
    "scripts/install_global.py",
    "examples/complex-app-smoke/README.md",
    "examples/complex-app-smoke/task-brief.md",
    "examples/provider-profiles/README.md",
    "examples/provider-profiles/all-codex.env",
    "examples/provider-profiles/all-claude.env",
    "examples/provider-profiles/mixed-throughput.env",
    "examples/ao-runtime-big-task/README.md",
    "examples/ao-runtime-big-task/artifact-pipeline-brief.md",
    "examples/outperform-ai-teams-fanout/README.md",
    "examples/outperform-ai-teams-fanout/task-brief.md",
    "examples/outperform-ai-teams-fanout/provider.env",
    "examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml",
    "examples/outperform-ai-teams-fanout/spec-forge.contract.json",
    "examples/outperform-ai-teams-fanout/expected-throughput.md",
    "examples/outperform-ai-teams-fanout/images/ao-operator-outperform-topology.svg",
    "examples/layered-openclaw-ao/README.md",
    "examples/layered-openclaw-ao/provider.env",
    ".codex/agents/codex-default.yaml",
    ".claude/agents/claude-default.yaml",
]

REQUIRED_ENV_KEYS = [
    "FACTORY_V3_DEFAULT_PROVIDER",
    "FACTORY_V3_PLANNER_PROVIDER",
    "FACTORY_V3_SPEC_FORGE_PROVIDER",
    "FACTORY_V3_RALPH_LOOP_PROVIDER",
    "FACTORY_V3_PLAN_HARDENER_PROVIDER",
    "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
    "FACTORY_V3_IMPLEMENTER_PROVIDER",
    "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
    "FACTORY_V3_INTEGRATOR_PROVIDER",
    "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
]

VALID_PROVIDERS = {"claude", "codex"}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        results.append(
            {
                "id": f"file:{rel}",
                "status": "ok" if path.is_file() else "fail",
                "message": "present" if path.is_file() else "missing",
            }
        )

    readme = ROOT / "README.md"
    readme_body = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    has_embed = "](images/ao-operator-architecture.svg)" in readme_body
    results.append(
        {
            "id": "readme.architecture_image",
            "status": "ok" if has_embed else "fail",
            "message": "README embeds primary architecture SVG"
            if has_embed
            else "README is missing primary architecture SVG embed",
        }
    )
    results.append(
        {
            "id": "readme.sdd_link",
            "status": "ok" if "docs/sdd/" in readme_body else "fail",
            "message": "README links full SDD" if "docs/sdd/" in readme_body else "README missing docs/sdd/ link",
        }
    )

    env_path = ROOT / ".env.example"
    env = parse_env(env_path) if env_path.is_file() else {}
    for key in REQUIRED_ENV_KEYS:
        present = key in env
        valid = env.get(key) in VALID_PROVIDERS
        results.append(
            {
                "id": f"env:{key}",
                "status": "ok" if present and valid else "fail",
                "message": f"{key}={env.get(key)}"
                if present
                else f"{key} missing",
            }
        )

    for rel in [
        "images/ao-operator-architecture.svg",
        "images/ao-operator-run-lifecycle.svg",
        "images/ao-operator-artifact-flow.svg",
        "examples/outperform-ai-teams-fanout/images/ao-operator-outperform-topology.svg",
    ]:
        path = ROOT / rel
        body = path.read_text(encoding="utf-8") if path.is_file() else ""
        results.append(
            {
                "id": f"svg:{rel}",
                "status": "ok" if "<svg" in body and "</svg>" in body else "fail",
                "message": "valid-looking SVG" if "<svg" in body else "missing SVG markup",
            }
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    results = check()
    ok = all(item["status"] == "ok" for item in results)
    payload = {"verdict": "PASS" if ok else "FAIL", "checks": results}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in results:
            print(f"{item['status'].upper():4} {item['id']} - {item['message']}")
        print(f"verdict={payload['verdict']}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
