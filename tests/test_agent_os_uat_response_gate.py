from __future__ import annotations

import json
from pathlib import Path

import agent_os_uat_response_gate


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def uat_state() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-uat-state/v1",
        "verdict": "PASS",
        "closure_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "uat_items": [
            {
                "id": "uat-01-planner",
                "role": "planner",
                "question": "Does planner satisfy its exit gate with acceptable evidence?",
                "status": "pending-human-acceptance",
                "accepted": False,
                "requires_human_response": True,
            },
            {
                "id": "uat-02-evaluator-closer",
                "role": "evaluator-closer",
                "question": "Does evaluator-closer satisfy its exit gate with acceptable evidence?",
                "status": "pending-human-acceptance",
                "accepted": False,
                "requires_human_response": True,
            },
        ],
    }


def responses(accepted: bool | None = True) -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-uat-responses/v1",
        "responses": [
            {
                "id": "uat-01-planner",
                "role": "planner",
                "accepted": accepted,
                "response": "accepted" if accepted else "rejected" if accepted is False else "",
                "responder": "operator" if accepted is not None else "",
                "responded_at": "2026-05-07T00:00:00Z" if accepted is not None else "",
            },
            {
                "id": "uat-02-evaluator-closer",
                "role": "evaluator-closer",
                "accepted": accepted,
                "response": "accepted" if accepted else "rejected" if accepted is False else "",
                "responder": "operator" if accepted is not None else "",
                "responded_at": "2026-05-07T00:00:00Z" if accepted is not None else "",
            },
        ],
    }


def seed_uat(root: Path) -> Path:
    path = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
    write_json(path, uat_state())
    return path


def test_response_gate_writes_template_and_blocks_without_responses(tmp_path):
    uat = seed_uat(tmp_path)
    response_path = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-responses.json"

    payload = agent_os_uat_response_gate.evaluate_gate(
        root=tmp_path,
        uat_report=uat,
        responses_path=response_path,
        write_template=True,
    )

    assert payload["verdict"] == "PASS"
    assert payload["closure_authorized"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["response_summary"]["accepted"] == 0
    assert "human UAT responses are incomplete" in payload["blockers"]
    saved = json.loads(response_path.read_text(encoding="utf-8"))
    assert saved["responses"][0]["accepted"] is None


def test_response_gate_authorizes_closure_when_all_items_are_accepted(tmp_path):
    uat = seed_uat(tmp_path)
    response_path = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-responses.json"
    write_json(response_path, responses(True))

    payload = agent_os_uat_response_gate.evaluate_gate(root=tmp_path, uat_report=uat, responses_path=response_path)

    assert payload["verdict"] == "PASS"
    assert payload["closure_authorized"] is True
    assert payload["blockers"] == []
    assert payload["response_summary"] == {"accepted": 2, "pending": 0, "rejected": 0, "required": 2}


def test_response_gate_blocks_when_any_item_is_rejected(tmp_path):
    uat = seed_uat(tmp_path)
    response_path = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-responses.json"
    write_json(response_path, responses(False))

    payload = agent_os_uat_response_gate.evaluate_gate(root=tmp_path, uat_report=uat, responses_path=response_path)

    assert payload["verdict"] == "PASS"
    assert payload["closure_authorized"] is False
    assert "human UAT responses contain rejection" in payload["blockers"]


def test_response_gate_fails_when_uat_state_authorizes_dispatch(tmp_path):
    data = uat_state()
    data["dispatch_authorized"] = True
    uat = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
    write_json(uat, data)

    payload = agent_os_uat_response_gate.evaluate_gate(root=tmp_path, uat_report=uat)

    assert payload["verdict"] == "FAIL"
    assert any("dispatch_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_gate_and_template(tmp_path, capsys):
    uat = seed_uat(tmp_path)
    output = tmp_path / "run-artifacts/gate.json"
    response_path = tmp_path / "run-artifacts/responses.json"

    code = agent_os_uat_response_gate.main(
        [
            "--root",
            str(tmp_path),
            "--uat-report",
            str(uat),
            "--responses",
            str(response_path),
            "--write-template",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-uat-response-gate/v1"
    assert saved["closure_authorized"] is False
    assert response_path.is_file()
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
