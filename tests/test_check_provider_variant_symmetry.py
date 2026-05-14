from __future__ import annotations

import json
from pathlib import Path

import check_provider_variant_symmetry as symmetry


def _profile(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "profile": "synthetic",
                "schema": "ao-operator/profile/v1",
                "version": 1,
                "common_instructions": [],
                "roles": [
                    {
                        "id": "planner-intake",
                        "role": "Planner Intake",
                        "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                        "deps": [],
                        "reads": ["task brief"],
                        "writes": ["docs/specs/<slug>-spec.md"],
                        "skills": ["skills/factory-intake/SKILL.md"],
                        "instructions": ["Validate intake."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _template_pair(prompts: Path, role_id: str) -> None:
    role_dir = prompts / role_id
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "claude.md").write_text("# Claude template\n", encoding="utf-8")
    (role_dir / "codex.toml").write_text('model = "codex"\n', encoding="utf-8")


def test_symmetry_passes_when_both_templates_exist(tmp_path: Path):
    _profile(tmp_path / "profiles" / "synthetic.json")
    _template_pair(tmp_path / "prompts", "planner-intake")

    payload = symmetry.check_symmetry(
        root=tmp_path,
        profiles_dir=tmp_path / "profiles",
        prompts_dir=tmp_path / "prompts",
    )

    assert payload["verdict"] == "PASS"
    assert payload["role_count"] == 1


def test_symmetry_fails_when_codex_template_missing(tmp_path: Path):
    _profile(tmp_path / "profiles" / "synthetic.json")
    role_dir = tmp_path / "prompts" / "planner-intake"
    role_dir.mkdir(parents=True)
    (role_dir / "claude.md").write_text("# Claude template\n", encoding="utf-8")

    payload = symmetry.check_symmetry(
        root=tmp_path,
        profiles_dir=tmp_path / "profiles",
        prompts_dir=tmp_path / "prompts",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["roles"][0]["missing"] == ["prompts/planner-intake/codex.toml"]


def test_warn_only_keeps_release_readiness_advisory(tmp_path: Path):
    _profile(tmp_path / "profiles" / "synthetic.json")

    payload = symmetry.check_symmetry(
        root=tmp_path,
        profiles_dir=tmp_path / "profiles",
        prompts_dir=tmp_path / "prompts",
        warn_only=True,
    )

    assert payload["verdict"] == "WARN"
    assert payload["enforced"] is False

