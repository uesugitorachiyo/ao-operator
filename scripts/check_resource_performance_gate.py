#!/usr/bin/env python3
"""Check non-live resource and performance guardrails for AO Operator."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redact_strict_public_artifacts import redact_text


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREP_REPORT = "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json"
DEFAULT_PROVIDER_BUDGET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json"
DEFAULT_OPERATOR_SUMMARY = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/resource-performance-gate.json"
DEFAULT_WORKTREE_PATH = "/tmp/ao-operator-worktrees/remote-transfer-v2-stress-live"
DEFAULT_AO_HOME_PATH = "/tmp/ao-operator-ao-remote-transfer-v2-stress-live"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def command_durations(payload: dict[str, Any]) -> list[float]:
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        return []
    return [
        float(item.get("duration_seconds"))
        for item in commands
        if isinstance(item, dict) and isinstance(item.get("duration_seconds"), int | float)
    ]


def command_exits(payload: dict[str, Any]) -> list[int]:
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        return []
    return [int(item.get("exit")) for item in commands if isinstance(item, dict) and isinstance(item.get("exit"), int)]


def tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def summarize(
    *,
    root: Path = ROOT,
    prep_report: str | Path = DEFAULT_PREP_REPORT,
    provider_budget: str | Path = DEFAULT_PROVIDER_BUDGET,
    operator_summary: str | Path = DEFAULT_OPERATOR_SUMMARY,
    worktree_path: str | Path = DEFAULT_WORKTREE_PATH,
    ao_home_path: str | Path = DEFAULT_AO_HOME_PATH,
    max_dry_run_seconds: float = 30.0,
    max_worktree_bytes: int = 512 * 1024 * 1024,
    max_ao_home_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    root = root.resolve()
    prep_path = resolve_path(root, prep_report)
    budget_path = resolve_path(root, provider_budget)
    summary_path = resolve_path(root, operator_summary)
    worktree = resolve_path(root, worktree_path)
    ao_home = resolve_path(root, ao_home_path)
    prep = load_json(prep_path)
    budget = load_json(budget_path)
    summary = load_json(summary_path)

    durations = command_durations(prep)
    dry_run_seconds = round(sum(durations), 3)
    dry_run_ok = (
        prep.get("schema") == "ao-operator/live-profile-dry-run-prep/v1"
        and prep.get("verdict") == "PASS"
        and prep.get("slices") == 50
        and prep.get("tasks") == 107
        and command_exits(prep) == [0, 0, 0, 0]
        and dry_run_seconds <= max_dry_run_seconds
    )
    abort_text = "\n".join(str(item) for item in budget.get("abort_conditions", []))
    budget_ok = (
        budget.get("schema") == "ao-operator/50-slice-provider-budget/v1"
        and budget.get("verdict") == "PASS"
        and budget.get("target_slices") == 50
        and budget.get("target_tasks") == 107
        and budget.get("recommended_timeout_seconds", 0) <= 3600
        and "429" in abort_text
        and "AO events stop advancing" in abort_text
        and budget.get("dispatch_authorized") is False
        and budget.get("live_providers_run") is False
    )
    summary_ok = (
        summary.get("schema") == "ao-operator/50-slice-operator-summary/v1"
        and summary.get("verdict") == "PASS"
        and summary.get("current_state") == "ACCEPTED_50_SLICE_LIVE"
        and summary.get("target_slices") == 50
        and summary.get("target_tasks") == 107
        and summary.get("dispatch_authorized") is False
        and summary.get("live_providers_run") is False
    )
    worktree_bytes = tree_size(worktree)
    ao_home_bytes = tree_size(ao_home)
    footprint_ok = worktree_bytes <= max_worktree_bytes and ao_home_bytes <= max_ao_home_bytes
    checks = {
        "dry_run_wallclock": {
            "verdict": "PASS" if dry_run_ok else "FAIL",
            "seconds": dry_run_seconds,
            "max_seconds": max_dry_run_seconds,
            "evidence": relpath(root, prep_path),
        },
        "provider_budget": {
            "verdict": "PASS" if budget_ok else "FAIL",
            "recommended_timeout_seconds": budget.get("recommended_timeout_seconds"),
            "has_rate_limit_abort": "429" in abort_text,
            "has_stalled_events_abort": "AO events stop advancing" in abort_text,
            "evidence": relpath(root, budget_path),
        },
        "accepted_operator_summary": {
            "verdict": "PASS" if summary_ok else "FAIL",
            "current_state": summary.get("current_state", "UNKNOWN"),
            "evidence": relpath(root, summary_path),
        },
        "temp_footprint": {
            "verdict": "PASS" if footprint_ok else "FAIL",
            "worktree_path": str(worktree),
            "worktree_bytes": worktree_bytes,
            "worktree_limit_bytes": max_worktree_bytes,
            "ao_home_path": str(ao_home),
            "ao_home_bytes": ao_home_bytes,
            "ao_home_limit_bytes": max_ao_home_bytes,
        },
    }
    blockers = [check_id for check_id, check in checks.items() if check.get("verdict") != "PASS"]
    payload = {
        "schema": "ao-operator/resource-performance-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not blockers else "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "blockers": blockers,
        "checks": checks,
        "next_safe_command": (
            "Resource and performance guardrails pass for the accepted 50-slice baseline."
            if not blockers
            else "Fix resource/performance blockers before larger live escalation."
        ),
    }
    return sanitize(payload)


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check resource/performance guardrails")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--worktree-path", default=DEFAULT_WORKTREE_PATH)
    parser.add_argument("--ao-home-path", default=DEFAULT_AO_HOME_PATH)
    parser.add_argument("--max-dry-run-seconds", type=float, default=30.0)
    parser.add_argument("--max-worktree-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-ao-home-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(
        root=args.root,
        worktree_path=args.worktree_path,
        ao_home_path=args.ao_home_path,
        max_dry_run_seconds=args.max_dry_run_seconds,
        max_worktree_bytes=args.max_worktree_bytes,
        max_ao_home_bytes=args.max_ao_home_bytes,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
