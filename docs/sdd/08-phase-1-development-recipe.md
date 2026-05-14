# Phase 1 development recipe

Status: design (no code)
Authored: 2026-05-03
Numbering: SDD 08 (07 = two-axis design)
Companion plan: [`docs/plans/two-axis-adaptive-scaling-plan.md`](../plans/two-axis-adaptive-scaling-plan.md)

## Purpose

Tighten the *development workflow* used to ship Phase 1 of the two-axis
adaptive scaling work. Adds four lightweight pre- and post-flight moves
borrowed from the gsd and gstack plugins. Does **not** change the Phase 1
code surface, the locked architectural parameters (`MAX_SLICES = 8`,
`MAX_WORKERS = 4`, `⌈3N/4⌉` quorum), or the AO chain.

The recipe is a checklist humans (and an assisting Claude session) follow
before, during, and after a `feat/ao-operator-*` PR. It is not pipeline
automation. If Phase 1's retro shows it earns its keep, it gets promoted to
Phase 2 / Phase 3 by reference.

## Scope and boundaries

**This recipe changes:**

- The order and evidence around the Phase 1 PR (`feat/ao-operator-auto-partition`).
- A single `.gitignore` line in ao-operator (excludes gsd's `.planning/`).

**This recipe does NOT change:**

- Two-axis architecture (SDD 07). All locked params unchanged.
- Phase 1 code surface: `auto_partition.py` + `factory_v3_config.py` +
  `factory_run.py` edit + 10 tests. LOC and locations unchanged.
- ao-operator runtime. gsd and gstack are tools we use to *build* ao-operator;
  ao-operator never dispatches into them at runtime.
- /ai-teams (v2). Decoupling rule preserved.
- Phase 1 → Phase 2 → Phase 3 ordering. Each phase remains independently
  revertible.

**Boundary rule (load-bearing):** gsd and gstack are tools we use to build
ao-operator. They are never tools ao-operator uses to build other things. They
run in our Claude Code session, not inside ao-operator's AO chain.

## Components

Four borrowed moves. Each is scoped tight; each is independently droppable
if the Phase 1 retro shows it is friction without value.

### 1. Pre-execution review (`/gstack:autoplan`)

- **Input:** the Phase 1 section of `docs/plans/two-axis-adaptive-scaling-plan.md`.
- **Action:** gstack's `autoplan` runs CEO + Eng + Design + DevEx perspectives
  in parallel against the plan, each producing a verdict + concerns.
- **Output:** appended `## Pre-execution review` block in the plan file with
  the four verdicts and any blockers.
- **Branch:** doc-only on `docs/ao-operator-phase-1-autoplan-review`, merged
  into `main` before code work starts.
- **Notes:** Phase 1 is backend Python — Design will likely vote
  `n/a (backend-only)`. CEO and Eng are the load-bearing votes; DevEx covers
  the env-override / `factory_v3_config.py` ergonomics surface.

### 2. Ambiguity gate (manual gsd rubric)

- **Input:** same Phase 1 plan section.
- **Action:** score four dimensions on `[0.0, 1.0]`:
  - Goal Clarity (weight 0.35, min 0.75)
  - Boundary Clarity (weight 0.25, min 0.70)
  - Constraint Clarity (weight 0.20, min 0.65)
  - Acceptance Criteria (weight 0.20, min 0.70)

  Compute `ambiguity = 1 − (0.35·G + 0.25·B + 0.20·C + 0.20·A)`.
  Gate: `ambiguity ≤ 0.20` AND every dimension at-or-above its minimum.

- **If gate fails:** tighten the plan inline, re-score. Max 2 tightening
  rounds. If still failing after round 2, escalate — do **not** weaken the
  gate.
- **Output:** appended `## Ambiguity scorecard` block in the plan file with
  the four scores, computed ambiguity, gate verdict, and rounds-to-pass.
- **Manual, not via `/gsd:spec-phase`.** We do not want gsd's `.planning/`
  directory next to our `docs/` directory.

### 3. Session continuity (gsd hooks, already wired)

- gsd's `PreCompact` and `SessionStart` hooks already fire (the gsd plugin
  install touched `~/.claude/settings.json`). Nothing to wire.
