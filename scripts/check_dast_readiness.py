#!/usr/bin/env python3
"""Run AO Operator no-provider DAST readiness checks.

This gate is dynamic application security testing for the current AO Operator
surface. By default it runs local dynamic tests only and refuses live/remote
dispatch. Set FACTORY_V3_DAST_REMOTE=1 to include the live remote transfer smoke
as a separate operator-approved action.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dast-readiness.json"
REMOTE_ENV = "FACTORY_V3_DAST_REMOTE"


def command_plan(*, include_remote: bool = False) -> list[list[str]]:
    commands = [
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_mac_ubuntu_remote_smoke.py",
            "tests/test_run_operator_slice.py",
            "tests/test_public_release_security.py",
        ],
        [
            sys.executable,
            "scripts/check_public_release_security.py",
            "--fail-on",
            "HIGH",
            "--path",
            "scripts/run_mac_ubuntu_remote_smoke.py",
            "--path",
            "scripts/run_operator_slice.py",
            "--json",
        ],
    ]
    if include_remote:
        commands.append(
            [
                sys.executable,
                "scripts/run_mac_ubuntu_remote_smoke.py",
                "--json",
            ]
        )
    return commands


def run_command(command: list[str], timeout: int) -> dict[str, Any]:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "duration_seconds": round(time.monotonic() - start, 3),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "verdict": "PASS" if completed.returncode == 0 else "FAIL",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "duration_seconds": round(time.monotonic() - start, 3),
            "returncode": None,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "verdict": "FAIL",
            "error": f"timed out after {timeout}s",
        }


def summarize(
    *,
    run_commands: bool = True,
    include_remote: bool | None = None,
    timeout: int = 180,
    run_command_fn: Callable[[list[str], int], dict[str, Any]] = run_command,
) -> dict[str, Any]:
    remote_enabled = os.environ.get(REMOTE_ENV) == "1" if include_remote is None else include_remote
    commands = command_plan(include_remote=remote_enabled)
    results = [run_command_fn(command, timeout) for command in commands] if run_commands else []
    blockers = [
        "command:" + " ".join(result["command"])
        for result in results
        if result.get("verdict") != "PASS"
    ]
    return {
        "schema": "ao-operator/dast-readiness/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "commands": commands,
        "results": results,
        "remote_dast_enabled": remote_enabled,
        "remote_approval_env": REMOTE_ENV,
        "dispatch_authorized": False,
        "live_providers_run": remote_enabled and not blockers,
        "next_safe_command": (
            "Resolve DAST blockers before public release."
            if blockers
            else "DAST readiness passed; strict public artifact cleanup remains a separate gate."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"remote_dast_enabled={str(payload['remote_dast_enabled']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"live_providers_run={str(payload['live_providers_run']).lower()}",
    ]
    lines.extend(f"blocker={blocker}" for blocker in payload["blockers"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run no-provider DAST readiness")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-remote", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(run_commands=not args.dry_run, include_remote=args.include_remote or None, timeout=args.timeout)
    if args.write_output is not None:
        output = Path(args.write_output)
        if not output.is_absolute():
            output = ROOT / output
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
