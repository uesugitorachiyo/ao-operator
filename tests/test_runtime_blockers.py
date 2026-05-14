"""Regression tests for the verdict-aggregation logic in factory_run.

Locks in the fix from PR #21 (closes #7 + #14): the aggregator demotes
"empty patch on idempotent task" and "non-load-bearing role BLOCK with
downstream success" from blockers to concerns. Real failures still
yield blockers.

These were previously verified inline as synthetic acceptance during
PR #21's bootstrap; this file makes them runnable via `pytest`.
"""
from __future__ import annotations

import auto_partition
import factory_run


def _role_body(task_id: str, result: str) -> str:
    return f"# {task_id} Role Artifact\n\nResult: {result}\n"


def _bundle(diff_bytes: int = 0, status_captured: bool = True) -> dict[str, object]:
    return {"diff_bytes": diff_bytes, "status_captured": status_captured}


def test_runtime_role_results_parses_each_body():
    tasks = [{"id": "planner-intake"}, {"id": "implementer-slice"}]
    role_bodies = [
        _role_body("planner-intake", "BLOCKED"),
        _role_body("implementer-slice", "DONE_WITH_CONCERNS"),
    ]
    results = factory_run.runtime_role_results(tasks, role_bodies)
    assert results == {
        "planner-intake": "BLOCKED",
        "implementer-slice": "DONE_WITH_CONCERNS",
    }


def test_issue_14_empty_patch_on_idempotent_task_is_concern_not_blocker():
    """Bug #14: implementer DONE/DONE_WITH_CONCERNS + empty patch is a no-op
    success, not a blocker."""
    tasks = [{"id": "implementer-slice"}]
    role_bodies = [_role_body("implementer-slice", "DONE_WITH_CONCERNS")]
    patch_bundles = {"implementer-slice": _bundle(diff_bytes=0)}
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)
    concerns = factory_run.runtime_concerns(tasks, role_results, patch_bundles)

    assert not any("empty patch bundle" in b for b in blockers), blockers
    assert any("empty patch bundle" in c for c in concerns), concerns


def test_issue_7_planner_block_with_downstream_success_is_concern_not_blocker():
    """Bug #7: planner-intake BLOCK + all load-bearing roles DONE means the
    chain delivered a working patch; the upstream BLOCK is compensable."""
    tasks = [
        {"id": "planner-intake"},
        {"id": "implementer-slice"},
        {"id": "evaluator-closer"},
    ]
    role_bodies = [
        _role_body("planner-intake", "BLOCKED"),
        _role_body("implementer-slice", "DONE"),
        _role_body("evaluator-closer", "DONE"),
    ]
    patch_bundles = {"implementer-slice": _bundle(diff_bytes=100)}
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)
    concerns = factory_run.runtime_concerns(tasks, role_results, patch_bundles)

    assert not any("At least one role returned" in b for b in blockers), blockers
    assert any("At least one role returned" in c for c in concerns), concerns


def test_regression_load_bearing_block_with_empty_patch_still_rejects():
    """Real failure: implementer-slice BLOCKED + empty patch must still
    yield BOTH blockers. PR #21 must not silently swallow real failures."""
    tasks = [{"id": "implementer-slice"}]
    role_bodies = [_role_body("implementer-slice", "BLOCKED")]
    patch_bundles = {"implementer-slice": _bundle(diff_bytes=0)}
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)

    assert any("At least one role returned" in b for b in blockers), blockers
    assert any("empty patch bundle" in b for b in blockers), blockers


def test_regression_implementer_with_real_patch_and_done_no_blockers():
    """Happy path: implementer DONE + non-empty patch + all roles DONE
    yields zero blockers and zero concerns."""
    tasks = [
        {"id": "planner-intake"},
        {"id": "implementer-slice"},
        {"id": "evaluator-closer"},
    ]
    role_bodies = [
        _role_body("planner-intake", "DONE"),
        _role_body("implementer-slice", "DONE"),
        _role_body("evaluator-closer", "DONE"),
    ]
    patch_bundles = {"implementer-slice": _bundle(diff_bytes=200)}
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)
    concerns = factory_run.runtime_concerns(tasks, role_results, patch_bundles)

    assert blockers == [], blockers
    assert concerns == [], concerns