- **Behavior:** when Claude Code's `/compact` triggers mid-Phase-1, gsd
  writes `.planning/HANDOFF.json` capturing phase, plan, task, and recent
  decisions. The next session detects it via `SessionStart` and auto-runs
  `/gsd:resume-work`.
- **One repo change:** add `.planning/` to ao-operator's `.gitignore` so
  gsd's checkpoint files never land in commits.

### 4. Targeted debug on failures (`/gstack:investigate`)

- **`/gstack:investigate`** runs if any test fails or the live OAuth smoke
  blocks. Enforces a structured triage (reproduce → localize → hypothesize
  → fix). Read-mostly by default.
- Invoked manually from the Claude session, not from ao-operator.
- **Diff review is owned by the existing v2 `code-reviewer` agent** (already
  battle-tested on this codebase). Adding `/gstack:review` as a second
  reviewer post-hoc was considered and rejected — see *What we are
  explicitly NOT borrowing* below.

### What we are explicitly NOT borrowing

- **`/gsd:execute-phase`** — would replace planner.md + dispatch_gate.py.
  Out of scope.
- **`/gsd:ship`** — would replace the existing PR flow. Out of scope.
- **`/gstack:review`** as post-implementation diff reviewer — duplicates the
  existing v2 `code-reviewer` agent. Two reviewers on the same diff means
  either redundant work (they agree) or reconciliation overhead (they
  disagree). The pre-flight `/gstack:autoplan` already injects
  multi-perspective signal where it has the highest leverage (before code
  is written); a second reviewer post-hoc is symmetry chasing, not value.
- **gstack `office-hours`, `plan-ceo-review`, etc. as standalone skills** —
  `autoplan` already runs all four perspectives.
- **gstack `gbrain`** (cross-machine memory via private GitHub repo) — adds
  a dependency for marginal value over claude-mem (already installed).
- **gstack `browse`** (headless Chromium) — Phase 1 is backend Python; no
  UI to dogfood. Park for future UI work.
- **gstack "Boil the Lake" philosophy** — explicitly contradicts the
  "design-only first, phased PRs" decision recorded in
  `docs/plans/two-axis-adaptive-scaling-plan.md`.

## Data flow (one Phase-1-style PR end-to-end)

```text
ARTIFACTS ALREADY ON MAIN
  docs/sdd/07-two-axis-adaptive-scaling.md      (locked design)
  docs/plans/two-axis-adaptive-scaling-plan.md  (Phase 1 scoped)
        │
        ▼
[STEP 0] Branch
   git checkout -b docs/ao-operator-phase-1-autoplan-review
        │
        ▼
[STEP 1] /gstack:autoplan  →  appends `## Pre-execution review`
   Gate: any Eng BLOCKER → tighten plan, re-run
        │
        ▼
[STEP 2] Manual ambiguity score (gsd rubric)
   Appends `## Ambiguity scorecard`
   Gate: ambiguity ≤ 0.20 AND all minimums met
   Fail: tighten inline, re-score (max 2 rounds)
        │
        ▼
[STEP 3] Merge review-branch into main
   Plan now carries autoplan + ambiguity evidence
        │
        ▼
[STEP 4] Cut implementation branch
   git checkout -b feat/ao-operator-auto-partition
   Add `.planning/` to .gitignore (one-line commit)
        │
        ▼
