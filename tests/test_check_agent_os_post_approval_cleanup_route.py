from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_post_approval_cleanup_route
import materialize_agent_os_approval


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_source(root: Path) -> None:
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
            "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml"],
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
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
                "accepted_risk": "",
                "approved_at": "2026-05-07T21:00:00+00:00",
                "expires_at": "2026-05-08T01:00:00+00:00",
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


def test_post_approval_cleanup_route_proves_accepted_route_then_absent_lifecycle(tmp_path):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    seed_source(source)

    payload = check_agent_os_post_approval_cleanup_route.check_route(
        root=source,
        fixture_root=fixture,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["materialization"]["approval_file_written"] is True
    assert payload["postrun_route"]["route"] == "ACCEPTED"
    assert payload["cleanup"]["removed"] is True
    assert payload["lifecycle_after_cleanup"]["approval_state"] == "ABSENT"
    assert payload["lifecycle_after_cleanup"]["approval_usable"] is False
    assert payload["audit_history"]["event_count"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_post_approval_cleanup_route_fails_closed_on_fixture_collision(tmp_path):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    seed_source(source)
    fixture.mkdir()

    payload = check_agent_os_post_approval_cleanup_route.check_route(
        root=source,
        fixture_root=fixture,
        now="2026-05-07T21:30:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert "fixture root exists without marker" in payload["errors"][0]


def test_post_approval_cleanup_route_cli_writes_report(tmp_path, capsys):
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    output = tmp_path / "post-approval-cleanup-route.json"
    seed_source(source)

    code = check_agent_os_post_approval_cleanup_route.main(
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
    assert saved["schema"] == "ao-operator/agent-os-post-approval-cleanup-route/v1"
    assert saved["postrun_route"]["route"] == "ACCEPTED"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
