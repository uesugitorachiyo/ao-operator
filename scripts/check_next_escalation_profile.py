#!/usr/bin/env python3
"""Check the next post-50-slice escalation profile without dispatching providers."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_stress_fixture import task_count


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_SLICES = 75
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_PREVIOUS_SUMMARY = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json"
DEFAULT_OUTPUT_ROOT = "run-artifacts/remote-transfer-v2-stress-live/dispatch"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def default_prep_report(target_slices: int) -> str:
    return f"run-artifacts/remote-transfer-v2-stress/profile-prep/{target_slices}-slice-dry-run-prep.json"


def default_output(target_slices: int, kind: str) -> str:
    return f"{DEFAULT_OUTPUT_ROOT}/{target_slices}-slice-next-escalation-{kind}.json"


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


def prep_ok(payload: dict[str, Any], target_slices: int, errors: list[str]) -> bool:
    expected_tasks = task_count(target_slices)
    checks = {
        "prep.verdict": payload.get("verdict") == "PASS",
        "prep.mode": payload.get("mode") == "dry-run-temp-worktree",
        "prep.slices": payload.get("slices") == target_slices,
        "prep.tasks": payload.get("tasks") == expected_tasks,
        "prep.evidence_preserved": payload.get("accepted_live_evidence_preserved_in_main") is True,
        "prep.command_exits": command_exits(payload) == [0, 0, 0, 0],
    }
    for check_id, ok in checks.items():
        if not ok:
            errors.append(f"{check_id} failed")
    return all(checks.values())


def previous_profile_ok(payload: dict[str, Any], errors: list[str]) -> bool:
    ok = (
        payload.get("verdict") == "PASS"
        and payload.get("current_state") == "ACCEPTED_50_SLICE_LIVE"
        and payload.get("target_slices") == 50
        and payload.get("target_tasks") == 107
        and payload.get("dispatch_authorized") is False
    )
    if not ok:
        errors.append("accepted 50-slice operator summary is missing or not accepted")
    return ok


def base_payload(kind: str, target_slices: int) -> dict[str, Any]:
    return {
        "schema": f"ao-operator/next-escalation-{kind}/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_slices": target_slices,
        "target_tasks": task_count(target_slices),
        "approval_env": APPROVAL_ENV,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def approval_gate(
    *,
    root: Path = ROOT,
    target_slices: int = DEFAULT_TARGET_SLICES,
    prep_report: str | Path | None = None,
    previous_summary: str | Path = DEFAULT_PREVIOUS_SUMMARY,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    prep_path = resolve_path(root, prep_report or default_prep_report(target_slices))
    summary_path = resolve_path(root, previous_summary)
    prep = load_json(prep_path)
    previous = load_json(summary_path)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    env_ok = env.get(APPROVAL_ENV) == "1"
    checks.append({"id": "override_env.present", "status": "PASS" if env_ok else "FAIL"})
    if not env_ok:
        errors.append(f"{APPROVAL_ENV}=1 is required")
    prep_pass = prep_ok(prep, target_slices, errors)
    previous_pass = previous_profile_ok(previous, errors)
    checks.extend(
        [
            {"id": "prep_report.pass", "status": "PASS" if prep_pass else "FAIL"},
            {"id": "accepted_50_slice_summary.pass", "status": "PASS" if previous_pass else "FAIL"},
        ]
    )
    ready = not errors
    payload = base_payload("approval-gate", target_slices)
    payload.update(
        {
            "verdict": "PASS" if ready else "FAIL",
            "errors": errors,
            "checks": checks,
            "ready_for_operator_approval": ready,
            "operator_approval_required": True,
            "provider_limit_evidence": relpath(root, prep_path),
            "prior_accepted_profile": {
                "summary": relpath(root, summary_path),
                "target_slices": previous.get("target_slices"),
                "current_state": previous.get("current_state"),
            },
            "next_actions": [
                "Do not run live providers from this gate.",
                "Add a separate live slice and explicit approval file before any dispatch.",
            ],
        }
    )
    return payload


def provider_budget(
    *,
    root: Path = ROOT,
    target_slices: int = DEFAULT_TARGET_SLICES,
    prep_report: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    prep_path = resolve_path(root, prep_report or default_prep_report(target_slices))
    prep = load_json(prep_path)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    prep_pass = prep_ok(prep, target_slices, errors)
    env_ok = env.get(APPROVAL_ENV) == "1"
    checks.extend(
        [
            {"id": "prep_report.pass", "status": "PASS" if prep_pass else "FAIL"},
            {"id": "override_env.present", "status": "PASS" if env_ok else "FAIL"},
        ]
    )
    if not env_ok:
        errors.append(f"{APPROVAL_ENV}=1 is required")
    payload = base_payload("provider-budget", target_slices)
    payload.update(
        {
            "verdict": "PASS" if not errors else "FAIL",
            "errors": errors,
            "checks": checks,
            "provider_limit_evidence": relpath(root, prep_path),
            "recommended_timeout_seconds": 5400,
            "abort_conditions": [
                "Provider returns sustained 429 or authentication failures.",
                "AO events stop advancing for 10 minutes.",
                "Task failure count is nonzero before reviewer fan-out completes.",
                "Generated role artifacts omit any load-bearing factory or reviewer output.",
            ],
        }
    )
    return payload


def manifest_has_live_slice(path: Path, target_slices: int) -> bool:
    data = load_json(path)
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return False
    target_text = f"{target_slices}-slice"
    for item in slices:
        if not isinstance(item, dict):
            continue
        if item.get("live_provider") is True and target_text in str(item.get("id") or ""):
            return True
    return False


def rehearsal(
    *,
    root: Path = ROOT,
    manifest: str | Path = DEFAULT_MANIFEST,
    target_slices: int = DEFAULT_TARGET_SLICES,
    prep_report: str | Path | None = None,
) -> dict[str, Any]:
    manifest_path = resolve_path(root, manifest)
    env = {APPROVAL_ENV: "1"}
    gate = approval_gate(root=root, target_slices=target_slices, prep_report=prep_report, env=env)
    budget = provider_budget(root=root, target_slices=target_slices, prep_report=prep_report, env=env)
    live_slice_present = manifest_has_live_slice(manifest_path, target_slices)
    errors: list[str] = []
    if gate.get("verdict") != "PASS":
        errors.append("approval gate did not pass")
    if budget.get("verdict") != "PASS":
        errors.append("provider budget did not pass")
    if live_slice_present:
        errors.append(f"{target_slices}-slice live slice already exists; rehearsal must stay non-dispatching")
    payload = base_payload("rehearsal", target_slices)
    payload.update(
        {
            "verdict": "PASS" if not errors else "FAIL",
            "errors": errors,
            "checks": [
                {"id": "approval_gate.pass", "status": "PASS" if gate.get("verdict") == "PASS" else "FAIL"},
                {"id": "provider_budget.pass", "status": "PASS" if budget.get("verdict") == "PASS" else "FAIL"},
                {"id": "target_live_slice.absent", "status": "PASS" if not live_slice_present else "FAIL"},
            ],
            "manifest": relpath(root, manifest_path),
            "live_slice_present": live_slice_present,
        }
    )
    return payload


def summary(
    *,
    root: Path = ROOT,
    target_slices: int = DEFAULT_TARGET_SLICES,
    prep_report: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    gate = load_json(resolve_path(root, default_output(target_slices, "approval-gate"))) if env is None else {}
    if gate.get("schema") != "ao-operator/next-escalation-approval-gate/v1":
        gate = approval_gate(root=root, target_slices=target_slices, prep_report=prep_report, env=env)
    budget = load_json(resolve_path(root, default_output(target_slices, "provider-budget"))) if env is None else {}
    if budget.get("schema") != "ao-operator/next-escalation-provider-budget/v1":
        budget = provider_budget(root=root, target_slices=target_slices, prep_report=prep_report, env=env)
    blockers = []
    if gate.get("verdict") != "PASS":
        blockers.append("approval gate is not PASS")
    if budget.get("verdict") != "PASS":
        blockers.append("provider budget is not PASS")
    current_state = "READY_FOR_EXPLICIT_APPROVAL_NOT_DISPATCH" if not blockers else "BLOCKED"
    payload = base_payload("summary", target_slices)
    payload.update(
        {
            "verdict": "PASS" if not blockers else "FAIL",
            "current_state": current_state,
            "blockers": blockers,
            "approval_status": "NEEDS_SEPARATE_LIVE_APPROVAL",
            "next_safe_command": (
                f"{target_slices}-slice dry-run prep is complete; add a separate live slice and explicit approval file before dispatch."
                if not blockers
                else "Fix next-escalation blockers before adding any live slice."
            ),
        }
    )
    return payload


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    kwargs = {
        "root": args.root,
        "target_slices": args.target_slices,
        "prep_report": args.prep_report or default_prep_report(args.target_slices),
    }
    if args.check == "approval-gate":
        return approval_gate(**kwargs)
    if args.check == "provider-budget":
        return provider_budget(**kwargs)
    if args.check == "rehearsal":
        return rehearsal(
            root=args.root,
            manifest=args.manifest,
            target_slices=args.target_slices,
            prep_report=kwargs["prep_report"],
        )
    if args.check == "summary":
        return summary(**kwargs)
    raise ValueError(f"unknown check {args.check}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check next escalation profile gates")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target-slices", type=int, default=DEFAULT_TARGET_SLICES)
    parser.add_argument("--prep-report", default="")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--check",
        choices=["approval-gate", "provider-budget", "rehearsal", "summary"],
        default="summary",
    )
    parser.add_argument("--write-output", nargs="?", const="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_payload(args)
    if args.write_output is not None:
        output = args.write_output or default_output(args.target_slices, args.check)
        output_path = resolve_path(args.root, output)
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
