from __future__ import annotations

from pathlib import Path

import pytest

import prepare_live_profile_dry_run


def test_prep_commands_prepare_50_slice_live_profile_without_live_run():
    commands = prepare_live_profile_dry_run.prep_commands(50)
    text = [" ".join(command) for command in commands]

    assert "python3 scripts/generate_stress_fixture.py --live-slices 50 --write-live-profile" in text
    assert any("scripts/factory_run.py" in command and "--dry-run" in command for command in text)
    assert any("scripts/validate_intake.py" in command for command in text)
    assert any("scripts/validate_factory.py" in command for command in text)
    assert all("--run" not in command for command in text)


def test_report_payload_marks_pass_only_when_commands_pass():
    payload = prepare_live_profile_dry_run.report_payload(
        slices=50,
        worktree=Path("/tmp/ao-operator-live-profile-prep-50"),
        commands=[{"command": "ok", "exit": 0}],
        preserved_main_evidence=True,
    )

    assert payload["verdict"] == "PASS"
    assert payload["mode"] == "dry-run-temp-worktree"
    assert payload["tasks"] == 107
    assert payload["accepted_live_evidence_preserved_in_main"] is True


def test_report_payload_fails_when_a_command_fails():
    payload = prepare_live_profile_dry_run.report_payload(
        slices=50,
        worktree=Path("/tmp/ao-operator-live-profile-prep-50"),
        commands=[{"command": "bad", "exit": 1}],
        preserved_main_evidence=True,
    )

    assert payload["verdict"] == "FAIL"


def test_worktree_must_be_outside_repository():
    unsafe = prepare_live_profile_dry_run.ROOT / "run-artifacts/remote-transfer-v2-stress-live"

    with pytest.raises(ValueError, match="outside the main repository"):
        prepare_live_profile_dry_run.resolve_safe_worktree(unsafe)


def test_report_must_stay_under_profile_prep_directory():
    safe = prepare_live_profile_dry_run.resolve_safe_report(
        Path("run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json")
    )

    assert safe.parent == prepare_live_profile_dry_run.REPORT_ROOT
    with pytest.raises(ValueError, match="profile-prep"):
        prepare_live_profile_dry_run.resolve_safe_report(
            Path("run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-status.md")
        )


def test_evidence_preserved_requires_exact_snapshot_match():
    before = {"run-artifacts/remote-transfer-v2-stress-live/a.md": "abc"}

    assert prepare_live_profile_dry_run.evidence_preserved(before, dict(before)) is True
    assert prepare_live_profile_dry_run.evidence_preserved(before, {}) is False
    assert prepare_live_profile_dry_run.evidence_preserved(before, {"run-artifacts/remote-transfer-v2-stress-live/a.md": "def"}) is False
