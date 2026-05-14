# Live OAuth Smoke Log

Records of live, OAuth-backed AO Operator (AO = AI Orchestration Operation;
repo `ao-operator`) end-to-end runs that exercise
particular SDD acceptance gates. Each entry captures the brief, the
provider mapping in effect, the wallclock measurements, and the verdict
chain so that subsequent reviewers can reproduce or audit the result
without re-running the smoke.

## 2026-05-03 — Phase 1 (auto_partition + slice quorum)

Briefs: `briefs/phase-1-one-file-baseline.md` (N=1 baseline) and
`briefs/phase-1-six-file-smoke.md` (N=6 fan-out). Both create marker
files under `docs/smoke/2026-05-03-phase-1/` so the work is idempotent
and easy to verify.

Provider mapping (`scripts/factory_run.py --show-providers`):

| Role | Provider |
|------|----------|
| planner-intake | codex |
| plan-hardener | claude |
| factory-manager | codex |
| implementer-slice | codex |
| reviewer-slice | claude |
| integrator | codex |
| evaluator-closer | codex |

Wallclock measurements (single laptop, sequential runs, fresh worktree
each time):

| Run | N | Wallclock | All slices DONE? | Top-level verdict |
|-----|---|-----------|-------------------|--------------------|
| Baseline (single mutator) | 1 | 429s | yes (1/1) | ACCEPTED |
| Slice fan-out             | 6 | 713s | yes (6/6 implementer + 6/6 reviewer) | REJECTED — see closure-gap note |

Implicit speedup vs sequential equivalent:

```
Sequential 6-file equivalent      = 6 × 429s    = 2574s
Parallel  N=6 actual              =              713s
Speedup                           = 2574 / 713  = 3.61×
```

SDD 07 acceptance threshold (`≥3× speedup vs sequential`): **PASS**.

### Per-role verdicts (N=6 run)

| Task | Result |
|------|--------|
| planner-intake | DONE |
| plan-hardener | DONE |
| factory-manager | DONE |
| implementer-slice-1..6 | DONE × 6 |
| reviewer-slice-1..6 | DONE × 6 |
| integrator | DONE_WITH_CONCERNS |
| evaluator-closer | REJECTED |

Quorum: 6/6 implementer slices DONE → quorum=DONE. 6/6 reviewer slices
DONE → quorum=DONE. The slice fan-out succeeded end-to-end.

### Closure-gap finding (N≥2)

The integrator and evaluator-closer were dispatched in the main
ao-operator workspace, not in any slice worktree. The N=1 path uses
`prepare_mutator_workspaces` to share the single mutator's worktree
with integrator + evaluator-closer (line ~1104 of `scripts/factory_run.py`),
but the N≥2 path has no equivalent: each slice gets its own worktree,
and the integrator's workspace is left as the main checkout, which never
sees any slice patch applied. The integrator's STATUS block reports
"docs/smoke/2026-05-03-phase-1/ is absent in this provider worktree";
the evaluator-closer reads the same empty workspace and REJECTS.

The 6 patch bundles are captured durably under
`run-artifacts/phase-1-six-file-smoke/patches/implementer-slice-{1..6}.patch`
and the AO chain itself is correct. What's missing is the
integrator-workspace materialization step that applies those bundles
before integrator dispatch — a Phase 1.5 follow-up.

### What this smoke proves

- `auto_partition.partition` correctly emits N=6 slices for a 6-file brief.
- `expand_slice_topology(BASELINE_TASKS, num_slices=6)` produces the
  expected 17-task DAG (planner-intake, plan-hardener, factory-manager,
  6 implementer-slice-N, 6 reviewer-slice-N, integrator, evaluator-closer).
- Slice-aware predicates (`is_mutator_task`, `is_load_bearing_result_task`)
  recognize `implementer-slice-N` / `reviewer-slice-N`.
- The 6 implementer + 6 reviewer slices execute in parallel against
  live OAuth providers and all return DONE.
- `slice_quorum_verdict` aggregates the 12 slice results to DONE for
  both families.
- Wallclock fan-out is real: 6 files complete in ~1.7× the time of 1
  file, a 3.61× speedup over sequential 6-file work.

### What this smoke does not prove

- Integrator workspace materialization for N≥2. The 6 patches exist but
  are not applied to a workspace the integrator can verify against.
  Tracked as Phase 1.5 follow-up.
- evaluator-closer top-level acceptance for N≥2. Will succeed once the
  closure gap is closed.

### Reproduce

```bash
cd /path/to/ao-operator

# Baseline (N=1, ~7 min)
rm -rf run-artifacts/phase-1-one-file-baseline docs/smoke
time python3 scripts/factory_run.py --brief briefs/phase-1-one-file-baseline.md --run

# Fan-out (N=6, ~12 min)
rm -rf run-artifacts/phase-1-six-file-smoke
time python3 scripts/factory_run.py --brief briefs/phase-1-six-file-smoke.md --run
```

Verdict + per-role results live under
`run-artifacts/<slug>/phase-1-*-status.md` and
`run-artifacts/<slug>/roles/*.md`.

## 2026-05-04 — Phase 1.5 (integrator workspace materialization)

Re-run of `briefs/phase-1-six-file-smoke.md` after closing the N≥2
closure-orchestration gap from issue #28. Same brief, same provider
mapping, split dispatch shape: chain 1 stops after reviewer-slice-N,
`factory_run.py` materializes a dedicated integrator worktree by applying
the captured slice patches, then chain 2 dispatches integrator +
evaluator-closer in that worktree.

