#!/usr/bin/env python3
"""Exercise Agent OS router v1/v2 state migration compatibility cases."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_router
import agent_os_state_v2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-migration-matrix.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def readiness(path: Path, *, ready: bool = True) -> dict[str, Any]:
    payload = {
        "schema": "ao-operator/agent-os-architecture-readiness/v1",
        "verdict": "PASS" if ready else "FAIL",
        "architecture_ready": ready,
        "baseline_count": 5,
        "blockers": [] if ready else ["baseline missing"],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    write_json(path, payload)
    return payload


def case_summary(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    blockers = payload.get("blockers")
    errors = payload.get("errors")
    return {
        "id": case_id,
        "schema": payload.get("schema"),
        "previous_schema": payload.get("previous_schema", ""),
        "verdict": payload.get("verdict", ""),
        "dispatch_authorized": payload.get("dispatch_authorized") is True,
        "live_providers_run": payload.get("live_providers_run") is True,
        "blocker_count": len(blockers) if isinstance(blockers, list) else 0,
        "error_count": len(errors) if isinstance(errors, list) else 0,
        "route_dispatch_authorized": bool(
            isinstance(payload.get("route"), dict) and payload["route"].get("dispatch_authorized") is True
        ),
    }


def build_matrix(*, root: Path = ROOT) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-router-migration-") as tmp:
        work = Path(tmp)
        readiness_path = work / "readiness.json"
        ready = readiness(readiness_path)
        brief = "Refactor router state internals.\n\nPinning suite: pytest tests/test_agent_os_router.py\n"
        route = agent_os_router.route_brief(brief, labels=["release"])

        v1_state = write_json(work / "router-v1.json", agent_os_router.build_state_snapshot(route))
        v1_migrated = agent_os_state_v2.load_or_migrate_state(root=work, state=v1_state)

        v2_state = write_json(
            work / "router-v2.json",
            agent_os_router.build_state_snapshot_v2(
                route,
                architecture_readiness=ready,
                architecture_readiness_path=readiness_path,
                root=work,
            ),
        )
        v2_reloaded = agent_os_state_v2.load_or_migrate_state(root=work, state=v2_state)

        stale = dict(v2_reloaded)
        stale["dispatch_authorized"] = True
        stale["live_providers_run"] = True
        stale_path = write_json(work / "stale-v2.json", stale)
        stale_reloaded = agent_os_state_v2.load_or_migrate_state(root=work, state=stale_path)

        live_route = agent_os_router.route_brief(
            "Run a live provider proof. Shape: greenfield.\n\n"
            "Outcome: record a bounded live provider proof.\n"
            "Scope: one approved Agent OS RunSpec only.\n"
            "Acceptance: explicit approval, provider budget, and evaluator closure all pass.\n",
            labels=["live-provider"],
        )
        live_path = write_json(work / "live-route-v1.json", agent_os_router.build_state_snapshot(live_route))
        live_migrated = agent_os_state_v2.load_or_migrate_state(root=work, state=live_path)

        invalid_path = write_json(work / "invalid.json", {"schema": "ao-operator/unknown"})
        invalid = agent_os_state_v2.load_or_migrate_state(root=work, state=invalid_path)

        missing_readiness = agent_os_router.build_state_snapshot_v2(
            route,
            architecture_readiness={},
            architecture_readiness_path=work / "missing-readiness.json",
            root=work,
        )

    cases = [
        case_summary("router_v1_to_state_v2", v1_migrated),
        case_summary("router_v2_reload", v2_reloaded),
        case_summary("stale_v2_flags_reset", stale_reloaded),
        case_summary("live_provider_blocker_preserved", live_migrated),
        case_summary("invalid_schema_fails", invalid),
        case_summary("missing_architecture_readiness_fails_closed", missing_readiness),
    ]
    by_id = {case["id"]: case for case in cases}
    errors: list[str] = []
    for case_id in ["router_v1_to_state_v2", "router_v2_reload", "stale_v2_flags_reset", "live_provider_blocker_preserved"]:
        if by_id[case_id]["verdict"] != "PASS":
            errors.append(f"{case_id} must pass")
    for case_id in ["invalid_schema_fails", "missing_architecture_readiness_fails_closed"]:
        if by_id[case_id]["verdict"] != "FAIL":
            errors.append(f"{case_id} must fail closed")
    for case in cases:
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case['id']} must keep top-level dispatch/live flags false")
    if by_id["router_v1_to_state_v2"]["previous_schema"] != agent_os_state_v2.STATE_SCHEMA_V1:
        errors.append("router_v1_to_state_v2 must record previous_schema v1")
    if by_id["router_v2_reload"]["previous_schema"] != agent_os_state_v2.STATE_SCHEMA_V2:
        errors.append("router_v2_reload must record previous_schema v2")
    if by_id["live_provider_blocker_preserved"]["blocker_count"] < 1:
        errors.append("live_provider_blocker_preserved must keep live-provider blocker")

    return {
        "schema": "ao-operator/agent-os-router-migration-matrix/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Router migration matrix passes; continue Agent OS architecture changes behind state v2."
            if not errors
            else "Fix Agent OS router migration regressions before architecture changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS router v1-to-v2 migration matrix")
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
