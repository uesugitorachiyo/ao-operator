from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_approval_lifecycle
import materialize_agent_os_approval


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def seed_gate(root: Path) -> tuple[Path, Path, str]:
    runspec = root / "ao/runspecs/agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text("kind: Run\nspec:\n  tasks: []\n", encoding="utf-8")
    digest = materialize_agent_os_approval.sha256_file(runspec)
    gate = write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "approval_file": "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json",
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": digest,
            "task_count": 7,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    approval = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
    return gate, approval, digest


def valid_approval(digest: str) -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
        "approved": True,
        "operator": "factory-operator",
        "approved_at": "2026-05-07T21:00:00+00:00",
        "expires_at": "2026-05-07T23:00:00+00:00",
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec_sha256": digest,
        "task_count": 7,
        "accepted_risk": "Approve one Agent OS no-provider execution rehearsal.",
    }


def test_absent_approval_file_is_safe_non_dispatching_state(tmp_path):
    gate, approval, _digest = seed_gate(tmp_path)

    payload = check_agent_os_approval_lifecycle.check_lifecycle(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "ABSENT"
    assert payload["approval_file_present"] is False
    assert payload["approval_usable"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_present_unexpired_approval_is_usable_but_does_not_dispatch(tmp_path):
    gate, approval, digest = seed_gate(tmp_path)
    write_json(approval, valid_approval(digest))

    payload = check_agent_os_approval_lifecycle.check_lifecycle(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_state"] == "APPROVED_ACTIVE"
    assert payload["approval_usable"] is True
    assert payload["expires_in_seconds"] == 5400
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_expired_approval_file_fails_closed(tmp_path):
    gate, approval, digest = seed_gate(tmp_path)
    stale = valid_approval(digest)
    stale["expires_at"] = "2026-05-07T21:15:00+00:00"
    write_json(approval, stale)

    payload = check_agent_os_approval_lifecycle.check_lifecycle(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["approval_state"] == "EXPIRED"
    assert payload["approval_usable"] is False
    assert "approval file is expired" in payload["errors"]


def test_runspec_hash_drift_fails_closed(tmp_path):
    gate, approval, digest = seed_gate(tmp_path)
    write_json(approval, valid_approval(digest))
    (tmp_path / "ao/runspecs/agent-os-phase-draft.yaml").write_text("kind: Run\nmetadata:\n  name: drift\n", encoding="utf-8")

    payload = check_agent_os_approval_lifecycle.check_lifecycle(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["approval_usable"] is False
    assert "current RunSpec sha256 must match approval file sha256" in payload["errors"]


def test_cli_writes_lifecycle_report(tmp_path, capsys):
    gate, approval, _digest = seed_gate(tmp_path)
    output = tmp_path / "run-artifacts/lifecycle.json"

    code = check_agent_os_approval_lifecycle.main(
        [
            "--root",
            str(tmp_path),
            "--approval-gate",
            str(gate),
            "--approval-file",
            str(approval),
            "--now",
            "2026-05-07T21:30:00Z",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-lifecycle/v1"
    assert saved["approval_state"] == "ABSENT"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
