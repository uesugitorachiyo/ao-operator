from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_audit_retention


def append_event(path: Path, event: str, *, payload: dict[str, object] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {
        "schema": "ao-operator/agent-os-approval-audit-event/v1",
        "event": event,
        "source_report": f"{event}.json",
        "source_schema": "ao-operator/test/v1",
        "source_verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    if payload:
        body.update(payload)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body, sort_keys=True) + "\n")


def test_retention_policy_passes_for_compact_audit_log(tmp_path):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    append_event(audit, "APPROVAL_CLEANUP_RECORDED")

    report = check_agent_os_approval_audit_retention.check_retention(
        root=tmp_path,
        audit_log=audit,
        max_events=10,
        max_bytes=4096,
    )

    assert report["verdict"] == "PASS"
    assert report["event_count"] == 1
    assert report["rotation_due"] is False
    assert report["retention_policy"]["max_events"] == 10
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False


def test_retention_policy_recommends_rotation_without_failing(tmp_path):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    append_event(audit, "ONE")
    append_event(audit, "TWO")

    report = check_agent_os_approval_audit_retention.check_retention(
        root=tmp_path,
        audit_log=audit,
        max_events=1,
        max_bytes=4096,
    )

    assert report["verdict"] == "PASS"
    assert report["rotation_due"] is True
    assert "event_count exceeds max_events" in report["rotation_reasons"]
    assert report["next_safe_command"].startswith("Rotate")


def test_retention_policy_rejects_nested_approval_payloads(tmp_path):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    append_event(audit, "APPROVAL_MATERIALIZED", payload={"approval": {"operator": "secret"}})

    report = check_agent_os_approval_audit_retention.check_retention(root=tmp_path, audit_log=audit)

    assert report["verdict"] == "FAIL"
    assert "audit event 1 must not include nested approval payload" in report["errors"]


def test_cli_writes_retention_report(tmp_path, capsys):
    audit = tmp_path / "run-artifacts/live/approval-audit.jsonl"
    output = tmp_path / "run-artifacts/live/approval-audit-retention.json"
    append_event(audit, "APPROVAL_CLEANUP_RECORDED")

    code = check_agent_os_approval_audit_retention.main(
        [
            "--root",
            str(tmp_path),
            "--audit-log",
            str(audit),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-audit-retention/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
