#!/usr/bin/env python3
"""Validate Agent OS approval audit retention and rotation posture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_LOG = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit.jsonl"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit-retention.json"
SCHEMA = "ao-operator/agent-os-approval-audit-retention/v1"
EVENT_SCHEMA = "ao-operator/agent-os-approval-audit-event/v1"


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


def read_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        errors.append("approval audit log is missing")
        return events, errors
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"audit event {idx} must be valid JSON")
            continue
        if not isinstance(event, dict):
            errors.append(f"audit event {idx} must be a JSON object")
            continue
        events.append(event)
    return events, errors


def validate_events(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for idx, event in enumerate(events, start=1):
        if event.get("schema") != EVENT_SCHEMA:
            errors.append(f"audit event {idx} schema must be {EVENT_SCHEMA}")
        if event.get("source_verdict") != "PASS":
            errors.append(f"audit event {idx} source_verdict must be PASS")
        if event.get("dispatch_authorized") is not False:
            errors.append(f"audit event {idx} dispatch_authorized must remain false")
        if event.get("live_providers_run") is not False:
            errors.append(f"audit event {idx} live_providers_run must remain false")
        if "approval" in event:
            errors.append(f"audit event {idx} must not include nested approval payload")
        if "accepted_risk" in event:
            errors.append(f"audit event {idx} must not include accepted_risk")
    return errors


def check_retention(
    *,
    root: Path = ROOT,
    audit_log: str | Path = DEFAULT_AUDIT_LOG,
    max_events: int = 500,
    max_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    root = root.resolve()
    audit_path = resolve_path(root, audit_log)
    events, errors = read_events(audit_path)
    errors.extend(validate_events(events))
    size_bytes = audit_path.stat().st_size if audit_path.is_file() else 0
    rotation_reasons: list[str] = []
    if len(events) > max_events:
        rotation_reasons.append("event_count exceeds max_events")
    if size_bytes > max_bytes:
        rotation_reasons.append("audit_log_bytes exceeds max_bytes")
    rotation_due = bool(rotation_reasons)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "audit_log": relpath(root, audit_path),
        "audit_log_present": audit_path.is_file(),
        "event_count": len(events),
        "audit_log_bytes": size_bytes,
        "retention_policy": {
            "max_events": max_events,
            "max_bytes": max_bytes,
            "rotation_mode": "manual-archive-before-truncate",
            "payload_policy": "compact-events-only",
        },
        "rotation_due": rotation_due,
        "rotation_reasons": rotation_reasons,
        "archive_target_hint": f"{relpath(root, audit_path)}.archive-YYYYMMDD",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Fix approval audit retention blockers before relying on audit history."
            if errors
            else (
                "Rotate approval audit log with archive-before-truncate policy."
                if rotation_due
                else "Approval audit retention passes; continue with the next gated SDD lane."
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS approval audit retention policy")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--audit-log", default=DEFAULT_AUDIT_LOG)
    parser.add_argument("--max-events", type=int, default=500)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_retention(
        root=args.root,
        audit_log=args.audit_log,
        max_events=args.max_events,
        max_bytes=args.max_bytes,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
