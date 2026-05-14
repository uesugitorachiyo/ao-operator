"""Regression tests for AO Operator worktree lease ownership."""
from __future__ import annotations

import json
import subprocess

import factory_run


def _init_git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    seed = path / "README.md"
    seed.write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "seed"], check=True)


def _write_slice_patch(patches_dir, slice_id, target_path, contents):
    patch = patches_dir / f"{slice_id}.patch"
    patch.write_text(
        "\n".join(
            [
                f"diff --git a/{target_path} b/{target_path}",
                "new file mode 100644",
                "index 0000000..1111111",
                "--- /dev/null",
                f"+++ b/{target_path}",
                "@@ -0,0 +1 @@",
                f"+{contents}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_prepare_worktrees_records_lease_and_cleanup_removes_it(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    worktree_root = tmp_path / "worktrees"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    tasks = [{"id": "implementer-slice"}]
    notes = factory_run.prepare_worktrees("lease-success", tasks, enabled=True, workspace_root=repo)

    lease_path = factory_run._worktree_lease_path("lease-success", "implementer-slice")
    payload = json.loads(lease_path.read_text(encoding="utf-8"))
    leased_path = tmp_path / "worktrees" / "lease-success" / "implementer-slice"

    assert any("isolated worktree" in note for note in notes)
    assert payload["schema"] == factory_run.WORKTREE_LEASE_SCHEMA
    assert payload["purpose"] == "mutator"
    assert payload["path"] == str(leased_path)
    assert leased_path.is_dir()
    assert tasks[0]["workspace"] == str(leased_path)

    cleanup_notes = factory_run.cleanup_worktree_leases("lease-success", repo)

    assert any("stale worktree lease cleaned" in note for note in cleanup_notes)
    assert not leased_path.exists()
    assert not lease_path.exists()


def test_prepare_worktrees_detects_and_cleans_stale_lease(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    worktree_root = tmp_path / "worktrees"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    first_tasks = [{"id": "implementer-slice"}]
    factory_run.prepare_worktrees("lease-interrupted", first_tasks, enabled=True, workspace_root=repo)

    second_tasks = [{"id": "implementer-slice"}]
    notes = factory_run.prepare_worktrees("lease-interrupted", second_tasks, enabled=True, workspace_root=repo)

    assert any("stale worktree lease cleaned" in note for note in notes), notes
    assert factory_run._worktree_lease_path("lease-interrupted", "implementer-slice").is_file()
    assert (worktree_root / "lease-interrupted" / "implementer-slice").is_dir()


def test_materialized_integrator_workspace_has_cleanup_lease(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    _write_slice_patch(patches_dir, "implementer-slice-1", "docs/smoke/slice-1.md", "slice 1")
    worktree_root = tmp_path / "worktrees"
    monkeypatch.setattr(factory_run, "WORKTREE_ROOT", worktree_root)

    path, notes, blockers = factory_run.materialize_integrator_workspace(
        slug="lease-integrator",
        slice_ids=["implementer-slice-1"],
        patches_dir=patches_dir,
        workspace_root=repo,
    )

    lease_path = factory_run._worktree_lease_path("lease-integrator", "integrator")
    payload = json.loads(lease_path.read_text(encoding="utf-8"))
    assert path is not None
    assert blockers == []
    assert any("materialized worktree" in note for note in notes)
    assert payload["purpose"] == "integrator"
    assert payload["path"] == str(path)

    cleanup_notes = factory_run.cleanup_worktree_leases("lease-integrator", repo)

    assert any("integrator: stale worktree lease cleaned" in note for note in cleanup_notes)
    assert not path.exists()
    assert not lease_path.exists()
