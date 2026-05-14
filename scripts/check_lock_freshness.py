#!/usr/bin/env python3
"""Check factory.lock.yaml against installed AO Operator runtime inputs.

The lockfile is JSON-compatible YAML so this checker can stay dependency-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/lock-freshness/v1"
LOCK_SCHEMA = "ao-operator/lock/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"UNAVAILABLE: {exc}"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode != 0:
        return f"UNAVAILABLE: exit={completed.returncode}"
    return output[0].strip() if output else ""


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else f"UNAVAILABLE: {completed.stderr.strip()}"


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def ao_packages(ao_runtime: Path) -> dict[str, str]:
    workspace = load_toml(ao_runtime / "Cargo.toml")
    workspace_version = str(workspace.get("workspace", {}).get("package", {}).get("version", ""))
    packages: dict[str, str] = {}
    for path in sorted((ao_runtime / "crates").glob("*/Cargo.toml")):
        data = load_toml(path)
        package = data.get("package", {})
        name = str(package.get("name") or path.parent.name)
        version = package.get("version")
        if isinstance(version, str):
            packages[name] = version
        elif isinstance(version, dict) and version.get("workspace") is True:
            packages[name] = workspace_version
        else:
            packages[name] = workspace_version
    return packages


def current_state(root: Path, ao_runtime: Path) -> dict[str, Any]:
    skills = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted((root / "skills").glob("*/SKILL.md"))
    }
    return {
        "schema": LOCK_SCHEMA,
        "providers": {
            "codex": command_version(["codex", "--version"]),
            "claude": command_version(["claude", "--version"]),
        },
        "skills": skills,
        "ao_runtime": {
            "path": "../ao-runtime",
            "git_head": git_head(ao_runtime),
            "workspace_packages": ao_packages(ao_runtime),
        },
    }


def flatten(prefix: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(flatten(f"{prefix}.{key}" if prefix else str(key), item))
        return out
    return {prefix: value}


def compare(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_flat = flatten("", expected)
    actual_flat = flatten("", actual)
    for key in sorted(set(expected_flat) | set(actual_flat)):
        if expected_flat.get(key) != actual_flat.get(key):
            errors.append(
                f"{key}: expected {expected_flat.get(key)!r}, observed {actual_flat.get(key)!r}"
            )
    return errors


def check_lock(*, root: Path, lockfile: Path, ao_runtime: Path) -> dict[str, Any]:
    try:
        expected = json.loads(lockfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        expected = {}
        errors = [f"{lockfile}: lockfile must be JSON-compatible YAML: {exc}"]
    else:
        errors = []
    actual = current_state(root, ao_runtime)
    if expected.get("schema") != LOCK_SCHEMA:
        errors.append(f"schema: expected {LOCK_SCHEMA}, observed {expected.get('schema')!r}")
    if not errors:
        errors.extend(compare(expected, actual))
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "lockfile": lockfile.relative_to(root).as_posix() if lockfile.is_relative_to(root) else lockfile.as_posix(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "expected": expected,
        "observed": actual,
        "next_safe_command": (
            "Lockfile freshness passes."
            if not errors
            else "Refresh factory.lock.yaml after intentionally changing provider, skill, or ao-runtime versions."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check factory.lock.yaml freshness.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--lockfile", type=Path, default=Path("factory.lock.yaml"))
    parser.add_argument("--ao-runtime", type=Path, default=Path("../ao-runtime"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    lockfile = args.lockfile if args.lockfile.is_absolute() else root / args.lockfile
    ao_runtime = args.ao_runtime if args.ao_runtime.is_absolute() else root / args.ao_runtime
    payload = check_lock(root=root, lockfile=lockfile, ao_runtime=ao_runtime.resolve())
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        for error in payload["errors"]:
            print(f"error={error}", file=sys.stderr)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
