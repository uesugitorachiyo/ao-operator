from __future__ import annotations

import json
from pathlib import Path

import generate_agent_os_approval_bundle


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_gate(root: Path) -> Path:
    gate = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
    write_json(
        gate,
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": "abc123",
            "runspec_lock": {
                "algorithm": "sha256",
                "path": "ao/runspecs/agent-os-phase-draft.yaml",
                "sha256": "abc123",
            },
            "task_count": 7,
            "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml"],
        },
    )
    return gate


def test_approval_bundle_embeds_runspec_hash_expiry_and_target_without_dispatch(tmp_path):
    gate = seed_gate(tmp_path)

    payload = generate_agent_os_approval_bundle.generate_bundle(
        root=tmp_path,
        approval_gate=gate,
        now="2026-05-07T21:00:00Z",
        expires_in_hours=6,
    )

    template = payload["approval_template"]
    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["approval_file_target"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
    assert template["schema"] == "ao-operator/agent-os-runspec-execution-approval/v1"
    assert template["approved"] is False
    assert template["operator"] == ""
    assert template["approved_at"] == "2026-05-07T21:00:00+00:00"
    assert template["expires_at"] == "2026-05-08T03:00:00+00:00"
    assert template["runspec_path"] == "ao/runspecs/agent-os-phase-draft.yaml"
    assert template["runspec_sha256"] == "abc123"
    assert template["task_count"] == 7


def test_approval_bundle_blocks_missing_hash_lock(tmp_path):
    gate = seed_gate(tmp_path)
    data = json.loads(gate.read_text(encoding="utf-8"))
    data["runspec_sha256"] = ""
    data["runspec_lock"] = {}
    write_json(gate, data)

    payload = generate_agent_os_approval_bundle.generate_bundle(root=tmp_path, approval_gate=gate)

    assert payload["verdict"] == "FAIL"
    assert "approval gate must include sha256 RunSpec lock" in payload["errors"]


def test_cli_writes_approval_bundle_template(tmp_path, capsys):
    seed_gate(tmp_path)
    output = tmp_path / "run-artifacts/approval-bundle.json"

    code = generate_agent_os_approval_bundle.main(
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
    assert saved["schema"] == "ao-operator/agent-os-execution-approval-bundle/v1"
    assert saved["approval_template"]["runspec_sha256"] == "abc123"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
