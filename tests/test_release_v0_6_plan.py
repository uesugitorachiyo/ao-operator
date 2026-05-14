from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "run-artifacts/release-v0.6/PLAN.md"
CLOSURE = ROOT / "run-artifacts/release-v0.6/CLOSURE.md"


def test_v0_6_plan_records_public_launch_scope() -> None:
    body = PLAN.read_text(encoding="utf-8")

    required = [
        "AO Operator v0.6 - Public OSS Launch Prep",
        "Public naming decision resolved as AO Operator",
        "Workflow-as-data export/import added",
        "Starter profiles, starter briefs, and Spec-Kit aliases added",
        "Hero demo assets and HN draft added",
        "Public README refresh",
        "Release notes for v0.6",
    ]
    for text in required:
        assert text in body


def test_v0_6_plan_preserves_launch_boundaries() -> None:
    body = PLAN.read_text(encoding="utf-8")

    required = [
        "no provider API",
        "No enterprise compliance package",
        "No SOC2 or HIPAA-specific templates",
        "No multi-provider router",
        "No hosted execution service",
        "No public AO Runtime launch in this release",
        "No HN, X, Reddit, or Product Hunt submission by an agent",
        "No domain purchase or GitHub organization claim by an agent",
    ]
    for text in required:
        assert text in body


def test_v0_6_closure_records_tagged_state() -> None:
    body = CLOSURE.read_text(encoding="utf-8")

    required = [
        "`v0.6.0` launch-prep candidate is tagged and pushed",
        "v0.6.0 -> eb58482a",
        "Post-tag repo maintenance is conditional",
    ]
    for text in required:
        assert text in body

    assert "Tagging Plan" not in body
    assert "create and push annotated tag `v0.6.0`" not in body
