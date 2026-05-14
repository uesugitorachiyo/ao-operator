#!/usr/bin/env python3
"""Prove materialized Agent OS approval reaches launcher PLAN without dispatch."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import materialize_agent_os_approval
import run_agent_os_runspec_execution
import validate_agent_os_runspec_execution_approval


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_FIXTURE_ROOT = Path("/tmp/ao-operator-agent-os-approved-launch-proof")
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approved-launch-proof.json"
APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"
APPROVAL_BUNDLE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-bundle.json"
APPROVAL_VALIDATION = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-validation.json"
RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"
MARKER = ".ao-operator-approved-launch-proof"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def reset_fixture_root(path: Path) -> None:
    if not path.exists():
        return
    marker = path / MARKER
    if path.is_dir() and marker.is_file():
        shutil.rmtree(path)
        return
    raise RuntimeError(f"fixture root exists without marker: {path}")


def copy_required_file(source_root: Path, fixture_root: Path, rel: str) -> None:
    source = resolve_path(source_root, rel)
    target = resolve_path(fixture_root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prepare_fixture(source_root: Path, fixture_root: Path) -> None:
    reset_fixture_root(fixture_root)
    fixture_root.mkdir(parents=True, exist_ok=True)
    (fixture_root / MARKER).write_text("AO Operator approved launch proof fixture\n", encoding="utf-8")
    for rel in (RUNSPEC, APPROVAL_GATE, APPROVAL_BUNDLE):
        copy_required_file(source_root, fixture_root, rel)


def launcher_summary(payload: dict[str, Any]) -> dict[str, Any]:
    lifecycle = payload.get("approval_lifecycle") if isinstance(payload.get("approval_lifecycle"), dict) else {}
    return {
        "verdict": payload.get("verdict", ""),
        "approval_state": lifecycle.get("approval_state", ""),
        "approval_usable": lifecycle.get("approval_usable", False),
        "would_run_provider": payload.get("would_run_provider", False),
        "dispatch_authorized": payload.get("dispatch_authorized", False),
        "live_providers_run": payload.get("live_providers_run", False),
        "errors": payload.get("errors", []),
    }


def validation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": payload.get("verdict", ""),
        "approval_valid": payload.get("approval_valid", False),
        "approval_state": payload.get("approval_state", ""),
        "dispatch_authorized": payload.get("dispatch_authorized", False),
        "live_providers_run": payload.get("live_providers_run", False),
        "errors": payload.get("errors", []),
    }


def lifecycle_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": payload.get("verdict", ""),
        "approval_state": payload.get("approval_state", ""),
        "approval_usable": payload.get("approval_usable", False),
        "approval_file_present": payload.get("approval_file_present", False),
        "expires_in_seconds": payload.get("expires_in_seconds"),
        "dispatch_authorized": payload.get("dispatch_authorized", False),
        "live_providers_run": payload.get("live_providers_run", False),
        "errors": payload.get("errors", []),
    }


def materialization_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": payload.get("verdict", ""),
        "approval_file_written": payload.get("approval_file_written", False),
        "approval_valid": payload.get("approval_valid", False),
        "dispatch_authorized": payload.get("dispatch_authorized", False),
        "live_providers_run": payload.get("live_providers_run", False),
        "errors": payload.get("errors", []),
    }


def check_proof(
    *,
    root: Path = ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    now: str | datetime | None = None,
    expires_in_hours: int = 4,
) -> dict[str, Any]:
    source_root = root.resolve()
    fixture_root = fixture_root.resolve()
    errors: list[str] = []

    try:
        prepare_fixture(source_root, fixture_root)
    except (OSError, RuntimeError) as exc:
        return {
            "schema": "ao-operator/agent-os-approved-launch-proof/v1",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "verdict": "FAIL",
            "fixture": "unavailable",
            "blocked_before_approval": {},
            "materialization": {},
            "approval_validation": {},
            "approval_lifecycle": {},
            "launcher_after_approval": {},
            "dispatch_authorized": False,
            "live_providers_run": False,
            "errors": [str(exc)],
            "next_safe_command": "Fix approved-launch proof fixture setup before using the launcher.",
        }

    initial_validation = validate_agent_os_runspec_execution_approval.validate_approval(
        root=fixture_root,
        approval_gate=APPROVAL_GATE,
        now=now,
    )
    initial_report = write_json(resolve_path(fixture_root, APPROVAL_VALIDATION), initial_validation)
    blocked_before = run_agent_os_runspec_execution.prepare_execution(
        root=fixture_root,
        approval_report=initial_report,
        now=now,
    )

    materialized = materialize_agent_os_approval.materialize(
        root=fixture_root,
        approval_bundle=APPROVAL_BUNDLE,
        approval_gate=APPROVAL_GATE,
        approved=True,
        operator="ao-operator-approved-launch-proof",
        accepted_risk="Approve one isolated proof fixture only; do not dispatch providers.",
        write_approval_file=True,
        overwrite=True,
        now=now,
        expires_in_hours=expires_in_hours,
    )
    if materialized.get("verdict") != "PASS" or materialized.get("approval_file_written") is not True:
        errors.append("materialization failed")

    approval_file = str(materialized.get("approval_file") or f"{STATUS_ROOT}/agent-os-runspec-execution-approval.json")
    approved_validation = validate_agent_os_runspec_execution_approval.validate_approval(
        root=fixture_root,
        approval_gate=APPROVAL_GATE,
        approval_file=approval_file,
        now=now,
    )
    approved_report = write_json(resolve_path(fixture_root, APPROVAL_VALIDATION), approved_validation)
    launcher_after = run_agent_os_runspec_execution.prepare_execution(
        root=fixture_root,
        approval_report=approved_report,
        execute=False,
        now=now,
    )
    launcher_lifecycle = launcher_after.get("approval_lifecycle") if isinstance(launcher_after.get("approval_lifecycle"), dict) else {}

    if blocked_before.get("verdict") != "BLOCKED":
        errors.append("launcher did not block before approval")
    if approved_validation.get("approval_valid") is not True:
        errors.append("approval validation did not accept materialized approval")
    if launcher_after.get("verdict") != "PLAN":
        errors.append("launcher did not reach PLAN after valid approval")
    if launcher_after.get("would_run_provider") is not False:
        errors.append("launcher would run provider without --execute")
    if launcher_lifecycle.get("approval_usable") is not True:
        errors.append("launcher lifecycle was not usable after valid approval")

    return {
        "schema": "ao-operator/agent-os-approved-launch-proof/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture": "isolated-temp",
        "source_runspec": RUNSPEC,
        "approval_gate": APPROVAL_GATE,
        "approval_bundle": APPROVAL_BUNDLE,
        "approval_report": APPROVAL_VALIDATION,
        "blocked_before_approval": launcher_summary(blocked_before),
        "materialization": materialization_summary(materialized),
        "approval_validation": validation_summary(approved_validation),
        "approval_lifecycle": lifecycle_summary(launcher_lifecycle),
        "launcher_after_approval": launcher_summary(launcher_after),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Positive approval proof passes; keep real execution blocked until a real approval is materialized."
            if not errors
            else "Fix the approved-launch proof before real approval use."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove approved Agent OS launcher path without dispatch")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--now", default=None)
    parser.add_argument("--expires-in-hours", type=int, default=4)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_proof(
        root=args.root,
        fixture_root=args.fixture_root,
        now=args.now,
        expires_in_hours=args.expires_in_hours,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
