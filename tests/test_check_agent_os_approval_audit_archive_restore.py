from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_audit_archive_restore


def append_event(path: Path, event: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": "ao-operator/agent-os-approval-audit-event/v1",
                    "event": event,
                    "source_report": f"{event}.json",
                    "source_schema": "ao-operator/test/v1",
                    "source_verdict": "PASS",
                    "dispatch_authorized": False,
                    "live_providers_run": False,
                },
                sort_keys=True,
            )
            + "\n"
        )


def test_archive_restore_proof_copies_and_verifies_audit_log(tmp_path):
    audit = tmp_path / "run-artifacts/live/audit.jsonl"
    append_event(audit, "APPROVAL_CLEANUP_RECORDED")

    report = check_agent_os_approval_audit_archive_restore.check_archive_restore(
        root=tmp_path,
        fixture_root=tmp_path / "fixture",
        audit_log=audit,
    )

    assert report["verdict"] == "PASS"
    assert report["archive_created"] is True
    assert report["restore_verified"] is True
    assert report["source_sha256"] == report["restored_sha256"]
    assert report["event_count"] == 1
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False


def test_archive_restore_rejects_nested_approval_payload(tmp_path):
    audit = tmp_path / "run-artifacts/live/audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps(
            {
                "schema": "ao-operator/agent-os-approval-audit-event/v1",
                "event": "APPROVAL_MATERIALIZED",
                "source_report": "materialization.json",
                "source_schema": "ao-operator/test/v1",
                "source_verdict": "PASS",
                "approval": {"operator": "do-not-archive"},
                "dispatch_authorized": False,
                "live_providers_run": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = check_agent_os_approval_audit_archive_restore.check_archive_restore(
        root=tmp_path,
        fixture_root=tmp_path / "fixture",
        audit_log=audit,
    )

    assert report["verdict"] == "FAIL"
    assert "audit event 1 must not include nested approval payload" in report["errors"]


def test_archive_restore_cli_writes_report(tmp_path, capsys):
    audit = tmp_path / "run-artifacts/live/audit.jsonl"
    append_event(audit, "APPROVAL_CLEANUP_RECORDED")
    output = tmp_path / "run-artifacts/live/archive-restore.json"

    code = check_agent_os_approval_audit_archive_restore.main(
        [
            "--root",
            str(tmp_path),
            "--fixture-root",
            str(tmp_path / "fixture"),
            "--audit-log",
            str(audit),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-audit-archive-restore/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
