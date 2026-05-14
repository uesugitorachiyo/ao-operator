#!/usr/bin/env python3
"""Run the local AO Operator PR readiness gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def py_compile_command() -> list[str]:
    scripts = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "scripts").glob("*.py"))
    return [sys.executable, "-m", "py_compile", *scripts]


def command_plan(
    *,
    include_pytest: bool = True,
    include_closure: bool = True,
    include_three_os_pre_public: bool = False,
    ci: bool = False,
) -> list[list[str]]:
    if ci:
        include_closure = False

    commands: list[list[str]] = [
        py_compile_command(),
        [sys.executable, "scripts/validate_scaffold.py"],
        [sys.executable, "scripts/validate_provider_profiles.py"],
        [sys.executable, "scripts/artifact_hygiene.py", "--strict"],
        [sys.executable, "scripts/redact_strict_public_artifacts.py", "--fail-on-changes", "--json"],
        [sys.executable, "scripts/check_status_json_integrity.py", "--json"],
        [sys.executable, "scripts/check_public_release_security.py", "--fail-on", "HIGH", "--json"],
        [
            sys.executable,
            "scripts/check_public_release_security.py",
            "--strict-public",
            "--fail-on",
            "HIGH",
            "--summary-only",
            "--json",
        ],
        [
            sys.executable,
            "scripts/check_public_release_security.py",
            "--strict-public",
            "--fail-on",
            "HIGH",
            "--json",
        ],
        [sys.executable, "scripts/check_dast_readiness.py", "--json"],
        [sys.executable, "scripts/check_security_sdlc_roadmap.py", "--json"],
        [sys.executable, "scripts/check_security_threat_model.py", "--json"],
        [sys.executable, "scripts/check_pentest_gate.py", "--json"],
        [sys.executable, "scripts/check_host_key_evidence.py", "--json"],
        [sys.executable, "scripts/classify_pentest_report.py", "--json"],
        [sys.executable, "scripts/check_supply_chain_gate.py", "--json"],
        [sys.executable, "scripts/check_evidence_pack_readiness.py", "--json"],
        [sys.executable, "scripts/check_live_evidence_pack_replay.py", "--json"],
        [sys.executable, "scripts/check_evidence_pack_replay_proof_status.py", "--json"],
    ]
    if include_three_os_pre_public:
        commands.append([sys.executable, "scripts/check_three_os_pre_public_gate.py", "--json"])
    if include_pytest:
        commands.append([sys.executable, "-m", "pytest", "-q"])
    if include_closure:
        commands.append([sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"])
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


def run(
    *,
    include_pytest: bool = True,
    include_closure: bool = True,
    include_three_os_pre_public: bool = False,
    ci: bool = False,
    dry_run: bool = False,
    timeout: int = 180,
) -> dict[str, Any]:
    commands = command_plan(
        include_pytest=include_pytest,
        include_closure=include_closure,
        include_three_os_pre_public=include_three_os_pre_public,
        ci=ci,
    )
    if dry_run:
        return {
            "repo": str(ROOT),
            "mode": "ci" if ci else "local",
            "verdict": "PASS",
            "commands": commands,
            "results": [],
            "errors": [],
        }

    results = [run_command(command, timeout) for command in commands]
    errors = [
        "{} failed".format(" ".join(result["command"]))
        for result in results
        if result["verdict"] != "PASS"
    ]
    return {
        "repo": str(ROOT),
        "mode": "ci" if ci else "local",
        "verdict": "PASS" if not errors else "FAIL",
        "commands": commands,
        "results": results,
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AO Operator local PR readiness checks.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run the CI-safe gate; skips closure checks that require local OAuth/AO runtime state",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print selected checks without running them")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip direct pytest; closure may still run pytest")
    parser.add_argument("--skip-closure", action="store_true", help="Skip verify_closure.py")
    parser.add_argument(
        "--pre-public",
        action="store_true",
        help="Require native macOS + Ubuntu + Windows setup proof from env-driven targets",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Per-command timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(
        include_pytest=not args.skip_pytest,
        include_closure=False if args.ci else not args.skip_closure,
        include_three_os_pre_public=args.pre_public,
        ci=args.ci,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["verdict"])
        for command in result["commands"]:
            print(" ".join(command))
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
