#!/usr/bin/env python3
"""Normalize AO events and Factory role STATUS blocks.

Factory's deterministic runner uses this module to translate AO event text into
stable evidence fields. It intentionally does not decide whether a run is
accepted; closure remains in the runner/gate layer.
"""

from __future__ import annotations

import json
import re

import summarize_ao_failure


STATUS_RE = re.compile(r"\*{0,2}Result:\*{0,2}\s*[A-Z_]+")


def event_summary(text: str) -> dict[str, object]:
    lines = text.splitlines()
    completed = [line for line in lines if "task.completed" in line]
    failed = [line for line in lines if "task.failed" in line]
    decisions = [line for line in lines if "policy." in line or "decision" in line.lower()]
    stdout_count = sum(1 for line in lines if "agent.stdout" in line or "stream.stdout" in line)
    stderr_count = sum(1 for line in lines if "agent.stderr" in line or "stream.stderr" in line)
    normalized_counts: dict[str, int] = {}
    normalized_order: list[str] = []
    for line in lines:
        if "task.failed" not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or str(event.get("kind") or "") != "task.failed":
            continue
        record = summarize_ao_failure.failure_record(event)
        reason = str(record.get("normalized_reason") or "unknown")
        if reason not in normalized_counts:
            normalized_order.append(reason)
        normalized_counts[reason] = normalized_counts.get(reason, 0) + 1
    normalized_counts = dict(sorted(normalized_counts.items()))
    primary_normalized_reason = ""
    if normalized_order:
        primary_normalized_reason = max(
            normalized_order,
            key=lambda reason: normalized_counts.get(reason, 0),
        )
    return {
        "task_completed": len(completed),
        "task_failed": len(failed),
        "policy_decisions": len(decisions),
        "stdout_events": stdout_count,
        "stderr_events": stderr_count,
        "lines": len(lines),
        "normalized_reason_counts": normalized_counts,
        "primary_normalized_reason": primary_normalized_reason,
    }


def failure_diagnostics_evidence(event_text: str) -> list[str]:
    summary = event_summary(event_text)
    counts = summary.get("normalized_reason_counts")
    if not isinstance(counts, dict) or not counts:
        return []
    return [
        "AO normalized failure reasons=" + json.dumps(counts, sort_keys=True),
        f"AO primary normalized failure reason={summary.get('primary_normalized_reason', '')}",
    ]


def task_seen(event_text: str, task_id: str) -> bool:
    return task_id in event_text and "task.completed" in event_text


def status_block(text: str) -> str:
    match = STATUS_RE.search(text)
    if not match:
        return ""
    block = text[match.start() :].strip()
    blocker = re.search(r"(?m)^\*{0,2}Blocker:\*{0,2}.*$", block)
    if blocker:
        return block[: blocker.end()].strip()
    return block


def status_from_event_object(value: object) -> str:
    if isinstance(value, list):
        for item in reversed(value):
            found = status_from_event_object(item)
            if found:
                return found
        return ""
    if not isinstance(value, dict):
        if isinstance(value, str):
            return status_block(value)
        return ""

    for key in ("result", "text"):
        raw = value.get(key)
        if isinstance(raw, str):
            found = status_block(raw)
            if found:
                return found

    line = value.get("line")
    if isinstance(line, str):
        try:
            found = status_from_event_object(json.loads(line))
        except json.JSONDecodeError:
            found = status_block(line)
        if found:
            return found

    item = value.get("item")
    if isinstance(item, dict):
        found = status_from_event_object(item)
        if found:
            return found

    message = value.get("message")
    if isinstance(message, dict):
        found = status_from_event_object(message)
        if found:
            return found

    content = value.get("content")
    if isinstance(content, list):
        for part in reversed(content):
            if isinstance(part, dict) and part.get("type") == "thinking":
                continue
            found = status_from_event_object(part)
            if found:
                return found
    return ""


def extract_agent_status(event_text: str, task_id: str) -> str:
    for line in event_text.splitlines():
        if f"task={task_id}" not in line or ("agent.stdout" not in line and "stream.stdout" not in line):
            continue
        start = line.find("{")
        if start == -1:
            continue
        try:
            payload = json.loads(line[start:])
        except (json.JSONDecodeError, AttributeError):
            continue
        found = status_from_event_object(payload)
        if found:
            return found
    return ""


def extract_task_events(event_text: str, task_id: str) -> str:
    lines = [line for line in event_text.splitlines() if f"task={task_id}" in line]
    return "\n".join(lines)


def result_from_status(status_text: str, fallback_completed: bool) -> str:
    match = re.search(r"\*{0,2}Result:\*{0,2}\s*([A-Z_]+)", status_text)
    if match:
        return match.group(1)
    return "DONE_WITH_CONCERNS" if fallback_completed else "BLOCKED"
