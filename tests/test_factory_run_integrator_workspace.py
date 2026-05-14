"""Unit tests for Phase 1.5 integrator workspace materialization.

Pins the contract for `_split_topology_for_n_ge_2` (chain-1 / chain-2
decomposition) and `materialize_integrator_workspace` (git-worktree +
git-apply mechanics).
"""
from __future__ import annotations

import factory_run


def test_split_topology_n1_returns_unchanged():
    """Defensive contract: even though `main()` only calls
    `_split_topology_for_n_ge_2` when num_slices >= 2, the helper itself
    must handle an N=1 input gracefully — chain1 contains the bare
    implementer-slice and reviewer-slice; chain2 contains integrator and
    evaluator-closer with deps rewritten. This pins that defensive
    behavior so a future implementer can't add a hard `assert n >= 2`
    without breaking the test."""
    tasks = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=1)
    chain1, chain2 = factory_run._split_topology_for_n_ge_2(tasks)
    chain1_ids = [str(t["id"]) for t in chain1]
    chain2_ids = [str(t["id"]) for t in chain2]
    assert "implementer-slice" in chain1_ids
    assert "reviewer-slice" in chain1_ids
    assert "integrator" in chain2_ids
    assert "evaluator-closer" in chain2_ids
    assert "integrator" not in chain1_ids
    assert "evaluator-closer" not in chain1_ids


def test_split_topology_n6_emits_chain1_with_15_tasks_chain2_with_2():
    """N=6 chain1 has: planner-intake, plan-hardener, factory-manager,
    6 implementer-slice-N, 6 reviewer-slice-N = 15 tasks.
    Chain2 has: integrator, evaluator-closer = 2 tasks."""
    tasks = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=6)
    chain1, chain2 = factory_run._split_topology_for_n_ge_2(tasks)
    assert len(chain1) == 15, [str(t["id"]) for t in chain1]
    assert len(chain2) == 2, [str(t["id"]) for t in chain2]
    chain2_ids = {str(t["id"]) for t in chain2}
    assert chain2_ids == {"integrator", "evaluator-closer"}


def test_split_topology_chain2_integrator_deps_empty_evaluator_deps_integrator():
    """In chain 2 topology, integrator must have deps=[] (AO ordering;
    upstream chain-1 tasks are not in this AO call). evaluator-closer
    must have deps=['integrator'] for intra-chain-2 ordering."""
    tasks = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=3)
    _, chain2 = factory_run._split_topology_for_n_ge_2(tasks)
    by_id = {str(t["id"]): t for t in chain2}
    assert by_id["integrator"]["deps"] == []
    assert by_id["evaluator-closer"]["deps"] == ["integrator"]


def test_split_topology_chain2_integrator_carries_chain1_handoffs():
    """Chain-2 integrator must carry a `chain1_handoffs` field listing
    every reviewer-slice-* task ID from chain 1, in chain-1 order. Order
    matters because `artifact_injections` iterates this list to render
    prompt context; stable ordering keeps prompt rendering deterministic
    across runs. Since AO deps for chain-2 integrator are intentionally
    empty (chain 1 isn't part of the same AO call), this field is the
    only mechanism that surfaces chain-1 reviewer artifacts to the
    chain-2 integrator prompt."""
    tasks = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=4)
    _, chain2 = factory_run._split_topology_for_n_ge_2(tasks)
    by_id = {str(t["id"]): t for t in chain2}
    handoffs = by_id["integrator"]["chain1_handoffs"]
    assert handoffs == [
        "reviewer-slice-1",
        "reviewer-slice-2",
        "reviewer-slice-3",
        "reviewer-slice-4",
    ]


