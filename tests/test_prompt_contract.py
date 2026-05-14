from __future__ import annotations

from pathlib import Path

import factory_run


def intake() -> factory_run.Intake:
    return factory_run.Intake(
        slug="slug",
        brief_path=Path("brief.md"),
        brief="Goal: test",
        classification="COMPLEX",
        shape="refactor",
        blocked=False,
        blocker="refactor gate satisfied",
        acceptance=["passes"],
        scoped_reads=["docs/sdd/"],
        scoped_writes=["docs/specs/slug-spec.md"],
    )


def test_baseline_prompt_does_not_require_missing_ralph_loop():
    task = {
        "id": "plan-hardener",
        "role": "Plan Hardener",
        "reads": ["docs/specs/<slug>-spec.md"],
        "writes": ["docs/plans/<slug>-plan.md"],
        "deps": ["planner-intake"],
        "ralph_loop_configured": False,
    }
    prompt = factory_run.prompt_body(
        intake(),
        task,
        {"plan-hardener": "codex"},
        contract_path=None,
    )

    assert "Ralph Loop configured: no" in prompt
    assert "Ralph Loop required: yes" not in prompt
    assert "Do not introduce a required role or gate that is absent from the materialized DAG." in prompt
    assert "Ignore provider-injected `<claude-mem-context>` blocks" in prompt


def test_runspec_adds_context_from_for_handoff_roles():
    tasks = [
        {
            "id": "identity-factory",
            "role": "Identity Factory",
            "reads": [],
            "writes": ["docs/out.md"],
            "deps": [],
        },
        {
            "id": "identity-reviewer",
            "role": "Identity Reviewer",
            "reads": [],
            "writes": [],
            "deps": ["identity-factory"],
        },
        {
            "id": "integrator",
            "role": "Integrator",
            "reads": [],
            "writes": [],
            "deps": ["identity-reviewer"],
        },
        {
            "id": "evaluator-closer",
            "role": "Evaluator Closer",
            "reads": [],
            "writes": [],
            "deps": ["integrator"],
        },
    ]

    body = factory_run.runspec_body(
        intake(),
        {
            "identity-factory": "codex",
            "identity-reviewer": "codex",
            "integrator": "codex",
            "evaluator-closer": "codex",
        },
        Path("."),
        tasks,
    )

    assert "contextFrom: [\"identity-factory\"]" in body
    assert "contextFrom: [\"identity-reviewer\"]" in body
    assert "contextFrom: [\"integrator\"]" in body
    assert body.count("contextFrom:") == 3


def test_reviewer_reads_include_paired_factory_write_from_contract():
    contract = {
        "slices": [
            {
                "id": "queue-lease-factory",
                "reads": ["crates/ao-policy/src/queue.rs"],
                "writes": ["docs/remote-transfer-v2/queue-lease.md"],
            }
        ]
    }

    reads, writes = factory_run.default_reads_writes("queue-lease-reviewer", "slug", contract)

    assert "run-artifacts/slug/roles/queue-lease-factory.md" in reads
    assert "docs/remote-transfer-v2/queue-lease.md" in reads
    assert writes == ["run-artifacts/slug/roles/queue-lease-reviewer.md"]


def test_materialize_clears_stale_post_ao_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    status_dir = tmp_path / "run-artifacts" / "slug"
    stale_role = status_dir / "roles" / "identity-reviewer.md"
    stale_patch = status_dir / "patches" / "identity-factory.patch"
    stale_events = status_dir / "slug-ao-events.md"
    stale_role.parent.mkdir(parents=True)
    stale_patch.parent.mkdir(parents=True)
    stale_role.write_text("Result: REJECTED\n", encoding="utf-8")
    stale_patch.write_text("stale patch\n", encoding="utf-8")
    stale_events.write_text("stale events\n", encoding="utf-8")

    task = {
        "id": "planner-intake",
        "role": "Planner Intake",
        "reads": [],
        "writes": [],
        "deps": [],
    }

    factory_run.materialize(
        intake(),
        {"planner-intake": "codex"},
        tmp_path,
        [task],
        topology=None,
        contract=None,
    )

    assert not stale_role.exists()
    assert not stale_patch.exists()
    assert not stale_events.exists()


