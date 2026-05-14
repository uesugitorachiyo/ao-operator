#!/usr/bin/env python3
"""Agent OS mission router and state snapshot foundation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import factory_run


VALID_LABELS = {
    "fast",
    "quick",
    "phase",
    "live-provider",
    "remote-worker",
    "security-sensitive",
    "frontend",
    "release",
}
PROJECT_ARTIFACTS = [
    "PROJECT.md",
    "REQUIREMENTS.md",
    "ROADMAP.md",
    "STATE.md",
    "DECISIONS.md",
    "LEARNINGS.md",
]
STATE_SCHEMA_V1 = "ao-operator/agent-os-state/v1"
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"
ROLE_GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
ARCHITECTURE_READINESS_SCHEMA = "ao-operator/agent-os-architecture-readiness/v1"
DEFAULT_ARCHITECTURE_READINESS = "run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def default_route(classification: str) -> str:
    if classification == "TRIVIAL":
        return "fast"
    if classification == "MODERATE":
        return "quick"
    return "phase"


def infer_required_verification(shape: str, routes: list[str]) -> list[str]:
    checks = ["python3 scripts/validate.py", "python3 -m pytest -q"]
    if shape == "bug-fix":
        checks.append("failing reproducer or red-to-green evidence")
    if shape == "refactor":
        checks.append("pinning suite or preservation evidence")
    if "live-provider" in routes:
        checks.append("explicit approval artifact and provider budget evidence")
    if "remote-worker" in routes:
        checks.append("Mac-to-Ubuntu transfer or RuntimeService smoke evidence")
    if "release" in routes:
        checks.append("python3 scripts/check_release_readiness.py --json")
    return checks


def route_brief(brief: str, *, labels: list[str] | None = None) -> dict[str, Any]:
    requested = [label for label in labels or [] if label in VALID_LABELS]
    classification, shape = factory_run.classify(brief)
    if classification == "TRIVIAL" and any(
        label in requested for label in ["remote-worker", "security-sensitive", "frontend", "release"]
    ):
        classification = "MODERATE"
    gate_blocked, gate_message = factory_run.shape_gate(shape, brief)
    routes = _dedupe(requested if "live-provider" in requested else [default_route(classification), *requested])
    blockers: list[str] = []
    if gate_blocked:
        blockers.append(gate_message)
    if "live-provider" in routes:
        blockers.append("live-provider route requires explicit approval")
    dispatch_authorized = not blockers
    return {
        "schema": "ao-operator/agent-os-route/v1",
        "classification": classification,
        "shape": shape,
        "routes": routes,
        "shape_gate": gate_message,
        "blockers": blockers,
        "dispatch_authorized": dispatch_authorized,
        "live_providers_run": False,
        "required_verification": infer_required_verification(shape, routes),
        "next_safe_command": (
            "Create explicit approval and provider-budget evidence before live dispatch."
            if "live-provider" in routes and blockers
            else "Record route in STATE.md and compile the next implementation phase."
            if dispatch_authorized
            else "Fix route blockers before AO dispatch."
        ),
    }


def build_state_snapshot(route: dict[str, Any], *, lane: str = "agent-os-mission-router-state") -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA_V1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lane": lane,
        "route": route,
        "project_artifacts": PROJECT_ARTIFACTS,
        "dispatch_authorized": route.get("dispatch_authorized") is True,
        "live_providers_run": False,
        "blockers": route.get("blockers", []),
        "next_safe_command": route.get("next_safe_command", ""),
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def build_state_snapshot_v2(
    route: dict[str, Any],
    *,
    architecture_readiness: dict[str, Any],
    architecture_readiness_path: Path,
    root: Path,
    lane: str = "agent-os-mission-router-state",
) -> dict[str, Any]:
    blockers = list(route.get("blockers", [])) if isinstance(route.get("blockers"), list) else []
    readiness_blockers = architecture_readiness.get("blockers")
    if architecture_readiness.get("schema") != ARCHITECTURE_READINESS_SCHEMA:
        blockers.append(f"architecture readiness schema must be {ARCHITECTURE_READINESS_SCHEMA}")
    if architecture_readiness.get("verdict") != "PASS" or architecture_readiness.get("architecture_ready") is not True:
        blockers.append("architecture readiness must be PASS")
    if architecture_readiness.get("dispatch_authorized") is not False:
        blockers.append("architecture readiness dispatch_authorized must remain false")
    if architecture_readiness.get("live_providers_run") is not False:
        blockers.append("architecture readiness live_providers_run must remain false")
    if isinstance(readiness_blockers, list):
        blockers.extend(str(item) for item in readiness_blockers if item)

    return {
        "schema": STATE_SCHEMA_V2,
        "previous_schema": STATE_SCHEMA_V1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lane": lane,
        "route": route,
        "project_artifacts": PROJECT_ARTIFACTS,
        "role_graph_schema": ROLE_GRAPH_SCHEMA,
        "architecture_readiness": relpath(root, architecture_readiness_path),
        "architecture_ready": architecture_readiness.get("architecture_ready") is True and not blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "blockers": blockers,
        "verdict": "PASS" if not blockers else "FAIL",
        "next_safe_command": (
            "Compile the next Agent OS implementation phase behind state v2 compatibility baselines."
            if not blockers
            else "Fix Agent OS router v2 blockers before AO dispatch."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a AO Operator task through the Agent OS mission router")
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--lane", default="agent-os-mission-router-state")
    parser.add_argument("--state-version", choices=["v1", "v2"], default="v2")
    parser.add_argument("--architecture-readiness", type=Path, default=Path(DEFAULT_ARCHITECTURE_READINESS))
    parser.add_argument("--write-state", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    route = route_brief(args.brief.read_text(encoding="utf-8"), labels=args.label)
    if args.state_version == "v2":
        readiness_path = args.architecture_readiness
        payload = build_state_snapshot_v2(
            route,
            architecture_readiness=load_json(readiness_path),
            architecture_readiness_path=readiness_path,
            root=Path.cwd(),
            lane=args.lane,
        )
    else:
        payload = build_state_snapshot(route, lane=args.lane)
    if args.write_state:
        write_output(args.write_state, payload)
        payload["output"] = str(args.write_state)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}")
    return 0 if not payload["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
