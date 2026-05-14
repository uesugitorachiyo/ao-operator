#!/usr/bin/env python3
"""Summarize the current 50-slice operator state without provider dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance
import run_50_slice_live


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json"
PATHS = {
    "prep_report": "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json",
    "provider_budget": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json",
    "approval_gate": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval-gate.json",
    "rehearsal": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-rehearsal.json",
    "postrun_route": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-postrun-route.json",
    "approval_file": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json",
    "accepted_25_evaluation": "docs/evaluations/remote-transfer-v2-stress-live-evaluation.md",
    "accepted_25_events": "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-ao-events.md",
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


def pass_verdict(payload: dict[str, Any]) -> bool:
    return payload.get("verdict") == "PASS"


def summarize(*, root: Path = ROOT, slug: str = DEFAULT_SLUG) -> dict[str, Any]:
    paths = {key: resolve_path(root, value) for key, value in PATHS.items()}
    prep = load_json(paths["prep_report"])
    budget = load_json(paths["provider_budget"])
    gate = load_json(paths["approval_gate"])
    rehearsal = load_json(paths["rehearsal"])
    postrun = load_json(paths["postrun_route"])
    acceptance = check_live_acceptance.check_slug(slug, root=root)
    approval_ok, approval_message = run_50_slice_live.approval_file_ok(paths["approval_file"])

    blockers: list[str] = []
    if not pass_verdict(prep):
        blockers.append("50-slice dry-run prep report is missing or not PASS")
    if not pass_verdict(budget):
        blockers.append("50-slice provider budget is missing or not PASS")
    if not pass_verdict(gate):
        blockers.append("50-slice approval gate is missing or not PASS")
    if not pass_verdict(rehearsal):
        blockers.append("50-slice no-provider rehearsal is missing or not PASS")
    if not pass_verdict(postrun):
        blockers.append("50-slice postrun route is missing or not PASS")
    if acceptance.get("verdict") != "PASS":
        blockers.append("accepted 25-slice live evidence is not currently PASS")
    if not approval_ok:
        blockers.append(approval_message)

    route = str(postrun.get("route") or "UNKNOWN")
    next_slice = str(postrun.get("next_slice") or "")
    approval_status = "APPROVED" if approval_ok else "NEEDS_EXPLICIT_APPROVAL"
    accepted_50_live = (
        route == "RUN_50_SLICE_ACCEPTANCE"
        and postrun.get("acceptance_verdict") == "PASS"
        and postrun.get("commit_success_evidence_allowed") is True
        and acceptance.get("verdict") == "PASS"
    )
    if accepted_50_live:
        current_state = "ACCEPTED_50_SLICE_LIVE"
    elif blockers and not approval_ok and all("approval file" in item for item in blockers[-1:]):
        current_state = "READY_FOR_APPROVAL_NOT_DISPATCH"
    elif blockers:
        current_state = "BLOCKED"
    elif route == "WAIT_FOR_50_SLICE_LIVE_RUN":
        current_state = "READY_FOR_50_SLICE_LIVE"
    else:
        current_state = route

    live_command = (
        "FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1 python3 scripts/run_operator_slice.py "
        "examples/remote-transfer-v2-stress/operator-slices.json "
        "--slice 31-run-50-slice-live --execute --allow-live --allow-override --json"
    )
    if approval_ok and current_state == "READY_FOR_50_SLICE_LIVE":
        next_safe_command = live_command
    elif current_state == "ACCEPTED_50_SLICE_LIVE":
        next_safe_command = "50-slice live is accepted; start a new gated escalation lane before any larger live run."
    elif current_state == "READY_FOR_APPROVAL_NOT_DISPATCH":
        next_safe_command = "No live command is safe yet; write 50-slice-live-approval.json only after explicit operator approval."
    else:
        next_safe_command = "Fix blockers before considering a 50-slice live command."

    return {
        "schema": "ao-operator/50-slice-operator-summary/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if current_state in {"READY_FOR_APPROVAL_NOT_DISPATCH", "READY_FOR_50_SLICE_LIVE", "ACCEPTED_50_SLICE_LIVE"} else "FAIL",
        "slug": slug,
        "current_state": current_state,
        "approval_status": approval_status,
        "approval_message": approval_message,
        "dispatch_authorized": approval_ok and current_state == "READY_FOR_50_SLICE_LIVE",
        "live_providers_run": False,
        "target_slices": 50,
        "target_tasks": 107,
        "accepted_25_live_verdict": acceptance.get("verdict"),
        "route": route,
        "next_slice": next_slice,
        "next_safe_command": next_safe_command,
        "blockers": blockers,
        "checks": {
            "prep_report": prep.get("verdict", "MISSING"),
            "provider_budget": budget.get("verdict", "MISSING"),
            "approval_gate": gate.get("verdict", "MISSING"),
            "rehearsal": rehearsal.get("verdict", "MISSING"),
            "postrun_route": postrun.get("verdict", "MISSING"),
            "accepted_25_live": acceptance.get("verdict"),
            "approval_file": "PASS" if approval_ok else "MISSING_OR_INVALID",
        },
        "evidence_paths": {key: relpath(root, path) for key, path in paths.items()},
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"current_state={payload['current_state']}",
        f"approval_status={payload['approval_status']}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"next_safe_command={payload['next_safe_command']}",
    ]
    lines.extend(f"blocker={blocker}" for blocker in payload.get("blockers", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize 50-slice operator state")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(root=args.root, slug=args.slug)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
