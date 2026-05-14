from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import validate_factory
import generate_stress_fixture


def _stress_tests_enabled() -> bool:
    return os.environ.get("FACTORY_V3_RUN_STRESS_TESTS") == "1"


def _contract(slice_ids: list[str]) -> dict[str, object]:
    return {
        "objective": f"Materialize {len(slice_ids)} slices.",
        "success_criteria": [f"The contract declares {len(slice_ids)} disjoint implementation slices."],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "description": f"The stress topology contains exactly {(len(slice_ids) * 2) + 7} tasks.",
            },
            {
                "id": "AC-003",
                "description": "The generated status says mode dry-run.",
            },
        ],
        "shalls": [{"id": "SHALL-001", "text": f"The contract has {len(slice_ids)} slices."}],
        "slices": [
            {
                "id": slice_id,
                "reads": [f"docs/{slice_id}.input.md"],
                "writes": [f"docs/{slice_id}.output.md"],
            }
            for slice_id in slice_ids
        ],
    }


def _large_topology(path: Path, factory_count: int = 12) -> Path:
    lines = [
        "apiVersion: ao.dev/v1",
        "kind: Run",
        "metadata:",
        "  name: stress",
        "spec:",
        "  tasks:",
        "    - id: planner-intake",
        "      deps: []",
        "      spec:",
        "        provider: codex",
        "    - id: spec-forge-contract",
        "      deps: [\"planner-intake\"]",
        "      spec:",
        "        provider: codex",
        "    - id: ralph-loop",
        "      deps: [\"spec-forge-contract\"]",
        "      spec:",
        "        provider: codex",
        "    - id: plan-hardener",
        "      deps: [\"ralph-loop\"]",
        "      spec:",
        "        provider: codex",
        "    - id: factory-manager",
        "      deps: [\"plan-hardener\"]",
        "      spec:",
        "        provider: codex",
    ]
    for index in range(1, factory_count + 1):
        lines.extend(
            [
                f"    - id: stress-{index:02d}-factory",
                "      deps: [\"factory-manager\"]",
                "      spec:",
                "        provider: codex",
            ]
        )
    for index in range(1, factory_count + 1):
        lines.extend(
            [
                f"    - id: stress-{index:02d}-reviewer",
                f"      deps: [\"stress-{index:02d}-factory\"]",
                "      spec:",
                "        provider: codex",
            ]
        )
    lines.extend(
        [
            "    - id: integrator",
            "      deps:",
            *[f"        - stress-{index:02d}-reviewer" for index in range(1, factory_count + 1)],
            "      spec:",
            "        provider: codex",
            "    - id: evaluator-closer",
            "      deps: [\"integrator\"]",
            "      spec:",
            "        provider: codex",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _status(results: list[dict[str, str]], check_id: str) -> str:
    return next(item["status"] for item in results if item["id"] == check_id)


def _message(results: list[dict[str, str]], check_id: str) -> str:
    return next(item["message"] for item in results if item["id"] == check_id)


def _write_live_slug(root: Path, slug: str, task_ids: list[str], *, blocked_task: str) -> None:
    status_dir = root / "run-artifacts" / slug
    prompts_dir = status_dir / "prompts"
    roles_dir = status_dir / "roles"
    for path in [
        root / "docs" / "specs" / f"{slug}-spec.md",
        root / "docs" / "plans" / f"{slug}-plan.md",
        status_dir / f"{slug}.runspec.yaml",
        status_dir / f"{slug}-status.md",
        status_dir / f"{slug}-ao-events.md",
        root / "docs" / "evaluations" / f"{slug}-evaluation.md",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    (root / "docs" / "evaluations" / f"{slug}-evaluation.md").write_text(
        "\n".join(["Verdict: ACCEPTED", "AO Run: r-live-123", "Evidence:", "- ok", "Blockers:", "- none"]),
        encoding="utf-8",
    )
    prompts_dir.mkdir(parents=True, exist_ok=True)
    roles_dir.mkdir(parents=True, exist_ok=True)
    prompt = "\n".join(
        [
            "Do not include full transcripts",
            "Do not include secret values",
            "Scoped Context",
            "Injected Artifact Contents",
            "Required STATUS Block",
            "## Relevant Skills",
            "skills/factory-intake/SKILL.md",
        ]
    )
    for task_id in task_ids:
        (prompts_dir / f"{task_id}.md").write_text(prompt, encoding="utf-8")
        result = "BLOCKED" if task_id == blocked_task else "DONE"
        (roles_dir / f"{task_id}.md").write_text(
            f"Result: {result}\nArtifact: x\nEvidence:\n- ok\nConcerns:\n- none\nBlocker: none\n",
            encoding="utf-8",
        )


def test_accepted_live_validation_ignores_non_load_bearing_control_blocker(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "slug"
    task_ids = ["factory-manager", "identity-factory", "identity-reviewer", "integrator", "evaluator-closer"]
    _write_live_slug(tmp_path, slug, task_ids, blocked_task="factory-manager")
    results: list[dict[str, str]] = []

    validate_factory.check_slug(results, slug, task_ids)

    assert _status(results, f"evaluation.accepted_roles_unblocked:{slug}") == "ok"


def test_accepted_live_validation_rejects_load_bearing_blocker(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "slug"
    task_ids = ["factory-manager", "identity-factory", "identity-reviewer", "integrator", "evaluator-closer"]
    _write_live_slug(tmp_path, slug, task_ids, blocked_task="identity-reviewer")
    results: list[dict[str, str]] = []

    validate_factory.check_slug(results, slug, task_ids)

    assert _status(results, f"evaluation.accepted_roles_unblocked:{slug}") == "fail"
    assert "identity-reviewer" in _message(results, f"evaluation.accepted_roles_unblocked:{slug}")


def test_accepted_live_validation_uses_top_level_role_result(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "slug"
    task_ids = ["factory-manager", "identity-factory", "identity-reviewer", "integrator", "evaluator-closer"]
    _write_live_slug(tmp_path, slug, task_ids, blocked_task="factory-manager")
    role = tmp_path / "run-artifacts" / slug / "roles" / "identity-reviewer.md"
    role.write_text(
        "\n".join(
            [
                "# identity-reviewer Role Artifact",
                "",
                "Result: DONE_WITH_CONCERNS",
                "Artifact: x",
                "Evidence:",
                "- `rg \"Result: BLOCKED|Result: REJECTED\" artifact.md` returned no matches.",
                "Concerns:",
                "- none",
                "Blocker: none",
                "",
                "## Captured STATUS",
                "",
                "```text",
                "Result: DONE_WITH_CONCERNS",
                "Blocker: none",
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    validate_factory.check_slug(results, slug, task_ids)

    assert _status(results, f"evaluation.accepted_roles_unblocked:{slug}") == "ok"


def test_accepted_live_validation_rejects_untracked_role_artifact(tmp_path, monkeypatch):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "slug"
    task_ids = ["factory-manager", "identity-factory", "identity-reviewer", "integrator", "evaluator-closer"]
    _write_live_slug(tmp_path, slug, task_ids, blocked_task="factory-manager")
    for path in (tmp_path / "run-artifacts" / slug / "roles").glob("*.md"):
        if path.name != "identity-reviewer.md":
            subprocess.run(["git", "add", str(path.relative_to(tmp_path))], cwd=tmp_path, check=True)
    results: list[dict[str, str]] = []

    validate_factory.check_slug(results, slug, task_ids)

    assert _status(results, "artifact.role_tracked:identity-reviewer") == "fail"
    assert _message(results, "artifact.role_tracked:identity-reviewer") == "untracked role artifact"


def test_dry_run_validation_ignores_empty_role_directory_without_post_ao_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "slug"
    task_ids = ["planner-intake", "identity-factory", "identity-reviewer", "integrator", "evaluator-closer"]
    status_dir = tmp_path / "run-artifacts" / slug
    prompts_dir = status_dir / "prompts"
    roles_dir = status_dir / "roles"
    for path in [
        tmp_path / "docs" / "specs" / f"{slug}-spec.md",
        tmp_path / "docs" / "plans" / f"{slug}-plan.md",
        status_dir / f"{slug}.runspec.yaml",
        status_dir / f"{slug}-status.md",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    prompts_dir.mkdir(parents=True)
    roles_dir.mkdir(parents=True)
    prompt = "\n".join(
        [
            "Do not include full transcripts",
            "Do not include secret values",
            "Scoped Context",
            "Injected Artifact Contents",
            "Required STATUS Block",
            "## Relevant Skills",
            "skills/factory-intake/SKILL.md",
        ]
    )
    for task_id in task_ids:
        (prompts_dir / f"{task_id}.md").write_text(prompt, encoding="utf-8")

    results: list[dict[str, str]] = []

    validate_factory.check_slug(results, slug, task_ids, exact_prompts=True)

    assert all(item["status"] == "ok" for item in results), results


def test_validate_factory_accepts_profile_task_set(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "evidence-profile"
    task_ids = ["intake", "report-writer"]
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "evidence.json").write_text(
        json.dumps(
            {
                "profile": "evidence",
                "schema": "ao-operator/profile/v1",
                "version": 1,
                "common_instructions": ["test profile"],
                "roles": [
                    {
                        "id": task_id,
                        "role": task_id,
                        "provider_key": "FACTORY_V3_TEST_PROVIDER",
                        "deps": [] if index == 0 else [task_ids[index - 1]],
                        "reads": ["input"],
                        "writes": [f"run-artifacts/{slug}/roles/{task_id}.md"],
                        "skills": [],
                        "instructions": ["test"],
                    }
                    for index, task_id in enumerate(task_ids)
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_live_slug(tmp_path, slug, task_ids, blocked_task="")
    (tmp_path / "docs" / "evaluations" / f"{slug}-evaluation.md").write_text(
        "\n".join(
            [
                "Verdict: ACCEPTED",
                f"Spec: docs/specs/{slug}-spec.md",
                f"Plan: docs/plans/{slug}-plan.md",
                "AO Run: r-live-123",
                "Evidence:",
                "- ok",
                "Blockers:",
                "- none",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runspec = tmp_path / "run-artifacts" / slug / f"{slug}.runspec.yaml"
    runspec.write_text(
        "\n".join(
            [
                "apiVersion: ao.dev/v1",
                "kind: Run",
                "spec:",
                "  tasks:",
                "    - id: intake",
                f"      promptFile: run-artifacts/{slug}/prompts/intake.md",
                "    - id: report-writer",
                f"      promptFile: run-artifacts/{slug}/prompts/report-writer.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    results: list[dict[str, str]] = []
    task_ids = validate_factory.check_profile(results, "evidence")
    validate_factory.check_slug(results, slug, task_ids, exact_prompts=True)

    assert all(item["status"] == "ok" for item in results), results
    assert _status(results, "profile.file:evidence") == "ok"
    assert _status(results, "artifact.prompt:report-writer") == "ok"


def test_validate_factory_accepts_large_balanced_topology(tmp_path):
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=12)
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "stress", topology)

    assert len(task_ids) == 31
    assert _status(results, "topology.task_count") == "ok"
    assert _status(results, "topology.factories.count") == "ok"
    assert _status(results, "topology.reviewers.count") == "ok"
    assert all(item["status"] == "ok" for item in results), results


def test_validate_factory_enforces_contract_exact_topology_size(tmp_path):
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=12)
    contract = _contract([f"stress-{index:02d}-factory" for index in range(1, 13)])
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "stress", topology, contract)

    assert len(task_ids) == 31
    assert _status(results, "topology.task_count") == "ok"
    assert _message(results, "topology.task_count") == "31 task(s), expected 31"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_validate_factory_rejects_contract_topology_size_mismatch(tmp_path):
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=12)
    contract = _contract([f"stress-{index:02d}-factory" for index in range(1, 11)])
    results: list[dict[str, str]] = []

    validate_factory.check_topology(results, "stress", topology, contract)

    assert _status(results, "topology.task_count") == "fail"
    assert _status(results, "topology.factories.count") == "fail"
    assert _status(results, "topology.factories.match_contract") == "fail"


def test_validate_factory_rejects_factory_without_matching_reviewer(tmp_path):
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=2)
    text = topology.read_text(encoding="utf-8")
    topology.write_text(text.replace("stress-02-reviewer", "orphan-02-reviewer"), encoding="utf-8")
    results: list[dict[str, str]] = []

    validate_factory.check_topology(results, "stress", topology)

    assert _status(results, "topology.factory_reviewer:stress-02-factory") == "fail"


def test_validate_factory_accepts_redacted_runspec_prompt_when_prompt_artifact_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "stress"
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=1)
    status_dir = tmp_path / "run-artifacts" / slug
    prompts_dir = status_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    for task_id in [
        "planner-intake",
        "spec-forge-contract",
        "ralph-loop",
        "plan-hardener",
        "factory-manager",
        "stress-01-factory",
        "stress-01-reviewer",
        "integrator",
        "evaluator-closer",
    ]:
        (prompts_dir / f"{task_id}.md").write_text("Scoped Context\n", encoding="utf-8")
    (status_dir / f"{slug}.runspec.yaml").write_text(
        "\n".join(
            [
                "apiVersion: ao.dev/v1",
                "kind: Run",
                "spec:",
                "  tasks:",
                "    - id: planner-intake",
                "      spec:",
                "        promptFile: [REDACTED_LOCAL_PATH]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    validate_factory.check_topology(results, slug, topology)

    assert _status(results, "runspec.prompt:planner-intake") == "ok"
    assert _message(results, "runspec.prompt:planner-intake") == "redacted promptFile with matching prompt artifact"


def test_runspec_prompt_target_accepts_windows_absolute_path():
    body = "\n".join(
        [
            "apiVersion: ao.dev/v1",
            "kind: Run",
            "spec:",
            "  tasks:",
            "    - id: planner-intake",
            "      spec:",
            r"        promptFile: C:\workspace\ao-operator\docs\status\stress\prompts\planner-intake.md",
        ]
    )

    ok, message = validate_factory.runspec_prompt_targets_slug(
        body,
        slug="stress",
        task_id="planner-intake",
    )

    assert ok is True
    assert message == "run-artifacts/stress/prompts/planner-intake.md"


def test_validate_factory_runtime_required_files_excludes_private_overlay_scripts():
    assert "scripts/check_release_readiness.py" not in validate_factory.RUNTIME_FILES
    assert "scripts/check_mac_ubuntu_approval_artifact_parity.py" not in validate_factory.RUNTIME_FILES


def test_validate_factory_rejects_redacted_runspec_prompt_without_prompt_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_factory, "ROOT", tmp_path)
    slug = "stress"
    topology = _large_topology(tmp_path / "stress.yaml", factory_count=1)
    status_dir = tmp_path / "run-artifacts" / slug
    status_dir.mkdir(parents=True)
    (status_dir / f"{slug}.runspec.yaml").write_text(
        "\n".join(
            [
                "apiVersion: ao.dev/v1",
                "kind: Run",
                "spec:",
                "  tasks:",
                "    - id: planner-intake",
                "      spec:",
                "        promptFile: [REDACTED_LOCAL_PATH]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    validate_factory.check_topology(results, slug, topology)

    assert _status(results, "runspec.prompt:planner-intake") == "fail"
    assert _message(results, "runspec.prompt:planner-intake") == "promptFile does not target generated slug"


def test_validate_factory_contract_requires_exact_slices_and_disjoint_writes(tmp_path):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        """{
  "shalls": [{"id": "SHALL-001", "text": "The contract SHALL declare 3 disjoint implementation slices."}],
  "acceptance_criteria": [{"id": "AC-001", "description": "The contract carries all 3 slices."}],
  "sensitive_fields": ["token"],
  "negative_constraints": ["MUST NOT leak token"],
  "slices": [
    {"id": "a-factory", "reads": ["a"], "writes": ["out/a"]},
    {"id": "b-factory", "reads": ["b"], "writes": ["out/b"]},
    {"id": "c-factory", "reads": ["c"], "writes": ["out/c"]}
  ]
}
""",
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    validate_factory.check_contract(results, contract_path)

    assert _status(results, "contract.slices.count") == "ok"
    assert _status(results, "contract.slices.unique_ids") == "ok"
    assert _status(results, "contract.slices.disjoint_writes") == "ok"


def test_validate_factory_contract_rejects_duplicate_ids_and_write_overlap(tmp_path):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        """{
  "shalls": [{"id": "SHALL-001", "text": "The contract SHALL declare 3 disjoint implementation slices."}],
  "acceptance_criteria": [{"id": "AC-001", "description": "The contract carries all 3 slices."}],
  "sensitive_fields": ["token"],
  "negative_constraints": ["MUST NOT leak token"],
  "slices": [
    {"id": "a-factory", "reads": ["a"], "writes": ["out/shared"]},
    {"id": "a-factory", "reads": ["b"], "writes": ["out/b"]},
    {"id": "c-factory", "reads": ["c"], "writes": ["out/shared"]}
  ]
}
""",
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    validate_factory.check_contract(results, contract_path)

    assert _status(results, "contract.slices.count") == "ok"
    assert _status(results, "contract.slices.unique_ids") == "fail"
    assert _status(results, "contract.slices.disjoint_writes") == "fail"


def test_stress_fixture_generator_builds_107_task_contract_and_topology(tmp_path):
    contract = generate_stress_fixture.contract(50)
    topology = tmp_path / "stress.yaml"
    topology.write_text(generate_stress_fixture.topology(50), encoding="utf-8")
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "remote-transfer-v2-stress", topology, contract)

    assert generate_stress_fixture.task_count(50) == 107
    assert len(contract["slices"]) == 50
    assert len(task_ids) == 107
    assert _status(results, "topology.task_count") == "ok"
    assert _message(results, "topology.task_count") == "107 task(s), expected 107"
    assert _status(results, "topology.factories.count") == "ok"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_stress_fixture_generator_builds_bounded_live_profile(tmp_path):
    topology_file = "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml"
    contract_file = "examples/remote-transfer-v2-stress/spec-forge.live.contract.json"
    contract = generate_stress_fixture.contract(
        10,
        slug=generate_stress_fixture.LIVE_SLUG,
        topology_file=topology_file,
        contract_file=contract_file,
        live_profile=True,
    )
    topology = tmp_path / "live-stress.yaml"
    topology.write_text(
        generate_stress_fixture.topology(
            10,
            slug=generate_stress_fixture.LIVE_SLUG,
            contract_file=contract_file,
            live_profile=True,
        ),
        encoding="utf-8",
    )
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, generate_stress_fixture.LIVE_SLUG, topology, contract)

    assert generate_stress_fixture.task_count(10) == 27
    assert len(contract["slices"]) == 10
    assert len(task_ids) == 27
    assert f"run-artifacts/{generate_stress_fixture.LIVE_SLUG}/prompts/identity-factory.md" in topology.read_text(encoding="utf-8")
    assert "MUST NOT run the 1000-slice dry-run topology as a live provider workload" in contract["negative_constraints"]
    assert _message(results, "topology.task_count") == "27 task(s), expected 27"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_stress_fixture_generator_live_25_uses_existing_runtime_reads():
    contract = generate_stress_fixture.contract(
        25,
        slug=generate_stress_fixture.LIVE_SLUG,
        topology_file="examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
        contract_file="examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
        live_profile=True,
    )
    by_id = {item["id"]: item for item in contract["slices"]}

    assert "crates/ao-policy/src/queue.rs" in by_id["queue-lease-factory"]["reads"]
    assert "scripts/remote_codex_smoke_preflight.sh" in by_id["codex-smoke-factory"]["reads"]
    assert "prompts/remote-codex-smoke.md" in by_id["codex-smoke-factory"]["reads"]
    assert "crates/ao-workspace/tests/workspace.rs" in by_id["temp-cleanup-factory"]["reads"]
    assert "crates/ao-workspace/src/workspace.rs" not in by_id["temp-cleanup-factory"]["reads"]


def test_stress_fixture_live_contract_pins_50_slice_reviewer_regressions():
    contract = generate_stress_fixture.contract(
        50,
        slug=generate_stress_fixture.LIVE_SLUG,
        topology_file="examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
        contract_file="examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
        live_profile=True,
    )
    by_id = {item["id"]: item for item in contract["slices"]}

    assert "crates/ao-scheduler/src/lib.rs" in by_id["backpressure-factory"]["reads"]
    assert "crates/ao-daemon/src/scheduler.rs" not in by_id["backpressure-factory"]["reads"]
    codex_preflight = " ".join(by_id["codex-preflight-factory"]["verification"])
    observability_events = " ".join(by_id["observability-events-factory"]["verification"])
    manifest_compat = " ".join(by_id["manifest-compat-factory"]["verification"])
    manifest_schema = " ".join(by_id["manifest-schema-factory"]["verification"])
    codex_timeout = " ".join(by_id["codex-timeout-factory"]["verification"])
    artifact_download = " ".join(by_id["artifact-download-factory"]["verification"])
    bundle_delta = " ".join(by_id["bundle-delta-factory"]["verification"])
    failure_recovery = " ".join(by_id["failure-recovery-factory"]["verification"])
    queue_lease = " ".join(by_id["queue-lease-factory"]["verification"])
    security_path_normalize = " ".join(by_id["security-path-normalize-factory"]["verification"])
    task_claim = " ".join(by_id["task-claim-factory"]["verification"])
    cleanup_sweeper = " ".join(by_id["cleanup-sweeper-factory"]["verification"])

    assert "workspace-provider-auth-material" in codex_preflight
    assert "task.progress" not in observability_events
    assert "normalized reason" in observability_events
    assert "verifier key compatibility" in manifest_compat
    assert "signature rejection" in manifest_compat
    assert "auth exclusion" in manifest_compat
    assert "version handling" not in manifest_schema
    assert "failure codes" in manifest_schema
    assert "retry policy" not in codex_timeout
    assert "smoke result path" not in codex_timeout
    assert "task completion event" not in codex_timeout
    assert "provider timeout" in codex_timeout
    assert "API key boundary" in codex_timeout
    assert "retry" not in artifact_download
    assert "fallback" not in bundle_delta
    assert "baseline mismatch" in bundle_delta
    assert "rollback" not in failure_recovery
    assert "AO event gap" not in failure_recovery
    assert "current no lease expiry" in queue_lease
    assert "requeue" not in queue_lease
    assert "double resolution" in queue_lease
    assert "workspace-bundle-special-file-rejected" not in security_path_normalize
    assert "remote-transfer-v2-stress-live" not in security_path_normalize
    assert "Race Behavior" not in task_claim
    assert "interval" not in cleanup_sweeper
    assert "cadence" not in cleanup_sweeper


def test_stress_fixture_generator_extends_with_synthetic_domains(tmp_path):
    contract = generate_stress_fixture.contract(100)
    topology = tmp_path / "stress.yaml"
    topology.write_text(generate_stress_fixture.topology(100), encoding="utf-8")
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "remote-transfer-v2-stress", topology, contract)

    assert generate_stress_fixture.task_count(100) == 207
    assert len(contract["slices"]) == 100
    assert any(item["id"] == "synthetic-transfer-100-factory" for item in contract["slices"])
    assert len(task_ids) == 207
    assert _message(results, "topology.task_count") == "207 task(s), expected 207"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_stress_fixture_generator_validates_max_synthetic_topology(tmp_path):
    contract = generate_stress_fixture.contract(1000)
    topology = tmp_path / "stress.yaml"
    topology.write_text(generate_stress_fixture.topology(1000), encoding="utf-8")
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "remote-transfer-v2-stress", topology, contract)

    assert generate_stress_fixture.task_count(1000) == 2007
    assert len(contract["slices"]) == 1000
    assert any(item["id"] == "synthetic-transfer-1000-factory" for item in contract["slices"])
    assert len(task_ids) == 2007
    assert _message(results, "topology.task_count") == "2007 task(s), expected 2007"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_stress_fixture_generator_validates_ceiling_probe_topology(tmp_path):
    if not _stress_tests_enabled():
        pytest.skip("set FACTORY_V3_RUN_STRESS_TESTS=1 to run the 50007-task topology probe")

    contract = generate_stress_fixture.contract(generate_stress_fixture.VALIDATED_PROBE_SLICE_COUNT)
    topology = tmp_path / "stress.yaml"
    topology.write_text(generate_stress_fixture.topology(generate_stress_fixture.VALIDATED_PROBE_SLICE_COUNT), encoding="utf-8")
    results: list[dict[str, str]] = []

    task_ids = validate_factory.check_topology(results, "remote-transfer-v2-stress", topology, contract)
    summary = generate_stress_fixture.check_only_summary(generate_stress_fixture.VALIDATED_PROBE_SLICE_COUNT)

    assert summary == {
        "slug": "remote-transfer-v2-stress",
        "mode": "check-only",
        "slices": 25000,
        "tasks": 50007,
        "first_slice": "identity-factory",
        "last_slice": "synthetic-transfer-25000-factory",
        "writes_artifacts": False,
    }
    assert generate_stress_fixture.task_count(generate_stress_fixture.VALIDATED_PROBE_SLICE_COUNT) == 50007
    assert len(contract["slices"]) == 25000
    assert any(item["id"] == "synthetic-transfer-25000-factory" for item in contract["slices"])
    assert len(task_ids) == 50007
    assert _message(results, "topology.task_count") == "50007 task(s), expected 50007"
    assert _message(results, "topology.factories.count") == "25000 factor(y/ies), expected 25000"
    assert _status(results, "topology.factories.match_contract") == "ok"


def test_stress_fixture_generator_check_only_supports_200007_task_ceiling():
    summary = generate_stress_fixture.check_only_summary(generate_stress_fixture.COUNT_ONLY_CEILING_SLICE_COUNT)

    assert summary == {
        "slug": "remote-transfer-v2-stress",
        "mode": "check-only",
        "slices": 100000,
        "tasks": 200007,
        "first_slice": "identity-factory",
        "last_slice": "synthetic-transfer-100000-factory",
        "writes_artifacts": False,
    }


def test_stress_fixture_generator_validate_topology_summary_uses_temp_artifacts():
    summary = generate_stress_fixture.topology_validation_summary(50)

    assert summary["verdict"] == "PASS"
    assert summary["checked_tasks"] == 107
    assert summary["duration_seconds"] >= 0
    assert summary["writes_artifacts"] is False
    assert summary["failure_count"] == 0
    assert summary["checks"]["topology.task_count"] == {"status": "ok", "message": "107 task(s), expected 107"}
    assert summary["checks"]["topology.integrator_deps"] == {"status": "ok", "message": "50 reviewer deps present"}
