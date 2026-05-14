#!/usr/bin/env python3
"""Check Factory AO normalized failure diagnostics reach summaries and evaluation evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import factory_run


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/normalized-failure-diagnostics/v1"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/normalized-failure-diagnostics.json"


def event_text() -> str:
    events = [
        {"kind": "task.started", "taskId": "provider-rate"},
        {
            "kind": "task.failed",
            "taskId": "provider-rate",
            "payload": {"stderr": "exceeded retry limit, last status: 429 Too Many Requests"},
        },
        {
            "kind": "task.failed",
            "taskId": "provider-auth",
            "payload": {"error": "login required: not logged in"},
        },
    ]
    return "\n".join(json.dumps(event) for event in events)


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def check(*, root: Path = ROOT) -> dict[str, Any]:
    text = event_text()
    summary = factory_run.event_summary(text)
    evidence = factory_run.failure_diagnostics_evidence(text)
    errors: list[str] = []

    expected_counts = {
        "provider-auth-missing": 1,
        "provider-rate-limit": 1,
    }
    if summary.get("normalized_reason_counts") != expected_counts:
        errors.append("event summary normalized reason counts are incorrect")
    if summary.get("primary_normalized_reason") != "provider-rate-limit":
        errors.append("event summary primary normalized reason is incorrect")
    if evidence != [
        'AO normalized failure reasons={"provider-auth-missing": 1, "provider-rate-limit": 1}',
        "AO primary normalized failure reason=provider-rate-limit",
    ]:
        errors.append("evaluator evidence omits normalized failure reasons")

    with tempfile.TemporaryDirectory(prefix="ao-operator-normalized-failure-diagnostics-") as tmp:
        work = Path(tmp)
        events_path = work / "run-artifacts/fixture/fixture-ao-events.md"
        run_result = subprocess.CompletedProcess(["ao", "run"], 1, "run r-fixture", "")
        events_result = subprocess.CompletedProcess(["ao", "run", "r-fixture", "events"], 0, text, "")
        factory_run.write_events(events_path, "r-fixture", run_result, events_result)
        event_markdown = events_path.read_text(encoding="utf-8")

    if 'Normalized reason counts: {"provider-auth-missing": 1, "provider-rate-limit": 1}' not in event_markdown:
        errors.append("AO event markdown omits normalized reason counts")
    if "Primary normalized reason: provider-rate-limit" not in event_markdown:
        errors.append("AO event markdown omits primary normalized reason")

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "repo": "${FACTORY_V3_ROOT}",
        "normalized_reason_counts": summary.get("normalized_reason_counts", {}),
        "primary_normalized_reason": summary.get("primary_normalized_reason", ""),
        "evaluator_evidence": evidence,
        "event_markdown_checked": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Normalized failure diagnostics are wired into Factory summaries and evaluator evidence."
            if not errors
            else "Fix normalized failure diagnostics before relying on failed-run summaries."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Factory normalized failure diagnostics")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = relpath(args.root, output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
