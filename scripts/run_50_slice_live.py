#!/usr/bin/env python3
"""Gated launcher for the 50-slice live Remote Transfer v2 profile."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_50_slice_live_approval_gate
import check_50_slice_provider_budget


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_FILE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json"
DEFAULT_BUDGET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json"
DEFAULT_GATE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval-gate.json"
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def approval_file_ok(path: Path) -> tuple[bool, str]:
    try:
        payload = load_json(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return False, f"approval file unavailable: {exc}"
    expected = {
        "approved": True,
        "target_slices": 50,
        "target_tasks": 107,
        "approval_env": APPROVAL_ENV,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            return False, f"approval file must contain {key}={value!r}"
    if not str(payload.get("approved_by") or "").strip():
        return False, "approval file must include approved_by"
    return True, "approval file accepted"


def report(
    *,
    root: Path,
    approval_file: Path,
    execute: bool,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    env_ok = env.get(APPROVAL_ENV) == "1"
    checks.append({"id": "override_env.present", "status": "PASS" if env_ok else "FAIL"})
    if not env_ok:
        errors.append(f"{APPROVAL_ENV}=1 is required")

    budget = check_50_slice_provider_budget.check_budget(root=root, env=env)
    budget_ok = budget.get("verdict") == "PASS"
    checks.append({"id": "provider_budget.pass", "status": "PASS" if budget_ok else "FAIL"})
    if not budget_ok:
        errors.append("50-slice provider budget must pass")

    gate = check_50_slice_live_approval_gate.check_gate(root=root, env=env)
    gate_ok = gate.get("verdict") == "PASS" and gate.get("ready_for_operator_approval") is True
    checks.append({"id": "approval_gate.pass", "status": "PASS" if gate_ok else "FAIL"})
    if not gate_ok:
        errors.append("50-slice approval gate must pass")

    approval_ok, approval_message = approval_file_ok(approval_file)
    checks.append({"id": "explicit_approval_file", "status": "PASS" if approval_ok else "FAIL", "message": approval_message})
    if not approval_ok:
        errors.append(approval_message)

    ready = not errors
    command = [
        "python3",
        "scripts/generate_stress_fixture.py",
        "--live-slices",
        "50",
        "--write-live-profile",
        "&&",
        "python3",
        "scripts/factory_run.py",
        "--brief",
        "examples/remote-transfer-v2-stress/task-brief-live.md",
        "--slug",
        "remote-transfer-v2-stress-live",
        "--provider-env",
        "examples/remote-transfer-v2-stress/provider.env",
        "--topology",
        "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
        "--run",
        "--overwrite-artifacts",
        "--scrub-root-context",
    ]
    return {
        "schema": "ao-operator/50-slice-live-launch/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "BLOCKED",
        "errors": errors,
        "checks": checks,
        "execute_requested": execute,
        "dispatch_authorized": ready and execute,
        "live_providers_run": False,
        "target_slices": 50,
        "target_tasks": 107,
        "approval_file": str(approval_file),
        "planned_shell_command": " ".join(command),
    }


def run_live(root: Path, env: dict[str, str]) -> int:
    generate = subprocess.run(
        ["python3", "scripts/generate_stress_fixture.py", "--live-slices", "50", "--write-live-profile"],
        cwd=root,
        env=env,
        check=False,
    )
    if generate.returncode != 0:
        return generate.returncode
    run = subprocess.run(
        [
            "python3",
            "scripts/factory_run.py",
            "--brief",
            "examples/remote-transfer-v2-stress/task-brief-live.md",
            "--slug",
            "remote-transfer-v2-stress-live",
            "--provider-env",
            "examples/remote-transfer-v2-stress/provider.env",
            "--topology",
            "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
            "--run",
            "--overwrite-artifacts",
            "--scrub-root-context",
        ],
        cwd=root,
        env=env,
        check=False,
    )
    return run.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gated 50-slice live launcher")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run", action="store_true", help="Alias for --execute; makes live intent explicit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    approval_file = resolve_path(args.root, args.approval_file)
    execute = args.execute or args.run
    payload = report(root=args.root, approval_file=approval_file, execute=execute)
    if payload["verdict"] != "PASS":
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(payload["errors"]))
        return 1
    if not execute:
        payload["verdict"] = "PLAN"
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload["planned_shell_command"])
        return 0
    exit_code = run_live(args.root, os.environ.copy())
    payload["live_providers_run"] = True
    payload["live_command_exit"] = exit_code
    payload["verdict"] = "PASS" if exit_code == 0 else "FAIL"
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
