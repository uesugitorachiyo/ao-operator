#!/usr/bin/env python3
"""Summarize AO failure evidence from a local AO home."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any


def latest_events_path(ao_home: Path) -> Path:
    candidates = list((ao_home / "runs").glob("r-*/events.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"no AO events.jsonl files found under {ao_home / 'runs'}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def compact(value: object, max_chars: int = 300) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def normalize_failure_reason(*values: object) -> str:
    text = " ".join(str(value) for value in values if value is not None).lower()
    if not text.strip():
        return "unknown"
    if "api key" in text and ("oauth" in text or "forbidden" in text or "boundary" in text):
        return "provider-api-key-boundary"
    if "429" in text or "too many requests" in text or "rate limit" in text or "retry limit" in text:
        return "provider-rate-limit"
    if "login required" in text or "not logged in" in text or "auth" in text or "oauth" in text:
        return "provider-auth-missing"
    if "timeout" in text or "timed out" in text or "exit code 124" in text:
        return "provider-timeout"
    if "network" in text or "connection reset" in text or "connection refused" in text or "dns" in text:
        return "provider-network"
    if "outside workspace" in text or "path traversal" in text or "absolute path" in text:
        return "workspace-path-boundary"
    if "sandbox" in text or "permission denied" in text or "operation not permitted" in text:
        return "provider-sandbox"
    return "unknown"


def failure_record(event: dict[str, Any]) -> dict[str, object]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    fields = event.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    explicit_reason = (
        event.get("normalized_reason")
        or payload.get("normalized_reason")
        or fields.get("normalized_reason")
    )
    error = event.get("error") or payload.get("error") or fields.get("error")
    stderr = event.get("stderr") or payload.get("stderr") or fields.get("stderr")
    stdout = event.get("stdout") or payload.get("stdout") or fields.get("stdout")
    exit_code = event.get("exit_code") or payload.get("exit_code") or fields.get("exit_code")
    normalized_reason = explicit_reason or normalize_failure_reason(error, stderr, stdout, exit_code)
    return {
        "task_id": (
            event.get("taskId")
            or event.get("task_id")
            or payload.get("taskId")
            or payload.get("task_id")
            or fields.get("taskId")
            or fields.get("task_id")
        ),
        "normalized_reason": normalized_reason,
        "exit_code": exit_code,
        "error": compact(error),
        "stderr": compact(stderr),
        "stdout": compact(stdout),
    }


def summarize_events(path: Path, *, first_failed: int) -> dict[str, object]:
    counts: collections.Counter[str] = collections.Counter()
    normalized_reasons: collections.Counter[str] = collections.Counter()
    failures: list[dict[str, object]] = []
    malformed = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        kind = str(event.get("kind") or "unknown")
        counts[kind] += 1
        if kind == "task.failed":
            record = failure_record(event)
            reason = str(record.get("normalized_reason") or "unknown")
            normalized_reasons[reason] += 1
            if len(failures) < first_failed:
                failures.append(record)
    return {
        "events": str(path),
        "counts": dict(counts),
        "normalized_reason_counts": dict(sorted(normalized_reasons.items())),
        "primary_normalized_reason": normalized_reasons.most_common(1)[0][0] if normalized_reasons else "",
        "malformed_lines": malformed,
        "first_failed": failures,
    }


def text_summary(summary: dict[str, object]) -> str:
    counts = summary["counts"]
    if not isinstance(counts, dict):
        counts = {}
    lines = [
        f"events={summary['events']}",
        f"counts={json.dumps(counts, sort_keys=True)}",
        f"normalized_reason_counts={json.dumps(summary.get('normalized_reason_counts', {}), sort_keys=True)}",
        f"primary_normalized_reason={summary.get('primary_normalized_reason', '')}",
        f"malformed_lines={summary['malformed_lines']}",
        "first_failed=" + json.dumps(summary["first_failed"], sort_keys=True),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize the latest AO events.jsonl failure evidence")
    parser.add_argument("ao_home", type=Path, help="AO home directory containing runs/r-*/events.jsonl")
    parser.add_argument("--first-failed", type=int, default=3, help="Number of task.failed samples to include")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        events = latest_events_path(args.ao_home)
        summary = summarize_events(events, first_failed=max(0, args.first_failed))
    except (FileNotFoundError, OSError) as exc:
        print(f"summarize_ao_failure.py: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(text_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
