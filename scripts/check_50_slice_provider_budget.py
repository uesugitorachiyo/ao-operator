#!/usr/bin/env python3
"""Record provider-limit budget evidence for a 50-slice live attempt."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREP_REPORT = "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json"
EXPECTED_SLICES = 50
EXPECTED_TASKS = 107
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"


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
    return [item["exit"] for item in commands if isinstance(item, dict) and isinstance(item.get("exit"), int)]


def check_budget(
    *,
    root: Path = ROOT,
    prep_report: str | Path = DEFAULT_PREP_REPORT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    prep_path = resolve_path(root, prep_report)
    errors: list[str] = []
    prep = load_json(errors, prep_path, "50-slice prep report")
    checks: list[dict[str, Any]] = []

    expected = {
        "prep.verdict": prep.get("verdict") == "PASS",
        "prep.mode": prep.get("mode") == "dry-run-temp-worktree",
        "prep.slices": prep.get("slices") == EXPECTED_SLICES,
        "prep.tasks": prep.get("tasks") == EXPECTED_TASKS,
        "prep.command_exits": command_exits(prep) == [0, 0, 0, 0],
        "prep.evidence_preserved": prep.get("accepted_live_evidence_preserved_in_main") is True,
    }
    for check_id, ok in expected.items():
        checks.append({"id": check_id, "status": "PASS" if ok else "FAIL"})
        if prep and not ok:
            errors.append(f"{check_id} failed")

    env_present = env.get(APPROVAL_ENV) == "1"
    checks.append(
        {
            "id": "override_env.present",
            "status": "PASS" if env_present else "FAIL",
            "message": f"{APPROVAL_ENV}={env.get(APPROVAL_ENV, '')}",
        }
    )
    if not env_present:
        errors.append(f"{APPROVAL_ENV}=1 is required for 107-task live approval")

    ready = not errors
    return {
        "schema": "ao-operator/50-slice-provider-budget/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "errors": errors,
        "checks": checks,
        "target_slices": EXPECTED_SLICES,
        "target_tasks": EXPECTED_TASKS,
        "task_breakdown": {
            "control_tasks": 5,
            "implementation_factories": 50,
            "reviewers": 50,
            "closure_tasks": 2,
        },
        "provider_limit_evidence": relpath(root, prep_path),
        "override_env": APPROVAL_ENV,
        "override_env_present": env_present,
        "recommended_timeout_seconds": 3600,
        "abort_conditions": [
            "AO task failure count is nonzero before reviewer fan-out completes.",
            "Provider returns sustained 429 or authentication failures.",
            "AO events stop advancing for 10 minutes.",
            "Role artifact generation omits load-bearing factory or reviewer outputs.",
        ],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"target_tasks={payload['target_tasks']}",
        f"override_env_present={str(payload['override_env_present']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check 50-slice provider budget evidence")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--prep-report", default=DEFAULT_PREP_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_budget(root=args.root, prep_report=args.prep_report)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
