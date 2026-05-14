from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_revocation


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_approval_fixture(root: Path) -> None:
    write_json(
        root / "run-artifacts/live/gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": "abc123",
            "task_count": 7,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        root / "run-artifacts/live/approval.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
            "approved": True,
            "operator": "test",
            "accepted_risk": "fixture only",
            "approved_at": "2026-05-07T00:00:00+00:00",
            "expires_at": "2026-05-08T00:00:00+00:00",
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": "abc123",
            "task_count": 7,
        },
    )


def test_revocation_plan_is_non_mutating_by_default(tmp_path):
    seed_approval_fixture(tmp_path)

    report = check_agent_os_approval_revocation.revoke_approval(
        root=tmp_path,
        approval_file="run-artifacts/live/approval.json",
        revocation_log="run-artifacts/live/revocations.jsonl",
        reason="test revoke",
        operator="tester",
        apply=False,
    )

    assert report["verdict"] == "PASS"
    assert report["revocation_applied"] is False
    assert report["approval_file_present_after"] is True
    assert report["dispatch_authorized"] is False
    assert not (tmp_path / "run-artifacts/live/revocations.jsonl").exists()


def test_revocation_apply_removes_approval_and_logs_event(tmp_path):
    seed_approval_fixture(tmp_path)

    report = check_agent_os_approval_revocation.revoke_approval(
        root=tmp_path,
        approval_file="run-artifacts/live/approval.json",
        revocation_log="run-artifacts/live/revocations.jsonl",
        reason="operator changed mind",
        operator="tester",
        apply=True,
        force=True,
    )

    assert report["verdict"] == "PASS"
    assert report["revocation_applied"] is True
    assert report["approval_file_present_after"] is False
    assert report["revocation_count"] == 1
    line = (tmp_path / "run-artifacts/live/revocations.jsonl").read_text(encoding="utf-8")
    assert "APPROVAL_REVOKED" in line
    assert "accepted_risk" not in line


def test_revocation_requires_reason_when_applying(tmp_path):
    seed_approval_fixture(tmp_path)

    report = check_agent_os_approval_revocation.revoke_approval(
        root=tmp_path,
        approval_file="run-artifacts/live/approval.json",
        revocation_log="run-artifacts/live/revocations.jsonl",
        reason="",
        operator="tester",
        apply=True,
        force=True,
    )

    assert report["verdict"] == "FAIL"
    assert "revocation reason is required when applying" in report["errors"]
    assert (tmp_path / "run-artifacts/live/approval.json").is_file()


def test_cli_writes_revocation_report(tmp_path, capsys):
    seed_approval_fixture(tmp_path)
    output = tmp_path / "run-artifacts/live/revocation.json"

    code = check_agent_os_approval_revocation.main(
        [
            "--root",
            str(tmp_path),
            "--approval-file",
            "run-artifacts/live/approval.json",
            "--revocation-log",
            "run-artifacts/live/revocations.jsonl",
            "--operator",
            "tester",
            "--reason",
            "dry run only",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-revocation/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