def test_git_diff_force_adds_ignored_scoped_write(tmp_path):
    """Ignored scoped write paths still need to appear in Factory patch bundles."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / ".gitignore").write_text("/docs/remote-transfer-v2/\n", encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)

    output = repo / "docs" / "remote-transfer-v2" / "identity.md"
    output.parent.mkdir(parents=True)
    output.write_text("# Identity\n", encoding="utf-8")

    exit_code, diff_text, diff_err = factory_run.git_diff(
        repo,
        exclude_paths=[],
        force_add_paths=["docs/remote-transfer-v2/identity.md"],
    )

    assert exit_code == 0, diff_err
    assert "new file mode" in diff_text
    assert "docs/remote-transfer-v2/identity.md" in diff_text


def test_load_bearing_includes_factory_and_reviewer_suffix_tasks():
    """is_load_bearing_result_task() must accept *-factory and *-reviewer
    suffixes for factory-of-factories topology."""
    assert factory_run.is_load_bearing_result_task("implementer-slice")
    assert factory_run.is_load_bearing_result_task("reviewer-slice")
    assert factory_run.is_load_bearing_result_task("integrator")
    assert factory_run.is_load_bearing_result_task("evaluator-closer")
    assert factory_run.is_load_bearing_result_task("backend-factory")
    assert factory_run.is_load_bearing_result_task("frontend-factory")
    assert factory_run.is_load_bearing_result_task("backend-reviewer")
    assert not factory_run.is_load_bearing_result_task("planner-intake")
    assert not factory_run.is_load_bearing_result_task("plan-hardener")
    assert not factory_run.is_load_bearing_result_task("factory-manager")


# ---------------------------------------------------------------------------
# Quorum gate tests (Phase 1, Axis 2 — within-task slice fan-out)
# ---------------------------------------------------------------------------


def test_quorum_n4_three_done_one_blocked_is_done_with_concerns():
    """N=4, threshold=ceil(3*4/4)=3. Three DONE meets threshold; one BLOCKED
    is tolerated. Verdict: DONE_WITH_CONCERNS."""
    results = ["DONE", "DONE", "DONE", "BLOCKED"]
    assert factory_run.slice_quorum_verdict(results, num_slices=4) == "DONE_WITH_CONCERNS"


def test_quorum_n4_two_done_two_blocked_is_blocked():
    """N=4, threshold=3. Only two DONE — below threshold. Verdict: BLOCKED."""
    results = ["DONE", "DONE", "BLOCKED", "BLOCKED"]
    assert factory_run.slice_quorum_verdict(results, num_slices=4) == "BLOCKED"


def test_quorum_n8_six_done_two_blocked_is_done_with_concerns():
    """N=8, threshold=ceil(3*8/4)=6. Six DONE meets threshold; two BLOCKED
    tolerated. Verdict: DONE_WITH_CONCERNS."""
    results = ["DONE"] * 6 + ["BLOCKED", "BLOCKED"]
    assert factory_run.slice_quorum_verdict(results, num_slices=8) == "DONE_WITH_CONCERNS"


def test_quorum_n8_five_done_three_blocked_is_blocked():
    """N=8, threshold=6. Five DONE — below threshold. Verdict: BLOCKED."""
    results = ["DONE"] * 5 + ["BLOCKED", "BLOCKED", "BLOCKED"]
    assert factory_run.slice_quorum_verdict(results, num_slices=8) == "BLOCKED"


def test_quorum_n1_done_is_done():
    """N=1, threshold=ceil(3/4)=1. Single DONE meets threshold and equals
    num_slices. Verdict: DONE (not DONE_WITH_CONCERNS)."""
    assert factory_run.slice_quorum_verdict(["DONE"], num_slices=1) == "DONE"


def test_quorum_done_with_concerns_counts_as_success():
    """DONE_WITH_CONCERNS is in SUCCESS_RESULTS. Mixed DONE + DONE_WITH_CONCERNS
    at full count yields DONE_WITH_CONCERNS (not DONE), because not all are pure."""
    results = ["DONE", "DONE", "DONE_WITH_CONCERNS", "DONE_WITH_CONCERNS"]
    assert factory_run.slice_quorum_verdict(results, num_slices=4) == "DONE_WITH_CONCERNS"


# ---------------------------------------------------------------------------
# expand_slice_topology() tests
# ---------------------------------------------------------------------------


def test_expand_slice_topology_n1_returns_baseline_unchanged():
    """N=1 must produce the same task list as baseline (no behavior change)."""
    expanded = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=1)
    assert expanded == factory_run.BASELINE_TASKS


def test_expand_slice_topology_n3_emits_three_pairs_and_rewires_integrator():
    """N=3 must produce 3 implementer-slice-* + 3 reviewer-slice-* tasks.
    Each reviewer-slice-i depends only on implementer-slice-i.
    Integrator depends on all 3 reviewer-slice-* tasks."""
    expanded = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=3)
    ids = [str(t["id"]) for t in expanded]
    assert "implementer-slice-1" in ids
    assert "implementer-slice-2" in ids
    assert "implementer-slice-3" in ids
    assert "reviewer-slice-1" in ids
    assert "reviewer-slice-2" in ids
    assert "reviewer-slice-3" in ids
    assert "implementer-slice" not in ids
    assert "reviewer-slice" not in ids
    by_id = {str(t["id"]): t for t in expanded}
    for i in (1, 2, 3):
        assert by_id[f"reviewer-slice-{i}"]["deps"] == [f"implementer-slice-{i}"]
    assert set(by_id["integrator"]["deps"]) == {
        "reviewer-slice-1", "reviewer-slice-2", "reviewer-slice-3",
    }


def test_expand_slice_topology_threads_per_slice_writes():
    """Partitioned slice writes must become the implementer task write scope."""
    slices = auto_partition.partition(
        brief="",
        scoped_writes=["docs/smoke/slice-1.md", "docs/smoke/slice-2.md", "docs/smoke/slice-3.md"],
    )
    expanded = factory_run.expand_slice_topology(
        factory_run.BASELINE_TASKS,
        num_slices=len(slices),
        slice_specs=slices,
    )
    by_id = {str(t["id"]): t for t in expanded}

    assert by_id["implementer-slice-1"]["writes"] == ["docs/smoke/slice-1.md"]
    assert by_id["implementer-slice-2"]["writes"] == ["docs/smoke/slice-2.md"]
    assert by_id["implementer-slice-3"]["writes"] == ["docs/smoke/slice-3.md"]


def test_expand_slice_topology_keeps_multi_file_slice_writes_together():
    """When MAX_SLICES caps fan-out, a slice can own multiple paths."""
    expanded = factory_run.expand_slice_topology(
        factory_run.BASELINE_TASKS,
        num_slices=2,
        slice_specs=[
            {"slice_id": 1, "writes": ["docs/smoke/a.md", "docs/smoke/c.md"]},
            {"slice_id": 2, "writes": ["docs/smoke/b.md"]},
        ],
    )
    by_id = {str(t["id"]): t for t in expanded}

    assert by_id["implementer-slice-1"]["writes"] == ["docs/smoke/a.md", "docs/smoke/c.md"]
    assert by_id["implementer-slice-2"]["writes"] == ["docs/smoke/b.md"]


def test_is_mutator_task_recognizes_slice_suffix():
    from scripts.factory_run import is_mutator_task

    assert is_mutator_task("implementer-slice-1") is True
    assert is_mutator_task("implementer-slice-7") is True
    assert is_mutator_task("reviewer-slice-1") is False
    assert is_mutator_task("reviewer-slice-3") is False


def test_is_mutator_task_n1_backwards_compat():
    from scripts.factory_run import is_mutator_task

    assert is_mutator_task("implementer-slice") is True
    assert is_mutator_task("api-factory") is True
    assert is_mutator_task("factory-manager") is False
    assert is_mutator_task("planner-intake") is False
    assert is_mutator_task("integrator") is False


def test_is_load_bearing_result_task_recognizes_slice_suffix():
    from scripts.factory_run import is_load_bearing_result_task

    assert is_load_bearing_result_task("implementer-slice-1") is True
    assert is_load_bearing_result_task("implementer-slice-8") is True
    assert is_load_bearing_result_task("reviewer-slice-1") is True
    assert is_load_bearing_result_task("reviewer-slice-3") is True


def test_environmental_exclude_paths_omits_root_instructions_unless_owned():
    task = {"id": "implementer-slice", "writes": ["docs/smoke/out.md"]}

    assert factory_run.environmental_exclude_paths(task) == ["AGENTS.md", "CLAUDE.md"]

    owned = {"id": "implementer-slice", "writes": ["AGENTS.md"]}

    assert factory_run.environmental_exclude_paths(owned) == ["CLAUDE.md"]


def test_evaluator_instructions_require_pythonpath_retry():
    instructions = "\n".join(factory_run.role_instructions("evaluator-closer"))

    assert "PYTHONPATH=." in instructions
    assert "ModuleNotFoundError: No module named 'scripts'" in instructions
    assert "No module named pytest" in instructions
    # F4 cross-platform: prompt now mentions both macOS (Homebrew) and
    # Windows native (python.exe) interpreters as retry candidates.
    assert "/opt/homebrew/bin/python3" in instructions
    assert "python.exe" in instructions
    assert "pytest` executable on PATH" in instructions


def test_is_load_bearing_result_task_n1_backwards_compat():
    from scripts.factory_run import is_load_bearing_result_task

    for tid in ("implementer-slice", "reviewer-slice", "integrator", "evaluator-closer"):
        assert is_load_bearing_result_task(tid) is True, tid
    assert is_load_bearing_result_task("api-factory") is True
    assert is_load_bearing_result_task("api-reviewer") is True


def test_is_load_bearing_result_task_unknowns_return_false():
    from scripts.factory_run import is_load_bearing_result_task

    assert is_load_bearing_result_task("planner-intake") is False
    assert is_load_bearing_result_task("factory-manager") is False
    assert is_load_bearing_result_task("plan-hardener") is False
    assert is_load_bearing_result_task("random-id") is False


# ---------------------------------------------------------------------------
# Quorum-aware runtime_blockers / runtime_concerns tests (Task 10)
# ---------------------------------------------------------------------------


def test_runtime_blockers_quorum_tolerates_minority_slice_failure():
    """N=4 with 3 DONE + 1 BLOCKED implementer slices → quorum=DONE_WITH_CONCERNS.
    Top-level must NOT contain 'At least one role returned BLOCKED' and must NOT
    contain a per-slice patch-bundle blocker for the failing slice. The aggregated
    family verdict succeeded, so the slice failure is tolerated."""
    tasks = [
        {"id": "implementer-slice-1"},
        {"id": "implementer-slice-2"},
        {"id": "implementer-slice-3"},
        {"id": "implementer-slice-4"},
        {"id": "reviewer-slice-1"},
        {"id": "reviewer-slice-2"},
        {"id": "reviewer-slice-3"},
        {"id": "reviewer-slice-4"},
        {"id": "integrator"},
    ]
    role_bodies = [
        _role_body("implementer-slice-1", "DONE"),
        _role_body("implementer-slice-2", "DONE"),
        _role_body("implementer-slice-3", "DONE"),
        _role_body("implementer-slice-4", "BLOCKED"),
        _role_body("reviewer-slice-1", "DONE"),
        _role_body("reviewer-slice-2", "DONE"),
        _role_body("reviewer-slice-3", "DONE"),
        _role_body("reviewer-slice-4", "DONE"),
        _role_body("integrator", "DONE"),
    ]
    patch_bundles = {
        "implementer-slice-1": _bundle(diff_bytes=200),
        "implementer-slice-2": _bundle(diff_bytes=200),
        "implementer-slice-3": _bundle(diff_bytes=200),
        # implementer-slice-4 produced no bundle (it BLOCKED early)
    }
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)

    assert not any("At least one role returned" in b for b in blockers), blockers
    assert not any("implementer-slice-4" in b for b in blockers), blockers


def test_runtime_blockers_quorum_breaks_below_threshold():
    """N=4 with 2 DONE + 2 BLOCKED implementer slices → quorum=BLOCKED
    (threshold=ceil(3*4/4)=3). Top-level MUST contain 'At least one role returned
    BLOCKED' because the aggregated family verdict failed."""
    tasks = [
        {"id": "implementer-slice-1"},
        {"id": "implementer-slice-2"},
        {"id": "implementer-slice-3"},
        {"id": "implementer-slice-4"},
    ]
    role_bodies = [
        _role_body("implementer-slice-1", "DONE"),
        _role_body("implementer-slice-2", "DONE"),
        _role_body("implementer-slice-3", "BLOCKED"),
        _role_body("implementer-slice-4", "BLOCKED"),
    ]
    patch_bundles = {
        "implementer-slice-1": _bundle(diff_bytes=200),
        "implementer-slice-2": _bundle(diff_bytes=200),
    }
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    blockers = factory_run.runtime_blockers(tasks, role_bodies, patch_bundles, role_results)

    assert any("At least one role returned" in b for b in blockers), blockers


