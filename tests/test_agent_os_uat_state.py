from __future__ import annotations

import json
from pathlib import Path

import agent_os_uat_state


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def handoff_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-phase-handoff/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "handoff_packets": [
            {
                "packet_id": "01-planner",
                "role": "planner",
                "depends_on": [],
                "required_status_fields": ["Result", "Artifact", "Evidence", "Concerns", "Blocker"],
                "verification_commands": ["python3 scripts/validate_factory.py --json"],
                "risk_gates": ["role evidence artifact required"],
                "full_transcript_allowed": False,
            },
            {
                "packet_id": "02-evaluator-closer",
                "role": "evaluator-closer",
                "depends_on": ["planner"],
                "required_status_fields": ["Result", "Artifact", "Evidence", "Concerns", "Blocker"],
                "verification_commands": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
                "risk_gates": ["role evidence artifact required", "closure evidence required for high-risk role"],
                "full_transcript_allowed": False,
            },
        ],
    }


def seed_handoff(root: Path, data: dict[str, object] | None = None) -> Path:
    path = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json"
    write(path, json.dumps(data or handoff_report()))
    return path


def test_build_uat_state_creates_pending_acceptance_items_without_dispatch(tmp_path):
    handoff = seed_handoff(tmp_path)

    payload = agent_os_uat_state.build_uat_state(root=tmp_path, handoff_report=handoff)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["closure_authorized"] is False
    assert payload["uat_required"] is True
    assert [item["role"] for item in payload["uat_items"]] == ["planner", "evaluator-closer"]
    assert all(item["status"] == "pending-human-acceptance" for item in payload["uat_items"])


def test_uat_state_records_acceptance_questions_and_blockers(tmp_path):
    handoff = seed_handoff(tmp_path)

    payload = agent_os_uat_state.build_uat_state(root=tmp_path, handoff_report=handoff)

    closer = next(item for item in payload["uat_items"] if item["role"] == "evaluator-closer")
    assert closer["question"] == "Does evaluator-closer satisfy its exit gate with acceptable evidence?"
    assert closer["requires_human_response"] is True
    assert "closure evidence required for high-risk role" in closer["risk_gates"]
    assert payload["blockers"] == ["human UAT acceptance is pending"]


def test_uat_state_fails_when_handoff_authorizes_dispatch(tmp_path):
    data = handoff_report()
    data["dispatch_authorized"] = True
    handoff = seed_handoff(tmp_path, data)

    payload = agent_os_uat_state.build_uat_state(root=tmp_path, handoff_report=handoff)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert any("dispatch_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_uat_report(tmp_path, capsys):
    handoff = seed_handoff(tmp_path)
    output = tmp_path / "run-artifacts/uat.json"

    code = agent_os_uat_state.main(
        ["--root", str(tmp_path), "--handoff-report", str(handoff), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-uat-state/v1"
    assert saved["closure_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