def test_split_topology_chain2_evaluator_carries_all_chain1_handoffs():
    """Chain-2 evaluator-closer needs visibility into every chain-1 task
    artifact to render a deterministic verdict — implementer-slice-* DONE
    evidence, reviewer-slice-* outcomes, and the upstream planner-intake /
    plan-hardener / factory-manager artifacts. With only deps=['integrator']
    the evaluator loses chain-1 context and BLOCKs the run.

    Without this contract: live N=6 OAuth smoke produces evaluator
    BLOCKED status with 'integrator handoff content empty / required
    closure evidence unavailable'."""
    tasks = factory_run.expand_slice_topology(factory_run.BASELINE_TASKS, num_slices=3)
    _, chain2 = factory_run._split_topology_for_n_ge_2(tasks)
    by_id = {str(t["id"]): t for t in chain2}
    handoffs = by_id["evaluator-closer"]["chain1_handoffs"]
    expected = [
        "planner-intake",
        "plan-hardener",
        "factory-manager",
        "implementer-slice-1",
        "implementer-slice-2",
        "implementer-slice-3",
        "reviewer-slice-1",
        "reviewer-slice-2",
        "reviewer-slice-3",
    ]
    assert handoffs == expected, handoffs


def _init_git_repo(path):
    """Helper: initialize a small git repo at `path` with one committed file."""
    import subprocess
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    seed = path / "README.md"
    seed.write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "seed"], check=True)


def _write_slice_patch(patches_dir, slice_id, target_path, contents):
    """Helper: write a unified-diff patch creating `target_path` with `contents`.

    The patch includes an `index` line (required by some `git apply` variants)
    and uses the canonical `@@ -0,0 +1 @@` hunk header form (no count when 1).
    The blob sha (0000000..1111111) is synthetic — git apply ignores the value
    when applying a new-file patch.
    """
    import textwrap
    patch = patches_dir / f"{slice_id}.patch"
    body = textwrap.dedent(f"""\
        diff --git a/{target_path} b/{target_path}
        new file mode 100644
        index 0000000..1111111
        --- /dev/null
        +++ b/{target_path}
        @@ -0,0 +1 @@
        +{contents}
        """)
    patch.write_text(body, encoding="utf-8")


