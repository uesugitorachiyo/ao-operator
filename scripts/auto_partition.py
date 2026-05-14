"""Within-task slice fan-out for ao-operator (Axis 2 of two-axis scaling).

partition(brief, scoped_writes) emits N slice dicts for factory-manager to
dispatch as parallel implementer-slice + reviewer-slice pairs. Metadata
paths (run-artifacts/, docs/evaluations/, docs/plans/) are excluded from the
slice count because they are written by the chain itself, not by mutator
slices. N is capped at factory_v3_config.MAX_SLICES (default 8).

Empty scoped_writes returns a single fallback slice — preserves today's
single-mutator behavior for briefs that don't declare specific paths.
"""
from __future__ import annotations

import factory_v3_config


METADATA_PREFIXES = (
    "run-artifacts/",
    "docs/evaluations/",
    "docs/plans/",
)
DEFAULT_SLICE_READS = ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"]
DEFAULT_SLICE_VERIFICATION = ["run the narrow verification listed in the accepted plan"]
DEFAULT_MERGE_OWNER = "integrator"
DEFAULT_REJOIN_ARTIFACT = "run-artifacts/<slug>/roles/integrator.md"


def is_metadata_path(path: str) -> bool:
    """True if `path` is written by the chain itself, not by a mutator slice."""
    return path.startswith(METADATA_PREFIXES)


def slice_contract(slice_id: int, writes: list[str] | None = None) -> dict:
    """Return the Gate-B-visible contract for one parallel slice."""
    return {
        "slice_id": slice_id,
        "id": f"slice-{slice_id}",
        "reads": list(DEFAULT_SLICE_READS),
        "writes": list(writes or []),
        "verification": list(DEFAULT_SLICE_VERIFICATION),
        "merge_owner": DEFAULT_MERGE_OWNER,
        "rejoin_artifact": DEFAULT_REJOIN_ARTIFACT,
    }


def partition(brief: str, scoped_writes: list[str]) -> list[dict]:
    """Return N slice dicts.

    N = min(len(non_metadata_paths), MAX_SLICES). One scoped path per slice
    when N <= MAX_SLICES; when input exceeds MAX_SLICES, paths are
    distributed round-robin so every input ends up in some slice (no silent
    drops). Empty scoped_writes returns a single fallback slice with no
    writes (preserves today's single-mutator behavior).

    Each slice carries a Gate B partition contract:
    `slice_id`, `id`, `reads`, `writes`, `verification`, `merge_owner`, and
    `rejoin_artifact`.
    `brief` is currently unused; it is part of the signature so a future
    enhancement (semantic partitioning) can read it without changing
    callers.
    """
    del brief  # reserved for future semantic partitioning
    mutator_paths = [p for p in scoped_writes if not is_metadata_path(p)]
    if not mutator_paths:
        return [slice_contract(1)]

    cap = factory_v3_config.MAX_SLICES
    n = min(len(mutator_paths), cap)
    slices: list[dict] = [slice_contract(i + 1) for i in range(n)]
    for index, path in enumerate(mutator_paths):
        slices[index % n]["writes"].append(path)
    return slices
