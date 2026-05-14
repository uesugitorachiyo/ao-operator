#!/usr/bin/env python3
"""Append and summarize Agent OS approval audit events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_SOURCE_REPORT = f"{STATUS_ROOT}/agent-os-approval-cleanup.json"
DEFAULT_AUDIT_LOG = f"{STATUS_ROOT}/agent-os-approval-audit.jsonl"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-audit.json"
EVENT_SCHEMA = "ao-operator/agent-os-approval-audit-event/v1"
SUMMARY_SCHEMA = "ao-operator/agent-os-approval-audit-history/v1"


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def event_name(payload: dict[str, Any]) -> str:
    schema = payload.get("schema")
    if schema == "ao-operator/agent-os-approval-materialization/v1":
        return "APPROVAL_MATERIALIZED" if payload.get("approval_file_written") is True else "APPROVAL_MATERIALIZATION_RECORDED"
    if schema == "ao-operator/agent-os-approval-cleanup/v1":
        return "APPROVAL_CLEANUP_APPLIED" if payload.get("removed") is True else "APPROVAL_CLEANUP_RECORDED"
    if schema == "ao-operator/agent-os-approved-launch-proof/v1":
        return "APPROVED_LAUNCH_PROOF_RECORDED"
    return "APPROVAL_REPORT_RECORDED"


def build_event(*, root: Path = ROOT, source_report: str | Path = DEFAULT_SOURCE_REPORT) -> dict[str, Any]:
    root = root.resolve()
    report_path = resolve_path(root, source_report)
    payload = load_json(report_path)
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "event": event_name(payload),
        "source_report": relpath(root, report_path),
        "source_schema": payload.get("schema", ""),
        "source_verdict": payload.get("verdict", "MISSING"),
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    for key in (
        "approval_file",
        "approval_file_written",
        "approval_valid",
        "approval_state",
        "approval_usable",
        "removed",
        "mode",
        "positive_approval_path",
    ):
        if key in payload:
            event[key] = payload[key]
    return event


def append_event(path: Path, event: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return path


def read_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return events, errors
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"audit line {idx} must be valid JSON")
            continue
        if not isinstance(data, dict):
            errors.append(f"audit line {idx} must be a JSON object")
            continue
        events.append(data)
    return events, errors


def event_errors(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for idx, event in enumerate(events, start=1):
        if event.get("schema") != EVENT_SCHEMA:
            errors.append(f"audit event {idx} schema must be {EVENT_SCHEMA}")
        if not str(event.get("event") or "").strip():
            errors.append(f"audit event {idx} event is required")
        if event.get("source_verdict") != "PASS":
            errors.append(f"audit event {idx} source_verdict must be PASS")
        if event.get("dispatch_authorized") is not False:
            errors.append(f"audit event {idx} dispatch_authorized must remain false")
        if event.get("live_providers_run") is not False:
            errors.append(f"audit event {idx} live_providers_run must remain false")
    return errors


def summarize(*, root: Path = ROOT, audit_log: str | Path = DEFAULT_AUDIT_LOG) -> dict[str, Any]:
    root = root.resolve()
    audit_path = resolve_path(root, audit_log)
    events, errors = read_events(audit_path)
    errors.extend(event_errors(events))
    latest = events[-1] if events else {}
    event_types = sorted({str(event.get("event")) for event in events if event.get("event")})
    return {
        "schema": SUMMARY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "audit_log": relpath(root, audit_path),
        "audit_log_present": audit_path.is_file(),
        "event_count": len(events),
        "event_types": event_types,
        "latest_event": latest.get("event", ""),
        "latest_source_report": latest.get("source_report", ""),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval audit history passes; continue with approval cleanup or the next gated SDD lane."
            if not errors
            else "Fix approval audit history before relying on approval evidence."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append and summarize Agent OS approval audit history")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-report", default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--audit-log", default=DEFAULT_AUDIT_LOG)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    audit_path = resolve_path(root, args.audit_log)
    if args.append:
        append_event(audit_path, build_event(root=root, source_report=args.source_report))
    payload = summarize(root=root, audit_log=audit_path)
    if args.write_output is not None:
        output = resolve_path(root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