This run also used a patched AO Runtime binary that executes all ready DAG
nodes concurrently. The previous accepted run (#6) took 887s because the
AO daemon engine serialized independent implementer/reviewer tasks. The
Phase 1.5 confirmation run (#8) completed in 491s and its AO event log
shows all six implementers started in the same millisecond.

| Run | N | Wallclock | All slices DONE? | Top-level verdict |
|-----|---|-----------|-------------------|--------------------|
| Phase 1 (rejected closure) | 6 | 713s | yes | REJECTED |
| Phase 1.5 smoke #6 (serial AO engine) | 6 | 887s | yes | ACCEPTED |
| Phase 1.5 smoke #8 (parallel AO engine) | 6 | 491s | yes | **ACCEPTED** |

AO evidence:

- Chain 1 run id: `r-phase-1-six-file-smoke-1777903510599358000`
- Chain 2 run id: `r-phase-1-six-file-smoke-1777903721303800000`
- Evaluation AO Run: `r-phase-1-six-file-smoke-1777903721303800000`
- `python3 scripts/validate_factory.py --slug phase-1-six-file-smoke` exit=0

Per-role for the Phase 1.5 N=6 run: planner-intake=DONE,
plan-hardener=DONE_WITH_CONCERNS, factory-manager=DONE, all 6
implementer-slice-N=DONE, all 6 reviewer-slice-N=DONE_WITH_CONCERNS,
integrator=DONE, evaluator-closer=DONE_WITH_CONCERNS. Concerns were
non-blocking; the evaluator accepted the run with blockers: none.

Materialized integrator workspace path:
`/tmp/ao-operator-worktrees/phase-1-six-file-smoke/integrator`.
All 6 marker files are present at
`docs/smoke/2026-05-03-phase-1/slice-{1..6}.md` inside that worktree.

### What this proves in addition to Phase 1

- The B-split dispatch from SDD 09 lands an ACCEPTED verdict end-to-end.
- The integrator and evaluator-closer roles see all 6 slice patches
  applied in their workspace.
- Factory validation understands suffixed slice artifacts
  (`implementer-slice-1..6`, `reviewer-slice-1..6`) and passes.
- AO Runtime now starts independent ready tasks concurrently for the live
  Factory path; the six implementers all started at `14:06:53.021Z`.

## 2026-05-04 — Task 15 (default AO runtime baseline)

Post-merge stabilization run after AO Runtime PR #47 and AO Operator PR #29
landed on `main`. The goal was to prove AO Operator can run through its
default AO binary path without `FACTORY_V3_AO_BIN` or `AO_BIN`.

Runtime baseline:

- AO Operator main: `798d8a2`
- Clean AO Runtime main worktree: `${FACTORY_V3_AO_RUNTIME_PATH}-main`
- AO Runtime main commit: `78d01ab`
- Built default binary: `${FACTORY_V3_AO_RUNTIME_PATH}/target/release/ao`
- AO override env vars: absent

Live smoke:

- Brief: `briefs/phase-1-one-file-baseline.md`
- Slug: `task-15-default-ao-baseline-smoke`
- AO run id: `r-task-15-default-ao-baseline-smoke-1777905936651375000`
- Wallclock: 8m42s
- Factory verdict: **ACCEPTED**
- `python3 scripts/validate_factory.py --slug task-15-default-ao-baseline-smoke` exit=0
- Closure verification with pytest exit=0; `67 passed`

This proves the merged AO Operator baseline resolves and executes the merged
AO Runtime default binary path without depending on a local override.

## 2026-05-04 — Task 15 refresh (current AO main)

Follow-up confirmation after AO Runtime main advanced to the daemon status
command baseline. The goal was to keep the AO Operator baseline pinned to the
current default AO binary path before opening the Task 15 PR.

Runtime baseline:

- AO Operator branch: `codex/task-15-runtime-baseline`
- AO Operator starting commit: `7735136`
- AO Runtime worktree: `${FACTORY_V3_AO_RUNTIME_PATH}`
- AO Runtime main commit: `c4393c5`
- Built default binary: `${FACTORY_V3_AO_RUNTIME_PATH}/target/release/ao`
- AO override env vars: absent (`FACTORY_V3_AO_BIN` and `AO_BIN` unset)

Live smoke:

- Command: `env -u FACTORY_V3_AO_BIN -u AO_BIN time python3 scripts/factory_run.py --brief briefs/phase-1-one-file-baseline.md --slug task-15-current-ao-baseline-smoke --run`
- Brief: `briefs/phase-1-one-file-baseline.md`
- Slug: `task-15-current-ao-baseline-smoke`
- AO run id: `r-task-15-current-ao-baseline-smoke-1777921918068491000`
- Wallclock: 7m43s
- Factory verdict: **ACCEPTED**
- `python3 scripts/validate_factory.py --slug task-15-current-ao-baseline-smoke` exit=0
- `python3 scripts/factory_doctor.py` exit=0
- `/opt/homebrew/bin/python3 scripts/verify_closure.py --repo . --with-pytest --json` exit=0; `67 passed`

This proves the Task 15 AO Operator branch still resolves and executes the
current AO Runtime main binary through the default path without local AO
override environment variables.
