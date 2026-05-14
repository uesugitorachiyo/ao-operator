from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approved_launch_proof
import materialize_agent_os_approval


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_source(root: Path) -> tuple[Path, Path, Path]:
    runspec = root / "ao/runspecs/agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text("kind: Run\nspec:\n  tasks: []\n", encoding="utf-8")
    digest = materialize_agent_os_approval.sha256_file(runspec)
    status = root / "run-artifacts/remote-transfer-v2-stress-live"
    gate = write_json(
        status / "agent-os-runspec-execution-approval-gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "approval_file": "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json",
            "approval_file_present": False,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": digest,
            "task_count": 7,
            "execution_command": [
                "ao",
                "run",
                "ao/runspecs/agent-os-phase-draft.yaml",
                "--home",
                "/tmp/ao-operator-ao-agent-os-phase-draft",
            ],
            "provider_profile": ".env.example",
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    bundle = write_json(
        status / "agent-os-runspec-execution-approval-bundle.json",
        {
            "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
            "verdict": "PASS",
            "approval_gate": str(gate.relative_to(root)),
            "approval_file_target": "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json",
            "approval_template": {
                "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
                "approved": False,
                "operator": "",
                "approved_at": "2026-05-07T21:00:00+00:00",
                "expires_at": "2026-05-08T01:00:00+00:00",
                "accepted_risk": "",
                "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
                "runspec_sha256": digest,
                "task_count": 7,
            },
            "runspec_lock": {
                "algorithm": "sha256",
                "path": "ao/runspecs/agent-os-phase-draft.yaml",
                "sha256": digest,
            },
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    return runspec, gate, bundle


def test_positive_launch_proof_transitions_from_absent_to_plan_without_dispatch(tmp_path):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    seed_source(source)

    payload = check_agent_os_approved_launch_proof.check_proof(
        root=source,
        fixture_root=fixture,
        now="2026-05-07T21:30:00Z",
        expires_in_hours=1,
    )

    assert payload["verdict"] == "PASS"
    assert payload["blocked_before_approval"]["verdict"] == "BLOCKED"
    assert payload["blocked_before_approval"]["approval_state"] == "ABSENT"
    assert payload["materialization"]["approval_file_written"] is True
    assert payload["approval_validation"]["approval_valid"] is True
    assert payload["approval_lifecycle"]["approval_state"] == "APPROVED_ACTIVE"
    assert payload["approval_lifecycle"]["approval_usable"] is True
    assert payload["launcher_after_approval"]["verdict"] == "PLAN"
    assert payload["launcher_after_approval"]["would_run_provider"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_positive_launch_proof_fails_closed_on_source_runspec_drift(tmp_path):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    seed_source(source)
    (source / "ao/runspecs/agent-os-phase-draft.yaml").write_text(
        "kind: Run\nmetadata:\n  name: changed\n",
        encoding="utf-8",
    )

    payload = check_agent_os_approved_launch_proof.check_proof(
        root=source,
        fixture_root=fixture,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert "materialization failed" in payload["errors"]


def test_positive_launch_proof_cli_writes_status_report(tmp_path, capsys):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    output = tmp_path / "proof.json"
    seed_source(source)

    code = check_agent_os_approved_launch_proof.main(
        [
            "--root",
            str(source),
            "--fixture-root",
            str(fixture),
            "--now",
            "2026-05-07T21:30:00Z",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approved-launch-proof/v1"
    assert saved["launcher_after_approval"]["verdict"] == "PLAN"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
