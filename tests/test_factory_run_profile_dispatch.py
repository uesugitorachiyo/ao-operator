"""Dispatch tests for T4 phase 3: role_instructions, skills_for_task,
default_reads_writes, and is_mutator_task should consult the profile
when supplied (or when set via _set_active_profile).

Per T4 SPEC F.2: profile=None falls back to legacy behavior, preserving
byte-for-byte parity for the default chain.
"""
from __future__ import annotations

import pytest

import factory_run


@pytest.fixture(autouse=True)
def _reset_active_profile():
    """Ensure module-level _ACTIVE_PROFILE is None before/after each test."""
    factory_run._set_active_profile(None)
    yield
    factory_run._set_active_profile(None)


def test_role_instructions_legacy_path_when_profile_none():
    """No profile -> legacy branch logic; matches v0.1.0 behavior."""
    legacy = factory_run.role_instructions("planner-intake")
    assert "Confirm classification, shape, acceptance criteria, scoped reads/writes, sensitive fields, and negative constraints." in legacy


def test_role_instructions_uses_profile_when_supplied():
    profile = factory_run._load_profile("evidence")
    out = factory_run.role_instructions("intake", profile=profile)
    assert "Classify the input as one of: pr, branch, patch, brief." in out
    common = list(profile["common_instructions"])
    assert out[: len(common)] == common


def test_role_instructions_uses_active_profile_when_set():
    profile = factory_run._load_profile("evidence")
    factory_run._set_active_profile(profile)
    out = factory_run.role_instructions("risk-scoper")
    assert any("blast radius" in s for s in out)


def test_role_instructions_unknown_task_id_in_profile_falls_back():
    """Profile is in scope but task_id is not in profile.roles_by_id —
    fall through to legacy branch logic. Mutator detection by suffix
    must still work."""
    profile = factory_run._load_profile("evidence")
    out = factory_run.role_instructions("implementer-slice", profile=profile)
    assert any("Scoped Writes" in s for s in out)


def test_skills_for_task_legacy_when_no_profile():
    out = factory_run.skills_for_task("planner-intake")
    assert "skills/factory-intake/SKILL.md" in out


def test_skills_for_task_uses_profile_when_supplied():
    profile = factory_run._load_profile("evidence")
    out = factory_run.skills_for_task("report-writer", profile=profile)
    assert "skills/closure-verification/SKILL.md" in out
    assert "skills/factory-intake/SKILL.md" in out


def test_default_reads_writes_legacy_when_no_profile():
    reads, writes = factory_run.default_reads_writes("planner-intake", slug="demo")
    assert "task brief" in reads
    assert any("docs/specs/" in w for w in writes)


def test_default_reads_writes_uses_profile_when_supplied():
    profile = factory_run._load_profile("evidence")
    reads, writes = factory_run.default_reads_writes("report-writer", slug="demo", profile=profile)
    assert any("docs/evidence/<slug>/evidence-report.md" in w for w in writes)


def test_is_mutator_task_legacy_when_no_profile():
    assert factory_run.is_mutator_task("implementer-slice") is True
    assert factory_run.is_mutator_task("planner-intake") is False


def test_is_mutator_task_honors_profile_is_mutator_field():
    profile = factory_run._load_profile("bug-fix")
    # implementer has is_mutator: true in the starter profile, but its
    # name does not match the legacy implementer-slice / *-factory rules.
    assert factory_run.is_mutator_task("implementer", profile=profile) is True


def test_is_mutator_task_evidence_profile_has_no_mutators():
    profile = factory_run._load_profile("evidence")
    for role in profile["roles"]:
        assert factory_run.is_mutator_task(role["id"], profile=profile) is False, (
            f"evidence role {role['id']} should not be a mutator"
        )


def test_active_profile_with_starter_drives_implementer_mutator_detection():
    profile = factory_run._load_profile("bug-fix")
    factory_run._set_active_profile(profile)
    # Without explicitly passing profile=, is_mutator_task picks it up
    # from the module-level active profile.
    assert factory_run.is_mutator_task("implementer") is True


def test_legacy_callers_unaffected_when_active_profile_none():
    """The four functions called with no profile arg AND no active
    profile must produce the same output as v0.1.0."""
    factory_run._set_active_profile(None)
    assert factory_run.role_instructions("planner-intake")[-1] == (
        "Do not dispatch or implement; this role only validates intake readiness."
    )
    assert factory_run.skills_for_task("planner-intake") == [
        "skills/factory-intake/SKILL.md"
    ]
    reads, writes = factory_run.default_reads_writes("planner-intake", slug="demo")
    assert reads == ["task brief", "docs/sdd/"]
    assert writes == ["docs/specs/<slug>-spec.md"]
