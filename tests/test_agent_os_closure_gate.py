from __future__ import annotations

import json
from pathlib import Path

import agent_os_closure_gate


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def response_gate(authorized: bool = True) -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-uat-response-gate/v1",
        "verdict": "PASS",
        "closure_authorized": authorized,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "response_summary": {
            "accepted": 7 if authorized else 0,
            "pending": 0 if authorized else 7,
            "rejected": 0,
            "required": 7,
        },
        "blockers": [] if authorized else ["human UAT responses are incomplete"],
    }


def readiness() -> dict[str, object]:
    return {
        "schema": "ao-operator/release-readiness-gate/v1",
        "verdict": "PASS",
        "ship_ready": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def seed_reports(root: Path, *, authorized: bool = True) -> tuple[Path, Path]:
    gate = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json"
    ready = root / "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json"
    write_json(gate, response_gate(authorized))
    write_json(ready, readiness())
    return gate, ready


def test_closure_gate_authorizes_agent_os_closure_when_uat_and_readiness_pass(tmp_path):
    gate, ready = seed_reports(tmp_path)

    payload = agent_os_closure_gate.evaluate_closure(root=tmp_path, response_gate=gate, readiness_report=ready)

    assert payload["verdict"] == "PASS"
    assert payload["agent_os_closed"] is True
    assert payload["closure_authorized"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["blockers"] == []


def test_closure_gate_blocks_when_uat_response_gate_is_not_authorized(tmp_path):
    gate, ready = seed_reports(tmp_path, authorized=False)

    payload = agent_os_closure_gate.evaluate_closure(root=tmp_path, response_gate=gate, readiness_report=ready)

    assert payload["verdict"] == "PASS"
    assert payload["agent_os_closed"] is False
    assert payload["closure_authorized"] is False
    assert "UAT response gate has not authorized closure" in payload["blockers"]


def test_closure_gate_fails_when_readiness_dispatch_is_enabled(tmp_path):
    gate, ready = seed_reports(tmp_path)
    data = readiness()
    data["dispatch_authorized"] = True
    write_json(ready, data)

    payload = agent_os_closure_gate.evaluate_closure(root=tmp_path, response_gate=gate, readiness_report=ready)

    assert payload["verdict"] == "FAIL"
    assert payload["agent_os_closed"] is False
    assert any("readiness dispatch_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_closure_report(tmp_path, capsys):
    gate, ready = seed_reports(tmp_path)
    output = tmp_path / "run-artifacts/closure.json"

    code = agent_os_closure_gate.main(
        [
            "--root",
            str(tmp_path),
            "--response-gate",
            str(gate),
            "--readiness-report",
            str(ready),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-closure-gate/v1"
    assert saved["agent_os_closed"] is True
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