[STEP 5] TDD per existing Phase 1 plan
   Discipline source:  superpowers:test-driven-development skill
   Fresh session boundary — Phase 1 starts in a /clear-ed session;
                            no Phase 1 context bleeds into Phase 2
   tests/test_auto_partition.py    (write first, 6 tests)
   scripts/factory_v3_config.py    (constants + env)
   scripts/auto_partition.py       (partition + helper)
   scripts/factory_run.py edits    (wire fan-out + quorum)
   tests/test_runtime_blockers.py  (4 quorum tests)
   On block:   /gstack:investigate
   On compact: gsd HANDOFF.json auto-resumes
        │
        ▼
[STEP 6] Verification
   pytest tests/                  (29 + 6 + 4 = 39 pass)
   validate_scaffold.py           (verdict=PASS)
   live_oauth_smoke               (6-file refactor → DONE)
   Wallclock: ≥3× speedup vs N=1  (per existing acceptance)
        │
        ▼
[STEP 7] Open PR with embedded evidence
   Reviewer:  existing v2 code-reviewer agent on the diff
   Body:      links to autoplan section + scorecard + smoke log
   Reviewers: standard ao-operator review
        │
        ▼
                       MAIN
```

**Invariants:**

- The plan file accumulates evidence (autoplan + scorecard) **before** code
  branches, so Phase 2 inherits the same hardened plan.
- Implementation branch is unchanged from the original Phase 1 plan: same
  files, same LOC, same TDD order.
- gsd's `HANDOFF.json` runs in the background; no manual step.
- Two new commits land on main *before* the implementation branch, both
  doc-only and trivially revertible.

## Failure modes and fallbacks

| # | Symptom | Resolution |
|---|---------|------------|
| 1 | `/gstack:autoplan` returns conflicting verdicts | Eng vote wins on technical concerns; CEO/DevEx wins on scope/UX. Genuine deadlock → user breaks tie. Any Eng `BLOCKED` is hard-blocking. |
| 2 | `/gstack:autoplan` hangs or crashes | Skip Step 1. Move to Step 2. Note in plan: `## Pre-execution review — skipped (autoplan unavailable)`. Try once, ~10 min budget. Do not retry. |
| 3 | Ambiguity score never passes gate | Stop after 2 tightening rounds. Either the plan is genuinely under-spec'd or my rubric application is wrong. Escalate to user. **Do not weaken the gate to make it pass.** |
| 4 | gsd `HANDOFF.json` conflicts with ao-operator's `run-artifacts/<slug>-status.md` | No actual conflict. ao-operator status files own ao-operator work; gsd HANDOFF owns *our session continuity*. `.gitignore` on `.planning/` prevents bleed. |
| 5 | `/gstack:investigate` makes unwanted edits | Wrap in `/gstack:freeze scripts/` to restrict edits to the test directory. First-line response: `git revert` or `git restore`. Read gstack `investigate` SKILL.md before first use. |
| 6 | `PreCompact` hook truncates pytest output we needed | Hook is non-destructive (HANDOFF written first). Re-run the failing test. Tests are deterministic. |
| 7 | Recipe wallclock overhead > 50% of Phase 1 budget | Threshold: ~20 min total added (autoplan ~10, scorecard ~5, gluing ~5). If overrun: log it, drop the worst-signal step on Phase 2. |

**Overall escape hatch:** the existing Phase 1 plan is executable today
without any of these moves. If at any point the recipe is friction without
value, drop back to the original plan and ship Phase 1 directly. The recipe
is purely additive; it never blocks the underlying work.

## Verification

Per-step evidence collected during the Phase 1 PR:

