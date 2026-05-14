from __future__ import annotations

import json
import os
from pathlib import Path

import summarize_ao_failure


def write_events(path: Path, events: list[object]) -> None:
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(event) if isinstance(event, dict) else str(event) for event in events), encoding="utf-8")


def test_latest_events_path_uses_newest_run(tmp_path):
    older = tmp_path / "runs" / "r-old" / "events.jsonl"
    newer = tmp_path / "runs" / "r-new" / "events.jsonl"
    write_events(older, [{"kind": "run.started"}])
    write_events(newer, [{"kind": "run.completed"}])
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert summarize_ao_failure.latest_events_path(tmp_path) == newer


def test_summarize_events_counts_and_samples_failures(tmp_path):
    events = tmp_path / "runs" / "r-test" / "events.jsonl"
    write_events(
        events,
        [
            {"kind": "run.started"},
            {"kind": "task.started"},
            {
                "kind": "task.failed",
                "taskId": "slice-1-factory",
                "normalized_reason": "codex-provider-error",
                "exit_code": 1,
                "stderr": "429 Too Many Requests\nretry later",
            },
            {"kind": "task.failed", "fields": {"task_id": "slice-2-factory", "error": "network reset"}},
            "{not json",
        ],
    )

    summary = summarize_ao_failure.summarize_events(events, first_failed=1)

    assert summary["counts"] == {"run.started": 1, "task.started": 1, "task.failed": 2}
    assert summary["malformed_lines"] == 1
    assert summary["first_failed"] == [
        {
            "task_id": "slice-1-factory",
            "normalized_reason": "codex-provider-error",
            "exit_code": 1,
            "error": "",
            "stderr": "429 Too Many Requests\\nretry later",
            "stdout": "",
        }
    ]


def test_summarize_events_reads_ao_payload_fields(tmp_path):
    events = tmp_path / "runs" / "r-test" / "events.jsonl"
    write_events(
        events,
        [
            {
                "kind": "task.failed",
                "taskId": "slice-1-factory",
                "payload": {
                    "normalized_reason": "codex-provider-error",
                    "exit_code": 1,
                    "stderr": "exceeded retry limit, last status: 429 Too Many Requests",
                },
            }
        ],
    )

    summary = summarize_ao_failure.summarize_events(events, first_failed=1)

    assert summary["first_failed"][0]["normalized_reason"] == "codex-provider-error"
    assert summary["first_failed"][0]["exit_code"] == 1
    assert "429 Too Many Requests" in summary["first_failed"][0]["stderr"]


def test_summarize_events_counts_normalized_reasons_and_infers_missing_values(tmp_path):
    events = tmp_path / "runs" / "r-test" / "events.jsonl"
    write_events(
        events,
        [
            {
                "kind": "task.failed",
                "taskId": "rate-limit",
                "payload": {"stderr": "exceeded retry limit, last status: 429 Too Many Requests"},
            },
            {
                "kind": "task.failed",
                "taskId": "auth",
                "payload": {"error": "login required: not logged in"},
            },
            {
                "kind": "task.failed",
                "taskId": "path",
                "payload": {"normalized_reason": "workspace-path-boundary", "error": "outside workspace"},
            },
        ],
    )

    summary = summarize_ao_failure.summarize_events(events, first_failed=3)

    assert summary["normalized_reason_counts"] == {
        "provider-auth-missing": 1,
        "provider-rate-limit": 1,
        "workspace-path-boundary": 1,
    }
    assert summary["primary_normalized_reason"] == "provider-rate-limit"
    assert summary["first_failed"][0]["normalized_reason"] == "provider-rate-limit"
    assert summary["first_failed"][1]["normalized_reason"] == "provider-auth-missing"


def test_main_emits_json(tmp_path, capsys):
    events = tmp_path / "runs" / "r-test" / "events.jsonl"
    write_events(events, [{"kind": "task.failed", "taskId": "slice-1"}])

    result = summarize_ao_failure.main([str(tmp_path), "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["events"] == str(events)
    assert payload["counts"] == {"task.failed": 1}
