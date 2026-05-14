from __future__ import annotations

import json
import subprocess

import factory_run


def failure_event_text() -> str:
    return "\n".join(
        json.dumps(event)
        for event in [
            {"kind": "task.started", "taskId": "slice-1"},
            {
                "kind": "task.failed",
                "taskId": "slice-1",
                "payload": {
                    "stderr": "exceeded retry limit, last status: 429 Too Many Requests",
                },
            },
            {
                "kind": "task.failed",
                "taskId": "slice-2",
                "payload": {
                    "error": "login required: not logged in",
                },
            },
        ]
    )


def test_event_summary_surfaces_normalized_failure_reasons():
    summary = factory_run.event_summary(failure_event_text())

    assert summary["task_failed"] == 2
    assert summary["normalized_reason_counts"] == {
        "provider-auth-missing": 1,
        "provider-rate-limit": 1,
    }
    assert summary["primary_normalized_reason"] == "provider-rate-limit"


def test_write_events_includes_normalized_failure_summary(tmp_path):
    events = tmp_path / "status" / "slug-ao-events.md"
    run_result = subprocess.CompletedProcess(["ao", "run"], 1, "run r-test", "")
    events_result = subprocess.CompletedProcess(["ao", "run", "r-test", "events"], 0, failure_event_text(), "")

    factory_run.write_events(events, "r-test", run_result, events_result)

    body = events.read_text(encoding="utf-8")
    assert 'Normalized reason counts: {"provider-auth-missing": 1, "provider-rate-limit": 1}' in body
    assert "Primary normalized reason: provider-rate-limit" in body


def test_failure_diagnostics_evidence_reaches_evaluator_output():
    evidence = factory_run.failure_diagnostics_evidence(failure_event_text())

    assert evidence == [
        'AO normalized failure reasons={"provider-auth-missing": 1, "provider-rate-limit": 1}',
        "AO primary normalized failure reason=provider-rate-limit",
    ]
