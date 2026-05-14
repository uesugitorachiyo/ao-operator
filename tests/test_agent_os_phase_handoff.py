from __future__ import annotations

import json
from pathlib import Path

import agent_os_phase_handoff


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compiled_phase() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-phase-compiler/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "phase_plan": {
            "lane": "agent-os-phase-compiler",
            "steps": [
                {
                    "order": 1,
                    "role": "planner",
                    "depends_on": [],
                    "capabilities": ["intake"],
                    "reads": ["task brief"],
                    "writes": ["docs/specs/"],
                    "risk_level": "medium",
                    "dispatch_mode": "ao-role",
                    "exit_gate": "role evidence accepted",
                },
                {
                    "order": 2,
                    "role": "implementer",
                    "depends_on": ["planner"],
                    "capabilities": ["implementation"],
                    "reads": ["slice contract"],
                    "writes": ["declared writes"],
                    "risk_level": "high",
                    "dispatch_mode": "ao-role",
                    "exit_gate": "role evidence accepted",
                },
                {
                    "order": 3,
                    "role": "evaluator-closer",
                    "depends_on": ["implementer"],
                    "capabilities": ["closure"],
                    "reads": ["verification evidence"],
                    "writes": ["docs/evaluations/"],
                    "risk_level": "high",
                    "dispatch_mode": "ao-role",
                    "exit_gate": "evaluator acceptance",
                },
            ],
        },
        "verification_matrix": {
            "required_commands": {
                "planner": ["python3 scripts/validate_factory.py --json"],
                "implementer": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
                "evaluator-closer": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
            },
            "risk_gates": {
                "planner": ["role evidence artifact required"],
                "implementer": ["role evidence artifact required", "closure evidence required for high-risk role"],
                "evaluator-closer": ["role evidence artifact required", "closure evidence required for high-risk role"],
            },
            "specialist_gates": {"qa": "future specialist role-contract slice"},
        },
    }


def seed_report(root: Path, data: dict[str, object] | None = None) -> Path:
    path = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json"
    write(path, json.dumps(data or compiled_phase()))
    return path


def test_build_handoff_packets_from_compiled_phase_without_dispatch(tmp_path):
    report = seed_report(tmp_path)

    payload = agent_os_phase_handoff.build_handoff(root=tmp_path, phase_report=report)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert [packet["role"] for packet in payload["handoff_packets"]] == [
        "planner",
        "implementer",
        "evaluator-closer",
    ]
    assert payload["handoff_packets"][0]["packet_id"] == "01-planner"
    assert payload["handoff_packets"][1]["scoped_context"]["reads"] == ["slice contract"]
    assert payload["handoff_packets"][1]["scoped_context"]["writes"] == ["declared writes"]
    assert payload["handoff_packets"][1]["full_transcript_allowed"] is False


def test_handoff_packets_include_status_contract_and_verification(tmp_path):
    report = seed_report(tmp_path)

    payload = agent_os_phase_handoff.build_handoff(root=tmp_path, phase_report=report)

    implementer = next(packet for packet in payload["handoff_packets"] if packet["role"] == "implementer")
    assert implementer["required_status_fields"] == ["Result", "Artifact", "Evidence", "Concerns", "Blocker"]
    assert implementer["verification_commands"] == [
        "python3 scripts/verify_closure.py --repo . --with-pytest --json"
    ]
    assert "closure evidence required for high-risk role" in implementer["risk_gates"]
    assert payload["specialist_activation"] == {"qa": "future specialist role-contract slice"}


def test_handoff_fails_when_compiled_phase_authorizes_dispatch(tmp_path):
    data = compiled_phase()
    data["dispatch_authorized"] = True
    report = seed_report(tmp_path, data)

    payload = agent_os_phase_handoff.build_handoff(root=tmp_path, phase_report=report)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert any("dispatch_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_handoff_report(tmp_path, capsys):
    report = seed_report(tmp_path)
    output = tmp_path / "run-artifacts/handoff.json"

    code = agent_os_phase_handoff.main(
        ["--root", str(tmp_path), "--phase-report", str(report), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-phase-handoff/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
