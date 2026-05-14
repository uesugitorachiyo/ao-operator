from __future__ import annotations

import json

import factory_event_normalizer


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
    summary = factory_event_normalizer.event_summary(failure_event_text())

    assert summary["task_failed"] == 2
    assert summary["normalized_reason_counts"] == {
        "provider-auth-missing": 1,
        "provider-rate-limit": 1,
    }
    assert summary["primary_normalized_reason"] == "provider-rate-limit"


def test_status_from_event_object_skips_thinking_and_finds_latest_text_status():
    event = {
        "content": [
            {"type": "thinking", "text": "hidden"},
            {
                "type": "text",
                "text": "Result: DONE\nArtifact: run-artifacts/demo/roles/task.md\nEvidence:\n- ok\nConcerns:\n- none\nBlocker: none",
            },
        ]
    }

    status = factory_event_normalizer.status_from_event_object(event)

    assert status.startswith("Result: DONE")
    assert status.endswith("Blocker: none")


def test_extract_agent_status_reads_json_stdout_payload_for_task():
    text = "\n".join(
        [
            '2026-05-11 agent.stdout task=other {"line":"Result: BLOCKED\\nBlocker: other"}',
            '2026-05-11 agent.stdout task=target {"line":"Result: DONE\\nArtifact: x\\nEvidence:\\n- ok\\nConcerns:\\n- none\\nBlocker: none"}',
        ]
    )

    status = factory_event_normalizer.extract_agent_status(text, "target")

    assert "Result: DONE" in status
    assert "Blocker: none" in status


def test_extract_task_events_filters_by_task_id():
    text = "\n".join(
        [
            "agent.stdout task=target first",
            "agent.stdout task=other second",
            "task.completed task=target third",
        ]
    )

    assert factory_event_normalizer.extract_task_events(text, "target") == "\n".join(
        [
            "agent.stdout task=target first",
            "task.completed task=target third",
        ]
    )


def test_result_from_status_prefers_explicit_result_then_completion_fallback():
    assert factory_event_normalizer.result_from_status("Result: DONE_WITH_CONCERNS", False) == "DONE_WITH_CONCERNS"
    assert factory_event_normalizer.result_from_status("", True) == "DONE_WITH_CONCERNS"
    assert factory_event_normalizer.result_from_status("", False) == "BLOCKED"
