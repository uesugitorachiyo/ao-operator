#!/usr/bin/env python3
"""Pre-public three-OS setup gate.

This wraps ``run_three_os_setup_smoke.py`` with environment-driven targets so
release gates can require native macOS, Ubuntu, and Windows proof without
committing private hostnames, usernames, or key paths into the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/three-os-pre-public-gate/v1"

REQUIRED_ENV = {
    "AO_OPERATOR_UBUNTU_TARGET": "--ubuntu-target",
    "AO_OPERATOR_UBUNTU_IDENTITY": "--ubuntu-identity",
    "AO_OPERATOR_UBUNTU_REPO": "--ubuntu-repo",
    "AO_OPERATOR_WINDOWS_TARGET": "--windows-target",
    "AO_OPERATOR_WINDOWS_IDENTITY": "--windows-identity",
    "AO_OPERATOR_WINDOWS_REPO": "--windows-repo",
}


def build_command(timeout: int) -> tuple[list[str], list[str]]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    command = [sys.executable, "scripts/run_three_os_setup_smoke.py", "--timeout", str(timeout)]
    for env_name, flag in REQUIRED_ENV.items():
        value = os.environ.get(env_name)
        if value:
            command.extend([flag, value])
    return command, missing


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    secret_value_flags = {
        "--ubuntu-target",
        "--ubuntu-identity",
        "--ubuntu-repo",
        "--windows-target",
        "--windows-identity",
        "--windows-repo",
    }
    for item in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted.append(item)
        if item in secret_value_flags:
            redact_next = True
    return redacted


def run_gate(timeout: int) -> dict[str, Any]:
    command, missing = build_command(timeout)
    if missing:
        return {
            "schema": SCHEMA,
            "status": "FAIL",
            "missing_env": missing,
            "command": redact_command(command),
            "errors": [
                "missing three-OS pre-public gate configuration: " + ", ".join(missing)
            ],
        }

    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload: dict[str, Any] | None = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None

    errors: list[str] = []
    if completed.returncode != 0:
        errors.append(f"three-OS smoke exited {completed.returncode}")
    if payload and payload.get("status") != "PASS":
        errors.append("three-OS smoke did not PASS")

    return {
        "schema": SCHEMA,
        "status": "PASS" if not errors else "FAIL",
        "command": redact_command(command),
        "returncode": completed.returncode,
        "smoke": payload,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Require three-OS setup smoke before public exposure.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--timeout", type=int, default=60, help="Remote host timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gate(timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
        for error in result.get("errors", []):
            print(error, file=sys.stderr)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
