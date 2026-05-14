from __future__ import annotations

import json
from pathlib import Path

import materialize_agent_os_approval


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def seed_bundle(root: Path) -> tuple[Path, Path, Path, str]:
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
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": digest,
            "runspec_lock": {
                "algorithm": "sha256",
                "path": "ao/runspecs/agent-os-phase-draft.yaml",
                "sha256": digest,
            },
            "task_count": 7,
            "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml"],
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    target = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
    bundle = write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json",
        {
            "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
            "verdict": "PASS",
            "approval_gate": str(gate.relative_to(root)),
            "approval_file_target": str(target.relative_to(root)),
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
            "errors": [],
        },
    )
    return bundle, gate, target, digest


def test_materializer_default_is_safe_dry_run_without_writing_approval(tmp_path):
    bundle, gate, target, digest = seed_bundle(tmp_path)

    payload = materialize_agent_os_approval.materialize(
        root=tmp_path,
        approval_bundle=bundle,
        approval_gate=gate,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_file_written"] is False
    assert payload["approval_valid"] is False
    assert payload["approval"]["runspec_sha256"] == digest
    assert target.exists() is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_materializer_requires_explicit_operator_and_risk_before_write(tmp_path):
    bundle, gate, target, _digest = seed_bundle(tmp_path)

    payload = materialize_agent_os_approval.materialize(
        root=tmp_path,
        approval_bundle=bundle,
        approval_gate=gate,
        approved=True,
        write_approval_file=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert target.exists() is False
    assert "operator is required when writing approval file" in payload["errors"]
    assert "accepted_risk is required when writing approval file" in payload["errors"]


def test_materializer_writes_valid_explicit_approval_without_dispatch(tmp_path):
    bundle, gate, target, digest = seed_bundle(tmp_path)

    payload = materialize_agent_os_approval.materialize(
        root=tmp_path,
        approval_bundle=bundle,
        approval_gate=gate,
        approved=True,
        operator="factory-operator",
        accepted_risk="Approve one no-provider Agent OS execution rehearsal.",
        write_approval_file=True,
        now="2026-05-07T21:00:00Z",
        expires_in_hours=2,
    )

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["approval_file_written"] is True
    assert payload["approval_valid"] is True
    assert saved["approved"] is True
    assert saved["operator"] == "factory-operator"
    assert saved["runspec_sha256"] == digest
    assert saved["expires_at"] == "2026-05-07T23:00:00+00:00"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_materializer_refuses_runspec_hash_drift(tmp_path):
    bundle, gate, target, _digest = seed_bundle(tmp_path)
    (tmp_path / "ao/runspecs/agent-os-phase-draft.yaml").write_text("kind: Run\nmetadata:\n  name: changed\n", encoding="utf-8")

    payload = materialize_agent_os_approval.materialize(
        root=tmp_path,
        approval_bundle=bundle,
        approval_gate=gate,
        approved=True,
        operator="factory-operator",
        accepted_risk="Approve one execution.",
        write_approval_file=True,
        now="2026-05-07T21:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert target.exists() is False
    assert "current RunSpec sha256 must match approval gate sha256" in payload["errors"]


def test_materializer_cli_writes_dry_run_report(tmp_path, capsys):
    bundle, gate, _target, _digest = seed_bundle(tmp_path)
    output = tmp_path / "run-artifacts/materialization.json"

    code = materialize_agent_os_approval.main(
        [
            "--root",
            str(tmp_path),
            "--approval-bundle",
            str(bundle),
            "--approval-gate",
            str(gate),
            "--now",
            "2026-05-07T21:00:00Z",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-materialization/v1"
    assert saved["approval_file_written"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
