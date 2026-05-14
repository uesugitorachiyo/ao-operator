from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cleanup_agent_os_approval


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def approval_file(root: Path, *, expires_at: str = "2026-05-07T20:00:00Z") -> Path:
    return write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
            "approved": True,
            "operator": "operator",
            "approved_at": "2026-05-07T19:00:00Z",
            "expires_at": expires_at,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": "a" * 64,
            "task_count": 7,
            "accepted_risk": "Approve one execution.",
        },
    )


def test_cleanup_reports_absent_approval_as_safe_noop(tmp_path):
    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "ABSENT"
    assert payload["candidate"] is False
    assert payload["removed"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_cleanup_plans_expired_approval_without_apply(tmp_path):
    approval = approval_file(tmp_path)

    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "EXPIRED"
    assert payload["candidate"] is True
    assert payload["removed"] is False
    assert approval.exists()


def test_cleanup_apply_removes_expired_approval_only(tmp_path):
    approval = approval_file(tmp_path)
    sibling = write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-materialization.json",
        {"schema": "keep"},
    )

    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        apply=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "EXPIRED"
    assert payload["candidate"] is True
    assert payload["removed"] is True
    assert not approval.exists()
    assert sibling.exists()


def test_cleanup_refuses_active_approval_without_force(tmp_path):
    approval = approval_file(tmp_path, expires_at="2026-05-07T23:00:00Z")

    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        apply=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["approval_state"] == "ACTIVE"
    assert payload["candidate"] is False
    assert payload["removed"] is False
    assert approval.exists()
    assert "active approval requires --force" in payload["errors"]


def test_cleanup_force_removes_active_approval(tmp_path):
    approval = approval_file(tmp_path, expires_at="2026-05-07T23:00:00Z")

    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        apply=True,
        force=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "ACTIVE"
    assert payload["candidate"] is True
    assert payload["removed"] is True
    assert not approval.exists()


def test_cleanup_refuses_path_outside_status_tree(tmp_path):
    approval = tmp_path / "approval.json"
    write_json(approval, {"schema": "ao-operator/agent-os-runspec-execution-approval/v1"})

    payload = cleanup_agent_os_approval.plan_cleanup(
        root=tmp_path,
        approval_file=approval,
        apply=True,
        force=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["removed"] is False
    assert approval.exists()
    assert "approval file must live under run-artifacts/" in payload["errors"]


def test_cleanup_cli_writes_report(tmp_path, capsys):
    output = tmp_path / "cleanup.json"

    code = cleanup_agent_os_approval.main(
        [
            "--root",
            str(tmp_path),
            "--now",
            "2026-05-07T21:00:00Z",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-cleanup/v1"
    assert saved["approval_state"] == "ABSENT"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
