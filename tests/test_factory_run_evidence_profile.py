"""Shape and contract tests for profiles/evidence.json (T4 SPEC H.3).

These tests validate that the evidence profile JSON conforms to the
design contract in run-artifacts/release-v0.1/mac/profile-design.md
section 3, without yet depending on a profile loader. They protect
against drift between the design doc and the runtime artifact.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PROFILE_PATH = REPO_ROOT / "profiles" / "evidence.json"

EXPECTED_ROLE_IDS = [
    "intake",
    "risk-scoper",
    "test-mapper",
    "evidence-collector",
    "qa-checklist",
    "report-writer",
]


def _load_evidence_profile() -> dict[str, object]:
    with EVIDENCE_PROFILE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_evidence_profile_loads():
    profile = _load_evidence_profile()
    assert profile["profile"] == "evidence"
    assert profile["schema"] == "ao-operator/profile/v1"
    assert profile["version"] == 1


def test_evidence_profile_role_count_and_order():
    profile = _load_evidence_profile()
    role_ids = [r["id"] for r in profile["roles"]]
    assert role_ids == EXPECTED_ROLE_IDS


def test_evidence_profile_no_mutator():
    """Evidence profile is read-only at the role level. No role may
    declare is_mutator: true, and none of the mutator-naming
    conventions (implementer-slice, *-factory) should appear."""
    profile = _load_evidence_profile()
    for role in profile["roles"]:
        assert role.get("is_mutator", False) is False, (
            f"evidence role {role['id']} unexpectedly marked mutator"
        )
        assert role["id"] != "implementer-slice"
        assert not role["id"].endswith("-factory")


def test_evidence_profile_dag_is_linear():
    """Each role except intake depends on exactly one predecessor,
    and intake has empty deps."""
    profile = _load_evidence_profile()
    by_id = {r["id"]: r for r in profile["roles"]}
    assert by_id["intake"]["deps"] == []
    for prev, curr in zip(EXPECTED_ROLE_IDS, EXPECTED_ROLE_IDS[1:]):
        assert by_id[curr]["deps"] == [prev], (
            f"evidence DAG drift: {curr}.deps != [{prev!r}]"
        )


def test_evidence_profile_report_writer_writes_evidence_report():
    """The terminal report-writer role must write under
    docs/evidence/<slug>/evidence-report.md per design doc 3b."""
    profile = _load_evidence_profile()
    by_id = {r["id"]: r for r in profile["roles"]}
    writes = by_id["report-writer"]["writes"]
    assert any("docs/evidence/<slug>/evidence-report.md" in w for w in writes), (
        f"report-writer.writes drift: {writes}"
    )


def test_evidence_profile_role_fields_well_typed():
    profile = _load_evidence_profile()
    for role in profile["roles"]:
        assert isinstance(role["id"], str) and role["id"]
        assert isinstance(role["role"], str) and role["role"]
        assert isinstance(role["provider_key"], str)
        assert role["provider_key"].replace("_", "").isalnum()
        assert role["provider_key"].isupper()
        for list_field in ("deps", "reads", "writes", "skills", "instructions"):
            value = role[list_field]
            assert isinstance(value, list), f"{role['id']}.{list_field} not list"
            for item in value:
                assert isinstance(item, str), (
                    f"{role['id']}.{list_field} contains non-str: {item!r}"
                )


def test_evidence_profile_provider_keys_use_existing_envvars():
    """Per design doc 3a, evidence reuses existing FACTORY_V3_*
    provider env vars; B4 in T4 SPEC bans renaming. Verify each
    provider_key is one of the seven existing keys."""
    allowed = {
        "FACTORY_V3_PLANNER_PROVIDER",
        "FACTORY_V3_PLAN_HARDENER_PROVIDER",
        "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
        "FACTORY_V3_IMPLEMENTER_PROVIDER",
        "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
        "FACTORY_V3_INTEGRATOR_PROVIDER",
        "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
    }
    profile = _load_evidence_profile()
    for role in profile["roles"]:
        assert role["provider_key"] in allowed, (
            f"evidence role {role['id']} uses unknown provider_key "
            f"{role['provider_key']!r}; renaming is out-of-scope per T4 SPEC B4"
        )
