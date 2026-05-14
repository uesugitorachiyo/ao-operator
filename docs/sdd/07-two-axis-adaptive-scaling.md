# Two-axis adaptive scaling for ao-operator

Status: Phase 1 shipped 2026-05-03 (within-task slice fan-out, ⌈3N/4⌉ quorum); Phase 1.5 shipped 2026-05-04 (integrator workspace materialization); Phase 2 shipped 2026-05-04 (cross-task queue, concurrent worker pool, default live worker isolation, artifact promotion, stale in-flight recovery, accepted two-task live default smoke); Phase 3 started 2026-05-04 with provider-rate telemetry, operator queue reports, synthetic larger pile canary, and guarded live-pile canary mode; remaining Phase 3 polish is executing the live larger pile canary
Authored: 2026-05-03
Numbering: SDD 07 (06 = implementation-checklist)

## Motivation

AO Operator originally ran one task at a time, with a single linear AO chain
(planner-intake → plan-hardener → factory-manager → implementer-slice →
reviewer-slice → integrator → evaluator-closer). Slice count is effectively
fixed at one (`scoped_writes` greater than 1 produces extra writes inside the
same single mutator, not extra mutators). There was no queue, no worker pool,
and no autosizing. Phase 1/1.5/2 now provide those primitives; this SDD remains
the source of truth for the shipped behavior and remaining polish.

This is fine on small tasks. It is the wrong shape for two cases the user
hits regularly:

- **Huge tasks** — one task that legitimately needs 6 file edits across 6
  unrelated areas. Today: one mutator does it serially; a single bad write
  blocks the whole task.
- **Piles of tasks** — five tasks queued back to back. Today: ao-operator
  serializes them; provider concurrency goes unused.

The /ai-teams (v2) factory has the opposite shape: in-process, near-100%
accept-rate, fast on small tasks, but the same single-thread bottleneck on
both axes. The user's stated goal: combine v2's accuracy with throughput
under load. AO Operator is the place to do it because it already has the
substrate (worktree isolation, manifest sync, verdict aggregator, skill
inlining, sonnet on Claude). What is missing is **adaptive parallelism on
two independent axes**.

## The two axes

Two axes of parallelism, scaled independently:

```
                Axis 1 — across tasks
                  (worker pool)
                       W
            ┌──────────┬──────────┐
            │ task A   │ task B   │ ...
            │  (N=3)   │  (N=1)   │
            └──┬───┬───┴──┬───────┘
               │   │      │
               └─slice fan-out per task─┐
                       Axis 2 — within a task
                         (slice mutators)
                                N
```

**Axis 1 — W (across tasks).** A worker pool, supervised by ao-runtime,
pulls tasks off a file-system queue. Each worker runs the standard 7-stage
AO chain on one task. Workers are mutually independent — they never share
working trees, manifests, or git refs.

**Axis 2 — N (within a task).** Per-task slice fan-out. When a task's
scoped writes span multiple files, factory-manager emits N parallel slice
mutators, each with its own scoped subset, its own worktree, and its own
reviewer-slice. The integrator collects all slices and applies a quorum
gate.

The two axes scale on different signals (queue depth vs scoped-writes
count). They never need to know about each other.

## Adaptive sizing policy

### N (within a task)

```
N = min(
    len(scoped_writes_excluding_metadata),
    MAX_SLICES,
)
```

- **MAX_SLICES = 8.** Cap chosen so that even a degenerate "edit 20 files
  in one task" brief does not spawn 20 parallel Claude calls and starve the
  provider. 8 is enough headroom for the largest realistic ao-operator task
  (whole-module refactor, 6–8 files); the shape-gate path forces anything
  larger to decompose at the spec stage.
- "Excluding metadata" means: `run-artifacts/...`, `docs/evaluations/...`,
  `docs/plans/...`, and any auto-emitted artifact paths. Those are written
  by the chain itself, not by mutator slices.
- N = 1 is the trivial case (single scoped_write). The chain runs exactly
  as today.

### W (across tasks)

```
W = min(
    queue_depth,
    MAX_WORKERS,
    provider_rate_limit_floor,
)
```

- **MAX_WORKERS = 4.** Cap chosen for the laptop-class deployment target.
  Above 4 concurrent Claude/Codex CLIs the provider quota is the binding
  constraint, not local CPU.
- `queue_depth` is the count of tasks currently in `pending/`. W shrinks
  to match a draining queue.
- `provider_rate_limit_floor` is computed from recent provider throttle
  telemetry under the queue root. On a fresh start it is set to MAX_WORKERS
  (no observation yet); any recent 429/rate-limit signal halves the next
  worker batch floor, bounded at 1.

