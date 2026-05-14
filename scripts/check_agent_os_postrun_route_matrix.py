#!/usr/bin/env python3
"""Exercise Agent OS postrun routing cases without provider dispatch."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import route_agent_os_runspec_postrun


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def approval_gate(root: Path, *, valid: bool = True) -> Path:
    return write_json(
        root / "approval-gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1" if valid else "invalid",
            "verdict": "PASS" if valid else "FAIL",
            "approval_request_ready": valid,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def execution_report(
    root: Path,
    *,
    verdict: str,
    ao_completed: bool,
    evaluator_accepted: bool,
) -> Path:
    return write_json(
        root / "execution-report.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-report/v1",
            "verdict": verdict,
            "ao_completed": ao_completed,
            "evaluator_accepted": evaluator_accepted,
            "dispatch_authorized": False,
            "live_providers_run": verdict == "PASS" and ao_completed,
        },
    )


def route_case(root: Path, case_id: str, *, gate_valid: bool = True, execution: dict[str, Any] | None) -> dict[str, Any]:
    case_root = root / case_id
    gate = approval_gate(case_root, valid=gate_valid)
    if execution is None:
        report = case_root / "missing-execution-report.json"
    else:
        report = execution_report(case_root, **execution)
    payload = route_agent_os_runspec_postrun.route(root=case_root, approval_gate=gate, execution_report=report)
    return {
        "id": case_id,
        "verdict": payload["verdict"],
        "route": payload["route"],
        "diagnostics_required": payload["diagnostics_required"],
        "commit_success_evidence_allowed": payload["commit_success_evidence_allowed"],
        "errors": payload["errors"],
    }


def build_matrix(*, root: Path = ROOT) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-route-matrix-") as tmp:
        work = Path(tmp)
        cases = [
            route_case(root if root != ROOT else work, "pending_without_execution", execution=None),
            route_case(
                root if root != ROOT else work,
                "accepted_completed_execution",
                execution={"verdict": "PASS", "ao_completed": True, "evaluator_accepted": True},
            ),
            route_case(
                root if root != ROOT else work,
                "failed_execution",
                execution={"verdict": "FAIL", "ao_completed": False, "evaluator_accepted": False},
            ),
            route_case(
                root if root != ROOT else work,
                "blocked_execution",
                execution={"verdict": "BLOCKED", "ao_completed": False, "evaluator_accepted": False},
            ),
            route_case(
                root if root != ROOT else work,
                "invalid_approval_gate",
                gate_valid=False,
                execution={"verdict": "PASS", "ao_completed": True, "evaluator_accepted": True},
            ),
            route_case(
                root if root != ROOT else work,
                "missing_evaluator_acceptance",
                execution={"verdict": "PASS", "ao_completed": True, "evaluator_accepted": False},
            ),
        ]
    errors = [
        f"{case['id']} expected PASS verdict"
        for case in cases
        if case["id"] != "invalid_approval_gate" and case["verdict"] != "PASS"
    ]
    invalid_gate = next(case for case in cases if case["id"] == "invalid_approval_gate")
    if invalid_gate["verdict"] != "FAIL" or invalid_gate["route"] != "BLOCKED":
        errors.append("invalid approval gate must fail closed to BLOCKED")
    accepted = next(case for case in cases if case["id"] == "accepted_completed_execution")
    if accepted["route"] != "ACCEPTED" or accepted["commit_success_evidence_allowed"] is not True:
        errors.append("completed accepted execution must route ACCEPTED and allow success evidence")
    for case_id in ["pending_without_execution", "failed_execution", "blocked_execution", "missing_evaluator_acceptance"]:
        case = next(item for item in cases if item["id"] == case_id)
        if case["commit_success_evidence_allowed"] is not False:
            errors.append(f"{case_id} must not allow success evidence commit")
    return {
        "schema": "ao-operator/agent-os-postrun-route-matrix/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Postrun routing matrix passes; keep success commits behind evaluator closure."
            if not errors
            else "Fix Agent OS postrun routing matrix failures before execution architecture changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS postrun route matrix")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_matrix(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
