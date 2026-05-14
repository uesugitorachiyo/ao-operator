#!/usr/bin/env python3
"""Filesystem queue primitives for AO Operator Phase 2.

The queue is intentionally boring: task files move through
pending -> in-flight -> done/failed with same-filesystem renames. This module
does not launch providers; worker_pool.py owns execution policy.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


# F5 cross-platform: use tempfile.gettempdir() so Windows hosts (where
# the temp dir is %TEMP%) work without an explicit FACTORY_V3_QUEUE_ROOT
# override. POSIX behavior is preserved because gettempdir() returns
# /tmp on Linux/macOS by default.
DEFAULT_QUEUE_ROOT = Path(tempfile.gettempdir()) / "ao-operator-queue"
QUEUE_DIRS = ("pending", "in-flight", "done", "failed")
BRIEF_SUFFIX = ".brief.md"
# F6c: claim_one embeds a unique-per-claim token in the in-flight name
# so concurrent worker threads never target the same destination. The
# separator is double-underscore; slugify() never emits `_` (it re-maps
# to `-`), so this is unambiguous. POSIX rename semantics unchanged.
CLAIM_TOKEN_SEP = "__"
# F6c-2: process-level lock around claim_one. The unique-token fix
# alone relies on os.replace() atomicity, which Windows does not
# honor reliably under thread contention (a brief "delete pending"
# state on the source can let two threads both succeed the rename in
# rare cases). Worker pools are single-process ThreadPoolExecutor by
# design, so a Python-level lock is sufficient. Cross-process queue
# contention is not currently exercised.
_CLAIM_LOCK = threading.Lock()


@dataclass(frozen=True)
class QueueTask:
    path: Path
    slug: str


def queue_root(path: str | Path | None = None) -> Path:
    configured = path or os.environ.get("FACTORY_V3_QUEUE_ROOT")
    return Path(configured) if configured else DEFAULT_QUEUE_ROOT


def queue_paths(root: str | Path | None = None) -> dict[str, Path]:
    base = queue_root(root)
    return {name: base / name for name in QUEUE_DIRS}


def ensure_queue(root: str | Path | None = None) -> Path:
    base = queue_root(root)
    for path in queue_paths(base).values():
        path.mkdir(parents=True, exist_ok=True)
    return base


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "task"


def task_filename(slug: str) -> str:
    return f"{slugify(slug)}{BRIEF_SUFFIX}"


def slug_from_task(path: Path) -> str:
    name = path.name
    base = name[: -len(BRIEF_SUFFIX)] if name.endswith(BRIEF_SUFFIX) else path.stem
    # In-flight / done / failed filenames may carry a claim-token prefix
    # (token__slug.brief.md). Strip it so callers see the canonical slug.
    if CLAIM_TOKEN_SEP in base:
        return base.split(CLAIM_TOKEN_SEP, 1)[1]
    return base


def _all_task_locations(root: Path, filename: str) -> list[Path]:
    paths = queue_paths(root)
    target_slug = slug_from_task(Path(filename))
    locations: list[Path] = []
    pending_match = paths["pending"] / filename
    if pending_match.exists():
        locations.append(pending_match)
    # in-flight / done / failed names may carry a claim-token prefix, so
    # match by slug rather than exact filename.
    for name in ("in-flight", "done", "failed"):
        directory = paths[name]
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if entry.is_file() and slug_from_task(entry) == target_slug:
                locations.append(entry)
    return locations


def enqueue(brief_path: str | Path, *, root: str | Path | None = None, slug: str | None = None) -> QueueTask:
    """Enqueue a brief by atomically publishing a copied task file.

    The source brief is left untouched. Atomicity applies to the queue-side
    publish: write a temp file under pending/ and replace it into the final
    task filename.
    """
    base = ensure_queue(root)
    source = Path(brief_path)
    if not source.is_file():
        raise FileNotFoundError(f"brief not found: {source}")

    filename = task_filename(slug or source.stem)
    existing = [path for path in _all_task_locations(base, filename) if path.exists()]
    if existing:
        raise FileExistsError(f"task already exists: {existing[0]}")

    pending = queue_paths(base)["pending"]
    destination = pending / filename
    temp = pending / f".{filename}.{os.getpid()}.tmp"
    temp.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temp, destination)
    return QueueTask(path=destination, slug=slug_from_task(destination))


def pending_tasks(root: str | Path | None = None) -> list[Path]:
    pending = queue_paths(ensure_queue(root))["pending"]
    return sorted(path for path in pending.iterdir() if path.is_file() and not path.name.startswith("."))


def queue_depth(root: str | Path | None = None) -> int:
    return len(pending_tasks(root))


def claim_one(root: str | Path | None = None) -> QueueTask | None:
    """Atomically claim the first pending task, returning None when empty.

    Concurrency-safe across OSes via two layers:

    1. A process-level lock serializes claim attempts within a Python
       process. This is sufficient for the worker_pool's single-process
       ThreadPoolExecutor model and avoids relying on OS-level rename
       atomicity, which Windows does not honor reliably under thread
       contention.
    2. A unique-per-claim destination filename (token__slug.brief.md)
       guards against any residual race even if a second process
       (currently not used) joined the queue.
    """
    base = ensure_queue(root)
    paths = queue_paths(base)
    with _CLAIM_LOCK:
        for source in pending_tasks(base):
            slug = slug_from_task(source)
            token = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
            destination_name = f"{token}{CLAIM_TOKEN_SEP}{source.name}"
            destination = paths["in-flight"] / destination_name
            try:
                os.replace(source, destination)
            except FileNotFoundError:
                continue
            return QueueTask(path=destination, slug=slug)
    return None


def _move_from_inflight(task: QueueTask, target_dir: str, *, root: str | Path | None = None) -> QueueTask:
    base = ensure_queue(root)
    destination = queue_paths(base)[target_dir] / task.path.name
    if destination.exists():
        raise FileExistsError(f"task destination already exists: {destination}")
    os.rename(task.path, destination)
    return QueueTask(path=destination, slug=task.slug)


def mark_done(task: QueueTask, *, root: str | Path | None = None) -> QueueTask:
    return _move_from_inflight(task, "done", root=root)


def mark_failed(task: QueueTask, *, root: str | Path | None = None) -> QueueTask:
    return _move_from_inflight(task, "failed", root=root)


def recover_stale_inflight(
    *,
    root: str | Path | None = None,
    stale_after_seconds: int = 1800,
    now: float | None = None,
) -> list[QueueTask]:
    """Move abandoned in-flight tasks back to pending."""
    base = ensure_queue(root)
    paths = queue_paths(base)
    current = time.time() if now is None else now
    recovered: list[QueueTask] = []
    for source in sorted(path for path in paths["in-flight"].iterdir() if path.is_file()):
        try:
            age = current - source.stat().st_mtime
        except FileNotFoundError:
            continue
        if age < stale_after_seconds:
            continue
        slug = slug_from_task(source)
        # Restore canonical pending-side filename (drop claim token).
        destination = paths["pending"] / task_filename(slug)
        if destination.exists():
            continue
        try:
            os.replace(source, destination)
        except FileNotFoundError:
            continue
        recovered.append(QueueTask(path=destination, slug=slug))
    return recovered
