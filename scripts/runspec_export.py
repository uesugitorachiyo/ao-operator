#!/usr/bin/env python3
"""Export a profile-shaped Factory run to workflow-as-data YAML."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import factory_run  # noqa: E402


SCHEMA = "ao-operator/runspec/v1"


def _relative(path: str | Path, *, root: Path = ROOT) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def target_path(output_path: str | Path) -> Path:
    base = Path(output_path)
    if base.suffix != ".factory":
        base = base.with_name(f"{base.name}.factory")
    return base / "runspec.yaml"


def build_export(
    *,
    slug: str,
    profile_name: str,
    brief: str | Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    profile = factory_run._load_profile(profile_name, repo_root=repo_root)
    roles = []
    for task in factory_run._tasks_from_profile(profile):
        role = {
            "id": task["id"],
            "provider_key": task["provider_key"],
            "host_tag": list(task.get("host_tag") or []),
            "deps": list(task.get("deps") or []),
            "reads": list(task.get("reads") or []),
            "writes": list(task.get("writes") or []),
        }
        roles.append(role)
    return {
        "schema": SCHEMA,
        "slug": slug,
        "profile": profile_name,
        "brief": _relative(brief, root=repo_root),
        "roles": roles,
        "gates": {"gate_b": True, "gate_r": True},
    }


def write_export(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a Factory run as .factory/runspec.yaml")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--brief", required=True)
    parser.add_argument(
        "--output-path",
        required=True,
        help="Base path; '.factory/runspec.yaml' is appended when needed.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)

    payload = build_export(slug=args.slug, profile_name=args.profile, brief=args.brief)
    path = write_export(payload, target_path(args.output_path))
    if args.json:
        print(json.dumps({"schema": SCHEMA, "path": str(path), "role_count": len(payload["roles"])}, indent=2))
    else:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