def test_materialize_creates_worktree_and_applies_clean_patches(tmp_path, monkeypatch):
    """Three disjoint slice patches are applied cleanly into the integrator
    worktree. Returns (path, notes, blockers=[])."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    for i in (1, 2, 3):
        _write_slice_patch(patches_dir, f"implementer-slice-{i}", f"docs/smoke/slice-{i}.md", f"slice {i}")

    worktree_root = tmp_path / "wt"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    path, notes, blockers = factory_run.materialize_integrator_workspace(
        slug="phase-1-5-test",
        slice_ids=["implementer-slice-1", "implementer-slice-2", "implementer-slice-3"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )
    assert path is not None
    assert blockers == []
    for i in (1, 2, 3):
        assert (path / f"docs/smoke/slice-{i}.md").read_text(encoding="utf-8").strip() == f"slice {i}"


def test_materialize_blocks_on_conflicting_patches(tmp_path, monkeypatch):
    """Two slice patches that both try to create the same file → git apply
    fails on the second. Returns (None, notes, blockers=[<conflict msg>])."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    _write_slice_patch(patches_dir, "implementer-slice-1", "docs/conflict.md", "first")
    _write_slice_patch(patches_dir, "implementer-slice-2", "docs/conflict.md", "second")

    worktree_root = tmp_path / "wt"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    path, notes, blockers = factory_run.materialize_integrator_workspace(
        slug="phase-1-5-conflict",
        slice_ids=["implementer-slice-1", "implementer-slice-2"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )
    assert path is None
    assert any("apply" in b.lower() or "conflict" in b.lower() for b in blockers), blockers


def test_materialize_idempotent_re_run(tmp_path, monkeypatch):
    """A pre-existing integrator worktree at the target path is removed
    before re-materialization. Re-running with the same slug + patches
    yields identical state and zero blockers."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    _write_slice_patch(patches_dir, "implementer-slice-1", "docs/smoke/slice-1.md", "v1")

    worktree_root = tmp_path / "wt"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    path1, _, blockers1 = factory_run.materialize_integrator_workspace(
        slug="phase-1-5-idem",
        slice_ids=["implementer-slice-1"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )
    path2, _, blockers2 = factory_run.materialize_integrator_workspace(
        slug="phase-1-5-idem",
        slice_ids=["implementer-slice-1"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )
    assert path1 == path2
    assert blockers1 == blockers2 == []
    assert (path2 / "docs/smoke/slice-1.md").read_text(encoding="utf-8").strip() == "v1"


def test_materialize_blocks_on_missing_patch_file(tmp_path, monkeypatch):
    """A slice_id whose patch file does not exist on disk → BLOCKED with
    a clear note. (Catches programmer errors where slice_ids and the
    patches_dir contents are out of sync.)"""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()  # intentionally empty

    worktree_root = tmp_path / "wt"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    path, notes, blockers = factory_run.materialize_integrator_workspace(
        slug="phase-1-5-missing",
        slice_ids=["implementer-slice-1"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )
    assert path is None
    assert any("missing" in b.lower() or "not found" in b.lower() for b in blockers), blockers


def test_scrub_claude_mem_pollution_reverts_polluted_existing_file(tmp_path):
    """Pollution scrubber reverts a contaminated file that exists at HEAD
    without the block. claude-mem is purely additive — HEAD is the clean
    baseline, so the safest fix is `git checkout HEAD -- <file>`. This
    avoids the byte-level drift (e.g. trailing-newline differences) that
    surgical regex stripping introduces, which previously caused
    `git apply` to fail when the second slice patch tried to apply the
    same residual diff on top of the first."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    polluted = repo / "AGENTS.md"
    head_content = "# Real content\n\nSome legitimate documentation.\n"
    polluted.write_text(head_content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "AGENTS.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    polluted.write_text(
        head_content
        + "\n\n"
        "<claude-mem-context>\n# Memory Context\ndifferent mem block\n</claude-mem-context>",
        encoding="utf-8",
    )

    scrubbed = factory_run.scrub_claude_mem_pollution(repo)

    assert "AGENTS.md" in scrubbed
    assert polluted.read_text(encoding="utf-8") == head_content
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "--", "AGENTS.md"],
        capture_output=True, text=True, check=True,
    )
    assert diff.stdout == "", f"expected zero diff after revert, got: {diff.stdout!r}"


def test_scrub_claude_mem_pollution_strips_block_from_new_file(tmp_path):
    """For a new (untracked) file containing a claude-mem block plus real
    content, regex-strip the block but keep the surrounding content. If
    nothing meaningful remains, the file is deleted."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    seed = repo / "seed.md"
    seed.write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    new_with_real_content = repo / "new.md"
    new_with_real_content.write_text(
        "real new content\n\n<claude-mem-context>\nblob\n</claude-mem-context>",
        encoding="utf-8",
    )
    new_only_block = repo / "only.md"
    new_only_block.write_text(
        "<claude-mem-context>\nblob\n</claude-mem-context>",
        encoding="utf-8",
    )

    scrubbed = factory_run.scrub_claude_mem_pollution(repo)

    assert "new.md" in scrubbed
    assert "only.md" in scrubbed
    cleaned = new_with_real_content.read_text(encoding="utf-8")
    assert "<claude-mem-context>" not in cleaned
    assert "real new content" in cleaned
    assert cleaned.endswith("\n")
    assert not new_only_block.exists()


def test_scrub_claude_mem_pollution_noop_when_no_block_present(tmp_path):
    """Idempotent on a clean worktree: no claude-mem block, no rewrites."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    f = repo / "AGENTS.md"
    f.write_text("# Real content\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "AGENTS.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    f.write_text("# Real content\n\nclean update\n", encoding="utf-8")

    scrubbed = factory_run.scrub_claude_mem_pollution(repo)

    assert scrubbed == []
    assert "<claude-mem-context>" not in f.read_text(encoding="utf-8")
