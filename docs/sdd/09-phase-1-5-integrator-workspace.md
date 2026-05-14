# Phase 1.5: Integrator workspace materialization for N≥2 slice fan-out

Status: shipped 2026-05-04 (accepted live OAuth smoke; AO Runtime parallel DAG execution verified)
Authored: 2026-05-03
Numbering: SDD 09 (07 = two-axis adaptive scaling; 08 = Phase 1 development recipe)
Issue: https://github.com/uesugitorachiyo/ao-operator/issues/28
Predecessor PR: #27 (Phase 1 — auto_partition + slice quorum)

## Motivation

Phase 1 (PR #27) shipped within-task slice fan-out. The live OAuth smoke
on 2026-05-03 proved the slice machinery is correct: 6 implementer +
6 reviewer slices completed in parallel for a 6-file brief, all 12
returning DONE, with a 3.61× implicit speedup over sequential
6-file work (≥3× SDD 07 threshold).

The same smoke surfaced one closure-orchestration gap: for N≥2, the
integrator and evaluator-closer AO turns ran against the bare main
checkout, not against any workspace where the 6 slice patches had been
applied. The integrator reported `docs/smoke/2026-05-03-phase-1/ is
absent in this provider worktree`; the evaluator-closer saw the same
empty workspace and REJECTED the run. Per-slice patches were captured
durably under `run-artifacts/<slug>/patches/implementer-slice-{1..6}.patch`
but were never materialized into a workspace before the closure roles
dispatched.

Phase 1.5 closes that gap so the multi-slice closure path can produce
ACCEPTED verdicts end-to-end without changing the OpenClaw AO library.

## Architecture

For N≥2 the AO chain is split into two topologies. For N=1 the existing
single-chain path is unchanged so backward compat is preserved
byte-identically.

### Chain shapes

```
N=1 (unchanged):
  planner-intake → plan-hardener → factory-manager
    → implementer-slice → reviewer-slice
    → integrator → evaluator-closer

N≥2 (split):
  Chain 1:
    planner-intake → plan-hardener → factory-manager
      → implementer-slice-1..N (parallel)
      → reviewer-slice-1..N    (parallel)
                                 [ STOP ]

  factory_run.py glue:
    write_patch_bundles(...)
    materialize_integrator_workspace(slug, slice_ids, patches_dir, root)
    bind integrator + evaluator-closer task workspaces

  Chain 2:
    integrator → evaluator-closer
      (both run in the materialized worktree)
```

### Materialization mechanism

```
git worktree add --detach /tmp/ao-operator-worktrees/<slug>/integrator HEAD
for each implementer-slice-N:
    git -C <integrator_worktree> apply --index <patches_dir>/implementer-slice-N.patch
```

`git apply --index` updates both the working tree and the index, so a
subsequent `git diff --cached` from inside chain-2 roles shows the union
of all slice patches. By design, slice writes are disjoint
(`auto_partition.partition` distributes round-robin across non-metadata
paths), so apply conflicts are an error condition rather than the
expected case.

If any apply fails, materialization sets workspace=None, surfaces a
top-level blocker, and chain 2 is not dispatched. The captured
conflict diff lives in the status doc for forensic use.

## New code surface

| Symbol | File | Approx LOC |
|---|---|---|
| `materialize_integrator_workspace(slug, slice_ids, patches_dir, root) → (path, notes, blockers)` | `scripts/factory_run.py` | 50 |
| `_split_topology_for_n_ge_2(tasks) → (chain1_tasks, chain2_tasks)` | `scripts/factory_run.py` | 25 |
| `_dispatch_chain(tasks, providers, paths, ...)` (factor existing dispatch into a reusable helper) | `scripts/factory_run.py` | 80 |
| `main()` modifications (detect N≥2, run chain 1 → materialize → run chain 2) | `scripts/factory_run.py` | 40 |
| `runtime_blockers` extension (surface materialize failures) | `scripts/factory_run.py` | 10 |
| Tests (unit-test materialize + split) | `tests/test_factory_run_integrator_workspace.py` (NEW) | ~100 |

Plus a re-run of `briefs/phase-1-six-file-smoke.md` to capture the
Phase 1.5 evidence row in `docs/live_oauth_smoke.md`.

## Failure modes

| Failure | Detection | Outcome |
|---|---|---|
| Slice patch apply conflict (overlapping writes) | `git apply --index` non-zero exit | BLOCKED at materialization; chain 2 not dispatched. Conflict diff captured. |
| Integrator worktree creation fails | `git worktree add` non-zero exit | BLOCKED at materialization; chain 2 not dispatched. Falls through to existing `prepare_worktrees` failure semantics. |
| Chain 1 quorum BLOCKED | `slice_quorum_verdict(...) == "BLOCKED"` | Chain 2 not dispatched. Top-level BLOCKED (existing semantics). |
| Chain 2 integrator BLOCKED / REJECTED | `runtime_role_results` parse | Top-level BLOCKED (existing `is_load_bearing_result_task` path). |
| Chain 2 evaluator-closer REJECTED | same | Top-level REJECTED (existing semantics). |
| Materialized worktree path collision | Pre-cleanup at `materialize_integrator_workspace` start | Existing worktree at the path is removed (mirror of `prepare_worktrees` line 1078). |

## Verdict + artifact semantics

- Each multi-slice run produces **one** integrator role artifact and
  **one** evaluator-closer role artifact (chain 2's). Chain 1 simply
  doesn't dispatch them; no reconciliation required.
- ACCEPTED iff: chain 1 quorum DONE ∧ all slice patches applied
  cleanly ∧ chain 2 integrator + evaluator-closer DONE.
- Status doc gains one new field for operator visibility:
  `Materialized integrator workspace: <path>`.
- The materialized worktree is preserved on disk after the run
  (subject to existing `WORKTREE_ROOT` cleanup conventions). Operators
  can `cd` into it to inspect what the integrator and evaluator-closer
  saw.

## Backward compatibility

- N=1 path unchanged. The existing `prepare_mutator_workspaces`
  share-with-integrator block (line ~1107) still fires for N=1; the
  new split path is gated on N≥2.
- All Phase 1 pinning tests must continue to pass (currently 53/53).
- Existing CLI flags unchanged. No new env vars are required; no new
  opt-out flag added (split mode is automatic when factory-manager
  emits N≥2 slices).

## Out of scope

- **Per-slice writes threading** — closed by Task 20. `auto_partition.partition`
  per-slice `writes` lists are now threaded into expanded
  `implementer-slice-N` task dicts so each slice prompt receives its own write
  ownership.
- **AO pre-task hook** (option C from the design discussion). Cleaner
  end-state but requires upstream OpenClaw AO changes; explicitly
  rejected in favor of ao-operator-only B-split per user direction
  (AO stability priority).
- **Phase 2 worker pool** — separate ground plan; this work does not
  block or unlock it.
- **Materialized worktree garbage collection policy** — existing
  `WORKTREE_ROOT` semantics apply.

## Acceptance

A reviewer accepting this work expects to see, on the Phase 1.5 PR:

1. Six new unit tests in `tests/test_factory_run_integrator_workspace.py`
   covering: clean apply with N=2/3/6, conflicting apply, worktree
   creation failure, idempotent re-run, materialize-then-dispatch
   integration.
2. `python3 -m pytest -q` → green (53 + 6 = 59).
3. `python3 scripts/validate_scaffold.py` → `verdict=PASS`.
4. A re-run of `briefs/phase-1-six-file-smoke.md` showing top-level
   verdict ACCEPTED, all 6 marker files present in the materialized
   workspace, and a new dated section in `docs/live_oauth_smoke.md`.
5. SDD 07 status line updated to reflect Phase 1.5 ship.
6. N=1 baseline still passes byte-identically (`briefs/phase-1-one-file-baseline.md`).

## References

- PR #27 (Phase 1 ship): https://github.com/uesugitorachiyo/ao-operator/pull/27
- Issue #28 (this design tracks): https://github.com/uesugitorachiyo/ao-operator/issues/28
- SDD 07 (architecture): `docs/sdd/07-two-axis-adaptive-scaling.md`
- SDD 08 (Phase 1 recipe): `docs/sdd/08-phase-1-development-recipe.md`
- Live smoke evidence: `docs/live_oauth_smoke.md` § 2026-05-04
- Phase 1 plan: `docs/plans/2026-05-03-phase-1-auto-partition-implementation-plan.md`
