from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_state_evidence_hygiene


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def state_payload(**extra: object) -> dict:
    payload = {
        "schema": "ao-operator/agent-os-state/v2",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
        "blockers": [],
    }
    payload.update(extra)
    return payload


def test_state_evidence_hygiene_accepts_clean_state_v2_files(tmp_path):
    write_json(tmp_path / "run-artifacts/live/agent-os-state-v2.json", state_payload())
    write_json(tmp_path / "run-artifacts/live/agent-os-router-v2-state.json", state_payload(architecture_ready=True))

    payload = check_agent_os_state_evidence_hygiene.check_hygiene(
        root=tmp_path,
        state_files=[
            "run-artifacts/live/agent-os-state-v2.json",
            "run-artifacts/live/agent-os-router-v2-state.json",
        ],
        git_status_lines=[],
    )

    assert payload["verdict"] == "PASS"
    assert payload["state_file_count"] == 2
    assert payload["dirty_state_artifacts"] == []
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_state_evidence_hygiene_rejects_dispatch_authorized_state(tmp_path):
    write_json(tmp_path / "state.json", state_payload(dispatch_authorized=True))

    payload = check_agent_os_state_evidence_hygiene.check_hygiene(
        root=tmp_path,
        state_files=["state.json"],
        git_status_lines=[],
    )

    assert payload["verdict"] == "FAIL"
    assert "state.json dispatch_authorized must remain false" in payload["blockers"]


def test_state_evidence_hygiene_rejects_untracked_state_artifacts(tmp_path):
    write_json(tmp_path / "state.json", state_payload())

    payload = check_agent_os_state_evidence_hygiene.check_hygiene(
        root=tmp_path,
        state_files=["state.json"],
        git_status_lines=["?? run-artifacts/live/agent-os-router-v2-state-debug.json"],
    )

    assert payload["verdict"] == "FAIL"
    assert payload["dirty_state_artifacts"] == ["run-artifacts/live/agent-os-router-v2-state-debug.json"]


def test_cli_writes_state_evidence_hygiene_report(tmp_path):
    write_json(tmp_path / "state.json", state_payload())
    output = tmp_path / "hygiene.json"

    code = check_agent_os_state_evidence_hygiene.main(
        [
            "--root",
            str(tmp_path),
            "--state-file",
            "state.json",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert output.is_file()
    assert "ao-operator/agent-os-state-evidence-hygiene/v1" in output.read_text(encoding="utf-8")
