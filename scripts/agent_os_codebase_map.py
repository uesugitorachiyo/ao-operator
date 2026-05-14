#!/usr/bin/env python3
"""Agent OS codebase surface mapper and specialist planner."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-codebase-specialists.json"
SURFACE_PATTERNS = {
    "runtime_scripts": ["scripts/*.py"],
    "tests": ["tests/test_*.py"],
    "sdd_docs": ["docs/sdd/*.md"],
    "agent_contracts": ["agents/*.toml", "agents/*.md"],
    "skills": ["skills/*/SKILL.md"],
}
REQUIRED_SURFACES = ["runtime_scripts", "tests", "sdd_docs"]


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def collect_surface(root: Path, patterns: list[str]) -> list[str]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted({relpath(root, path) for path in paths})


def recommend_specialists(surfaces: dict[str, dict[str, Any]]) -> list[str]:
    specialists = ["engineering-manager", "release-manager"]
    if surfaces.get("sdd_docs", {}).get("count", 0):
        specialists.append("docs-release")
    if surfaces.get("runtime_scripts", {}).get("count", 0):
        specialists.append("qa")
    if surfaces.get("agent_contracts", {}).get("count", 0) or surfaces.get("skills", {}).get("count", 0):
        specialists.append("capability-validator")
    return list(dict.fromkeys(specialists))


def map_codebase(*, root: Path = ROOT) -> dict[str, Any]:
    surfaces: dict[str, dict[str, Any]] = {}
    for name, patterns in SURFACE_PATTERNS.items():
        paths = collect_surface(root, patterns)
        surfaces[name] = {
            "patterns": patterns,
            "count": len(paths),
            "sample_paths": paths[:20],
        }
    errors = [
        f"{name} surface is missing"
        for name in REQUIRED_SURFACES
        if surfaces[name]["count"] == 0
    ]
    return {
        "schema": "ao-operator/agent-os-codebase-map/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "repo": str(root),
        "surfaces": surfaces,
        "recommended_specialists": recommend_specialists(surfaces),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Plan capability validation for recommended specialists."
            if not errors
            else "Restore missing codebase surfaces before specialist planning."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map AO Operator codebase surfaces for Agent OS specialist planning")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = map_codebase(root=args.root)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
