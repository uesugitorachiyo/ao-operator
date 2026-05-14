"""Central configuration for ao-operator two-axis adaptive scaling.

Constants are used by:
- scripts/auto_partition.py — slice fan-out (Axis 2)
- scripts/factory_run.py    — integrator quorum gate
- scripts/worker_pool.py    — worker pool (Axis 1) and provider telemetry

Each constant has a `FACTORY_V3_*` env override for ops-time tuning
without code changes. Locked defaults match SDD 07.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    """Read an int from env; fall back to default if unset or unparseable."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Per-task slice fan-out cap. Above this, partition() distributes round-robin.
MAX_SLICES = _int_env("FACTORY_V3_MAX_SLICES", 8)

# Cross-task worker pool cap.
MAX_WORKERS = _int_env("FACTORY_V3_MAX_WORKERS", 4)

# Worktree lease stale threshold. New runs treat existing lease files as
# interrupted-run residue and clean them before creating fresh worktrees; this
# value is recorded for ops-time policy and future external cleanup jobs.
WORKTREE_LEASE_STALE_AFTER_SECONDS = _int_env("FACTORY_V3_WORKTREE_LEASE_STALE_AFTER_SECONDS", 24 * 60 * 60)

# Quorum threshold = ceil(QUORUM_NUM * N / QUORUM_DEN). Defaults to 3/4.
QUORUM_NUM = _int_env("FACTORY_V3_QUORUM_NUM", 3)
QUORUM_DEN = _int_env("FACTORY_V3_QUORUM_DEN", 4)
