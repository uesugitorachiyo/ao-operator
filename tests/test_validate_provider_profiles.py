from __future__ import annotations

import validate_provider_profiles


def test_all_codex_profile_renders_every_core_task_as_codex():
    profile = validate_provider_profiles.validate_profile(
        validate_provider_profiles.PROFILES_DIR / "all-codex.env"
    )

    assert profile["verdict"] == "PASS"
    assert set(profile["rendered_providers"].values()) == {"codex"}


def test_all_antigravity_profile_renders_every_core_task_as_antigravity():
    profile = validate_provider_profiles.validate_profile(
        validate_provider_profiles.PROFILES_DIR / "all-antigravity.env"
    )

    assert profile["verdict"] == "PASS"
    assert set(profile["rendered_providers"].values()) == {"antigravity"}


def test_validate_provider_profiles_passes_for_bundled_profiles():
    payload = validate_provider_profiles.payload()

    assert payload["verdict"] == "PASS"
    assert {profile["profile"] for profile in payload["profiles"]} == {
        "all-claude.env",
        "all-codex.env",
        "all-antigravity.env",
        "mixed-throughput.env",
    }
