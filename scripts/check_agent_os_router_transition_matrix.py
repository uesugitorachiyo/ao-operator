#!/usr/bin/env python3
"""Exercise deterministic Agent OS router transition cases without dispatch."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_router


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-transition-matrix.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def readiness(path: Path) -> dict[str, Any]:
    payload = {
        "schema": "ao-operator/agent-os-architecture-readiness/v1",
        "verdict": "PASS",
        "architecture_ready": True,
        "baseline_count": 5,
        "blockers": [],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    write_json(path, payload)
    return payload


def case_summary(
    *,
    case_id: str,
    brief: str,
    labels: list[str] | None = None,
    state_v2: bool = False,
    work: Path,
) -> dict[str, Any]:
    route = agent_os_router.route_brief(brief, labels=labels or [])
    state: dict[str, Any] = {}
    if state_v2:
        readiness_path = work / f"{case_id}-readiness.json"
        state = agent_os_router.build_state_snapshot_v2(
            route,
            architecture_readiness=readiness(readiness_path),
            architecture_readiness_path=readiness_path,
            root=work,
            lane=case_id,
        )
    return {
        "id": case_id,
        "classification": route["classification"],
        "shape": route["shape"],
        "routes": route["routes"],
        "route_dispatch_authorized": route["dispatch_authorized"],
        "blocker_count": len(route.get("blockers", [])),
        "required_verification_count": len(route.get("required_verification", [])),
        "state_schema": state.get("schema", ""),
        "state_verdict": state.get("verdict", ""),
        "state_dispatch_authorized": state.get("dispatch_authorized") if state else False,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def build_matrix(*, root: Path = ROOT) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-router-transition-") as tmp:
        work = Path(tmp)
        cases = [
            case_summary(case_id="trivial_to_fast", brief="Build a tiny README note.", work=work),
            case_summary(
                case_id="moderate_remote_worker_to_quick",
                brief=(
                    "Fix the remote transfer cancellation bug.\n\n"
                    "Failing reproducer evidence:\n"
                    "- pytest tests/test_cancel.py::test_cancel_kills_provider fails before the fix.\n"
                ),
                labels=["remote-worker"],
                work=work,
            ),
            case_summary(
                case_id="complex_phase_to_phase",
                brief="Build complex factory orchestration for users, projects, tasks, and comments. Scope: SDD only.",
                work=work,
            ),
            case_summary(
                case_id="frontend_label_promotes_to_moderate",
                brief="Build frontend operator cockpit polish. Scope: UI only.",
                labels=["frontend"],
                work=work,
            ),
            case_summary(
                case_id="security_label_promotes_to_moderate",
                brief="Build a security-sensitive approval audit check. Scope: no-provider validation.",
                labels=["security-sensitive"],
                work=work,
            ),
            case_summary(
                case_id="live_provider_blocks_dispatch",
                brief=(
                    "Run the approved live provider proof. Shape: greenfield.\n\n"
                    "Outcome: bounded live execution evidence.\n"
                    "Scope: one approved Agent OS RunSpec only.\n"
                ),
                labels=["live-provider"],
                work=work,
            ),
            case_summary(case_id="unknown_label_ignored", brief="Build a tiny README note.", labels=["unknown"], work=work),
            case_summary(case_id="bug_fix_without_reproducer_fails_shape_gate", brief="Fix broken cancellation. Shape: bug-fix.", work=work),
            case_summary(
                case_id="refactor_with_release_state_v2",
                brief="Refactor router internals.\n\nPinning suite: pytest tests/test_agent_os_router.py\n",
                labels=["release"],
                state_v2=True,
                work=work,
            ),
        ]

    errors: list[str] = []
    by_id = {case["id"]: case for case in cases}
    expected = {
        "trivial_to_fast": ("TRIVIAL", ["fast"], True),
        "moderate_remote_worker_to_quick": ("MODERATE", ["quick", "remote-worker"], True),
        "complex_phase_to_phase": ("COMPLEX", ["phase"], True),
        "frontend_label_promotes_to_moderate": ("MODERATE", ["quick", "frontend"], True),
        "security_label_promotes_to_moderate": ("MODERATE", ["quick", "security-sensitive"], True),
        "live_provider_blocks_dispatch": ("TRIVIAL", ["live-provider"], False),
        "unknown_label_ignored": ("TRIVIAL", ["fast"], True),
        "bug_fix_without_reproducer_fails_shape_gate": ("TRIVIAL", ["fast"], False),
        "refactor_with_release_state_v2": ("MODERATE", ["quick", "release"], True),
    }
    for case_id, (classification, routes, route_dispatch) in expected.items():
        case = by_id[case_id]
        if case["classification"] != classification:
            errors.append(f"{case_id} classification must be {classification}")
        if case["routes"] != routes:
            errors.append(f"{case_id} routes must be {routes}")
        if case["route_dispatch_authorized"] is not route_dispatch:
            errors.append(f"{case_id} route dispatch_authorized must be {route_dispatch}")
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case_id} matrix case must keep top-level dispatch/live flags false")
    if by_id["live_provider_blocks_dispatch"]["blocker_count"] < 1:
        errors.append("live_provider_blocks_dispatch must keep an approval blocker")
    if by_id["bug_fix_without_reproducer_fails_shape_gate"]["blocker_count"] < 1:
        errors.append("bug_fix_without_reproducer_fails_shape_gate must keep a shape-gate blocker")
    if by_id["refactor_with_release_state_v2"]["state_schema"] != agent_os_router.STATE_SCHEMA_V2:
        errors.append("refactor_with_release_state_v2 must emit state v2")
    if by_id["refactor_with_release_state_v2"]["state_verdict"] != "PASS":
        errors.append("refactor_with_release_state_v2 state v2 must pass")

    return {
        "schema": "ao-operator/agent-os-router-transition-matrix/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Router transition matrix passes; continue Agent OS architecture changes behind no-provider gates."
            if not errors
            else "Fix Agent OS router transition regressions before architecture changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS router transition matrix")
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
