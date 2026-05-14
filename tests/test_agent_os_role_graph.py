from __future__ import annotations

import json
from pathlib import Path

import agent_os_role_graph
from test_agent_os_capability_validator import role_toml, valid_contract, write


def seed_repo(root: Path) -> Path:
    contract = valid_contract()
    contract["core_roles"] = [
        {
            "id": "planner",
            "contract": "agents/planner.toml",
            "capabilities": ["intake"],
            "allowed_tools": ["read", "write-artifact"],
            "reads": ["task brief"],
            "writes": ["docs/specs/"],
            "risk_level": "medium",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/validate_factory.py --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "plan-hardener",
            "contract": "agents/plan-hardener.toml",
            "capabilities": ["plan-hardening"],
            "allowed_tools": ["read", "write-artifact"],
            "reads": ["docs/specs/"],
            "writes": ["docs/plans/"],
            "risk_level": "medium",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/validate_factory.py --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "factory-manager",
            "contract": "agents/factory-manager.toml",
            "capabilities": ["dag-planning"],
            "allowed_tools": ["read", "write-artifact"],
            "reads": ["docs/specs/", "docs/plans/"],
            "writes": ["run-artifacts/"],
            "risk_level": "medium",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "implementer",
            "contract": "agents/implementer.toml",
            "capabilities": ["implementation"],
            "allowed_tools": ["read", "write-scoped-files", "run-tests"],
            "reads": ["slice contract"],
            "writes": ["declared writes"],
            "risk_level": "high",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/verify_closure.py --repo . --with-pytest --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "slice-reviewer",
            "contract": "agents/slice-reviewer.toml",
            "capabilities": ["code-review"],
            "allowed_tools": ["read", "write-artifact"],
            "reads": ["slice artifact"],
            "writes": ["run-artifacts/"],
            "risk_level": "medium",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/verify_closure.py --repo . --with-pytest --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "integrator",
            "contract": "agents/integrator.toml",
            "capabilities": ["integration"],
            "allowed_tools": ["read", "write-scoped-files", "run-tests"],
            "reads": ["accepted slice artifacts"],
            "writes": ["integrated artifacts"],
            "risk_level": "high",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/verify_closure.py --repo . --with-pytest --json",
            "required_skills": ["factory-intake"],
        },
        {
            "id": "evaluator-closer",
            "contract": "agents/evaluator-closer.toml",
            "capabilities": ["acceptance-evaluation"],
            "allowed_tools": ["read", "write-artifact"],
            "reads": ["verification evidence"],
            "writes": ["docs/evaluations/"],
            "risk_level": "high",
            "dispatch_mode": "ao-role",
            "provider_boundary": "local-oauth",
            "verification": "python3 scripts/verify_closure.py --repo . --with-pytest --json",
            "required_skills": ["factory-intake"],
        },
    ]
    for role in contract["core_roles"]:
        write(root / str(role["contract"]), role_toml(str(role["id"])))
    write(root / "skills/factory-intake/SKILL.md", "# Factory Intake\n")
    path = root / "docs/contracts/ao-operator-agent-capabilities.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract), encoding="utf-8")
    return path


def test_role_graph_builds_versioned_dag_without_dispatch(tmp_path):
    contract = seed_repo(tmp_path)

    payload = agent_os_role_graph.build_role_graph(root=tmp_path, contract=contract)

    assert payload["verdict"] == "PASS"
    assert payload["schema"] == "ao-operator/agent-os-role-graph/v1"
    assert payload["state_schema_version"] == "ao-operator/agent-os-state/v2"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["role_count"] == 7
    assert payload["edges"] == [
        {"from": "planner", "to": "plan-hardener"},
        {"from": "plan-hardener", "to": "factory-manager"},
        {"from": "factory-manager", "to": "implementer"},
        {"from": "implementer", "to": "slice-reviewer"},
        {"from": "slice-reviewer", "to": "integrator"},
        {"from": "integrator", "to": "evaluator-closer"},
    ]


def test_role_graph_rejects_missing_core_role(tmp_path):
    contract = seed_repo(tmp_path)
    data = json.loads(contract.read_text(encoding="utf-8"))
    data["core_roles"] = [role for role in data["core_roles"] if role["id"] != "integrator"]
    contract.write_text(json.dumps(data), encoding="utf-8")

    payload = agent_os_role_graph.build_role_graph(root=tmp_path, contract=contract)

    assert payload["verdict"] == "FAIL"
    assert any("missing core role: integrator" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_v1_state_snapshot_is_migrated_to_v2():
    v1 = {
        "schema": "ao-operator/agent-os-state/v1",
        "lane": "agent-os-mission-router-state",
        "route": {"routes": ["quick"], "dispatch_authorized": True},
        "blockers": [],
    }

    migrated = agent_os_role_graph.migrate_state_snapshot(v1)

    assert migrated["schema"] == "ao-operator/agent-os-state/v2"
    assert migrated["previous_schema"] == "ao-operator/agent-os-state/v1"
    assert migrated["role_graph_schema"] == "ao-operator/agent-os-role-graph/v1"
    assert migrated["route"] == v1["route"]
    assert migrated["dispatch_authorized"] is False


def test_cli_writes_role_graph(tmp_path, capsys):
    contract = seed_repo(tmp_path)
    output = tmp_path / "run-artifacts/role-graph.json"

    code = agent_os_role_graph.main(
        ["--root", str(tmp_path), "--contract", str(contract), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-role-graph/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