### Bounds in numbers

|  Scenario                  | scoped_writes | queue_depth | N | W | parallelism |
|----------------------------|--------------:|------------:|--:|--:|------------:|
| Single trivial task        |             1 |           1 | 1 | 1 |           1 |
| Single huge task           |             6 |           1 | 6 | 1 |           6 |
| Pile of trivial tasks      |             1 |           5 | 1 | 4 |           4 |
| Pile of huge tasks         |             6 |           5 | 6 | 4 |          24 |
| Pile + provider rate-limit |             6 |           5 | 6 | 2 |          12 |

The 24-way max is bounded by per-task isolation (each mutator has its own
worktree). It is theoretical; provider rate-limit usually pulls W below 4.

## Quorum gate (integrator)

Per-task slice quorum: **⌈3N/4⌉ DONE among slice mutators ⇒ ACCEPTED with
concerns.**

| N | Quorum threshold | Slices that may fail |
|--:|-----------------:|---------------------:|
| 1 |                1 |                    0 |
| 2 |                2 |                    0 |
| 3 |                3 |                    0 |
| 4 |                3 |                    1 |
| 5 |                4 |                    1 |
| 6 |                5 |                    1 |
| 7 |                6 |                    1 |
| 8 |                6 |                    2 |

For N ≤ 3 the threshold equals N — every slice must succeed. For
N ≥ 4 a single slice may BLOCK without sinking the whole task. For N = 8 a
second BLOCK is tolerated. Reviewer-slice still runs on every successful
slice, so a slice that is "DONE" has already passed local review.

If the threshold is not met the integrator emits BLOCKED for the whole
task. The verdict aggregator (PR #21, `runtime_blockers` /
`runtime_role_results` / `runtime_concerns`) already supports the
DONE-with-concerns shape; the integrator only needs to count slice results
and choose between `DONE`, `DONE_WITH_CONCERNS`, and `BLOCKED`.

## Components

### New components

| Component | Type | Phase | Purpose |
|-----------|------|------:|---------|
| `scripts/auto_partition.py` | Python module | 1 | Take a brief and a list of scoped_writes, emit an N-slice runspec (one slice per scoped_write up to MAX_SLICES). |
| `scripts/factory_queue.py` | Python module | 2 | Atomic-mv queue primitives for `pending/`, `in-flight/`, `done/`, and `failed/`. Named to avoid shadowing Python's stdlib `queue` module in pytest. |
| `scripts/worker_pool.py` | Python module + ao-runtime supervisor | 2/3 | Pull from `/tmp/ao-operator-queue/pending/`, recover stale `in-flight/`, atomic-mv claim, run the selected task through `factory_run.py`, and mv to `done/` or `failed/` on completion. Live mode defaults to per-task isolated worker worktrees with artifact promotion back to `--workspace`. Phase 3 records provider rate-limit telemetry and applies it to worker sizing. |
| `scripts/worker_pile_canary.py` | Python module + CLI | 3 | Run a deterministic larger-pile canary. Default mode uses a local synthetic runner; guarded live mode enqueues the same pile shape and drains it through live provider workers only when an explicit confirmation token is supplied. |
| `ao-operator enqueue <brief.md>` | CLI subcommand | 2 | Drop a brief into `/tmp/ao-operator-queue/pending/`. |
| `/tmp/ao-operator-queue/{pending,in-flight,done,failed}/` | Directory contract | 2 | The queue itself. |

### Reused components