| Step | Artifact | What it proves |
|------|----------|----------------|
| 1 — autoplan | `## Pre-execution review` block (4 verdicts) | At least one perspective surfaced something the original plan missed (or didn't — also a data point) |
| 2 — scorecard | `## Ambiguity scorecard` block (G/B/C/A scores + ambiguity + rounds-to-pass) | Plan passes the gate before code is written |
| 3 — HANDOFF | `.planning/HANDOFF.json` exists at end of session 1; the next session (after `/compact` or window restart) auto-resumes | Continuity worked end-to-end without a manual `/brief` re-orientation |
| 4 — Phase 1 | All original Phase 1 verifications still pass: 39 tests green, `validate_scaffold` PASS, `live_oauth_smoke` 6-file refactor → DONE, ≥ 3× wallclock speedup vs N=1 | Recipe didn't degrade the underlying ship |

### Recipe-level acceptance (decision criteria for Phase 2 / 3)

After the Phase 1 PR ships, write a one-page retro answering:

1. **Did autoplan find anything plan-hardener wouldn't have?** Yes ≥ 1
   actionable finding → keep for Phase 2. No → drop or downgrade to optional.
2. **Did the ambiguity score change behavior?** Tightened the plan because
   of it → keep. Rubber-stamped → drop or run silently in the background.
3. **Did `HANDOFF.json` save a session re-orientation?** Binary. Track count
   over Phase 2 / 3.
4. **Total wallclock overhead.** Target ≤ 20 min added. If > 45 min: trim
   aggressively.

### Codification trigger

If Phase 1's retro shows the recipe is net-positive (≥ 3 of 4 keeps from
above):

- Write `docs/dev-workflow/recipe-autoplan-and-score.md` describing the
  recipe.
- Add a one-line pointer in ao-operator's `CLAUDE.md` (or equivalent):
  `Before any feat/* PR, follow the recipe in docs/dev-workflow/...`.
- Phase 2 PR follows the same recipe by default.

If retro is net-neutral or negative:

- Leave Phase 1 evidence in the plan file (still useful history).
- Do not codify. Phase 2 reverts to the existing planner.md flow.

**No GitHub Actions changes, no CI integration, no automation in this
design.** The recipe is a checklist, not a pipeline. If we eventually
automate it, that is a separate decision after we know it earns the cost.

## Out of scope

- Migrating ao-operator to gsd's project model (`/gsd:new-milestone`,
  `/gsd:execute-phase`, `/gsd:ship`). Would replace orchestration; not
  worth the ceremony for a 150-LOC PR.
- Wholesale adoption of gstack's "Boil the Lake" philosophy. Contradicts
  the existing phased-PR decision.
- Cross-machine memory via gstack `gbrain`. Marginal value over already-
  installed claude-mem.
- Any change to /ai-teams (v2 factory). Decoupling rule preserved.
- Any runtime call from ao-operator into gsd or gstack. Boundary rule.
- **The "spec-driven autonomous" composition** popularised in third-party
  walkthroughs (gstack-spec + gsd-phases + superpowers-exec + Ralph-loop
  orchestrating headless `claude -p` sessions per phase). Right pattern at
  the wrong scale for Phase 1 (150 LOC). Its centerpiece —
  orchestrator-delegates-to-headless-sessions to keep main context clean
  — is structurally identical to what ao-operator *itself* does at runtime
  (worker pool + per-task worktrees + verdict aggregator, SDD 07). Adopting
  it as our dev-tooling layer would solve the same problem twice and stand
  up a third orchestrator on top of v2 + v3. The cross-phase invariants
  the AO chain enforces inline (per-slice scoped writes, integrator quorum
  gate) would re-emerge as cross-session reconciliation problems
  (summary fidelity, drift between headless runs). Reconsider only if a
  future initiative needs 5+ phases shipped autonomously overnight; for
  Phase 1, single-session TDD with pre-flight autoplan + ambiguity score
  earns more accuracy per minute.

## References

- SDD 07 — Two-axis adaptive scaling design
- `docs/plans/two-axis-adaptive-scaling-plan.md` — Companion ground plan
- gsd plugin: `~/.claude/plugins/cache/gsd-plugin/gsd/2.40.0/`
- gstack skills: `~/.claude/skills/gstack/`
- v2/v3 factory decoupling memory:
  `[REDACTED_LOCAL_MEMORY_PATH]/factory_decoupling.md`
