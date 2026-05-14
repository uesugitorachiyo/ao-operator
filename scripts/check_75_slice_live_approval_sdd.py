#!/usr/bin/env python3
"""Record the 75-slice live approval SDD without dispatching providers."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_stress_fixture import task_count


ROOT = Path(__file__).resolve().parents[1]
TARGET_SLICES = 75
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_APPROVAL_FILE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-live-approval.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-live-approval-sdd.json"
DEFAULT_REPORTS = {
    "prep": "run-artifacts/remote-transfer-v2-stress/profile-prep/75-slice-dry-run-prep.json",
    "previous_accepted": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json",
    "approval_gate": "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-approval-gate.json",
    "provider_budget": "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-provider-budget.json",
    "rehearsal": "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-rehearsal.json",
    "summary": "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-summary.json",
}


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


def command_exits(payload: dict[str, Any]) -> list[int]:
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        return []
    return [item["exit"] for item in commands if isinstance(item, dict) and isinstance(item.get("exit"), int)]


def check(condition: bool, checks: list[dict[str, str]], errors: list[str], check_id: str, message: str) -> None:
    checks.append({"id": check_id, "status": "PASS" if condition else "FAIL"})
    if not condition:
        errors.append(message)


def check_prerequisite_reports(
    *,
    reports: dict[str, dict[str, Any]],
    checks: list[dict[str, str]],
    errors: list[str],
) -> None:
    target_tasks = task_count(TARGET_SLICES)
    prep = reports["prep"]
    previous = reports["previous_accepted"]
    approval_gate = reports["approval_gate"]
    provider_budget = reports["provider_budget"]
    rehearsal = reports["rehearsal"]
    summary = reports["summary"]

    check(prep.get("verdict") == "PASS", checks, errors, "prep.verdict", "75-slice dry-run prep is not PASS")
    check(prep.get("slices") == TARGET_SLICES, checks, errors, "prep.slices", "75-slice dry-run prep has the wrong slice count")
    check(prep.get("tasks") == target_tasks, checks, errors, "prep.tasks", "75-slice dry-run prep has the wrong task count")
    check(
        prep.get("accepted_live_evidence_preserved_in_main") is True,
        checks,
        errors,
        "prep.preserves_accepted_live_evidence",
        "75-slice dry-run prep did not preserve accepted 50-slice live evidence",
    )
    check(command_exits(prep) == [0, 0, 0, 0], checks, errors, "prep.command_exits", "75-slice prep commands are not all exit 0")

    check(
        previous.get("verdict") == "PASS" and previous.get("current_state") == "ACCEPTED_50_SLICE_LIVE",
        checks,
        errors,
        "previous_50.accepted",
        "accepted 50-slice live summary is missing or not accepted",
    )
    check(previous.get("dispatch_authorized") is False, checks, errors, "previous_50.dispatch_false", "50-slice summary must not authorize new dispatch")

    check(
        approval_gate.get("verdict") == "PASS" and approval_gate.get("ready_for_operator_approval") is True,
        checks,
        errors,
        "approval_gate.pass",
        "75-slice approval gate is not ready",
    )
    check(
        approval_gate.get("dispatch_authorized") is False,
        checks,
        errors,
        "approval_gate.dispatch_false",
        "75-slice approval gate must not authorize dispatch",
    )

    check(provider_budget.get("verdict") == "PASS", checks, errors, "provider_budget.pass", "75-slice provider budget is not PASS")
    check(
        provider_budget.get("target_tasks") == target_tasks,
        checks,
        errors,
        "provider_budget.tasks",
        "75-slice provider budget has the wrong task count",
    )
    check(
        provider_budget.get("dispatch_authorized") is False,
        checks,
        errors,
        "provider_budget.dispatch_false",
        "75-slice provider budget must not authorize dispatch",
    )
    check(
        bool(provider_budget.get("abort_conditions")),
        checks,
        errors,
        "provider_budget.abort_conditions",
        "75-slice provider budget must record abort conditions",
    )

    check(rehearsal.get("verdict") == "PASS", checks, errors, "rehearsal.pass", "75-slice rehearsal is not PASS")
    check(rehearsal.get("live_slice_present") is False, checks, errors, "rehearsal.no_live_slice", "75-slice rehearsal found a live slice")
    check(rehearsal.get("dispatch_authorized") is False, checks, errors, "rehearsal.dispatch_false", "75-slice rehearsal must not authorize dispatch")

    check(summary.get("verdict") == "PASS", checks, errors, "summary.pass", "75-slice escalation summary is not PASS")
    check(
        summary.get("current_state") == "READY_FOR_EXPLICIT_APPROVAL_NOT_DISPATCH",
        checks,
        errors,
        "summary.state",
        "75-slice escalation summary is not ready-for-approval",
    )
    check(summary.get("dispatch_authorized") is False, checks, errors, "summary.dispatch_false", "75-slice summary must not authorize dispatch")


def manifest_has_target_live_slice(manifest: dict[str, Any]) -> bool:
    slices = manifest.get("slices", [])
    if not isinstance(slices, list):
        return False
    for item in slices:
        if not isinstance(item, dict) or item.get("live_provider") is not True:
            continue
        identifier = str(item.get("id") or "")
        if f"{TARGET_SLICES}-slice" in identifier or item.get("task_count") == task_count(TARGET_SLICES):
            return True
    return False


def report_paths(root: Path) -> dict[str, Path]:
    return {name: resolve_path(root, path) for name, path in DEFAULT_REPORTS.items()}


def build_report(
    *,
    root: Path = ROOT,
    manifest: str | Path = DEFAULT_MANIFEST,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    paths = report_paths(root)
    reports = {name: load_json(path) for name, path in paths.items()}
    manifest_path = resolve_path(root, manifest)
    approval_path = resolve_path(root, approval_file)
    manifest_data = load_json(manifest_path)
    checks: list[dict[str, str]] = []
    errors: list[str] = []

    check(
        env.get(APPROVAL_ENV) == "1",
        checks,
        errors,
        "override_env.present",
        f"{APPROVAL_ENV}=1 is required to record 75-slice live approval posture",
    )
    check_prerequisite_reports(reports=reports, checks=checks, errors=errors)

    live_slice_present = manifest_has_target_live_slice(manifest_data)
    check(
        not live_slice_present,
        checks,
        errors,
        "manifest.no_75_slice_live_slice",
        "75-slice live slice already exists; approval SDD must be accepted before adding dispatch",
    )

    approval_file_present = approval_path.is_file()
    approval_state = "NOT_APPROVED" if not approval_file_present else "APPROVAL_FILE_PRESENT_REVIEW_BEFORE_DISPATCH"
    ready = not errors
    return {
        "schema": "ao-operator/75-slice-live-approval-sdd/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "current_state": "READY_FOR_OPERATOR_APPROVAL_NOT_DISPATCH" if ready else "BLOCKED",
        "target_slices": TARGET_SLICES,
        "target_tasks": task_count(TARGET_SLICES),
        "approval_env": APPROVAL_ENV,
        "approval_file": relpath(root, approval_path),
        "approval_file_present": approval_file_present,
        "approval_state": approval_state,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "live_slice_present": live_slice_present,
        "checks": checks,
        "errors": errors,
        "evidence": {name: relpath(root, path) for name, path in paths.items()},
        "required_operator_actions": [
            "Review 75-slice dry-run, provider budget, and rehearsal evidence.",
            "Write a separate explicit approval file only after accepting provider-limit risk.",
            "Add a dedicated 75-slice live operator slice in a later commit.",
            "Run live providers only through the dedicated live slice with --allow-live, --allow-override, and the approval env.",
        ],
        "next_safe_command": (
            "Prepare a separate 75-slice live run slice after explicit approval; do not dispatch from this SDD gate."
            if ready
            else "Fix failed 75-slice approval SDD checks before adding any live slice."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check 75-slice live approval SDD posture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--write-output", nargs="?", const="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_report(root=args.root, manifest=args.manifest, approval_file=args.approval_file)
    if args.write_output is not None:
        output = args.write_output or DEFAULT_OUTPUT
        output_path = resolve_path(args.root, output)
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
