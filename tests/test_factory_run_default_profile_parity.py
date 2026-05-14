"""Parity tests for profiles/default.json (T4 SPEC C1, H.2).

These tests pin profiles/default.json as a byte-faithful representation
of the legacy BASELINE_TASKS / role_instructions / skills_for_task /
default_reads_writes constants in scripts/factory_run.py. If anyone
edits either side, these tests fail until they're brought back into
parity.

The tests deliberately do NOT depend on a profile loader function
existing yet. They read the JSON directly. That is the SPEC's
phase-0 invariant gate (data parity) that must hold before any code
refactor lands.
"""
from __future__ import annotations

import json
from pathlib import Path

import factory_run

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = REPO_ROOT / "profiles" / "default.json"


def _load_default_profile() -> dict[str, object]:
    with DEFAULT_PROFILE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_default_profile_file_exists():
    assert DEFAULT_PROFILE_PATH.exists(), (
        f"profiles/default.json missing at {DEFAULT_PROFILE_PATH}"
    )


def test_default_profile_parses_as_json():
    profile = _load_default_profile()
    assert isinstance(profile, dict)
    assert profile["profile"] == "default"
    assert profile["schema"] == "ao-operator/profile/v1"
    assert profile["version"] == 1


def test_default_profile_has_seven_roles_in_order():
    profile = _load_default_profile()
    role_ids = [r["id"] for r in profile["roles"]]
    expected = [
        "planner-intake",
        "plan-hardener",
        "factory-manager",
        "implementer-slice",
        "reviewer-slice",
        "integrator",
        "evaluator-closer",
    ]
    assert role_ids == expected


def test_default_profile_role_metadata_matches_baseline_tasks():
    profile = _load_default_profile()
    profile_by_id = {r["id"]: r for r in profile["roles"]}
    for legacy_task in factory_run.BASELINE_TASKS:
        task_id = legacy_task["id"]
        assert task_id in profile_by_id, f"profile missing role: {task_id}"
        prof_role = profile_by_id[task_id]
        for field in ("role", "provider_key", "deps", "reads", "writes"):
            assert prof_role[field] == legacy_task[field], (
                f"{task_id}.{field} mismatch: profile={prof_role[field]!r} "
                f"legacy={legacy_task[field]!r}"
            )


def test_default_profile_role_instructions_match_legacy():
    profile = _load_default_profile()
    common = profile["common_instructions"]
    for role in profile["roles"]:
        task_id = role["id"]
        composed = list(common) + list(role["instructions"])
        legacy = factory_run.role_instructions(task_id)
        assert composed == legacy, (
            f"role_instructions({task_id!r}) drift between profile and legacy"
        )


def test_default_profile_skills_match_legacy():
    profile = _load_default_profile()
    for role in profile["roles"]:
        task_id = role["id"]
        assert role["skills"] == factory_run.skills_for_task(task_id), (
            f"skills_for_task({task_id!r}) drift between profile and legacy"
        )


def test_default_profile_reads_writes_match_legacy():
    profile = _load_default_profile()
    for role in profile["roles"]:
        task_id = role["id"]
        legacy_reads, legacy_writes = factory_run.default_reads_writes(
            task_id, slug="<slug>"
        )
        assert role["reads"] == legacy_reads, (
            f"reads drift on {task_id}: profile={role['reads']} "
            f"legacy={legacy_reads}"
        )
        assert role["writes"] == legacy_writes, (
            f"writes drift on {task_id}: profile={role['writes']} "
            f"legacy={legacy_writes}"
        )


def test_default_profile_common_instructions_match_legacy_common_block():
    """The common_instructions list at profile level must equal the
    `common` list at the top of factory_run.role_instructions, which
    we extract by taking role_instructions for any role and stripping
    the role-specific tail.

    Reference: scripts/factory_run.py:891-902.
    """
    profile = _load_default_profile()
    profile_common = profile["common_instructions"]
    legacy_planner = factory_run.role_instructions("planner-intake")
    planner_role = next(
        r for r in profile["roles"] if r["id"] == "planner-intake"
    )
    legacy_common = legacy_planner[: -len(planner_role["instructions"])]
    assert profile_common == legacy_common
