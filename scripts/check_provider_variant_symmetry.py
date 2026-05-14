#!/usr/bin/env python3
"""Check Claude/Codex prompt-template symmetry for AO Operator profiles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/provider-variant-symmetry/v1"
REQUIRED_TEMPLATES = {
    "claude": "claude.md",
    "codex": "codex.toml",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_profile_roles(profiles_dir: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    roles: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        profile = str(data.get("profile") or path.stem) if isinstance(data, dict) else path.stem
        raw_roles = data.get("roles") if isinstance(data, dict) else None
        if not isinstance(raw_roles, list):
            errors.append(f"{path}: roles must be a list")
            continue
        for raw_role in raw_roles:
            if not isinstance(raw_role, dict):
                errors.append(f"{path}: role must be an object")
                continue
            role_id = raw_role.get("id")
            if not isinstance(role_id, str) or not role_id:
                errors.append(f"{path}: role.id is required")
                continue
            entry = roles.setdefault(
                role_id,
                {
                    "id": role_id,
                    "profiles": [],
                    "role_names": [],
                },
            )
            if profile not in entry["profiles"]:
                entry["profiles"].append(profile)
            role_name = raw_role.get("role")
            if isinstance(role_name, str) and role_name and role_name not in entry["role_names"]:
                entry["role_names"].append(role_name)
    return roles, errors


def check_symmetry(*, root: Path, profiles_dir: Path, prompts_dir: Path, warn_only: bool = False) -> dict[str, Any]:
    roles, errors = load_profile_roles(profiles_dir)
    role_reports: list[dict[str, Any]] = []
    for role_id in sorted(roles):
        role_dir = prompts_dir / role_id
        templates: dict[str, str] = {}
        missing: list[str] = []
        for provider, filename in REQUIRED_TEMPLATES.items():
            path = role_dir / filename
            templates[provider] = rel(root, path)
            if not path.is_file():
                missing.append(rel(root, path))
        if missing:
            errors.extend(f"{role_id}: missing {path}" for path in missing)
        role_reports.append(
            {
                **roles[role_id],
                "templates": templates,
                "missing": missing,
                "verdict": "PASS" if not missing else "FAIL",
            }
        )
    raw_verdict = "PASS" if not errors else "FAIL"
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "profiles_dir": rel(root, profiles_dir),
        "prompts_dir": rel(root, prompts_dir),
        "required_templates": REQUIRED_TEMPLATES,
        "role_count": len(role_reports),
        "roles": role_reports,
        "errors": errors,
        "verdict": "WARN" if warn_only and errors else raw_verdict,
        "enforced": not warn_only,
        "next_safe_command": (
            "Provider variant symmetry passes."
            if not errors
            else "Create the missing prompts/<role>/claude.md and codex.toml templates."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check AO Operator provider template symmetry.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profiles-dir", type=Path)
    parser.add_argument("--prompts-dir", type=Path)
    parser.add_argument("--warn-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    profiles_dir = args.profiles_dir or root / "profiles"
    prompts_dir = args.prompts_dir or root / "prompts"
    payload = check_symmetry(
        root=root,
        profiles_dir=profiles_dir if profiles_dir.is_absolute() else root / profiles_dir,
        prompts_dir=prompts_dir if prompts_dir.is_absolute() else root / prompts_dir,
        warn_only=args.warn_only,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        for error in payload["errors"]:
            print(f"error={error}", file=sys.stderr)
    return 0 if payload["verdict"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