| Component | Reuse |
|-----------|-------|
| `scripts/factory_run.py` | Each worker invokes it as today. No worker logic in factory_run itself. |
| 7-stage AO chain | Unchanged. factory-manager gains slice fan-out via auto_partition. |
| Worktree isolation (`/tmp/ao-operator-worktrees/<slug>/<task_id>/`) | Already isolates per-task. Phase 1 makes it isolate per-slice (`/<slug>/<task_id>/<slice_id>/`). |
| Manifest sync (PR #17) | Already syncs per-mutator. Continues to work per-slice. |
| Skill inlining (PR #25) | Each slice mutator gets the same inlined SKILL.md content. |
| Verdict aggregator (PR #21) | `runtime_blockers` / `runtime_role_results` / `runtime_concerns` already model DONE-with-concerns. |
| sonnet on Claude (PR #25) | Shape-aware judgment for plan-hardener / reviewer-slice / evaluator-closer. |

## Data flow

### Phase 1 (within-task fan-out only)

```
brief.md
   │
   ▼
planner-intake ─▶ plan-hardener ─▶ factory-manager
                                       │
                                       │ scoped_writes count > 1?
                                       ▼
                               auto_partition.py
                                       │
                                       │ emit N slices
                                       ▼
              ┌──────────────┬──────────┴──────────┬──────────────┐
              │ slice 1      │ slice 2             │ slice N      │
              │ implementer  │ implementer         │ implementer  │
              │   ▼          │   ▼                 │   ▼          │
              │ reviewer     │ reviewer            │ reviewer     │
              └──────────────┴──────────┬──────────┴──────────────┘
                                       ▼
                                   integrator
                                       │
                                       │ quorum: ⌈3N/4⌉ DONE?
                                       ▼
                              evaluator-closer
                                       │
                                       ▼
                            DONE / DONE_WITH_CONCERNS / BLOCKED
```

### Phase 2 (cross-task fan-out added)

```
ao-operator enqueue brief1.md  ┐
ao-operator enqueue brief2.md  ├─▶  /tmp/ao-operator-queue/pending/
ao-operator enqueue brief3.md  ┘            │
                                            │
                              worker_pool (ao-runtime supervised)
                                            │
                              W workers (claim via atomic mv)
                              ┌─────────┬─────────┬─────────┐
                              │worker A │worker B │worker C │
                              │ task 1  │ task 2  │ task 3  │
                              │ (N=3)   │ (N=1)   │ (N=2)   │
                              └─────────┴─────────┴─────────┘
                              each runs the Phase 1 chain end-to-end
                                            │
                                            ▼
                              done/  or  failed/  (atomic mv)
```

The two axes shipped independently. Phase 1 removes the "huge task"
bottleneck; Phase 2 removes the "pile of tasks" bottleneck while preserving
the same seven-role AO chain inside each worker.

## Atomic claim protocol (Phase 2)

Worker startup loop:

```
1. recover stale in-flight tasks older than --recover-stale-after
2. ls /tmp/ao-operator-queue/pending/
3. pick first entry (deterministic order)
4. mv pending/<task> in-flight/<task>      ← atomic on POSIX
   if mv fails (raced) → goto 1
5. run factory_run.py on <task>
6. live mode: run from /tmp/ao-operator-worker-worktrees/<slug> and promote generated artifacts back to --workspace
7. on exit: mv in-flight/<task> done/      (or failed/)
8. goto 1
```

`mv` is atomic on the same filesystem. Two workers racing the same file
result in exactly one winner; the loser sees ENOENT and retries. No locks,
no fcntl, no Redis. `/tmp/ao-operator-queue/` lives on the same volume as
the worktrees, so atomicity is preserved.

Crash recovery: on worker startup and before worker-batch sizing, scan
`in-flight/`. Anything older than `--recover-stale-after` (default: 30 min)
is considered abandoned and moved back to `pending/`. Recovery is conservative:
if a matching pending task already exists, the stale in-flight file is left in
place rather than overwritten.

## Accept-rate guarantees

Goal: keep accept-rate at or above /ai-teams's near-100%, even with two
axes of parallelism.

| Risk to accept-rate | Mitigation |
|---|---|
| Cross-slice interference (slice A overwrites slice B) | Per-slice worktree + per-slice `scoped_writes`. Slice A cannot write to slice B's paths. |
| Skill drift between planner and slice mutators | PR #25 inlines SKILL.md content into every prompt; slices receive the same body the planner saw. |
| Reviewer mis-classifying partial success as failure | sonnet on Claude (PR #25) + reviewer prompt hardened in PR #1. |
| Verdict aggregator over-blocking on idempotent-success | PR #21 `runtime_role_results` distinguishes load-bearing roles from compensable concerns. |
| One slice failing kills the whole task | Quorum gate ⌈3N/4⌉ allows progress for N ≥ 4 with a single failed slice. |
| Reviewer skipped on partial success | Reviewer-slice runs per slice, before integrator. A passing slice has already been locally reviewed. |
| Race between two workers on the same task | Atomic `mv` claim; loser retries. Tested in Phase 2 with crash-recovery test. |
| Live worker artifact/context pollution | Live `run-once` and `pool` default to per-task isolated worker worktrees and promote only known Factory evidence paths back to `--workspace`. |
| Failed isolated worker loses diagnostics | Artifact promotion runs for failed workers too, so status/evaluation evidence is available from the target workspace. |
| Stale `in-flight` task blocks queue progress | `--recover-stale-after` recovers abandoned tasks before claiming and before worker sizing. |

The throughput axes (W and N) do not relax any quality gate. Every slice
still runs its full reviewer; the integrator still runs; evaluator-closer
still runs. Only the task-level acceptance threshold relaxes (⌈3N/4⌉
instead of N).

## Why throughput improves

| Bottleneck today | Removed by | Throughput shape |
|---|---|---|
| Single mutator on a huge task | Phase 1 (Axis 2: N slices) | `wallclock(N=k) ≈ wallclock(N=1) / k` for embarrassingly-parallel scoped_writes |
| Single task at a time on the box | Phase 2 (Axis 1: W workers) | `wallclock(W=k tasks) ≈ wallclock(W=1, single-task) × ⌈total/k⌉` |
| Provider concurrency unused | W and N exploit it together | Up to MAX_WORKERS × MAX_SLICES = 32 in-flight Claude calls (theoretical; clipped by `provider_rate_limit_floor`) |

The composition (W × N) is multiplicative on a queue of huge tasks. The
rate-limit floor is what keeps it from running away.

## Provider-rate telemetry (Phase 3)

Worker subprocess output is streamed back to the operator and scanned for
provider-throttle signals (`429`, `Too Many Requests`, `rate_limit`, and
`quota exceeded`). When a signal appears, `worker_pool.py` appends a compact
JSONL event to `<queue-root>/telemetry/provider-rate-limits.jsonl` with only
timestamp, task slug, and signal. It deliberately does not persist raw provider
transcripts or environment data.

Before each foreground worker batch, the pool counts recent telemetry in a
30-minute window and derives:

```
provider_rate_limit_floor =
  adjusted_rate_limit_floor(MAX_WORKERS or --workers, recent_429s)
```

Any recent rate-limit signal halves the floor, bounded at 1. Queue status JSON
also reports `provider_rate_limits.window_seconds`, `recent_429s`, and
`provider_rate_limit_floor`, making the sizing decision inspectable without
opening provider logs.

## Operator queue report (Phase 3)

`scripts/worker_pool.py report` provides a human-readable and JSON operator
summary for the queue:

- queue counts for `pending/`, `in-flight/`, `done/`, and `failed/`
- pending, in-flight, done, and failed task slugs
- stale in-flight detection using `--recover-stale-after`
- recent provider-rate telemetry and the derived floor
- a suggested next action: `recover-stale`, `run-pool`, `inspect-failed`, or
  `idle`
- a concrete suggested command when the queue needs action

This keeps the default `status` command stable for simple machine checks while
giving operators a morning-report view that exposes the metrics needed to make
the next scheduling decision.

## Larger pile canary (Phase 3)

`scripts/worker_pile_canary.py` provides the cheap first validation loop for
larger queue piles. The default canary creates six synthetic briefs, enqueues
them into a temporary queue, drains the queue with three workers, and verifies
that the final queue state is:

```
pending=0 in-flight=0 done=6 failed=0
```

The canary supports text and JSON output. Default `--mode synthetic` does not
launch providers; that is intentional. Its job is to prove the local queue,
worker sizing, report payload, and full-drain behavior are sound before the
same queue shape is promoted to a live OAuth pile smoke.

Every canary payload includes runtime provenance for the AO side of the run:
resolved AO binary path/source/version plus the configured AO runtime
worktree branch, HEAD, dirty flag, dirty-entry count, and a capped
porcelain-status preview. This keeps live canary evidence attributable when the
default AO runtime worktree is carrying unmerged runtime work.

Guarded live mode is available through:

```bash
python3 scripts/worker_pile_canary.py \
  --mode live \
  --confirm-live launch-live-providers \
  --tasks 6 \
  --workers 3 \
  --workspace ${FACTORY_V3_ROOT}
```

Live mode uses the worker-pool `run` defaults: per-task isolated worktrees and
artifact promotion back to `--workspace`. Without the exact confirmation token,
the command exits before enqueuing work. Live baseline mode also requires the
configured AO runtime worktree to be clean; `--allow-dirty-ao-runtime` is
available only for explicitly non-baseline experiments.

## Testing strategy

### Phase 1 — auto_partition.py

- `tests/test_auto_partition.py` — unit tests:
  - 1 scoped_write → 1 slice
  - 2 scoped_writes → 2 slices
  - 8 scoped_writes → 8 slices
  - 9 scoped_writes → 8 slices (capped)
  - scoped_writes containing a `run-artifacts/...` metadata path → that path is excluded from slice count
  - empty scoped_writes → falls back to single slice (today's behavior)
- Integrator quorum tests (in `tests/test_runtime_blockers.py`):
  - N=4, 3 DONE + 1 BLOCKED → DONE_WITH_CONCERNS
  - N=4, 2 DONE + 2 BLOCKED → BLOCKED
  - N=8, 6 DONE + 2 BLOCKED → DONE_WITH_CONCERNS
  - N=8, 5 DONE + 3 BLOCKED → BLOCKED

### Phase 2 — worker_pool.py + queue

- `tests/test_worker_pool.py` — unit + integration:
  - Atomic-mv claim under contention (two simulated workers, one task)
  - Crash recovery: stale `in-flight/` entry > threshold → moved back
  - W = 0 when queue empty, W ramps to MAX_WORKERS as queue fills
  - 429/rate-limit telemetry lowers `provider_rate_limit_floor` and shrinks W
  - `report` recommends pool execution, stale recovery, failed inspection, or
    idle state from queue evidence
  - `worker_pile_canary.py` drains a six-task pile with three workers and
    verifies final queue counts
  - `worker_pile_canary.py` reports AO binary and AO runtime worktree
    provenance in text and JSON evidence
  - `worker_pile_canary.py --mode live` refuses to launch without the
    `launch-live-providers` confirmation token
  - `worker_pile_canary.py --mode live --confirm-live launch-live-providers`
    refuses to launch against a dirty AO runtime unless
    `--allow-dirty-ao-runtime` is supplied
  - guarded live canary mode uses worker-pool live defaults: isolated worktrees
    and artifact promotion
  - Live `--mode run` defaults to isolated worker worktrees and artifact promotion
  - `--shared-workspace(s)` and `--no-promote-artifacts` explicitly opt out
  - Failed isolated workers still promote diagnostic artifacts
- `tests/test_factory_queue.py` — queue primitives:
  - stale `in-flight` recovery
  - fresh `in-flight` protection
  - pending filename collision protection

### Acceptance: `live_oauth_smoke`

- Phase 1/1.5: 6-file refactor task, single brief → N=6, accepted after
  integrator workspace materialization.
- Phase 2: two-task live default worker smoke → `pool --workers 2
  --foreground --once --mode run --workspace <temp-base>` with no explicit
  isolation/promotion flags; both tasks accepted, both promoted spec/plan/status/evaluation artifacts, final queue `pending=0 in-flight=0 done=2 failed=0`.
- Phase 3 synthetic larger pile canary: `worker_pile_canary.py --tasks 6
  --workers 3` verifies final queue `pending=0 in-flight=0 done=6 failed=0`.
- Phase 3 guarded live canary mode: `worker_pile_canary.py --mode live` exits
  unless `--confirm-live launch-live-providers` is supplied.
- Phase 3 canary runtime provenance: canary output records AO binary
  path/version and AO runtime worktree branch/HEAD/dirty status before any live
  provider launch is interpreted as baseline evidence.
- Phase 3 live baseline guard: confirmed live canary exits before queue
  creation/provider launch when the AO runtime worktree is dirty, unless
  `--allow-dirty-ao-runtime` is explicitly supplied.
- Remaining Phase 3 polish: execute the live larger pile canary.

## Bounded blast radius

The two axes are designed to be revertible per-axis without touching the
other:

- Disable Phase 1 → set MAX_SLICES = 1 in env. factory-manager emits one
  slice always; behavior reverts to today's single-mutator chain.
- Disable Phase 2 → run `factory_run.py` directly, skip
  `worker_pool.py`. Queue is unused; behavior reverts to today's
  one-task-at-a-time.
- Disable live worker isolation/promotion for a specific run →
  `--shared-workspace(s)` and/or `--no-promote-artifacts`.
- Disable both → MAX_SLICES = 1 + run factory_run.py directly =
  identical to today.

This is by design: the AO chain itself is unchanged. Only the dispatcher
above it (auto_partition + worker_pool) is new. Reverting either is a
config flip, not a code revert.

## Out of scope

- Cross-task slice migration (steal slices from another worker's task).
  Workers are share-nothing.
- Cross-task scheduling priorities (every task is FIFO).
- Distributed multi-host mode. The queue is local to one box.
- /ai-teams interop. The decoupling rule still holds — ao-operator owns
  its own queue and its own auto_partition; /ai-teams is unchanged.
- Provider-side parallelism beyond what the CLI already gives us.

## References

- PR #17 — manifest sync to mutator worktrees
- PR #21 — verdict aggregator with `runtime_blockers` /
  `runtime_role_results` / `runtime_concerns`
- PR #22 — pytest seed and `tests/test_runtime_blockers.py`
- PR #24 — `tests/test_extract_scoped_writes.py`
- PR #25 — inline SKILL.md bodies + Claude default to sonnet
- SDD 01 — architecture
- SDD 02 — implementation plan
- SDD 03 — interfaces and contracts
- SDD 04 — verification plan
- SDD 05 — provider routing
- SDD 06 — implementation checklist
