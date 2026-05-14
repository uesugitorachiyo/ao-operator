"""T4 phase 4 (SPEC F.1): tests for the profile-derived task graph helper.

`_tasks_from_profile(profile)` projects a profile's `roles` list down to the
task-dict shape the rest of the runner consumes (id, role, provider_key, deps,
reads, writes), dropping the per-role profile-only fields (skills,
instructions, is_mutator) — those are consulted by the four dispatch helpers
via roles_by_id, not by the task graph that reaches materialize() / RunSpec.

When `--profile default` (or no flag) is in effect, the runner does NOT load
the default profile JSON; it stays on the legacy BASELINE_TASKS path, which
already produces a byte-identical default chain. These tests verify that
when the helper IS invoked against the default profile, the projection
matches BASELINE_TASKS field-for-field — so any future code that prefers
the profile path over the legacy constant remains byte-compatible.
"""
from __future__ import annotations

import pytest

import factory_run


@pytest.fixture(autouse=True)
def _reset_active_profile():
    factory_run._set_active_profile(None)
    yield
    factory_run._set_active_profile(None)


def test_tasks_from_profile_default_matches_baseline_tasks_field_for_field():
    profile = factory_run._load_profile("default")
    projected = factory_run._tasks_from_profile(profile)
    assert projected == factory_run.BASELINE_TASKS


def test_tasks_from_profile_evidence_returns_six_linear_roles():
    profile = factory_run._load_profile("evidence")
    tasks = factory_run._tasks_from_profile(profile)
    ids = [task["id"] for task in tasks]
    assert ids == [
        "intake",
        "risk-scoper",
        "test-mapper",
        "evidence-collector",
        "qa-checklist",
        "report-writer",
    ]
    for i, task in enumerate(tasks):
        if i == 0:
            assert task["deps"] == []
        else:
            assert tasks[i - 1]["id"] in task["deps"]


def test_tasks_from_profile_greenfield_returns_six_starter_roles():
    profile = factory_run._load_profile("greenfield")
    tasks = factory_run._tasks_from_profile(profile)
    ids = [task["id"] for task in tasks]
    assert ids == [
        "intake",
        "architect",
        "planner",
        "implementer",
        "reviewer",
        "evaluator-closer",
    ]


def test_tasks_from_profile_strips_profile_only_fields():
    """skills, instructions, is_mutator are not part of the task-graph shape;
    they live on the profile's roles_by_id index and are looked up by the
    four dispatch helpers (role_instructions etc), not by materialize()."""
    profile = factory_run._load_profile("evidence")
    tasks = factory_run._tasks_from_profile(profile)
    for task in tasks:
        assert "skills" not in task
        assert "instructions" not in task
        assert "is_mutator" not in task


def test_tasks_from_profile_preserves_provider_key_per_role():
    profile = factory_run._load_profile("evidence")
    tasks = factory_run._tasks_from_profile(profile)
    for task in tasks:
        assert task["provider_key"].startswith("FACTORY_V3_")
        assert task["provider_key"].endswith("_PROVIDER")


def test_tasks_from_profile_preserves_deterministic_replay_metadata():
    profile = {
        "roles": [
            {
                "id": "deterministic-check",
                "role": "Deterministic Check",
                "provider_key": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
                "deps": [],
                "reads": [],
                "writes": ["run-artifacts/<slug>/roles/deterministic-check.md"],
                "deterministic": True,
                "replay_command": ["python3", "scripts/check_evidence_pack_readiness.py", "--json"],
                "replay_outputs": ["deterministic-check.json"],
                "skills": [],
                "instructions": [],
            }
        ]
    }

    task = factory_run._tasks_from_profile(profile)[0]

    assert task["deterministic"] is True
    assert task["replay_command"] == ["python3", "scripts/check_evidence_pack_readiness.py", "--json"]
    assert task["replay_outputs"] == ["deterministic-check.json"]
