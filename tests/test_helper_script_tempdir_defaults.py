"""F5 cross-platform: helper-script /tmp defaults must resolve to tempfile.gettempdir().

These tests pin the contract that helper-script DEFAULT_* path constants
no longer hard-code ``/tmp`` so the same scripts run on Mac / Ubuntu /
Windows without an explicit override. POSIX behavior is preserved
because ``tempfile.gettempdir()`` returns ``/tmp`` on Linux and macOS by
default.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import factory_queue  # noqa: E402
import prepare_ao_runtime_big_task  # noqa: E402
import worker_pool  # noqa: E402


_TMP = Path(tempfile.gettempdir())


def test_factory_queue_default_root_uses_tempdir():
    assert factory_queue.DEFAULT_QUEUE_ROOT == _TMP / "ao-operator-queue"
    # Stays a Path so consumers can call .mkdir/.exists/etc.
    assert isinstance(factory_queue.DEFAULT_QUEUE_ROOT, Path)


def test_worker_pool_worktree_root_uses_tempdir():
    assert worker_pool.WORKER_WORKTREE_ROOT == _TMP / "ao-operator-worker-worktrees"
    assert isinstance(worker_pool.WORKER_WORKTREE_ROOT, Path)


def test_prepare_ao_runtime_big_task_defaults_use_tempdir():
    expected = {
        "DEFAULT_RUNNER_WORKTREE": _TMP / "ao-operator-ao-runtime-runner",
        "DEFAULT_TARGET_WORKTREE": _TMP / "ao-operator-ao-runtime-target",
        "DEFAULT_QUEUE_ROOT": _TMP / "ao-operator-ao-runtime-big-task-queue",
    }
    for name, want in expected.items():
        got = getattr(prepare_ao_runtime_big_task, name)
        assert got == want, f"{name}: {got!r} != {want!r}"
        assert isinstance(got, Path), f"{name} must be a Path"


def test_no_helper_constant_starts_with_literal_tmp_when_tempdir_differs():
    """Belt-and-braces: if a future Windows host has tempfile.gettempdir()
    return e.g. C:\\Users\\X\\AppData\\Local\\Temp, none of the resolved
    constants should still begin with the POSIX literal '/tmp/'.
    """
    constants = [
        factory_queue.DEFAULT_QUEUE_ROOT,
        worker_pool.WORKER_WORKTREE_ROOT,
        prepare_ao_runtime_big_task.DEFAULT_RUNNER_WORKTREE,
        prepare_ao_runtime_big_task.DEFAULT_TARGET_WORKTREE,
        prepare_ao_runtime_big_task.DEFAULT_QUEUE_ROOT,
    ]
    tempdir_str = tempfile.gettempdir()
    for path in constants:
        # Must live under the resolved tempdir, not under a hard-coded /tmp.
        assert str(path).startswith(tempdir_str), (
            f"{path} does not live under tempfile.gettempdir()={tempdir_str}"
        )
