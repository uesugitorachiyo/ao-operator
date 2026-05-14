#!/usr/bin/env python3
"""Approval-only Agent OS RunSpec execution launcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import check_agent_os_approval_lifecycle


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def default_command_runner(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True)


def tail(value: str, limit: int = 4000) -> str:
    return value[-limit:]


def command_errors(command: Any) -> list[str]:
    if not isinstance(command, list) or not command:
        return ["execution_command must be a non-empty list"]
    if not all(isinstance(part, str) and part for part in command):
        return ["execution_command entries must be non-empty strings"]
    if command[:2] != ["ao", "run"]:
        return ["execution_command must start with: ao run"]
    if any(part in {"&&", ";", "|"} for part in command):
        return ["execution_command must not contain shell control operators"]
    return []


def prepare_execution(
    *,
    root: Path = ROOT,
    approval_report: str | Path = DEFAULT_APPROVAL_REPORT,
    execute: bool = False,
    now: str | datetime | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = default_command_runner,
) -> dict[str, Any]:
    approval_path = resolve_path(root, approval_report)
    approval = load_json(approval_path)
    errors: list[str] = []
    if approval.get("schema") != "ao-operator/agent-os-runspec-execution-approval-validation/v1":
        errors.append("approval validation schema must be ao-operator/agent-os-runspec-execution-approval-validation/v1")
    if approval.get("approval_valid") is not True:
        errors.append("explicit approval is not valid")
    if approval.get("dispatch_authorized") is not False:
        errors.append("approval validation dispatch_authorized must remain false")
    if approval.get("provider_profile_checked") is not True or approval.get("provider_profile_matches") is not True:
        errors.append("approval provider profile must be checked and match")
    if approval.get("provider_mismatches"):
        errors.append("approval must not contain provider mismatches")
    command = approval.get("execution_command", [])
    runspec_path = str(approval.get("runspec_path") or "")
    runspec_sha256 = str(approval.get("runspec_sha256") or "")
    current_runspec_sha256 = ""
    resolved_runspec: Path | None = None
    if runspec_path:
        resolved_runspec = resolve_path(root, runspec_path)
        if resolved_runspec.is_file():
            current_runspec_sha256 = sha256_file(resolved_runspec)
    lifecycle: dict[str, Any] = {}
    approval_gate = str(approval.get("approval_gate") or "").strip()
    approval_file = str(approval.get("approval_file") or "").strip()
    if approval_gate and approval_file:
        lifecycle = check_agent_os_approval_lifecycle.check_lifecycle(
            root=root,
            approval_gate=approval_gate,
            approval_file=approval_file,
            now=now,
        )
    if approval.get("approval_valid") is True:
        if not approval_gate:
            errors.append("approval validation missing approval_gate")
        if not approval_file:
            errors.append("approval validation missing approval_file")
        if lifecycle.get("approval_usable") is not True:
            errors.append("approval lifecycle must be usable at execution time")
            errors.extend(str(error) for error in lifecycle.get("errors", []))
        if not runspec_path:
            errors.append("approval validation missing runspec_path")
        elif resolved_runspec is None or not resolved_runspec.is_file():
            errors.append("approved RunSpec file must exist")
        if not runspec_sha256:
            errors.append("approval validation missing runspec_sha256")
        elif current_runspec_sha256 and current_runspec_sha256 != runspec_sha256:
            errors.append("current RunSpec sha256 must match approved RunSpec sha256")
    if approval.get("approval_valid") is True:
        errors.extend(command_errors(command))

    base = {
        "schema": "ao-operator/agent-os-runspec-execution-report/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "approval_report": relpath(root, approval_path),
        "execution_command": command,
        "planned_command": command,
        "runspec_path": runspec_path,
        "runspec_sha256": runspec_sha256,
        "current_runspec_sha256": current_runspec_sha256,
        "approval_lifecycle": {
            "schema": lifecycle.get("schema", ""),
            "verdict": lifecycle.get("verdict", ""),
            "approval_state": lifecycle.get("approval_state", ""),
            "approval_usable": lifecycle.get("approval_usable", False),
            "approval_file_present": lifecycle.get("approval_file_present", False),
            "checked_at": lifecycle.get("checked_at", ""),
            "expires_in_seconds": lifecycle.get("expires_in_seconds"),
            "errors": lifecycle.get("errors", []),
        },
        "provider_profile": approval.get("provider_profile", ""),
        "provider_profile_checked": approval.get("provider_profile_checked") is True,
        "provider_profile_matches": approval.get("provider_profile_matches") is True,
        "provider_mismatches": approval.get("provider_mismatches", []),
        "execute_requested": execute,
        "ao_completed": False,
        "evaluator_accepted": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "would_run_provider": False,
        "diagnostics_required": False,
        "errors": errors,
    }
    if errors:
        return {
            **base,
            "verdict": "BLOCKED",
            "next_safe_command": "Execution blocked until explicit approval is valid.",
        }
    if not execute:
        return {
            **base,
            "verdict": "PLAN",
            "next_safe_command": "Run with --execute only after operator approval.",
        }

    result = command_runner(command, cwd=root)
    return {
        **base,
        "verdict": "PASS" if result.returncode == 0 else "FAIL",
        "would_run_provider": True,
        "dispatch_authorized": True,
        "live_providers_run": True,
        "ao_completed": result.returncode == 0,
        "diagnostics_required": result.returncode != 0,
        "live_command_exit": result.returncode,
        "stdout_tail": tail(result.stdout or ""),
        "stderr_tail": tail(result.stderr or ""),
        "next_safe_command": "Run Agent OS evaluator closure contract." if result.returncode == 0 else "Route and preserve Agent OS execution diagnostics.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agent OS RunSpec only after explicit approval")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-report", default=DEFAULT_APPROVAL_REPORT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--now", default=None, help="UTC timestamp override for deterministic approval lifecycle validation")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = prepare_execution(root=args.root, approval_report=args.approval_report, execute=args.execute, now=args.now)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    if "live_command_exit" in payload:
        return int(payload["live_command_exit"])
    return 0 if payload["verdict"] in {"PASS", "PLAN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
