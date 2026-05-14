#!/usr/bin/env python3
"""Preserve sanitized Agent OS RunSpec execution diagnostics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import summarize_ao_failure


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTE_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json"
DEFAULT_AO_HOME = "/tmp/ao-operator-ao-agent-os-phase-draft"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-diagnostics-preservation.json"


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def redact_ao_home(value: object, ao_home: str) -> object:
    if isinstance(value, str):
        return value.replace(ao_home, "/tmp/[REDACTED_AO_HOME]")
    if isinstance(value, list):
        return [redact_ao_home(item, ao_home) for item in value]
    if isinstance(value, dict):
        return {key: redact_ao_home(item, ao_home) for key, item in value.items()}
    return value


def summary_path(root: Path, timestamp: str) -> Path:
    return root / "run-artifacts/remote-transfer-v2-stress-live/failure-snapshots" / f"agent-os-ao-home-{timestamp}-summary.json"


def preserve(
    *,
    root: Path = ROOT,
    route_report: str | Path = DEFAULT_ROUTE_REPORT,
    ao_home: str | Path = DEFAULT_AO_HOME,
    execute: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    route_path = resolve_path(root, route_report)
    route = load_json(route_path)
    errors: list[str] = []
    if route.get("schema") != "ao-operator/agent-os-runspec-postrun-route/v1":
        errors.append("route schema must be ao-operator/agent-os-runspec-postrun-route/v1")
    if route.get("verdict") != "PASS":
        errors.append("route verdict must be PASS before diagnostics preservation")
    diagnostics_required = route.get("diagnostics_required") is True
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = timestamp or generated_at.strftime("%Y%m%d-%H%M%S")
    ao_home_path = Path(ao_home)
    summary_written = False
    summary_output: str | None = None
    summary_payload: dict[str, Any] | None = None
    primary_reason = ""
    reason_counts: dict[str, object] = {}

    if errors:
        verdict = "FAIL"
        next_actions = ["Fix postrun route before preserving diagnostics."]
    elif not diagnostics_required:
        verdict = "PASS"
        next_actions = ["No Agent OS execution diagnostics are required for the current route."]
    elif not execute:
        verdict = "BLOCKED"
        next_actions = ["Rerun with --execute after confirming diagnostic preservation is needed."]
    else:
        try:
            events = summarize_ao_failure.latest_events_path(ao_home_path)
            summary = summarize_ao_failure.summarize_events(events, first_failed=3)
        except (FileNotFoundError, OSError) as exc:
            verdict = "FAIL"
            errors.append(f"AO failure events unavailable: {exc}")
            next_actions = ["Recover AO events before preserving diagnostics."]
        else:
            summary_payload = redact_ao_home(summary, str(ao_home_path))
            if isinstance(summary_payload, dict):
                primary_reason = str(summary_payload.get("primary_normalized_reason") or "")
                counts = summary_payload.get("normalized_reason_counts")
                if isinstance(counts, dict):
                    reason_counts = counts
            output = summary_path(root, stamp)
            write_json(output, summary_payload if isinstance(summary_payload, dict) else {})
            summary_written = True
            summary_output = relpath(root, output)
            verdict = "PASS"
            next_actions = ["Review sanitized Agent OS diagnostics before rerun."]

    return {
        "schema": "ao-operator/agent-os-runspec-diagnostics-preservation/v1",
        "generated_at": generated_at.isoformat(),
        "verdict": verdict,
        "route_report": relpath(root, route_path),
        "route": route.get("route", ""),
        "diagnostics_required": diagnostics_required,
        "execute": execute,
        "summary_written": summary_written,
        "summary": summary_output,
        "summary_payload": summary_payload,
        "primary_normalized_reason": primary_reason,
        "normalized_reason_counts": reason_counts,
        "raw_snapshot_commit_allowed": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "ao_home": "/tmp/[REDACTED_AO_HOME]",
        "errors": errors,
        "next_actions": next_actions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preserve Agent OS RunSpec diagnostics")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--route-report", default=DEFAULT_ROUTE_REPORT)
    parser.add_argument("--ao-home", default=DEFAULT_AO_HOME)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = preserve(root=args.root, route_report=args.route_report, ao_home=args.ao_home, execute=args.execute, timestamp=args.timestamp)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    if payload["verdict"] == "PASS":
        return 0
    if payload["verdict"] == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
