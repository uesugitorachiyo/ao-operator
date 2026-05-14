#!/usr/bin/env python3
"""Check whether the 50-slice live profile may be submitted for approval."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_PREP_REPORT = "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json"
DEFAULT_ACCEPTANCE_EVALUATION = "docs/evaluations/remote-transfer-v2-stress-live-evaluation.md"
DEFAULT_ACCEPTANCE_STATUS = "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-status.md"
DEFAULT_ACCEPTANCE_EVENTS = "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-ao-events.md"
DEFAULT_SUCCESS_GUARD = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-success-commit-guard.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval-gate.json"
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
EXPECTED_SLICES = 50
EXPECTED_TASKS = 107


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(errors: list[str], path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        errors.append(f"{label} unavailable: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return data


def command_exits(payload: dict[str, Any]) -> list[int]:
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        return []
    exits: list[int] = []
    for item in commands:
        if isinstance(item, dict) and isinstance(item.get("exit"), int):
            exits.append(item["exit"])
    return exits


def success_guard_ok(path: Path, errors: list[str]) -> bool:
    guard_errors: list[str] = []
    guard = load_json(guard_errors, path, "accepted live success guard")
    if guard_errors:
        errors.extend(guard_errors)
        return False
    ok = (
        guard.get("verdict") == "PASS"
        and guard.get("acceptance_verdict") == "PASS"
        and guard.get("classification") == "ACCEPTED"
        and guard.get("commit_success_evidence_allowed") is True
    )
    if not ok:
        errors.append("accepted live success guard does not preserve accepted evidence")
    return ok


def accepted_live_evidence_ok(paths: dict[str, Path], errors: list[str]) -> bool:
    evaluation = paths["acceptance_evaluation"]
    status = paths["acceptance_status"]
    events = paths["acceptance_events"]
    current_errors: list[str] = []
    ok = True
    if not evaluation.is_file():
        current_errors.append("accepted 25-slice evaluation is missing")
        ok = False
    else:
        body = evaluation.read_text(encoding="utf-8")
        for needle in ["Verdict: ACCEPTED", "AO Run: r-", "Blockers:", "- none"]:
            if needle not in body:
                current_errors.append(f"accepted 25-slice evaluation missing {needle!r}")
                ok = False
    if not status.is_file():
        current_errors.append("accepted 25-slice status is missing")
        ok = False
    elif "Mode: run" not in status.read_text(encoding="utf-8"):
        current_errors.append("accepted 25-slice status must say Mode: run")
        ok = False
    if not events.is_file():
        current_errors.append("accepted 25-slice AO events file is missing")
        ok = False
    if ok:
        return True
    if success_guard_ok(paths["success_guard"], []):
        return True
    errors.extend(current_errors)
    return False


def check_gate(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    prep_report: str | Path = DEFAULT_PREP_REPORT,
    acceptance_evaluation: str | Path = DEFAULT_ACCEPTANCE_EVALUATION,
    acceptance_status: str | Path = DEFAULT_ACCEPTANCE_STATUS,
    acceptance_events: str | Path = DEFAULT_ACCEPTANCE_EVENTS,
    success_guard: str | Path = DEFAULT_SUCCESS_GUARD,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    paths = {
        "prep_report": resolve_path(root, prep_report),
        "acceptance_evaluation": resolve_path(root, acceptance_evaluation),
        "acceptance_status": resolve_path(root, acceptance_status),
        "acceptance_events": resolve_path(root, acceptance_events),
        "success_guard": resolve_path(root, success_guard),
    }
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    env_ok = env.get(APPROVAL_ENV) == "1"
    checks.append({"id": "approval_env.present", "status": "PASS" if env_ok else "FAIL", "message": f"{APPROVAL_ENV}={env.get(APPROVAL_ENV, '')}"})
    if not env_ok:
        errors.append(f"{APPROVAL_ENV}=1 is required")

    prep = load_json(errors, paths["prep_report"], "50-slice prep report")
    prep_checks = {
        "prep.verdict": prep.get("verdict") == "PASS",
        "prep.mode": prep.get("mode") == "dry-run-temp-worktree",
        "prep.slices": prep.get("slices") == EXPECTED_SLICES,
        "prep.tasks": prep.get("tasks") == EXPECTED_TASKS,
        "prep.evidence_preserved": prep.get("accepted_live_evidence_preserved_in_main") is True,
        "prep.command_exits": command_exits(prep) == [0, 0, 0, 0],
    }
    for check_id, ok in prep_checks.items():
        checks.append({"id": check_id, "status": "PASS" if ok else "FAIL", "message": str(prep.get(check_id.split(".", 1)[1], ""))})
        if prep and not ok:
            errors.append(f"{check_id} failed")

    accepted_ok = accepted_live_evidence_ok(paths, errors)
    checks.append({"id": "accepted_25_slice_live_evidence", "status": "PASS" if accepted_ok else "FAIL", "message": "accepted 25-slice live evidence"})

    ready = not errors
    return {
        "schema": "ao-operator/50-slice-live-approval-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "errors": errors,
        "checks": checks,
        "slug": slug,
        "target_slices": EXPECTED_SLICES,
        "target_tasks": EXPECTED_TASKS,
        "approval_env": APPROVAL_ENV,
        "provider_limit_evidence": relpath(root, paths["prep_report"]),
        "prior_accepted_live_evidence": {
            "evaluation": relpath(root, paths["acceptance_evaluation"]),
            "status": relpath(root, paths["acceptance_status"]),
            "events": relpath(root, paths["acceptance_events"]),
            "success_guard": relpath(root, paths["success_guard"]),
        },
        "ready_for_operator_approval": ready,
        "operator_approval_required": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "operator_dispatch_command": "not-authorized; add a separate 50-slice live slice after approval",
        "next_actions": [
            "Ask for explicit operator approval before running the 50-slice live provider profile.",
            "Do not treat this gate as dispatch authorization.",
            "Do not run live providers until a separate live operator slice is added or selected.",
        ],
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"ready_for_operator_approval={str(payload['ready_for_operator_approval']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"target_tasks={payload['target_tasks']}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the 50-slice live approval gate")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--prep-report", default=DEFAULT_PREP_REPORT)
    parser.add_argument("--acceptance-evaluation", default=DEFAULT_ACCEPTANCE_EVALUATION)
    parser.add_argument("--acceptance-status", default=DEFAULT_ACCEPTANCE_STATUS)
    parser.add_argument("--acceptance-events", default=DEFAULT_ACCEPTANCE_EVENTS)
    parser.add_argument("--success-guard", default=DEFAULT_SUCCESS_GUARD)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_gate(
        root=args.root,
        slug=args.slug,
        prep_report=args.prep_report,
        acceptance_evaluation=args.acceptance_evaluation,
        acceptance_status=args.acceptance_status,
        acceptance_events=args.acceptance_events,
        success_guard=args.success_guard,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
