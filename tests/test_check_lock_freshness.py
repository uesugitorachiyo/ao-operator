from __future__ import annotations

import json
from pathlib import Path

import check_lock_freshness as freshness


def _write_ao_runtime(root: Path) -> Path:
    ao = root / "ao-runtime"
    crate = ao / "crates" / "ao-core"
    crate.mkdir(parents=True)
    (ao / "Cargo.toml").write_text(
        """
[workspace]
members = ["crates/ao-core"]

[workspace.package]
version = "0.0.0"
""",
        encoding="utf-8",
    )
    (crate / "Cargo.toml").write_text(
        """
[package]
name = "ao-core"
version.workspace = true
""",
        encoding="utf-8",
    )
    return ao


def test_compare_detects_provider_version_drift():
    errors = freshness.compare(
        {"schema": "ao-operator/lock/v1", "providers": {"codex": "old"}},
        {"schema": "ao-operator/lock/v1", "providers": {"codex": "new"}},
    )

    assert errors == ["providers.codex: expected 'old', observed 'new'"]


def test_check_lock_passes_matching_state(tmp_path: Path, monkeypatch):
    ao = _write_ao_runtime(tmp_path)
    skills = tmp_path / "ao-operator" / "skills" / "factory-intake"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("skill body\n", encoding="utf-8")
    root = tmp_path / "ao-operator"
    lockfile = root / "factory.lock.yaml"

    monkeypatch.setattr(freshness, "command_version", lambda command: "version")
    monkeypatch.setattr(freshness, "git_head", lambda path: "abc12345")
    current = freshness.current_state(root, ao)
    lockfile.write_text(json.dumps(current), encoding="utf-8")

    payload = freshness.check_lock(root=root, lockfile=lockfile, ao_runtime=ao)

    assert payload["verdict"] == "PASS"


def test_check_lock_fails_when_skill_hash_changes(tmp_path: Path, monkeypatch):
    ao = _write_ao_runtime(tmp_path)
    skills = tmp_path / "ao-operator" / "skills" / "factory-intake"
    skills.mkdir(parents=True)
    skill = skills / "SKILL.md"
    skill.write_text("skill body\n", encoding="utf-8")
    root = tmp_path / "ao-operator"
    lockfile = root / "factory.lock.yaml"

    monkeypatch.setattr(freshness, "command_version", lambda command: "version")
    monkeypatch.setattr(freshness, "git_head", lambda path: "abc12345")
    lockfile.write_text(json.dumps(freshness.current_state(root, ao)), encoding="utf-8")
    skill.write_text("changed skill body\n", encoding="utf-8")

    payload = freshness.check_lock(root=root, lockfile=lockfile, ao_runtime=ao)

    assert payload["verdict"] == "FAIL"
    assert any("skills.skills/factory-intake/SKILL.md" in error for error in payload["errors"])
