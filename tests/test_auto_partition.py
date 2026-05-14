"""Unit tests for auto_partition.partition() and is_metadata_path().

partition() takes a brief and a list of scoped_writes and returns N slice
dicts. N is min(len(non_metadata_paths), MAX_SLICES). Empty scoped_writes
returns a single fallback slice (today's single-mutator behavior).

Locks SDD 07 contract: metadata paths (run-artifacts/, docs/evaluations/,
docs/plans/) are excluded from the slice count — they are written by the
chain itself, not by mutator slices.
"""
from __future__ import annotations

import auto_partition


def _slice_paths(slices: list[dict]) -> list[list[str]]:
    """Project the writes from a list of slice dicts for assertion."""
    return [s["writes"] for s in slices]


def test_one_scoped_write_yields_one_slice():
    slices = auto_partition.partition(brief="", scoped_writes=["scripts/foo.py"])
    assert len(slices) == 1
    assert _slice_paths(slices) == [["scripts/foo.py"]]
    assert slices[0]["id"] == "slice-1"
    assert slices[0]["merge_owner"] == "integrator"
    assert slices[0]["rejoin_artifact"] == "run-artifacts/<slug>/roles/integrator.md"
    assert slices[0]["reads"]
    assert slices[0]["verification"]


def test_two_scoped_writes_yield_two_slices():
    slices = auto_partition.partition(
        brief="",
        scoped_writes=["scripts/foo.py", "scripts/bar.py"],
    )
    assert len(slices) == 2
    assert _slice_paths(slices) == [["scripts/foo.py"], ["scripts/bar.py"]]


def test_eight_scoped_writes_yield_eight_slices():
    paths = [f"scripts/file_{i}.py" for i in range(1, 9)]
    slices = auto_partition.partition(brief="", scoped_writes=paths)
    assert len(slices) == 8
    assert _slice_paths(slices) == [[p] for p in paths]


def test_nine_scoped_writes_capped_at_max_slices():
    """MAX_SLICES = 8. Ninth path must end up in some slice (no silent drop)."""
    paths = [f"scripts/file_{i}.py" for i in range(1, 10)]
    slices = auto_partition.partition(brief="", scoped_writes=paths)
    assert len(slices) == 8
    assigned = [p for s in slices for p in s["writes"]]
    assert set(assigned) == set(paths)


def test_metadata_paths_excluded_from_slice_count():
    """run-artifacts/, docs/evaluations/, docs/plans/ are written by the chain,
    not by mutator slices. They must not inflate N."""
    paths = [
        "scripts/foo.py",
        "scripts/bar.py",
        "run-artifacts/foo-status.md",
        "docs/evaluations/foo-evaluation.md",
        "docs/plans/foo-plan.md",
    ]
    slices = auto_partition.partition(brief="", scoped_writes=paths)
    assert len(slices) == 2  # Only the two scripts are mutator paths.
    assigned = [p for s in slices for p in s["writes"]]
    assert "scripts/foo.py" in assigned
    assert "scripts/bar.py" in assigned
    for meta in paths[2:]:
        assert meta not in assigned


def test_empty_scoped_writes_falls_back_to_one_slice():
    """Empty scoped_writes preserves today's single-mutator behavior."""
    slices = auto_partition.partition(brief="", scoped_writes=[])
    assert len(slices) == 1
    assert slices[0]["writes"] == []


def test_is_metadata_path_recognises_three_prefixes():
    assert auto_partition.is_metadata_path("run-artifacts/foo-status.md")
    assert auto_partition.is_metadata_path("docs/evaluations/foo-evaluation.md")
    assert auto_partition.is_metadata_path("docs/plans/foo-plan.md")
    assert not auto_partition.is_metadata_path("scripts/foo.py")
    assert not auto_partition.is_metadata_path("docs/specs/foo-spec.md")
    assert not auto_partition.is_metadata_path("docs/sdd/07-two-axis-adaptive-scaling.md")
