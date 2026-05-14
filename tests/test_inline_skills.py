"""Regression tests for inline_skills() in factory_run.

inline_skills(task_id) renders a role's relevant skills as INLINED
content (not just paths) into the prompt. This lets bounded providers
(Claude with --tools "") use skill knowledge without a Read tool.

These tests pin the contract: skill body is included, headers identify
each skill, missing-file fallback is graceful, and the per-task skill
selection from skills_for_task is preserved.
"""
from __future__ import annotations

import factory_run

inline_skills = factory_run.inline_skills


def test_planner_intake_inlines_factory_intake_skill():
    out = inline_skills("planner-intake")
    assert "### factory-intake" in out
    assert "Source: `skills/factory-intake/SKILL.md`" in out
    # Body of the skill must be inlined, not just the path.
    assert "Factory Intake" in out  # H1 from the SKILL.md body


def test_factory_manager_inlines_three_skills():
    out = inline_skills("factory-manager")
    # factory-manager's skill set per skills_for_task: factory-intake,
    # spec-forge-contracting, context-offload.
    assert "### factory-intake" in out
    assert "### spec-forge-contracting" in out
    assert "### context-offload" in out


def test_plan_hardener_inlines_dedicated_skill():
    out = inline_skills("plan-hardener")
    assert "### plan-hardener" in out
    assert "Source: `skills/plan-hardener/SKILL.md`" in out
    assert "Shape Lint Rules" in out
    assert "Blocker: NEEDS_CONTEXT" in out


def test_evaluator_closer_inlines_closure_verification_and_mission_monitor():
    out = inline_skills("evaluator-closer")
    assert "### closure-verification" in out
    assert "### mission-monitor-ops" in out
    # Body content of closure-verification must be present.
    assert "Source: `skills/closure-verification/SKILL.md`" in out


def test_inlined_content_is_substantial_not_just_path():
    """Regression guard: the helper must inline the FILE BODY, not just
    return the path string. Pre-fix, skills were wired as bullet paths
    only, which Claude (--tools "") could not Read at runtime. After
    the fix, each skill section must contain >100 chars of body content."""
    out = inline_skills("evaluator-closer")
    sections = [s for s in out.split("### ") if s.strip()]
    # evaluator-closer pulls 3 skills: factory-intake, closure-verification, mission-monitor-ops.
    assert len(sections) == 3
    # Each section should be substantial (header + Source + body), not just a path.
    for section in sections:
        assert len(section) > 100, f"section too short, looks like just a path: {section[:80]!r}"


def test_unknown_task_id_still_returns_factory_intake():
    """factory-intake is the floor: every task gets it. An unknown
    task_id should still return at least factory-intake content."""
    out = inline_skills("totally-made-up-role-id")
    assert "### factory-intake" in out


def test_no_relevant_skills_placeholder_for_empty_set():
    """Defensive: if skills_for_task ever returned [], inline_skills
    must not blow up with a join error. Today skills_for_task always
    returns at least factory-intake, but we test the edge case via a
    monkeypatch in case that contract changes."""
    original = factory_run.skills_for_task
    try:
        factory_run.skills_for_task = lambda _task_id: []  # type: ignore[assignment]
        out = inline_skills("anything")
        assert "No relevant skills" in out
    finally:
        factory_run.skills_for_task = original  # type: ignore[assignment]


def test_missing_skill_file_does_not_crash():
    """If a skill path resolves to a missing file, the helper must
    emit a graceful '(file not found)' marker instead of raising."""
    original = factory_run.skills_for_task
    try:
        factory_run.skills_for_task = lambda _task_id: ["skills/does-not-exist/SKILL.md"]  # type: ignore[assignment]
        out = inline_skills("anything")
        assert "file not found" in out
    finally:
        factory_run.skills_for_task = original  # type: ignore[assignment]
