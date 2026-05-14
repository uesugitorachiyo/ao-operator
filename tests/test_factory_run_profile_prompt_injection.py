"""Regression test for profile-derived prompts: every non-root profile role
must carry a "Prior Role Handoff Content" section so the agent can synthesize
its scoped artifact without reading run-artifacts/<slug>/roles/*.md from disk.

Surfaced by the v0.1.1 T5 live evidence smoke (Mac, 2026-05-09): the
`report-writer` role returned BLOCKED because its prompt promised an
"Injected Artifact Contents" section but the profile-derived path did not
actually inject upstream role handoffs. The default-chain gate was
hardcoded to {integrator, evaluator-closer, *-reviewer} and skipped
profile roles entirely.

Default-chain parity is preserved by tests in test_prompt_contract.py and
test_factory_run_default_profile_parity.py — those continue to pass
because _active_profile() returns None outside profile mode.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import factory_run


@pytest.fixture(autouse=True)
def _reset_active_profile():
    factory_run._set_active_profile(None)
    yield
    factory_run._set_active_profile(None)


def _intake(slug: str = "factoryv3-test-slug") -> factory_run.Intake:
    return factory_run.Intake(
        slug=slug,
        brief_path=Path("brief.md"),
        brief="Goal: profile prompt injection regression",
        classification="COMPLEX",
        shape="greenfield",
        blocked=False,
        blocker="greenfield gate satisfied",
        acceptance=["evidence report renders"],
        scoped_reads=[],
        scoped_writes=["docs/evidence/<slug>/evidence-report.md"],
    )


def _task_for(profile: dict, role_id: str) -> dict:
    role = profile["roles_by_id"][role_id]
    return {
        "id": role["id"],
        "role": role["role"],
        "deps": list(role.get("deps", [])),
        "reads": list(role.get("reads", [])),
        "writes": list(role.get("writes", [])),
        "ralph_loop_configured": False,
    }


def _private_linear_profile() -> dict:
    roles = [
        {
            "id": "intake",
            "role": "Intake",
            "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
            "deps": [],
            "reads": ["task brief"],
            "writes": ["run-artifacts/<slug>/roles/intake.md"],
            "skills": [],
            "instructions": [],
        },
        {
            "id": "policy-binder",
            "role": "Policy Binder",
            "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
            "deps": ["intake"],
            "reads": ["run-artifacts/<slug>/roles/intake.md"],
            "writes": ["run-artifacts/<slug>/roles/policy-binder.md"],
            "skills": [],
            "instructions": [],
        },
        {
            "id": "approval-planner",
            "role": "Approval Planner",
            "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
            "deps": ["policy-binder"],
            "reads": ["run-artifacts/<slug>/roles/policy-binder.md"],
            "writes": ["run-artifacts/<slug>/roles/approval-planner.md"],
            "skills": [],
            "instructions": [],
        },
        {
            "id": "secured-implementer",
            "role": "Secured Implementer",
            "provider_key": "FACTORY_V3_IMPLEMENTER_PROVIDER",
            "deps": ["approval-planner"],
            "reads": [
                "run-artifacts/<slug>/roles/policy-binder.md",
                "run-artifacts/<slug>/roles/approval-planner.md",
            ],
            "writes": ["run-artifacts/<slug>/roles/secured-implementer.md"],
            "skills": [],
            "instructions": [],
            "is_mutator": True,
        },
        {
            "id": "policy-auditor",
            "role": "Policy Auditor",
            "provider_key": "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
            "deps": ["secured-implementer"],
            "reads": [
                "run-artifacts/<slug>/roles/policy-binder.md",
                "run-artifacts/<slug>/roles/approval-planner.md",
                "run-artifacts/<slug>/roles/secured-implementer.md",
            ],
            "writes": ["run-artifacts/<slug>/roles/policy-auditor.md"],
            "skills": [],
            "instructions": [],
        },
        {
            "id": "compliance-reporter",
            "role": "Compliance Reporter",
            "provider_key": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
            "deps": ["policy-auditor"],
            "reads": [
                "run-artifacts/<slug>/roles/intake.md",
                "run-artifacts/<slug>/roles/policy-binder.md",
                "run-artifacts/<slug>/roles/approval-planner.md",
                "run-artifacts/<slug>/roles/policy-auditor.md",
            ],
            "writes": ["docs/compliance/<slug>/compliance-report.md"],
            "skills": [],
            "instructions": [],
        },
    ]
    return factory_run._validate_profile(
        "private-linear",
        {
            "profile": "private-linear",
            "schema": factory_run.PROFILE_SCHEMA_ID,
            "version": factory_run.PROFILE_VERSION,
            "description": "synthetic private linear profile",
            "common_instructions": [],
            "roles": roles,
        },
    )


def test_evidence_report_writer_prompt_carries_prior_role_handoff_section():
    """The report-writer role (final, deps=['qa-checklist']) must inline
    upstream role handoff content under the 'Prior Role Handoff Content'
    header so it can render schema ao-operator/evidence-report/v1 without
    looking at run-artifacts/<slug>/roles/*.md on disk."""
    profile = factory_run._load_profile("evidence")
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "report-writer")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    assert "### Prior Role Handoff Content" in body, (
        "profile-derived report-writer prompt is missing the upstream role "
        "handoff injection — agents will BLOCK because the prompt forbids "
        "looking on disk for run-artifacts/<slug>/roles/*.md but provides no "
        "inlined alternative. Live T5 smoke regressed without this."
    )
    # Each upstream dep must be referenced under the handoff section.
    for dep in ("qa-checklist",):
        assert dep in body, f"upstream dep {dep} missing from prompt"


def test_private_linear_final_role_prompt_carries_prior_role_handoff_section():
    """Private linear final role (deps non-empty) must also inline prior-role
    handoff content so it can render schema ao-operator/compliance-report/v1."""
    profile = _private_linear_profile()
    factory_run._set_active_profile(profile)

    role_ids = [role["id"] for role in profile["roles"]]
    is_dep_of_someone = {rid: False for rid in role_ids}
    for role in profile["roles"]:
        for dep in role.get("deps", []):
            is_dep_of_someone[dep] = True
    final_id = next(
        rid for rid in role_ids
        if not is_dep_of_someone[rid]
        and profile["roles_by_id"][rid].get("deps")
    )
    task = _task_for(profile, final_id)
    providers = {rid: "codex" for rid in role_ids}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    assert "### Prior Role Handoff Content" in body


def test_evidence_root_role_intake_has_no_prior_role_handoff_section():
    """Root profile role (intake, deps=[]) has no upstream to inject; the
    Prior Role Handoff Content section must be absent. This guards against
    overly-broad gates that would inject empty handoff blocks."""
    profile = factory_run._load_profile("evidence")
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "intake")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    assert "### Prior Role Handoff Content" not in body


def test_default_chain_implementer_slice_still_omits_prior_role_handoff():
    """Default-chain parity: implementer-slice historically does NOT receive
    the 'Prior Role Handoff Content' block — only integrator/evaluator-closer
    /reviewers do. Extending the gate for profile roles must not regress
    this. (No active profile is set; _active_profile() is None per fixture.)"""
    intake = _intake()
    task = {
        "id": "implementer-slice",
        "role": "Implementer Slice",
        "deps": ["factory-manager"],
        "reads": ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"],
        "writes": ["src/feature.py"],
        "ralph_loop_configured": False,
    }
    body = factory_run.prompt_body(
        intake,
        task,
        {"implementer-slice": "codex"},
        contract_path=None,
    )

    assert "### Prior Role Handoff Content" not in body


# --- F-E private linear sandbox path regression suite ----------------------
#
# Closes the post-AO-write gap captured in
# run-artifacts/release-v0.1.1/mac/PROGRESS-t6.md (lane head f0be2fa9):
# `write_role_artifacts()` writes `run-artifacts/<slug>/roles/<dep>.md`
# files only AFTER the AO `run` completes, but the agent prompts list
# those paths under "Scoped Reads". The Mac codex auditor on the
# T9-secagent-live retry `sed`-ed the paths during its turn and
# returned BLOCKED with "No such file or directory". Annotating each
# inlined-handoff path under Scoped Reads with an explicit
# "do not read from disk during this turn" suffix discourages the
# agent from reaching for the on-disk file and steers it to the
# already-inlined "Injected Artifact Contents" section.

_F_E_INLINE_NOTE = (
    "content inlined below in 'Injected Artifact Contents'; "
    "do not read from disk during this turn"
)


def test_private_linear_policy_auditor_scoped_reads_annotate_inlined_role_artifacts():
    """The policy-auditor role lists run-artifacts/<slug>/roles/policy-binder.md
    and approval-planner.md as Scoped Reads. F-E annotates those bullets so
    the agent stops `sed`-ing files that don't exist until post-AO."""
    profile = _private_linear_profile()
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "policy-auditor")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    for dep in ("policy-binder", "approval-planner"):
        path = f"run-artifacts/factoryv3-test-slug/roles/{dep}.md"
        line = next(
            (line for line in body.splitlines() if line.lstrip("- ").startswith(path)),
            None,
        )
        assert line is not None, (
            f"Scoped Reads is missing a bullet for {path}; full body:\n{body}"
        )
        assert _F_E_INLINE_NOTE in line, (
            f"Scoped Reads bullet for {path} is missing F-E inline-handoff "
            f"annotation. Codex on Mac was `sed`-ing this path during the AO "
            f"turn even though the file is written post-AO. Got: {line}"
        )


def test_private_linear_compliance_reporter_scoped_reads_annotate_inlined_role_artifacts():
    """compliance-reporter has 4 upstream role-artifact reads (intake,
    policy-binder, approval-planner, policy-auditor); all four must be
    annotated as inlined."""
    profile = _private_linear_profile()
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "compliance-reporter")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    for dep in ("intake", "policy-binder", "approval-planner", "policy-auditor"):
        path = f"run-artifacts/factoryv3-test-slug/roles/{dep}.md"
        assert any(_F_E_INLINE_NOTE in line for line in body.splitlines() if path in line), (
            f"compliance-reporter Scoped Reads bullet for {path} must carry "
            f"F-E annotation. Body:\n{body}"
        )


def test_private_linear_intake_root_role_has_no_inline_annotation():
    """Root role (intake, deps=[]) has no inlined upstream artifacts. The
    F-E annotation must NOT fire — its Scoped Reads ('task brief',
    'docs/sdd/...') are real disk paths the agent should read."""
    profile = _private_linear_profile()
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "intake")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    assert _F_E_INLINE_NOTE not in body, (
        "intake has no upstream role artifacts; the F-E inline annotation "
        "should not appear. Body:\n" + body
    )


def test_default_chain_implementer_slice_does_not_get_inline_annotation():
    """Default-chain parity: implementer-slice does not have inlined
    upstream role artifacts (only integrator/evaluator-closer/reviewers do).
    F-E must not regress non-inlined tasks. (No active profile per fixture.)"""
    intake = _intake()
    task = {
        "id": "implementer-slice",
        "role": "Implementer Slice",
        "deps": ["factory-manager"],
        "reads": [
            "docs/specs/<slug>-spec.md",
            "docs/plans/<slug>-plan.md",
            "run-artifacts/<slug>/roles/factory-manager.md",
        ],
        "writes": ["src/feature.py"],
        "ralph_loop_configured": False,
    }
    body = factory_run.prompt_body(
        intake,
        task,
        {"implementer-slice": "codex"},
        contract_path=None,
    )

    assert _F_E_INLINE_NOTE not in body


def test_default_chain_integrator_does_get_inline_annotation():
    """Default-chain integrator inlines all upstream role artifacts
    (artifact_injections gate at task_id == 'integrator'). F-E annotation
    must fire so codex doesn't `sed` the role artifact files. (No active
    profile per fixture.)"""
    intake = _intake()
    task = {
        "id": "integrator",
        "role": "Integrator",
        "deps": ["reviewer-slice"],
        "reads": [
            "docs/specs/<slug>-spec.md",
            "run-artifacts/<slug>/roles/reviewer-slice.md",
        ],
        "writes": ["run-artifacts/<slug>/roles/integrator.md"],
        "ralph_loop_configured": False,
    }
    body = factory_run.prompt_body(
        intake,
        task,
        {"integrator": "codex"},
        contract_path=None,
    )
    expected_path = "run-artifacts/factoryv3-test-slug/roles/reviewer-slice.md"
    line = next(
        (line for line in body.splitlines() if line.lstrip("- ").startswith(expected_path)),
        None,
    )
    assert line is not None and _F_E_INLINE_NOTE in line, (
        f"integrator Scoped Reads bullet for {expected_path} must carry F-E "
        f"annotation (default-chain parity guard). Got: {line!r}"
    )


def test_private_linear_policy_auditor_inlines_transitive_handoff_for_each_read():
    """F-E substantive guard: the auditor's transitive role-artifact reads
    (policy-binder, approval-planner) must each surface inside 'Prior Role
    Handoff Content' — not just be annotated on the Scoped Reads line.

    Before F-E, only direct deps were inlined; the auditor's deps =
    ['secured-implementer'], so policy-binder and approval-planner had no
    presence in the prompt body, and codex's `sed` of the on-disk paths was
    its only fallback for missing content. After F-E, the prompt must
    contain at minimum a placeholder block for each transitive read so the
    agent has a rendered alternative to reaching for disk."""
    profile = _private_linear_profile()
    factory_run._set_active_profile(profile)

    task = _task_for(profile, "policy-auditor")
    providers = {role["id"]: "codex" for role in profile["roles"]}

    body = factory_run.prompt_body(_intake(), task, providers, contract_path=None)

    assert "### Prior Role Handoff Content" in body, (
        "F-E premise: auditor must carry the Prior Role Handoff Content "
        "section so transitive reads can be inlined into it."
    )
    handoff_section_start = body.index("### Prior Role Handoff Content")
    handoff_section = body[handoff_section_start:]
    for dep in ("policy-binder", "approval-planner"):
        # Either fenced content (file existed at render-time) or the
        # placeholder block — both surface the dep id by name.
        assert dep in handoff_section, (
            f"transitive read {dep} must appear inside Prior Role Handoff "
            f"Content; without it codex has no rendered alternative to "
            f"`sed`-ing the on-disk path. Section:\n{handoff_section[:1500]}"
        )


def test_role_artifact_dep_ids_extracts_transitive_reads_only():
    """Unit-level guard for the helper that drives F-E: the extractor must
    pick up every run-artifacts/<slug>/roles/*.md path in task['reads'] and
    NOT pick up unrelated paths (specs, plans, AO event logs, etc.)."""
    intake = _intake()
    task = {
        "id": "policy-auditor",
        "role": "Policy Auditor",
        "deps": ["secured-implementer"],
        "reads": [
            "run-artifacts/<slug>/roles/policy-binder.md",
            "run-artifacts/<slug>/roles/approval-planner.md",
            "AO event log for slug",
            "docs/specs/<slug>-spec.md",
        ],
        "writes": [],
        "ralph_loop_configured": False,
    }
    extracted = factory_run._role_artifact_dep_ids_from_reads(intake, task)
    assert extracted == ["policy-binder", "approval-planner"], (
        f"expected transitive role-artifact dep ids only, in order, "
        f"deduped; got {extracted!r}"
    )