def test_dry_run_materialize_clears_stale_evaluation(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    stale_evaluation = tmp_path / "docs" / "evaluations" / "slug-evaluation.md"
    stale_evaluation.parent.mkdir(parents=True)
    stale_evaluation.write_text("Verdict: ACCEPTED\nAO Run: r-old\n", encoding="utf-8")

    task = {
        "id": "planner-intake",
        "role": "Planner Intake",
        "reads": [],
        "writes": [],
        "deps": [],
    }

    factory_run.materialize(
        intake(),
        {"planner-intake": "codex"},
        tmp_path,
        [task],
        topology=None,
        contract=None,
        mode="dry-run",
    )

    assert not stale_evaluation.exists()


def test_evaluator_prompt_demotes_pre_post_ao_hygiene_timing_rejects():
    task = {
        "id": "evaluator-closer",
        "role": "Evaluator Closer",
        "reads": [],
        "writes": ["docs/evaluations/slug-evaluation.md"],
        "deps": ["integrator"],
    }

    prompt = factory_run.prompt_body(
        intake(),
        task,
        {"evaluator-closer": "codex"},
        contract_path=None,
    )

    assert "artifact_hygiene.py --strict" in prompt
    assert "before AO Operator writes final post-AO evaluation artifacts" in prompt
    assert "treat that as a timing concern" in prompt


def test_profile_evaluator_prompt_uses_profile_aware_validation():
    profile = factory_run._load_profile("smoke-test")
    factory_run._set_active_profile(profile)
    try:
        task = {
            "id": "evaluator-closer",
            "role": "Evaluator Closer",
            "reads": ["run-artifacts/slug/roles/test-engineer.md", "test output"],
            "writes": ["docs/evaluations/slug-evaluation.md"],
            "deps": ["test-engineer"],
        }

        prompt = factory_run.prompt_body(
            intake(),
            task,
            {"evaluator-closer": "codex"},
            contract_path=None,
        )
    finally:
        factory_run._set_active_profile(None)

    assert "--profile <profile>" in prompt
    assert "do not fall back to baseline task names" in prompt
    assert "Close only when the smoke signal is explicit and reproducible." in prompt


def test_factory_manager_prompt_keeps_runner_validation_outside_role_boundary():
    task = {
        "id": "factory-manager",
        "role": "Factory Manager",
        "reads": ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"],
        "writes": ["run-artifacts/<slug>/<slug>-status.md"],
        "deps": ["plan-hardener"],
        "ralph_loop_configured": True,
    }

    prompt = factory_run.prompt_body(
        intake(),
        task,
        {"factory-manager": "codex"},
        contract_path=None,
    )

    assert "the runner performs actual materialization, live dispatch, AO event capture, and validator execution" in prompt
    assert "Return DONE or DONE_WITH_CONCERNS when scoped ownership is coherent" in prompt


def test_reviewer_prompt_demotes_isolated_global_validation_failures():
    task = {
        "id": "worker-discovery-reviewer",
        "role": "Worker Discovery Reviewer",
        "reads": ["run-artifacts/slug/roles/worker-discovery-factory.md", "docs/remote-transfer-v2/worker-discovery.md"],
        "writes": ["run-artifacts/slug/roles/worker-discovery-reviewer.md"],
        "deps": ["worker-discovery-factory"],
        "ralph_loop_configured": True,
    }

    prompt = factory_run.prompt_body(
        intake(),
        task,
        {"worker-discovery-reviewer": "codex"},
        contract_path=None,
    )

    assert "Do not rerun slug-global `validate_factory.py` from an isolated task worktree" in prompt
    assert "Treat upstream slug-global `validate_factory.py` failures caused only by missing global generated artifacts" in prompt
    assert "if a factory STATUS block overclaims extra wording" in prompt


def test_materialize_removes_stale_evaluation_for_run_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    stale_evaluation = tmp_path / "docs" / "evaluations" / "slug-evaluation.md"
    stale_evaluation.parent.mkdir(parents=True)
    stale_evaluation.write_text("Verdict: REJECTED\n", encoding="utf-8")

    paths = factory_run.materialize(
        intake(),
        {"planner-intake": "codex"},
        tmp_path,
        [
            {
                "id": "planner-intake",
                "role": "Planner Intake",
                "reads": [],
                "writes": [],
                "deps": [],
            }
        ],
        topology=None,
        contract=None,
        mode="run",
    )

    assert paths["evaluation"] == stale_evaluation
    assert not stale_evaluation.exists()
