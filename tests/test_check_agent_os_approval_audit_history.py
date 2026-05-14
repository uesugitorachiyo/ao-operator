from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_audit_history


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_build_event_from_materialization_report_redacts_approval_payload(tmp_path):
    report = write_json(
        tmp_path / "run-artifacts/live/materialization.json",
        {
            "schema": "ao-operator/agent-os-approval-materialization/v1",
            "verdict": "PASS",
            "approval_file_written": True,
            "approval_file": "run-artifacts/live/agent-os-runspec-execution-approval.json",
            "approval": {"operator": "do-not-copy"},
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )

    event = check_agent_os_approval_audit_history.build_event(root=tmp_path, source_report=report)

    assert event["event"] == "APPROVAL_MATERIALIZED"
    assert event["source_report"] == "run-artifacts/live/materialization.json"
    assert event["approval_file_written"] is True
    assert "approval" not in event
    assert event["dispatch_authorized"] is False
    assert event["live_providers_run"] is False


def test_append_event_is_append_only_and_summary_reports_latest(tmp_path):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    first = {
        "schema": "ao-operator/agent-os-approval-audit-event/v1",
        "event": "APPROVAL_MATERIALIZED",
        "source_report": "materialization.json",
        "source_schema": "ao-operator/agent-os-approval-materialization/v1",
        "source_verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    second = {
        **first,
        "event": "APPROVAL_CLEANUP_RECORDED",
        "source_report": "cleanup.json",
        "source_schema": "ao-operator/agent-os-approval-cleanup/v1",
    }

    check_agent_os_approval_audit_history.append_event(audit, first)
    check_agent_os_approval_audit_history.append_event(audit, second)
    summary = check_agent_os_approval_audit_history.summarize(root=tmp_path, audit_log=audit)

    assert len(audit.read_text(encoding="utf-8").splitlines()) == 2
    assert summary["verdict"] == "PASS"
    assert summary["event_count"] == 2
    assert summary["latest_event"] == "APPROVAL_CLEANUP_RECORDED"
    assert summary["dispatch_authorized"] is False
    assert summary["live_providers_run"] is False


def test_summary_blocks_dispatching_audit_events(tmp_path):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    check_agent_os_approval_audit_history.append_event(
        audit,
        {
            "schema": "ao-operator/agent-os-approval-audit-event/v1",
            "event": "BAD",
            "source_report": "bad.json",
            "source_schema": "bad",
            "source_verdict": "PASS",
            "dispatch_authorized": True,
            "live_providers_run": False,
        },
    )

    summary = check_agent_os_approval_audit_history.summarize(root=tmp_path, audit_log=audit)

    assert summary["verdict"] == "FAIL"
    assert "audit event 1 dispatch_authorized must remain false" in summary["errors"]


def test_cli_appends_event_and_writes_summary(tmp_path, capsys):
    report = write_json(
        tmp_path / "run-artifacts/live/cleanup.json",
        {
            "schema": "ao-operator/agent-os-approval-cleanup/v1",
            "verdict": "PASS",
            "approval_state": "EXPIRED",
            "removed": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    output = tmp_path / "run-artifacts/live/approval-audit.json"

    code = check_agent_os_approval_audit_history.main(
        [
            "--root",
            str(tmp_path),
            "--source-report",
            str(report),
            "--audit-log",
            str(audit),
            "--append",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert audit.read_text(encoding="utf-8").count("\n") == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-audit-history/v1"
    assert saved["latest_event"] == "APPROVAL_CLEANUP_APPLIED"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
