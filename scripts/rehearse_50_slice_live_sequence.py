#!/usr/bin/env python3
"""Run a no-provider rehearsal of the 50-slice live operator sequence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-rehearsal.json"
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"


def run(command: list[str], *, root: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def parse_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def rehearse(*, root: Path = ROOT, manifest: str = DEFAULT_MANIFEST) -> dict[str, Any]:
    py = sys.executable
    env = os.environ.copy()
    env[APPROVAL_ENV] = "1"
    missing_approval = root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/missing-50-slice-live-approval.json"
    commands = [
        ("manifest", [py, "scripts/validate_operator_slices.py", manifest, "--json"], 0, "PASS", os.environ.copy()),
        (
            "live_slice_blocked_without_live",
            [py, "scripts/run_operator_slice.py", manifest, "--slice", "31-run-50-slice-live", "--json"],
            1,
            "BLOCKED",
            os.environ.copy(),
        ),
        (
            "provider_budget",
            [py, "scripts/check_50_slice_provider_budget.py", "--json"],
            0,
            "PASS",
            env,
        ),
        (
            "approval_gate",
            [py, "scripts/check_50_slice_live_approval_gate.py", "--json"],
            0,
            "PASS",
            env,
        ),
        (
            "launch_refuses_without_approval_file",
            [py, "scripts/run_50_slice_live.py", "--approval-file", str(missing_approval), "--json"],
            1,
            "BLOCKED",
            env,
        ),
    ]
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    for check_id, command, expected_exit, expected_verdict, command_env in commands:
        report = run(command, root=root, env=command_env)
        payload = parse_json(report["stdout"])
        actual_verdict = payload.get("verdict")
        ok = report["exit"] == expected_exit and actual_verdict == expected_verdict
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if ok else "FAIL",
                "expected_exit": expected_exit,
                "actual_exit": report["exit"],
                "expected_verdict": expected_verdict,
                "actual_verdict": actual_verdict,
            }
        )
        if not ok:
            errors.append(f"{check_id} expected exit={expected_exit} verdict={expected_verdict}")
    ready = not errors
    return {
        "schema": "ao-operator/50-slice-live-rehearsal/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "errors": errors,
        "checks": checks,
        "target_slices": 50,
        "target_tasks": 107,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rehearse 50-slice live sequence without providers")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = rehearse(root=args.root, manifest=args.manifest)
    if args.write_output is not None:
        output = Path(args.write_output)
        if not output.is_absolute():
            output = args.root / output
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
