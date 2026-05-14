#!/usr/bin/env python3
"""Build a provider-free Agent OS failed diagnostics preservation fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import preserve_agent_os_runspec_diagnostics


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = "run-artifacts/remote-transfer-v2-stress-live/failed-diagnostics-fixture"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-failed-diagnostics-fixture.json"
SUMMARY_TIMESTAMP = "20260507-000000"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def route_report(root: Path, fixture_root: Path) -> Path:
    return write_json(
        fixture_root / "postrun-route.json",
        {
            "schema": "ao-operator/agent-os-runspec-postrun-route/v1",
            "verdict": "PASS",
            "route": "DIAGNOSTIC_REQUIRED",
            "diagnostics_required": True,
            "commit_success_evidence_allowed": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def ao_events(fixture_root: Path) -> Path:
    events = fixture_root / "ao-home" / "runs" / "r-failed-diagnostics-fixture" / "events.jsonl"
    body = (
        json.dumps(
            {
                "kind": "task.started",
                "task_id": "agent-os-fixture",
            },
            sort_keys=True,
        )
        + "\n"
        + json.dumps(
            {
                "kind": "task.failed",
                "task_id": "agent-os-fixture",
                "error": "429 Too Many Requests",
                "stderr": "exceeded retry limit after provider returned 429",
            },
            sort_keys=True,
        )
        + "\n"
    )
    return write_text(events, body)


def build_fixture(
    *,
    root: Path = ROOT,
    fixture_dir: str | Path = FIXTURE_DIR,
) -> dict[str, Any]:
    fixture_root = resolve_path(root, fixture_dir)
    route = route_report(root, fixture_root)
    events = ao_events(fixture_root)
    preservation = preserve_agent_os_runspec_diagnostics.preserve(
        root=root,
        route_report=route,
        ao_home=events.parents[2],
        execute=True,
        timestamp=SUMMARY_TIMESTAMP,
    )
    preservation_path = write_json(fixture_root / "diagnostics-preservation.json", preservation)
    errors: list[str] = []
    if preservation.get("verdict") != "PASS":
        errors.append("diagnostics preservation fixture must pass")
    if preservation.get("summary_written") is not True:
        errors.append("diagnostics preservation fixture must write a summary")
    if preservation.get("raw_snapshot_commit_allowed") is not False:
        errors.append("raw snapshot commit must stay blocked")
    if preservation.get("primary_normalized_reason") != "provider-rate-limit":
        errors.append("fixture must preserve provider-rate-limit as primary reason")

    return {
        "schema": "ao-operator/agent-os-failed-diagnostics-fixture/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture_only": True,
        "route": preservation.get("route", ""),
        "preservation_verdict": preservation.get("verdict", ""),
        "summary": preservation.get("summary", ""),
        "primary_normalized_reason": preservation.get("primary_normalized_reason", ""),
        "normalized_reason_counts": preservation.get("normalized_reason_counts", {}),
        "raw_snapshot_commit_allowed": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "artifacts": {
            "route": relpath(root, route),
            "events": relpath(root, events),
            "preservation": relpath(root, preservation_path),
        },
        "next_safe_command": (
            "Use failed diagnostics fixture as a provider-free preservation baseline only."
            if not errors
            else "Fix failed diagnostics fixture before relying on diagnostics preservation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check provider-free Agent OS failed diagnostics fixture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-dir", default=FIXTURE_DIR)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_fixture(root=args.root, fixture_dir=args.fixture_dir)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