def test_runtime_concerns_records_quorum_done_with_concerns():
    """N=4 with 3 DONE + 1 BLOCKED implementer slices → quorum=DONE_WITH_CONCERNS.
    runtime_concerns must record at least one concern naming the failing slice
    (so operators can see WHICH slice was tolerated by the quorum)."""
    tasks = [
        {"id": "implementer-slice-1"},
        {"id": "implementer-slice-2"},
        {"id": "implementer-slice-3"},
        {"id": "implementer-slice-4"},
    ]
    role_bodies = [
        _role_body("implementer-slice-1", "DONE"),
        _role_body("implementer-slice-2", "DONE"),
        _role_body("implementer-slice-3", "DONE"),
        _role_body("implementer-slice-4", "BLOCKED"),
    ]
    patch_bundles = {
        "implementer-slice-1": _bundle(diff_bytes=200),
        "implementer-slice-2": _bundle(diff_bytes=200),
        "implementer-slice-3": _bundle(diff_bytes=200),
    }
    role_results = factory_run.runtime_role_results(tasks, role_bodies)

    concerns = factory_run.runtime_concerns(tasks, role_results, patch_bundles)

    assert any("implementer-slice-4" in c for c in concerns), concerns


def test_quorum_zero_denominator_returns_blocked(monkeypatch):
    """QUORUM_DEN=0 env poisoning returns BLOCKED instead of raising ZeroDivisionError."""
    import factory_v3_config

    monkeypatch.setattr(factory_v3_config, "QUORUM_DEN", 0)
    assert factory_run.slice_quorum_verdict(["DONE"], num_slices=1) == "BLOCKED"
    assert factory_run.slice_quorum_verdict(["DONE", "DONE", "DONE", "DONE"], num_slices=4) == "BLOCKED"


