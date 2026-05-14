from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_sdd


def write_file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def valid_sdd() -> str:
    sections = [
        "# AO Operator Agent OS SDD",
        "Classification: COMPLEX",
        "Shape: greenfield",
        "## Scope",
        "## Mission Router",
        "## Project State Layer",
        "## Role Capability Schema",
        "## Specialist Registry",
        "## Phase Compiler",
        "## Verification Matrix",
        "## UAT Gate",
        "## Learning Loop",
        "## Operator Cockpit",
        "## Negative Constraints",
        "- MUST NOT dispatch AO providers from this SDD.",
        "- MUST NOT change runtime role behavior in the doc-only slice.",
        "## Implementation Slices",
        "## Acceptance Criteria",
    ]
    return "\n\n".join(sections) + "\n"


def valid_contract() -> dict[str, object]:
    phases = [
        "agent-os-sdd",
        "mission-router-state",
        "codebase-mapper-specialists",
        "capability-validation",
        "phase-compiler-verification",
        "uat-learning-cockpit",
    ]
    return {
        "schema": "ao-operator/agent-os-sdd-contract/v1",
        "classification": "COMPLEX",
        "shape": "greenfield",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "problem": "AO Operator needs a typed Agent OS layer above AO Runtime.",
        "success_criteria": [
            "Agent OS SDD exists",
            "validation contract exists",
            "operator slice records non-dispatching evidence",
        ],
        "negative_constraints": [
            "MUST NOT dispatch AO providers from this SDD",
            "MUST NOT alter runtime role behavior in this slice",
        ],
        "sensitive_fields": [
            "provider OAuth credentials",
            "provider transcripts",
            "project state artifacts",
        ],
        "trigger_hints": ["docs", "provider/runtime boundaries", "release"],
        "phases": phases,
        "shall_statements": [
            {
                "id": "SHALL-001",
                "condition": "WHEN a AO Operator task is accepted",
                "actor": "mission router",
                "requirement": "SHALL classify route, shape, risk, and required verification before AO dispatch",
                "rationale": "Factory work needs a typed entrypoint before role fan-out.",
            },
            {
                "id": "SHALL-002",
                "condition": "WHEN a role is selected",
                "actor": "capability validator",
                "requirement": "SHALL verify declared capabilities, allowed tools, reads, writes, and risk gates",
                "rationale": "Roles must not execute outside their contract.",
            },
            {
                "id": "SHALL-003",
                "condition": "WHEN a phase is compiled",
                "actor": "phase compiler",
                "requirement": "SHALL produce AO waves, dependencies, and verification matrix entries",
                "rationale": "Plans must become inspectable AO execution graphs.",
            },
            {
                "id": "SHALL-004",
                "condition": "WHEN a phase closes",
                "actor": "operator cockpit",
                "requirement": "SHALL show blocker state, approval state, evidence paths, and next safe command",
                "rationale": "Operators need one current source of truth.",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "shall_refs": ["SHALL-001", "SHALL-002"],
                "oracle": "SDD contains required Agent OS architecture sections",
                "verification": "python3 scripts/check_agent_os_sdd.py --json",
                "file_hints": ["docs/sdd/13-agent-os.md"],
                "risk_tags": ["docs", "runtime-boundary"],
            },
            {
                "id": "AC-002",
                "shall_refs": ["SHALL-003", "SHALL-004"],
                "oracle": "Contract records doc-only dispatch posture",
                "verification": "python3 scripts/check_agent_os_sdd.py --json",
                "file_hints": ["docs/contracts/ao-operator-agent-os.contract.json"],
                "risk_tags": ["release", "provider-boundary"],
            },
        ],
        "slices": [
            {
                "id": "agent-os-sdd-contract",
                "depends_on": [],
                "reads": ["docs/sdd/12-bounded-live-acceptance.md"],
                "writes": [
                    "docs/sdd/13-agent-os.md",
                    "docs/contracts/ao-operator-agent-os.contract.json",
                    "run-artifacts/remote-transfer-v2-stress-live/agent-os-sdd-validation.json",
                ],
                "acceptance": ["AC-001", "AC-002"],
                "verification": "python3 scripts/check_agent_os_sdd.py --write-output --json",
            }
        ],
    }


def write_valid_agent_os_files(root: Path) -> None:
    write_file(root / "docs/sdd/13-agent-os.md", valid_sdd())
    path = root / "docs/contracts/ao-operator-agent-os.contract.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid_contract()), encoding="utf-8")


def test_agent_os_sdd_contract_passes_without_dispatch(tmp_path):
    write_valid_agent_os_files(tmp_path)

    payload = check_agent_os_sdd.build_report(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["classification"] == "COMPLEX"
    assert payload["shape"] == "greenfield"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["phase_count"] == 6
    assert payload["current_state"] == "AGENT_OS_SDD_ACCEPTED_NOT_IMPLEMENTED"


def test_agent_os_sdd_fails_when_required_section_is_missing(tmp_path):
    write_valid_agent_os_files(tmp_path)
    write_file(tmp_path / "docs/sdd/13-agent-os.md", valid_sdd().replace("## Operator Cockpit\n\n", ""))

    payload = check_agent_os_sdd.build_report(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("Operator Cockpit" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_agent_os_sdd_fails_if_contract_authorizes_dispatch(tmp_path):
    write_valid_agent_os_files(tmp_path)
    contract_path = tmp_path / "docs/contracts/ao-operator-agent-os.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["dispatch_authorized"] = True
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    payload = check_agent_os_sdd.build_report(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("dispatch_authorized" in error for error in payload["errors"])
    assert payload["live_providers_run"] is False


def test_cli_write_output_uses_default_report(tmp_path, capsys):
    write_valid_agent_os_files(tmp_path)

    code = check_agent_os_sdd.main(["--root", str(tmp_path), "--write-output", "--json"])

    output = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-sdd-validation.json"
    assert code == 0
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
