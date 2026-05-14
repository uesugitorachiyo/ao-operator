from __future__ import annotations

import json
from pathlib import Path

import gate_b


def _contract(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "classification": "MODERATE",
                "shape": "greenfield",
                "problem": "Need deterministic v0.3 gate validation.",
                "success_criteria": ["Gate B produces a dispatch decision."],
                "constraints": ["Do not dispatch invalid contracts."],
                "sensitive_fields": ["repo paths"],
                "trigger_hints": ["docs"],
                "acceptance_criteria": [
                    {
                        "id": "AC-001",
                        "oracle": "pytest",
                        "verification": "pytest tests/test_gate_b.py",
                    }
                ],
                "slices": [
                    {
                        "id": "slice-01",
                        "reads": ["scripts/validate_intake.py"],
                        "writes": ["scripts/gate_b.py"],
                        "verification": ["python3 scripts/gate_b.py --json"],
                        "merge_owner": "integrator",
                        "rejoin_artifact": "run-artifacts/<slug>/roles/integrator.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _profile(path: Path, *, posture: object | None = None) -> Path:
    data: dict[str, object] = {
        "profile": path.stem,
        "schema": "ao-operator/profile/v1",
        "version": 1,
        "description": "Synthetic profile for Gate B tests.",
        "common_instructions": [],
        "roles": [
            {
                "id": "planner-intake",
                "role": "Planner Intake",
                "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                "deps": [],
                "reads": ["task brief"],
                "writes": ["docs/specs/<slug>-spec.md"],
                "skills": ["skills/factory-intake/SKILL.md"],
                "instructions": ["Validate intake."],
            }
        ],
    }
    if posture is not None:
        data["policy_posture"] = posture
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_gate_b_passes_valid_contract_and_profile(tmp_path: Path):
    contract = _contract(tmp_path / "contract.json")
    profile = _profile(
        tmp_path / "synthetic.json",
        posture={
            "shell": {
                "allow_prefixes": ["python3"],
                "require_approval_for": [],
                "deny_prefixes": ["rm -rf"],
            },
            "fs": {
                "write_scopes_must_match_contract": True,
                "deny_outside_workspace": True,
            },
            "network": {"egress_default": "deny", "allow_hosts": []},
            "secrets": {
                "forbidden_env": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
                "require_approval_for_read": True,
            },
        },
    )

    report = gate_b.run_gate(
        repo=tmp_path,
        slug="synthetic",
        intake_artifacts=[contract],
        profile_path=profile,
    )

    assert report["verdict"] == "PASS"
    assert report["role_contracts"][0]["writes"] == ["docs/specs/synthetic-spec.md"]
    assert report["spec"]["schema"] == "ao-operator/gate-b/spec/v1"
    assert report["constitution"]["schema"] == "ao-operator/gate-b/constitution/v1"
    assert report["validators"]["spec_kit_analyze"]["verdict"] == "PASS"
    assert report["partition"]["verdict"] == "PASS"
    assert report["spec"]["partition_slices"][0]["rejoin_artifact"] == (
        "run-artifacts/synthetic/roles/integrator.md"
    )
    assert report["spec"]["roles"][0]["allowed_artifacts"] == [
        "run-artifacts/synthetic/roles/planner-intake.md",
        "docs/specs/synthetic-spec.md",
    ]


def test_gate_b_rejects_malformed_policy_posture(tmp_path: Path):
    contract = _contract(tmp_path / "contract.json")
    profile = _profile(tmp_path / "broken.json", posture={"network": {"egress_default": "maybe"}})

    report = gate_b.run_gate(
        repo=tmp_path,
        slug="synthetic",
        intake_artifacts=[contract],
        profile_path=profile,
    )

    assert report["verdict"] == "FAIL"
    assert any("policy_posture.shell" in error for error in report["errors"])
    assert any("egress_default" in error for error in report["errors"])


def test_gate_b_spec_kit_analyze_rejects_non_rfc_constitution():
    spec = {
        "schema": "ao-operator/gate-b/spec/v1",
        "roles": [
            {
                "id": "planner-intake",
                "writes": ["docs/specs/demo-spec.md"],
                "role_artifact": "run-artifacts/demo/roles/planner-intake.md",
                "allowed_artifacts": ["run-artifacts/demo/roles/planner-intake.md"],
            }
        ],
    }
    constitution = {
        "schema": "ao-operator/gate-b/constitution/v1",
        "requirements": [{"id": "BAD-001", "text": "Maybe validate something later."}],
    }

    result = gate_b.spec_kit_analyze(spec, constitution)

    assert result["verdict"] == "FAIL"
    assert any("EARS trigger" in error for error in result["errors"])
    assert any("RFC-2119" in error for error in result["errors"])


def test_gate_b_partition_rejects_overlapping_writes():
    result = gate_b.validate_partition_slices(
        [
            {
                "id": "slice-1",
                "reads": ["docs/specs/<slug>-spec.md"],
                "writes": ["scripts/shared.py"],
                "verification": ["pytest tests/test_gate_b.py"],
                "merge_owner": "integrator",
                "rejoin_artifact": "run-artifacts/<slug>/roles/integrator.md",
            },
            {
                "id": "slice-2",
                "reads": ["docs/specs/<slug>-spec.md"],
                "writes": ["scripts/shared.py"],
                "verification": ["pytest tests/test_gate_b.py"],
                "merge_owner": "integrator",
                "rejoin_artifact": "run-artifacts/<slug>/roles/integrator.md",
            },
        ],
        "demo",
    )

    assert result["verdict"] == "FAIL"
    assert any("overlaps with slice-1" in error for error in result["errors"])


def test_gate_b_partition_rejects_missing_rejoin_contract():
    result = gate_b.validate_partition_slices(
        [
            {
                "id": "slice-1",
                "reads": ["docs/specs/<slug>-spec.md"],
                "writes": ["scripts/one.py"],
                "verification": ["pytest tests/test_gate_b.py"],
            }
        ],
        "demo",
    )

    assert result["verdict"] == "FAIL"
    assert any("merge_owner is required" in error for error in result["errors"])
    assert any("rejoin_artifact must be a concrete path" in error for error in result["errors"])
