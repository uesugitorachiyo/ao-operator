from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "plan-hardener" / "SKILL.md"


def test_plan_hardener_skill_contract_is_shape_specific():
    text = SKILL.read_text(encoding="utf-8")

    assert "greenfield" in text
    assert "bug-fix" in text
    assert "refactor" in text
    assert "at most five internal hardening passes" in text
    assert "overlapping concrete writes" in text
    assert "verification commands" in text


def test_plan_hardener_skill_rejects_run_level_retry_and_ouroboros():
    text = SKILL.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "Do not add Ouroboros-style MCP servers" in text
    assert "outer retry loops around AO Operator" in text
    assert "does not dispatch providers, run AO, wrap `factory_run.py`" in compact
