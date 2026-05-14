from __future__ import annotations

import factory_run


STARTERS = {
    "bug-fix": ["intake", "planner", "implementer", "reviewer", "evaluator-closer"],
    "refactor": ["intake", "planner", "plan-hardener", "implementer", "reviewer", "evaluator-closer"],
    "greenfield": ["intake", "architect", "planner", "implementer", "reviewer", "evaluator-closer"],
    "doc-update": ["intake", "docs-writer", "evaluator-closer"],
    "smoke-test": ["intake", "test-engineer", "evaluator-closer"],
}


def test_starter_profiles_load_and_keep_expected_order():
    for name, expected_ids in STARTERS.items():
        profile = factory_run._load_profile(name)
        assert [role["id"] for role in profile["roles"]] == expected_ids
        assert profile["profile"] == name


def test_starter_profiles_do_not_use_host_tags():
    for name in STARTERS:
        profile = factory_run._load_profile(name)
        for role in profile["roles"]:
            assert "host_tag" not in role


def test_list_profiles_includes_starters():
    names = {entry["name"] for entry in factory_run._list_profiles()}
    assert set(STARTERS).issubset(names)


def test_starter_profiles_project_to_task_fields():
    profile = factory_run._load_profile("bug-fix")
    tasks = factory_run._tasks_from_profile(profile)
    assert tasks[0] == {
        "id": "intake",
        "role": "Intake",
        "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
        "deps": [],
        "reads": ["task brief", "failing test output"],
        "writes": ["run-artifacts/<slug>/roles/intake.md"],
    }
