from __future__ import annotations

import json
from pathlib import Path

import agent_os_capability_validator


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def role_toml(name: str) -> str:
    return f"""
name = "{name}"
description = "Role {name}"
inputs = ["input"]
outputs = ["output"]
status_required = true
"""


def valid_contract() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-capability-contract/v1",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "core_roles": [
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
            }
        ],
        "specialists": [
            {
                "id": "engineering-manager",
                "capabilities": ["plan-review"],
                "allowed_tools": ["read"],
                "executable": False,
                "activation_gate": "future capability-validation slice",
            }
        ],
        "negative_constraints": [
            "MUST NOT dispatch AO providers from capability validation",
            "MUST NOT activate specialists without explicit executable role contracts",
        ],
    }


def seed_repo(root: Path, contract: dict[str, object] | None = None) -> Path:
    write(root / "agents/planner.toml", role_toml("planner"))
    write(root / "skills/factory-intake/SKILL.md", "# Factory Intake\n")
    path = root / "docs/contracts/ao-operator-agent-capabilities.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract or valid_contract()), encoding="utf-8")
    return path


def test_capability_contract_passes_without_authorizing_dispatch(tmp_path):
    contract = seed_repo(tmp_path)

    payload = agent_os_capability_validator.validate_capabilities(root=tmp_path, contract=contract)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["core_role_count"] == 1
    assert payload["specialist_count"] == 1
    assert payload["inactive_specialists"] == ["engineering-manager"]


def test_capability_contract_fails_when_required_skill_is_missing(tmp_path):
    contract = seed_repo(tmp_path)
    (tmp_path / "skills/factory-intake/SKILL.md").unlink()

    payload = agent_os_capability_validator.validate_capabilities(root=tmp_path, contract=contract)

    assert payload["verdict"] == "FAIL"
    assert any("factory-intake" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_capability_contract_fails_if_specialist_is_executable(tmp_path):
    contract_data = valid_contract()
    specialists = contract_data["specialists"]
    assert isinstance(specialists, list)
    specialists[0]["executable"] = True
    contract = seed_repo(tmp_path, contract_data)

    payload = agent_os_capability_validator.validate_capabilities(root=tmp_path, contract=contract)

    assert payload["verdict"] == "FAIL"
    assert any("specialist engineering-manager must remain non-executable" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_cli_writes_output(tmp_path, capsys):
    contract = seed_repo(tmp_path)
    output = tmp_path / "run-artifacts/capability.json"

    code = agent_os_capability_validator.main(
        ["--root", str(tmp_path), "--contract", str(contract), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-capability-validation/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
