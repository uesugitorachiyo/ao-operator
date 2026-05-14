"""Tests for the profile loader (T4 SPEC H.1).

Covers _load_profile, _validate_profile, and _list_profiles in
scripts/factory_run.py. Validation rules per T4 SPEC D.1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import factory_run


def test_load_default_profile_from_disk():
    profile = factory_run._load_profile("default")
    assert profile["profile"] == "default"
    assert profile["schema"] == factory_run.PROFILE_SCHEMA_ID
    assert profile["version"] == factory_run.PROFILE_VERSION
    assert "roles_by_id" in profile
    assert "planner-intake" in profile["roles_by_id"]


def test_load_evidence_profile_from_disk():
    profile = factory_run._load_profile("evidence")
    assert profile["profile"] == "evidence"
    assert len(profile["roles"]) == 6


def test_load_public_profiles_from_disk():
    entries = factory_run._list_profiles()
    names = {entry["name"] for entry in entries}
    assert {"default", "evidence"}.issubset(names)
    assert "secure-agent" not in names


def test_rejects_missing_profile_file():
    with pytest.raises(FileNotFoundError):
        factory_run._load_profile("nonexistent-profile-xyzzy")


def _write_profile(tmp_path: Path, name: str, payload: dict) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    target = profiles_dir / f"{name}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _valid_profile(name: str) -> dict:
    return {
        "profile": name,
        "schema": factory_run.PROFILE_SCHEMA_ID,
        "version": factory_run.PROFILE_VERSION,
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


def test_rejects_schema_mismatch(tmp_path):
    payload = _valid_profile("synthetic")
    payload["schema"] = "wrong/schema/v0"
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="schema"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_version_mismatch(tmp_path):
    payload = _valid_profile("synthetic")
    payload["version"] = 2
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="version"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_filename_stem_mismatch(tmp_path):
    payload = _valid_profile("synthetic")
    payload["profile"] = "different-name"
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="profile"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_empty_roles(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"] = []
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="non-empty"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_duplicate_role_ids(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"].append(dict(payload["roles"][0]))
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="duplicate"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_dangling_dep(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["deps"] = ["nonexistent"]
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="dep"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_invalid_provider_key(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["provider_key"] = "lower_case_key"
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="provider_key"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_non_str_in_list_field(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["reads"] = ["valid", 42]
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="reads"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_rejects_non_bool_is_mutator(tmp_path):
    payload = _valid_profile("synthetic")
    payload["roles"][0]["is_mutator"] = "yes"
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(factory_run.ProfileError, match="is_mutator"):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def test_list_profiles_returns_public_profiles():
    entries = factory_run._list_profiles()
    names = {e["name"] for e in entries}
    assert {"default", "evidence"}.issubset(names)
    assert "secure-agent" not in names
    assert "financial-services:earnings-note" in names


def test_list_profiles_handles_missing_directory(tmp_path):
    entries = factory_run._list_profiles(repo_root=tmp_path)
    assert entries == []


def test_load_profile_normalized_dict_has_roles_by_id():
    profile = factory_run._load_profile("default")
    by_id = profile["roles_by_id"]
    assert isinstance(by_id, dict)
    assert by_id["planner-intake"]["role"] == "Planner Intake"


def test_load_profile_preserves_policy_posture_when_present(tmp_path):
    payload = _valid_profile("synthetic")
    payload["policy_posture"] = {
        "network": {"egress_default": "deny"},
        "secrets": {"forbidden_env": ["OPENAI_API_KEY"]},
    }
    _write_profile(tmp_path, "synthetic", payload)

    profile = factory_run._load_profile("synthetic", repo_root=tmp_path)
    posture = profile["policy_posture"]
    assert posture["network"]["egress_default"] == "deny"
    assert "OPENAI_API_KEY" in posture["secrets"]["forbidden_env"]
