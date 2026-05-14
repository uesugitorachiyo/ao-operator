from __future__ import annotations

import json
from pathlib import Path

import agent_os_phase_compiler


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def role(role_id: str, *, risk: str = "medium", verification: str = "python3 scripts/validate_factory.py --json") -> dict[str, object]:
    return {
        "id": role_id,
        "contract": f"agents/{role_id}.toml",
        "capabilities": ["capability"],
        "allowed_tools": ["read", "write-artifact"],
        "reads": ["input"],
        "writes": [f"run-artifacts/{role_id}.json"],
        "risk_level": risk,
        "dispatch_mode": "ao-role",
        "provider_boundary": "local-oauth",
        "verification": verification,
        "required_skills": ["closure-verification"] if risk == "high" else ["factory-intake"],
    }


def contract() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-capability-contract/v1",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "negative_constraints": ["MUST NOT dispatch AO providers from phase compilation"],
        "core_roles": [
            role("planner"),
            role("plan-hardener"),
            role("factory-manager"),
            role("implementer", risk="high", verification="python3 scripts/verify_closure.py --repo . --with-pytest --json"),
            role("evaluator-closer", risk="high", verification="python3 scripts/verify_closure.py --repo . --with-pytest --json"),
        ],
        "specialists": [
            {
                "id": "release-manager",
                "capabilities": ["release-readiness"],
                "allowed_tools": ["read"],
                "executable": False,
                "activation_gate": "future specialist role-contract slice",
            }
        ],
    }


def seed_repo(root: Path, data: dict[str, object] | None = None) -> Path:
    path = root / "docs/contracts/ao-operator-agent-capabilities.json"
    write(path, json.dumps(data or contract()))
    return path


def seed_state_v2(root: Path, data: dict[str, object] | None = None) -> Path:
    path = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json"
    write(
        path,
        json.dumps(
            data
            or {
                "schema": "ao-operator/agent-os-state/v2",
                "verdict": "PASS",
                "previous_schema": "ao-operator/agent-os-state/v1",
                "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
                "dispatch_authorized": False,
                "live_providers_run": False,
                "evidence_paths": ["run-artifacts/agent-os-role-graph.json"],
            }
        ),
    )
    return path


def test_compile_phase_plan_keeps_dispatch_disabled_and_orders_core_roles(tmp_path):
    path = seed_repo(tmp_path)
    seed_state_v2(tmp_path)

    payload = agent_os_phase_compiler.compile_phase(root=tmp_path, contract=path, lane="agent-os-phase-compiler")

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert [step["role"] for step in payload["phase_plan"]["steps"]] == [
        "planner",
        "plan-hardener",
        "factory-manager",
        "implementer",
        "evaluator-closer",
    ]
    assert payload["phase_plan"]["steps"][0]["depends_on"] == []
    assert payload["phase_plan"]["steps"][1]["depends_on"] == ["planner"]
    assert payload["phase_plan"]["steps"][-1]["exit_gate"] == "evaluator acceptance"


def test_compile_phase_plan_builds_verification_matrix_from_role_contract(tmp_path):
    path = seed_repo(tmp_path)
    seed_state_v2(tmp_path)

    payload = agent_os_phase_compiler.compile_phase(root=tmp_path, contract=path)

    matrix = payload["verification_matrix"]
    assert matrix["required_commands"]["planner"] == ["python3 scripts/validate_factory.py --json"]
    assert matrix["required_commands"]["implementer"] == [
        "python3 scripts/verify_closure.py --repo . --with-pytest --json"
    ]
    assert "closure evidence required for high-risk role" in matrix["risk_gates"]["implementer"]
    assert matrix["specialist_gates"]["release-manager"] == "future specialist role-contract slice"


def test_compile_phase_records_state_v2_baseline(tmp_path):
    path = seed_repo(tmp_path)
    state = seed_state_v2(tmp_path)

    payload = agent_os_phase_compiler.compile_phase(root=tmp_path, contract=path, state_v2=state)

    assert payload["verdict"] == "PASS"
    assert payload["phase_plan"]["state_schema_version"] == "ao-operator/agent-os-state/v2"
    assert payload["state_baseline"] == {
        "path": "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json",
        "schema": "ao-operator/agent-os-state/v2",
        "verdict": "PASS",
        "previous_schema": "ao-operator/agent-os-state/v1",
        "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
        "evidence_path_count": 1,
    }


def test_compile_phase_fails_closed_without_safe_state_v2(tmp_path):
    path = seed_repo(tmp_path)
    state = seed_state_v2(
        tmp_path,
        {
            "schema": "ao-operator/agent-os-state/v2",
            "verdict": "PASS",
            "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
            "dispatch_authorized": True,
            "live_providers_run": False,
        },
    )

    payload = agent_os_phase_compiler.compile_phase(root=tmp_path, contract=path, state_v2=state)

    assert payload["verdict"] == "FAIL"
    assert "state_v2 dispatch_authorized must remain false" in payload["errors"]


def test_compile_phase_fails_if_capability_contract_authorizes_dispatch(tmp_path):
    data = contract()
    data["dispatch_authorized"] = True
    path = seed_repo(tmp_path, data)
    seed_state_v2(tmp_path)

    payload = agent_os_phase_compiler.compile_phase(root=tmp_path, contract=path)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert any("dispatch_authorized must remain false" in error for error in payload["errors"])


def test_cli_writes_phase_report(tmp_path, capsys):
    path = seed_repo(tmp_path)
    state = seed_state_v2(tmp_path)
    output = tmp_path / "run-artifacts/phase.json"

    code = agent_os_phase_compiler.main(
        [
            "--root",
            str(tmp_path),
            "--contract",
            str(path),
            "--state-v2",
            str(state),
            "--lane",
            "agent-os-phase-compiler",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-phase-compiler/v1"
    assert saved["state_baseline"]["schema"] == "ao-operator/agent-os-state/v2"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
