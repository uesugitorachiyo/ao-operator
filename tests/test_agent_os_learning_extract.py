from __future__ import annotations

import json
from pathlib import Path

import agent_os_learning_extract


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def uat_state() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-uat-state/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "closure_authorized": False,
        "blockers": ["human UAT acceptance is pending"],
        "uat_items": [
            {
                "id": "uat-01-planner",
                "role": "planner",
                "status": "pending-human-acceptance",
                "accepted": False,
                "risk_gates": ["role evidence artifact required"],
                "verification_commands": ["python3 scripts/validate_factory.py --json"],
            },
            {
                "id": "uat-02-evaluator-closer",
                "role": "evaluator-closer",
                "status": "pending-human-acceptance",
                "accepted": False,
                "risk_gates": ["role evidence artifact required", "closure evidence required for high-risk role"],
                "verification_commands": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
            },
        ],
    }


def seed_uat(root: Path, data: dict[str, object] | None = None) -> Path:
    path = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
    write(path, json.dumps(data or uat_state()))
    return path


def test_extract_learning_records_pending_uat_without_authorizing_dispatch(tmp_path):
    uat = seed_uat(tmp_path)

    payload = agent_os_learning_extract.extract_learning(root=tmp_path, uat_report=uat)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["closure_authorized"] is False
    assert payload["pending_uat_count"] == 2
    assert payload["open_blockers"] == ["human UAT acceptance is pending"]


def test_extract_learning_creates_lessons_and_next_actions(tmp_path):
    uat = seed_uat(tmp_path)

    payload = agent_os_learning_extract.extract_learning(root=tmp_path, uat_report=uat)

    assert "Keep generated UAT state separate from human acceptance." in payload["lessons"]
    assert "Do not authorize closure while UAT items remain pending." in payload["negative_learnings"]
    assert payload["next_actions"] == [
        "Record human UAT responses or continue with operator cockpit visibility."
    ]
    assert payload["role_learning"]["evaluator-closer"]["high_risk"] is True


def test_extract_learning_fails_when_uat_authorizes_closure(tmp_path):
    data = uat_state()
    data["closure_authorized"] = True
    uat = seed_uat(tmp_path, data)

    payload = agent_os_learning_extract.extract_learning(root=tmp_path, uat_report=uat)

    assert payload["verdict"] == "FAIL"
    assert any("closure_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_learning_report(tmp_path, capsys):
    uat = seed_uat(tmp_path)
    output = tmp_path / "run-artifacts/learning.json"

    code = agent_os_learning_extract.main(
        ["--root", str(tmp_path), "--uat-report", str(uat), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-learning-extract/v1"
    assert saved["closure_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