def test_n1_share_with_integrator_assigns_workspace_via_prepare_worktrees(tmp_path, monkeypatch):
    """Phase 1.5 regression guard: prepare_worktrees in N=1 mode must share
    the single mutator's worktree with reviewer-slice, integrator, and
    evaluator-closer (line ~1104 block in scripts/factory_run.py).

    This test invokes prepare_worktrees against a real git repo so a
    regression in production code (e.g. deleting the share-with block)
    would actually fail the test."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    seed = repo / "README.md"
    seed.write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)

    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", tmp_path / "wt")

    tasks = [
        {"id": "planner-intake", "deps": []},
        {"id": "implementer-slice", "deps": []},
        {"id": "reviewer-slice", "deps": ["implementer-slice"]},
        {"id": "integrator", "deps": ["reviewer-slice"]},
        {"id": "evaluator-closer", "deps": ["integrator"]},
    ]

    factory_run.prepare_worktrees(slug="test-n1-share", tasks=tasks, enabled=True, workspace_root=repo)

    by_id = {t["id"]: t for t in tasks}
    impl_ws = by_id["implementer-slice"]["workspace"]
    assert impl_ws.startswith(str(tmp_path / "wt" / "test-n1-share")), impl_ws
    assert by_id["reviewer-slice"]["workspace"] == impl_ws
    assert by_id["integrator"]["workspace"] == impl_ws
    assert by_id["evaluator-closer"]["workspace"] == impl_ws


def test_materialize_failure_surfaces_in_run_level_blockers(tmp_path, monkeypatch):
    """Pins the contract that materialize_integrator_workspace returns
    substring-matchable blockers when patches conflict — and that the
    run_live concat path (chain1.blockers + chain2.blockers + mat_blockers)
    will surface them as top-level blockers, not silently drop them.

    Does not exercise run_live directly (subprocess-heavy); instead pins
    the materialize blocker shape so the run_live concat above remains
    meaningful."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "ao-operator-tests@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "AO Operator Tests"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "seed"], check=True)
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", tmp_path / "wt")

    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    # Two patches that both create the same file at the same line —
    # second apply must conflict.
    same_target = "smoke/marker.txt"
    for slice_id in ("implementer-slice-1", "implementer-slice-2"):
        (patches_dir / f"{slice_id}.patch").write_text(
            f"diff --git a/{same_target} b/{same_target}\n"
            "new file mode 100644\n"
            "index 0000000..1111111\n"
            f"--- /dev/null\n"
            f"+++ b/{same_target}\n"
            "@@ -0,0 +1 @@\n"
            f"+content from {slice_id}\n"
        )

    path, notes, blockers = factory_run.materialize_integrator_workspace(
        slug="test-mat-fail",
        slice_ids=["implementer-slice-1", "implementer-slice-2"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )

    assert path is None, "expected materialize to fail on conflicting patches"
    assert blockers, "expected non-empty blockers on conflict"
    # The substring contract that run_live's concat depends on:
    assert any("materialization" in b.lower() or "git apply" in b.lower() for b in blockers), blockers
    assert any("implementer-slice-2" in b for b in blockers), blockers
