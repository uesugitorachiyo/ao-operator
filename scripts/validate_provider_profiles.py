#!/usr/bin/env python3
"""Validate bundled AO Operator provider profiles."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import render_runspec


ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "examples" / "provider-profiles"
VALID_PROVIDERS = {"claude", "codex"}
EXPECTED_CORE_PROVIDERS = {
    "all-codex.env": {
        "planner-intake": "codex",
        "plan-hardener": "codex",
        "factory-manager": "codex",
        "implementer-slice": "codex",
        "reviewer-slice": "codex",
        "integrator": "codex",
        "evaluator-closer": "codex",
    },
    "all-claude.env": {
        "planner-intake": "claude",
        "plan-hardener": "claude",
        "factory-manager": "claude",
        "implementer-slice": "claude",
        "reviewer-slice": "claude",
        "integrator": "claude",
        "evaluator-closer": "claude",
    },
    "mixed-throughput.env": {
        "planner-intake": "claude",
        "plan-hardener": "claude",
        "factory-manager": "codex",
        "implementer-slice": "codex",
        "reviewer-slice": "claude",
        "integrator": "codex",
        "evaluator-closer": "claude",
    },
}


def provider_keys(env: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in env.items()
        if key == "FACTORY_V3_DEFAULT_PROVIDER"
        or (key.startswith("FACTORY_V3_") and key.endswith("_PROVIDER"))
    }


def rendered_core_providers(rendered: str) -> dict[str, str]:
    providers: dict[str, str] = {}
    current_task: str | None = None
    for line in rendered.splitlines():
        task_match = re.match(r"\s+- id: (.+)$", line)
        if task_match:
            current_task = task_match.group(1)
            continue
        provider_match = re.match(r"\s+provider: (.+)$", line)
        if provider_match and current_task:
            providers[current_task] = provider_match.group(1)
    return providers


def validate_profile(path: Path) -> dict[str, Any]:
    env = render_runspec.parse_env(path)
    errors: list[str] = []
    keys = provider_keys(env)
    for key, value in sorted(keys.items()):
        if value not in VALID_PROVIDERS:
            errors.append(f"{key} resolved to unsupported provider {value!r}")

    try:
        rendered = render_runspec.render(env)
        rendered_providers = rendered_core_providers(rendered)
    except ValueError as exc:
        rendered_providers = {}
        errors.append(str(exc))

    expected = EXPECTED_CORE_PROVIDERS.get(path.name)
    if expected is None:
        errors.append(f"no expected provider map for {path.name}")
    elif rendered_providers != expected:
        errors.append(f"rendered providers mismatch: expected {expected}, got {rendered_providers}")

    return {
        "profile": path.name,
        "verdict": "PASS" if not errors else "FAIL",
        "provider_keys": keys,
        "rendered_providers": rendered_providers,
        "errors": errors,
    }


def payload(profiles_dir: Path = PROFILES_DIR) -> dict[str, Any]:
    profiles = [validate_profile(path) for path in sorted(profiles_dir.glob("*.env"))]
    errors = [error for profile in profiles for error in profile["errors"]]
    return {
        "verdict": "PASS" if not errors else "FAIL",
        "profiles_dir": str(profiles_dir),
        "profiles": profiles,
        "errors": errors,
    }


def print_table(data: dict[str, Any]) -> None:
    for profile in data["profiles"]:
        rendered = ", ".join(
            f"{task}={provider}"
            for task, provider in profile["rendered_providers"].items()
        )
        print(f"{profile['verdict']:4} {profile['profile']} - {rendered}")
        for error in profile["errors"]:
            print(f"     ERROR {error}")
    print(f"verdict={data['verdict']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    data = payload()
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_table(data)
    return 0 if data["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
