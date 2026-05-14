from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import factory_queue


def _brief(tmp_path, name: str = "brief.md"):
    path = tmp_path / name
    path.write_text("# Brief\n\nShape: greenfield\n", encoding="utf-8")
    return path


def test_enqueue_copies_brief_to_pending_without_removing_source(tmp_path):
    source = _brief(tmp_path)
    task = factory_queue.enqueue(source, root=tmp_path / "queue", slug="My Task")

    assert source.is_file()
    assert task.slug == "my-task"
    assert task.path.name == "my-task.brief.md"
    assert task.path.parent.name == "pending"
    assert task.path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_enqueue_rejects_duplicate_task_across_queue_states(tmp_path):
    source = _brief(tmp_path)
    root = tmp_path / "queue"
    factory_queue.enqueue(source, root=root, slug="dupe")
    task = factory_queue.claim_one(root)
    assert task is not None

    with pytest.raises(FileExistsError):
        factory_queue.enqueue(source, root=root, slug="dupe")


def test_claim_one_is_deterministic_and_single_winner(tmp_path):
    root = tmp_path / "queue"
    first = _brief(tmp_path, "b.md")
    second = _brief(tmp_path, "a.md")
    factory_queue.enqueue(first, root=root, slug="b-task")
    factory_queue.enqueue(second, root=root, slug="a-task")

    claimed = factory_queue.claim_one(root)
    assert claimed is not None
    assert claimed.slug == "a-task"
    assert claimed.path.parent.name == "in-flight"

    next_claimed = factory_queue.claim_one(root)
    assert next_claimed is not None
    assert next_claimed.slug == "b-task"

    assert factory_queue.claim_one(root) is None


def test_mark_done_and_failed_move_from_inflight(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="ok")
    ok_task = factory_queue.claim_one(root)
    assert ok_task is not None
    done = factory_queue.mark_done(ok_task, root=root)
    assert done.path.parent.name == "done"

    factory_queue.enqueue(source, root=root, slug="bad")
    bad_task = factory_queue.claim_one(root)
    assert bad_task is not None
    failed = factory_queue.mark_failed(bad_task, root=root)
    assert failed.path.parent.name == "failed"


def test_recover_stale_inflight_moves_old_tasks_back_to_pending(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="stale")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))

    recovered = factory_queue.recover_stale_inflight(root=root, stale_after_seconds=1800)

    assert [item.slug for item in recovered] == ["stale"]
    assert recovered[0].path.parent.name == "pending"


def test_recover_stale_inflight_leaves_fresh_tasks_inflight(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="fresh")
    task = factory_queue.claim_one(root)
    assert task is not None
    now = time.time()
    os.utime(task.path, (now, now))

    recovered = factory_queue.recover_stale_inflight(root=root, stale_after_seconds=1800, now=now)

    assert recovered == []
    assert task.path.is_file()
    assert task.path.parent.name == "in-flight"


def test_recover_stale_inflight_skips_when_pending_collision_exists(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="same")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))
    # Recovery canonicalizes the pending filename (drops claim token),
    # so a pending collision targets the canonical task filename.
    pending_collision = factory_queue.queue_paths(root)["pending"] / factory_queue.task_filename(task.slug)
    pending_collision.write_text("# Collision\n", encoding="utf-8")

    recovered = factory_queue.recover_stale_inflight(root=root, stale_after_seconds=1800)

    assert recovered == []
    assert task.path.is_file()
    assert pending_collision.is_file()


def test_recover_stale_inflight_skips_disappearing_files(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    paths = factory_queue.queue_paths(factory_queue.ensure_queue(root))
    ghost = paths["in-flight"] / "1234-claim__ghost.brief.md"

    original_iterdir = Path.iterdir
    original_is_file = Path.is_file

    def fake_iterdir(path):
        if path == paths["in-flight"]:
            return iter([ghost])
        return original_iterdir(path)

    def fake_is_file(path):
        if path == ghost:
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    monkeypatch.setattr(Path, "is_file", fake_is_file)

    recovered = factory_queue.recover_stale_inflight(root=root, stale_after_seconds=1800)

    assert recovered == []
