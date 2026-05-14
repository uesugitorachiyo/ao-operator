from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_revocation_apply_proof


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_fixture_inputs(root: Path) -> None:
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
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
        },
    )
    write_json(
        root / "run-artifacts/live/bundle.json",
        {
            "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
            "verdict": "PASS",
            "approval_file_target": "run-artifacts/live/approval.json",
            "approval_template": {
                "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
                "runspec_sha256": "abc123",
                "task_count": 7,
            },
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    runspec = root / "ao/runspecs/agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text("fixture-runspec", encoding="utf-8")


def test_revocation_apply_proof_materializes_then_revokes_in_fixture(tmp_path):
    seed_fixture_inputs(tmp_path)

    report = check_agent_os_approval_revocation_apply_proof.check_apply_proof(
        root=tmp_path,
        fixture_root=tmp_path / "fixture",
        approval_gate="run-artifacts/live/gate.json",
        approval_bundle="run-artifacts/live/bundle.json",
    )

    assert report["verdict"] == "PASS"
    assert report["materialization"]["approval_file_written"] is True
    assert report["revocation"]["revocation_applied"] is True
    assert report["revocation"]["approval_file_present_after"] is False
    assert report["revocation_log_sanitized"] is True
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False


def test_revocation_apply_proof_cli_writes_report(tmp_path, capsys):
    seed_fixture_inputs(tmp_path)
    output = tmp_path / "run-artifacts/live/revocation-apply-proof.json"

    code = check_agent_os_approval_revocation_apply_proof.main(
        [
            "--root",
            str(tmp_path),
            "--fixture-root",
            str(tmp_path / "fixture"),
            "--approval-gate",
            "run-artifacts/live/gate.json",
            "--approval-bundle",
            "run-artifacts/live/bundle.json",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-revocation-apply-proof/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
