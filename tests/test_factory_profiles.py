"""Direct tests for the deterministic Factory profile contract boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import factory_profiles


def _write_profile(tmp_path: Path, name: str, payload: dict) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    target = profiles_dir / f"{name}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _valid_profile(name: str) -> dict:
    return {
        "profile": name,
        "schema": factory_profiles.PROFILE_SCHEMA_ID,
        "version": factory_profiles.PROFILE_VERSION,
        "description": "synthetic test profile",
        "common_instructions": ["c1"],
        "roles": [
            {
                "id": "alpha",
                "role": "Alpha",
                "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                "deps": [],
                "reads": ["task brief"],
                "writes": ["docs/<slug>/alpha.md"],
                "skills": [],
                "instructions": ["a1"],
            },
        ],
    }


def test_load_profile_normalizes_roles_by_id_from_disk():
    profile = factory_profiles.load_profile("default")

    assert profile["profile"] == "default"
    assert profile["roles_by_id"]["planner-intake"]["role"] == "Planner Intake"


def test_tasks_from_profile_matches_baseline_task_shape():
    profile = factory_profiles.load_profile("default")

    assert factory_profiles.tasks_from_profile(profile) == factory_profiles.BASELINE_TASKS


def test_tasks_from_profile_preserves_deterministic_replay_metadata(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["deterministic"] = True
    payload["roles"][0]["replay_command"] = ["python3", "scripts/check_alpha.py"]
    payload["roles"][0]["replay_outputs"] = ["alpha-report.json"]
    _write_profile(tmp_path, "synthetic", payload)
    profile = factory_profiles.load_profile("synthetic", repo_root=tmp_path)

    task = factory_profiles.tasks_from_profile(profile)[0]

    assert task["deterministic"] is True
    assert task["replay_command"] == ["python3", "scripts/check_alpha.py"]
    assert task["replay_outputs"] == ["alpha-report.json"]


def test_tasks_from_profile_preserves_codex_sandbox(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["codex_sandbox"] = "danger-full-access"
    _write_profile(tmp_path, "synthetic", payload)
    profile = factory_profiles.load_profile("synthetic", repo_root=tmp_path)

    task = factory_profiles.tasks_from_profile(profile)[0]

    assert task["codex_sandbox"] == "danger-full-access"


def test_validate_profile_rejects_unknown_codex_sandbox(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["codex_sandbox"] = "network-party"
    _write_profile(tmp_path, "synthetic", payload)

    with pytest.raises(factory_profiles.ProfileError, match="codex_sandbox"):
        factory_profiles.load_profile("synthetic", repo_root=tmp_path)


def test_smoke_test_starter_declares_deterministic_replay_proof():
    profile = factory_profiles.load_profile("smoke-test")
    tasks = factory_profiles.tasks_from_profile(profile)
    by_id = {task["id"]: task for task in tasks}

    task = by_id["test-engineer"]
    assert task["deterministic"] is True
    assert task["replay_command"] == [
        "python3",
        "-c",
        "from pathlib import Path; Path('smoke-test-deterministic-replay.json').write_text('{\"schema\":\"ao-operator/smoke-test-deterministic-replay/v1\",\"verdict\":\"PASS\"}\\n', encoding='utf-8')",
    ]
    assert task["replay_outputs"] == ["smoke-test-deterministic-replay.json"]


def test_evidence_profile_declares_deterministic_replay_proof():
    profile = factory_profiles.load_profile("evidence")
    tasks = factory_profiles.tasks_from_profile(profile)
    by_id = {task["id"]: task for task in tasks}

    task = by_id["report-writer"]
    assert task["deterministic"] is True
    assert "evidence-profile-deterministic-replay.json" not in task["writes"]
    assert task["replay_command"] == [
        "python3",
        "-c",
        "from pathlib import Path; Path('evidence-profile-deterministic-replay.json').write_text('{\"schema\":\"ao-operator/evidence-profile-deterministic-replay/v1\",\"verdict\":\"PASS\"}\\n', encoding='utf-8')",
    ]
    assert task["replay_outputs"] == ["evidence-profile-deterministic-replay.json"]


def test_validate_profile_rejects_invalid_deterministic_replay_metadata(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["deterministic"] = True
    payload["roles"][0]["replay_command"] = []
    payload["roles"][0]["replay_outputs"] = ["alpha-report.json"]
    _write_profile(tmp_path, "synthetic", payload)

    with pytest.raises(factory_profiles.ProfileError, match="replay_command"):
        factory_profiles.load_profile("synthetic", repo_root=tmp_path)


def test_validate_profile_rejects_dangling_dependency(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["deps"] = ["missing"]
    _write_profile(tmp_path, "synthetic", payload)

    with pytest.raises(factory_profiles.ProfileError, match="dep"):
        factory_profiles.load_profile("synthetic", repo_root=tmp_path)


def test_render_policy_yaml_turns_profile_posture_into_ordered_rules(tmp_path):
    payload = _valid_profile("synthetic")
    payload["policy_posture"] = {
        "shell": {
            "deny_prefixes": ["git push --force"],
            "require_approval_for": ["rm -rf"],
            "allow_prefixes": ["pytest"],
        },
        "network": {"egress_default": "deny"},
        "secrets": {
            "forbidden_env": ["OPENAI_API_KEY"],
            "require_approval_for_read": True,
        },
    }
    _write_profile(tmp_path, "synthetic", payload)
    profile = factory_profiles.load_profile("synthetic", repo_root=tmp_path)

    body = factory_profiles.render_policy_yaml(profile, "demo-slug")

    assert "id: ao-operator-synthetic-demo-slug" in body
    assert "decision: deny" in body
    assert "action.commandPrefix: \"git push --force\"" in body
    assert "action.commandPrefix: \"pytest\"" in body
    assert "action.type: network.egress" in body
    assert "OPENAI_API_KEY" in body


def test_profile_has_policy_posture_is_true_only_for_nonempty_dict():
    assert factory_profiles.profile_has_policy_posture(None) is False
    assert factory_profiles.profile_has_policy_posture({"policy_posture": {}}) is False
    assert factory_profiles.profile_has_policy_posture({"policy_posture": {"shell": {}}}) is True
