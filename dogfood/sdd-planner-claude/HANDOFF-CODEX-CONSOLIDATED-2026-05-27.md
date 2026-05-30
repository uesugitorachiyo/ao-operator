# Consolidated handoff to codex — 7-item sweep

Date: 2026-05-27
Author: claude (ao-operator session)
Scope: full takeover of all open work surfaced by the 3-repo audit (ao2, ao-operator, ao2-control-plane).

## Why one doc

Normally items 1/3/4/6 live on the claude side (ao-operator, memory) and items 2/5/7 live on the codex side (ao2 source). The user asked for a single consolidated handoff so codex can drive everything end to end. The trust boundary is temporarily lifted *for this sweep* — codex may edit ao-operator and the claude-memory directory for the items listed below. Outside this sweep the usual boundary still holds (claude owns ao-operator + sdd-planner-private; codex owns ao2 + ao2-control-plane).

## Order of operations

Run items in this order — later items depend on the earlier cleanup:

1 (stage 1 commit) → 3 (memory hygiene) → 4 (working-tree triage) → 6 (gap-backlog investigation) → 2 (PR drop-ins) → 5 (Phase-2 W2) → 7 (sdd-planner merge)

Rationale: clear ao-operator's working-tree noise first so subsequent diffs are readable; do the disruptive ao2/cp work last when there's a clean state to fall back to.

## Constraints that hold throughout

- **Watchdog autocommit risk** — `~/Documents/ao2` (and probably ao-operator too) has a watchdog process that auto-commits during long cargo test windows with its own author identity. Before every `git commit` in those repos, run `git rev-parse HEAD` and confirm it matches what you expect. Memory: `feedback_concurrent_watchdog_autocommits_during_long_tests.md`.
- **ao2 pre-commit hook rewrites long commit subjects** — multi-paragraph subjects collapse to one line. Body survives. Expect to see "exit 1 then success" once per commit on ao2; that's normal. Memory: `feedback_ao2_precommit_rewrites_long_subject.md`.
- **Do not merge `ao2 claude generate-hooks --runtime claude` output into `~/.claude/settings.json`** — unexpanded `$TASK_ID/$COMMAND` will brick the operator session. Memory: `feedback_ao_claude_hooks_brick_operator_session.md`.
- **Never `--no-verify` or `--no-gpg-sign`** — keep governance hooks in play. Investigate failures, don't bypass.
- **Lane refresh order in ao-operator status artifacts**: lane → parity-refresh → readiness-refresh as three separate commits; never regen readiness from a dirty tree. Memory: `feedback_status_artifact_lane_order.md`.

---

## Item 1 — Commit ao-operator stage 1 (shim + dogfood handoffs)

**Why:** Three artifacts from the 2026-05-27 sdd-planner self-build session are sitting untracked. They're stable, small, and unrelated to the noisier status-artifact refresh. Commit them as one clean atomic commit before doing anything else so subsequent diffs are readable.

**Files to add:**

```
tools/claude-shim/claude
tools/claude-shim/dogfood.sh            # if present
tools/claude-shim/README.md             # if present
dogfood/sdd-planner-claude/findings.md
dogfood/sdd-planner-claude/HANDOFF-EXECUTE-PLANS.md
dogfood/sdd-planner-claude/HANDOFF-MERGE-SDD-PLANNER-INTO-AO2.md
dogfood/sdd-planner-claude/HANDOFF-CODEX-CONSOLIDATED-2026-05-27.md   # this file
```

**Commands:**

```bash
cd ~/Documents/ao-operator
git rev-parse HEAD                       # remember this — watchdog check
git add tools/claude-shim/ dogfood/sdd-planner-claude/
git status                               # confirm only the intended files staged
git rev-parse HEAD                       # confirm still the same — watchdog hasn't autocommitted
git commit -m "$(cat <<'EOF'
feat(tools): land claude-shim + sdd-planner dogfood handoffs

Three artifacts from the 2026-05-27 sdd-planner self-build dogfood:
- tools/claude-shim/ — Python OAuth wrapper for `claude --print`,
  required ahead of $PATH for `ao2 sdd plan --provider claude`
- dogfood/sdd-planner-claude/findings.md — G1-G11 dogfood gap writeup
- dogfood/sdd-planner-claude/HANDOFF-*.md — codex handoffs (executed,
  merge proposal, consolidated sweep)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Verification:** `git log -1 --name-status` shows the three files only.

---

## Item 3 — Memory hygiene sweep (claude auto-memory)

**Why:** 8 memory files at `~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/` point at a `scripts/check_release_readiness.py` and a `run-artifacts/remote-transfer-v2-stress-live/` lane that no longer exist in ao-operator. They will cause future claude sessions to make decisions based on a removed subsystem. Same treatment as the SDD-130 entry already got (marked STALE).

**Memory files to mark STALE (do NOT delete — preserve as historical):**

```
~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/
├── feedback_gate_work_dir_must_be_tempfile.md
├── feedback_gate_case_field_observed_verdict.md
├── feedback_readiness_cascade_redaction_chicken_egg.md
├── feedback_readiness_cascade_dirty_subordinates.md
├── feedback_launcher_test_now_pinning.md
├── feedback_lane_commit_a_must_register_readiness.md
├── feedback_status_artifact_lane_order.md
├── feedback_section_6_row_text_avoid_concrete_identifiers.md
└── project_ao2_phase2_resume_point.md
```

**Treatment:** For each file, edit the frontmatter `description` field to prepend `STALE 2026-05-27 — ` and add a short body section at the top:

```markdown
## STALE 2026-05-27

**Why stale (verified 2026-05-27):** This memory references `scripts/check_release_readiness.py`, `run-artifacts/remote-transfer-v2-stress-live/`, and SHAs that are not in ao-operator HEAD. The readiness-cascade subsystem was removed; the project advanced along the Hermes/governed-backend/control-plane/nightly-ao2 axis instead. Pattern matches [[sdd-130-resume-point-stale-as-of-2026-05-27]].

**How to apply:** Do not act on the rules below without re-verifying. Kept for historical context only.

---
```

(Original content remains untouched below the separator.)

**MEMORY.md update:** Edit each line in `MEMORY.md` so the affected entries are prefixed with `(STALE) ` to make the index honest:

```
- (STALE) [Readiness cascade — pass allowed_dirty for subordinate refreshes](feedback_readiness_cascade_dirty_subordinates.md) — ...
- (STALE) [Launcher tests — pin `now=` ...](feedback_launcher_test_now_pinning.md) — ...
```

…and so on for the 9 files above.

**Replacement memory to add** — write a new file `feedback_claude_shim_path.md`:

```markdown
---
name: feedback-claude-shim-path
description: claude-shim lives at ao-operator/tools/claude-shim/claude (committed 2026-05-27 in item-1 of consolidated codex handoff). Old reference to scripts/claude-oauth-shim.py is stale.
metadata:
  type: feedback
---

The persistent OAuth shim for `ao2 sdd plan --provider claude` lives at:

```
~/Documents/ao-operator/tools/claude-shim/claude
```

**Why:** It moved from `/tmp/sdd-planner-claude-shim/` to `ao-operator/tools/` on 2026-05-27 to survive `/tmp` cleanup. The upstream copy at `sdd-planner-private/scripts/claude-oauth-shim.py` (G7) mirrors the same OAuth wrapping logic.

**How to apply:** When invoking `ao2 sdd plan --provider claude`, put the ao-operator shim ahead on PATH. **Do not** put it ahead for `ao2 run --provider claude` — that uses argv, not stdin envelope, and the shim will reject with "shim: stdin is not JSON".
```

…and add the line to `MEMORY.md`:

```
- [claude-shim PATH discipline](feedback_claude_shim_path.md) — ao-operator/tools/claude-shim/claude for `ao2 sdd plan`; never PATH-prefix it for `ao2 run`
```

**Commit:** Memory is not in a repo. The hygiene sweep is a single-pass file edit. After the sweep, run a sanity check that future-claude can still load:

```bash
ls -la ~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/MEMORY.md
wc -l ~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/MEMORY.md
```

Expected line count is ≤200 (truncation boundary).

---

## Item 4 — Triage ao-operator working tree

**Why:** 42 modified files + 177 untracked files. A mix of in-progress nightly-cascade refresh (commit-worthy), watchdog log series (gitignore-worthy), and abandoned smoke-run scratch (delete-worthy).

**Step 4a — Commit the in-progress nightly cascade**

The 42 modified files under `run-artifacts/hermes-nightly-ao2/` + `run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/` are mid-refresh. Follow the three-commit lane→parity→readiness pattern.

```bash
cd ~/Documents/ao-operator
git rev-parse HEAD

# Inspect the modified set
git status --short | grep '^ M' | head -50

# Commit 1: lane refresh (logs, evidence, gap-backlog regen)
git add run-artifacts/hermes-nightly-ao2/logs/ \
        run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/
git rev-parse HEAD                         # watchdog check
git commit -m "$(cat <<'EOF'
chore(status): refresh hermes-nightly-ao2 lane (2026-05-27 cascade)

Regen of logs, evidence packs, and gap-backlog snapshots from
nightly cascade left mid-flight. No semantic changes; lane refresh
only, per the lane→parity→readiness three-commit pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 2: parity refresh (ao2 / control-plane / factory verifiers)
git add run-artifacts/hermes-nightly-ao2/ao2-provider-registry.json \
        run-artifacts/hermes-nightly-ao2/closure-obligation-gate.json \
        run-artifacts/hermes-nightly-ao2/control-plane-release-smoke.json \
        run-artifacts/hermes-nightly-ao2/midpoint-obligation-gate.json
git rev-parse HEAD
git commit -m "$(cat <<'EOF'
chore(status): refresh hermes-nightly-ao2 parity gates

Refresh of provider-registry / closure-obligation / midpoint-obligation /
control-plane-release-smoke gate verdicts following the lane refresh.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 3: readiness refresh (advancement summary + notification)
git add run-artifacts/hermes-nightly-ao2/nightly-ao2-advancement.{json,md} \
        run-artifacts/hermes-nightly-ao2/gap-backlog.json \
        run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/nightly-ao2-advancement.{json,md} \
        run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/gap-backlog.json \
        run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/nightly-notification.json
git rev-parse HEAD
git commit -m "$(cat <<'EOF'
chore(status): refresh hermes-nightly-ao2 readiness summary

Final readiness-cascade commit after lane + parity refreshes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Step 4b — Gitignore watchdog log series**

The audit identified 177 untracked files under `run-artifacts/hermes-governed-backend-control-plane/`, mostly `watchdog-loop.out.log` series and operator launchd scaffolding. Most are not commit-worthy.

```bash
# Inspect first
ls -la run-artifacts/hermes-governed-backend-control-plane/ | head -30
find run-artifacts/hermes-governed-backend-control-plane/ -name 'watchdog-loop*.log' | head -10
find run-artifacts/hermes-governed-backend-control-plane/ -name 'watchdog-loop*.out*' | head -10
```

Append to `.gitignore`:

```
# Operator-local watchdog log rotations — never commit
run-artifacts/hermes-governed-backend-control-plane/**/watchdog-loop*.log
run-artifacts/hermes-governed-backend-control-plane/**/watchdog-loop*.out
run-artifacts/hermes-governed-backend-control-plane/**/watchdog-loop*.out.*
run-artifacts/hermes-governed-backend-control-plane/**/watchdog-launchd-*.log
```

Verify and commit:

```bash
git status --short run-artifacts/hermes-governed-backend-control-plane/ | wc -l   # should drop significantly
git add .gitignore
git commit -m "chore(gitignore): exclude operator-local watchdog log rotations

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**Step 4c — Commit the legitimate untracked under hermes-governed-backend-control-plane**

After the gitignore prunes log noise, the remaining untracked files should be evidence packs, factory-compat signed payloads, and watchdog runtime config (plist + shell). Inspect remaining `git status` and commit the substantive ones:

```bash
git status --short run-artifacts/hermes-governed-backend-control-plane/ | head -30
# Stage carefully — never `git add -A`. Add directories or specific files.
git add run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/com.ao-operator.hermes-ao2-watchdog.plist
git add run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/watchdog-loop.sh
git add run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/watchdog-launchd-tick.sh
git add run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/guard-bin/git
# Inspect and add other substantive untracked individually.
git rev-parse HEAD
git commit -m "feat(watchdog): land hermes-ao2 watchdog operator scaffolding

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

**Step 4d — Delete abandoned scratch lanes**

The audit identified these as never-committed, mtime >14 days, no live consumers:

- `run-artifacts/claude-loop-control-plane/`
- `run-artifacts/factoryv3-smoke-secagent-live-mac-retry{3,4}/`
- `run-artifacts/factoryv3-smoke-evidence-live/`
- `run-artifacts/factoryv3-smoke-evidence-postfix/`
- `run-artifacts/factoryv3-smoke-fa-secagent/`
- `run-artifacts/factoryv3-smoke-secagent-debug-mac/`
- `run-artifacts/factoryv3-smoke-secagent-live-mac/`
- `run-artifacts/factoryv3-smoke-secagent-mac-fe-verify/`
- `run-artifacts/factoryv3-smoke-changelog{,-v2,-v5}/`

```bash
# Final inspection before delete
for d in \
  run-artifacts/claude-loop-control-plane \
  run-artifacts/factoryv3-smoke-secagent-live-mac-retry3 \
  run-artifacts/factoryv3-smoke-secagent-live-mac-retry4 \
  run-artifacts/factoryv3-smoke-evidence-live \
  run-artifacts/factoryv3-smoke-evidence-postfix \
  run-artifacts/factoryv3-smoke-fa-secagent \
  run-artifacts/factoryv3-smoke-secagent-debug-mac \
  run-artifacts/factoryv3-smoke-secagent-live-mac \
  run-artifacts/factoryv3-smoke-secagent-mac-fe-verify \
  run-artifacts/factoryv3-smoke-changelog \
  run-artifacts/factoryv3-smoke-changelog-v2 \
  run-artifacts/factoryv3-smoke-changelog-v5
do
  [ -d "$d" ] && echo "WILL DELETE: $d ($(find "$d" -type f | wc -l) files)"
done

# If the list looks right:
rm -rf run-artifacts/claude-loop-control-plane/ \
       run-artifacts/factoryv3-smoke-secagent-live-mac-retry3/ \
       run-artifacts/factoryv3-smoke-secagent-live-mac-retry4/ \
       run-artifacts/factoryv3-smoke-evidence-live/ \
       run-artifacts/factoryv3-smoke-evidence-postfix/ \
       run-artifacts/factoryv3-smoke-fa-secagent/ \
       run-artifacts/factoryv3-smoke-secagent-debug-mac/ \
       run-artifacts/factoryv3-smoke-secagent-live-mac/ \
       run-artifacts/factoryv3-smoke-secagent-mac-fe-verify/ \
       run-artifacts/factoryv3-smoke-changelog/ \
       run-artifacts/factoryv3-smoke-changelog-v2/ \
       run-artifacts/factoryv3-smoke-changelog-v5/
```

These directories are untracked — no `git rm` needed. No commit needed for the deletion itself (nothing was tracked).

**Step 4e — Sanity check final working-tree state**

```bash
git status --short | wc -l                # should be <20
git log --oneline -5                      # should show 4 new commits from item 1 + 4a/b/c
```

---

## Item 6 — Investigate stuck gap-backlog

**Why:** Both `run-artifacts/hermes-nightly-ao2/gap-backlog.json` (2026-05-26) and `run-artifacts/hermes-governed-backend-control-plane/watchdog-runtime/nightly-ao2/gap-backlog.json` (2026-05-25) show *identical* 179 test-skip + 17 openssl-test-fixture + 4 openssl-reference items. Two consecutive snapshot windows with zero advancement — either the advancement script regressed, or these items are intentionally permanent.

**Diagnosis steps:**

```bash
cd ~/Documents/ao-operator

# 1. Find the advancement script
find . -name 'hermes_nightly_ao2_advancement.py' -not -path './node_modules/*' 2>/dev/null
# Should be in scripts/.

# 2. Read its logic — what "advances" a gap-backlog item?
# Look for: how does a test-skip item get retired? Is there an automated path or only manual?
less scripts/hermes_nightly_ao2_advancement.py

# 3. Spot-check 5 test-skip items: are they live env-gated tests or actual debt?
jq -r '.items[] | select(.category=="test-skip") | "\(.repo):\(.path):\(.line)"' \
  run-artifacts/hermes-nightly-ao2/gap-backlog.json | head -5

# 4. For each spot-check item, inspect: is it gated on an env var like AO_LIVE_CROSS_HOST=1?
#    If yes → it's permanent, should move to accepted-skip
#    If no  → it's debt, should advance
```

**Two possible outcomes:**

**Outcome A: items are permanent env-gated tests.** Split the schema. Add an `accepted_skip` bucket to the gap-backlog producer and move the 179 test-skip items there. The "advancement" lane should then report `gap_backlog: 21, accepted_skip: 179`. Writeup: `run-artifacts/hermes-nightly-ao2/findings-2026-05-27-gap-backlog-stuck.md` with the diagnosis and the proposed schema split. Update the producer script in the same PR.

**Outcome B: advancement script regressed.** Find the regression. Probable culprit: a commit that changed the filter predicate (test-skip items now never match), a clock-skew issue in the "is this older than the cutoff" check, or a producer that overwrites the snapshot before the advancer runs. Fix and verify by running the advancer on the live backlog and confirming the count drops.

**Either way**, commit the findings + fix as one or two atomic commits to ao-operator main.

---

## Item 2 — Apply the 5 ready-to-PR drop-ins

**Why:** `~/Documents/ao2/docs/ready-to-pr/` contains 5 drafted PR bundles from Phase-2 W3/W4/W5 that an autonomous-mode classifier blocked from auto-commit. They're complete diffs ready to apply — converting blocked-drafted work into shipped work.

**Inventory** (read each before applying):

```
ao2/docs/ready-to-pr/
├── W3-handler-annotations/
│   ├── phase1_promotion.diff           → ao2-control-plane/crates/ao2-cp-server/src/handlers/phase1_promotion.rs
│   └── provider_readiness.diff         → ao2-control-plane/crates/ao2-cp-server/src/handlers/provider_readiness.rs
├── release-gate.yml                    → ao2/.github/workflows/release-gate.yml (new file)
├── private-release-build.diff         → ao2/<somewhere — read header>
├── W5-P0-healthz-extended/
│   ├── health.diff                     → ao2-control-plane/crates/ao2-cp-server/src/health.rs
│   ├── metrics.diff                    → ao2-control-plane/crates/ao2-cp-server/src/metrics.rs
│   ├── server.diff                     → ao2-control-plane/crates/ao2-cp-server/src/server.rs
│   └── test.diff                       → ao2-control-plane/crates/ao2-cp-server/tests/<…>.rs
└── W5-P1-long-lived-dev.md             → ao2-control-plane/docs/runbooks/long-lived-dev.md (new file)
```

**Apply order:**

1. **W3 handler annotations** (cp) — small, low-risk, ao-operator evidence consumers depend on the annotations.

   ```bash
   cd ~/Documents/ao2-control-plane
   git rev-parse HEAD
   git apply --check ~/Documents/ao2/docs/ready-to-pr/W3-handler-annotations/phase1_promotion.diff
   git apply --check ~/Documents/ao2/docs/ready-to-pr/W3-handler-annotations/provider_readiness.diff
   # If both --check pass:
   git apply ~/Documents/ao2/docs/ready-to-pr/W3-handler-annotations/phase1_promotion.diff
   git apply ~/Documents/ao2/docs/ready-to-pr/W3-handler-annotations/provider_readiness.diff
   cargo build --workspace
   cargo test --workspace
   git add crates/ao2-cp-server/src/handlers/
   git rev-parse HEAD       # watchdog check
   git commit -m "feat(handlers): annotate phase1_promotion + provider_readiness for ao-operator migration window

Applies W3 ready-to-PR drop-ins from ao2/docs/ready-to-pr/W3-handler-annotations/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```

2. **W5 P0 healthz-extended** (cp) — adds dashboard uptime metric + retention policy to `/healthz`.

   ```bash
   cd ~/Documents/ao2-control-plane
   for f in health.diff metrics.diff server.diff test.diff; do
     git apply --check ~/Documents/ao2/docs/ready-to-pr/W5-P0-healthz-extended/$f
   done
   # If all 4 --check pass:
   for f in health.diff metrics.diff server.diff test.diff; do
     git apply ~/Documents/ao2/docs/ready-to-pr/W5-P0-healthz-extended/$f
   done
   cargo build --workspace
   cargo test --workspace -p ao2-cp-server
   git add -A
   git rev-parse HEAD
   git commit -m "feat(cp): extend /healthz with dashboard uptime + retention policy (W5 P0)

Applies W5 P0 ready-to-PR drop-ins from ao2/docs/ready-to-pr/W5-P0-healthz-extended/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```

3. **W5 P1 long-lived dev runbook** (cp) — documentation drop-in.

   ```bash
   cd ~/Documents/ao2-control-plane
   mkdir -p docs/runbooks
   cp ~/Documents/ao2/docs/ready-to-pr/W5-P1-long-lived-dev.md docs/runbooks/long-lived-dev.md
   git add docs/runbooks/long-lived-dev.md
   git commit -m "docs(runbooks): land long-lived dev environment runbook (W5 P1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```

4. **W4 release-gate workflow** (ao2) — CI workflow + private build path.

   ```bash
   cd ~/Documents/ao2
   mkdir -p .github/workflows
   cp docs/ready-to-pr/release-gate.yml .github/workflows/release-gate.yml
   git apply --check docs/ready-to-pr/private-release-build.diff
   git apply docs/ready-to-pr/private-release-build.diff
   cargo build --workspace      # sanity
   git add .github/workflows/release-gate.yml
   git add -u                   # picks up the private-release-build edits
   git rev-parse HEAD
   git commit -m "ci(release): land release-gate workflow + private build path (W4)

Applies W4 ready-to-PR drop-ins. Inspect the new workflow before
pushing — first run will likely need secret config in the repo settings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```

5. After all 5 land, remove the now-applied drop-ins from `ao2/docs/ready-to-pr/`:

   ```bash
   cd ~/Documents/ao2
   git rm -r docs/ready-to-pr/W3-handler-annotations/ \
             docs/ready-to-pr/W5-P0-healthz-extended/ \
             docs/ready-to-pr/W5-P1-long-lived-dev.md \
             docs/ready-to-pr/release-gate.yml \
             docs/ready-to-pr/private-release-build.diff
   git commit -m "chore(docs): retire applied W3/W4/W5 ready-to-PR drop-ins

Each landed in its target repo:
- W3 → ao2-control-plane (handlers)
- W4 → ao2 (.github/workflows + private build)
- W5 P0 → ao2-control-plane (healthz extension)
- W5 P1 → ao2-control-plane (runbook)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```

**Verification:** `cargo test --workspace` green on both `~/Documents/ao2` and `~/Documents/ao2-control-plane`.

---

## Item 5 — Phase-2 W2 P3/P4 cutover in ao2

**Why:** Three TODOs in `~/Documents/ao2/docs/roadmap/PHASE-2-BASELINE-METRICS.md` (lines 83–85) are blocking baseline-metrics closure:

- **W2 P4: parity oracle for `ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1`.** Schema emitted at `crates/ao2-cli/src/main.rs:1159` and `:5232`, no parity oracle exists. The ao-operator producer (if any) and the ao2-native emitter need a side-by-side diff oracle so the cutover can be confirmed.
- **W2 P3 part 1: complete `release-evaluator-decision` producer cutover.** AO2-native Rust producer landed at `crates/ao2-cli/src/main.rs:28377` (`EVALUATOR_DECISION_SCHEMA`), but `ao-operator/scripts/ao2_release_evaluator_decision.py` is still the authoritative source per the baseline-metrics doc. Decide: deprecate the Python producer, write a one-shot diff confirming the two produce equivalent output, then delete the Python.
- **W2 P3 part 2: audit `ao-operator/closer-decision/v*` ownership.** Only AO2-side reference is `crates/ao2-cli/src/factory_bridge.rs:1215` emitting `ao2.evaluator-closer-decision.v1`. Determine whether ao-operator still owns a producer or if AO2 is now sole authority; update the baseline-metrics doc accordingly.

**Recommended steps:**

1. Write the parity oracle as a small Rust integration test or a `bin/parity-watchdog-no-active-ao2-runs.rs` that runs both producers on a fixed input, diffs the JSON outputs, and emits a parity verdict. Land in `~/Documents/ao2/crates/ao2-cli/tests/` or `bin/`.
2. Run the parity oracle against `release-evaluator-decision` too. If outputs match, mark the Python deprecated (add a `# DEPRECATED 2026-05-27 — superseded by ao2-cli EVALUATOR_DECISION_SCHEMA` header to `~/Documents/ao-operator/scripts/ao2_release_evaluator_decision.py` and update baseline-metrics doc).
3. For closer-decision ownership: `git grep -l ao-operator/closer-decision` across all three repos. Determine current consumer/producer split. Update PHASE-2-BASELINE-METRICS.md line 85 with the resolution.

**Commit each step atomically.** Three commits expected on `~/Documents/ao2`, one on `~/Documents/ao-operator` (the deprecation header).

**Verification:** PHASE-2-BASELINE-METRICS.md no longer has any TODO lines.

---

## Item 7 — Merge sdd-planner-private into ao2 workspace

**Already drafted.** Read and execute `~/Documents/ao-operator/dogfood/sdd-planner-claude/HANDOFF-MERGE-SDD-PLANNER-INTO-AO2.md` in full. Summary:

- Goal: `~/Documents/sdd-planner-private` → `~/Documents/ao2/crates/sdd-planner/` via `git subtree add` preserving all 10 claude-session commits.
- Wire workspace member + `[workspace.dependencies] vergen-git2 = "1.0.7"`.
- Add `.github/CODEOWNERS` with `/crates/sdd-planner/** @claude-ao-operator` and `* @codex-owner`.
- Verify with `cargo test --workspace` + dogfood `ao2 sdd plan` smoke against the merged target.
- Archive (don't delete) `~/Documents/sdd-planner-private` remote; retain local working tree for 30 days.

Do this **last** because it materially changes the ao2 repo layout and would invalidate any in-flight ao2 patch you have open elsewhere.

---

## What I'm asking back

1. **Per-item completion checklist** — one line per item (1–7) with: status (done | partial | skipped), new HEAD SHA on the affected repo, any deviations from the steps above.
2. **Sanity-check summary** — `cargo test --workspace` results on ao2 and ao2-control-plane after the sweep; `git status --short | wc -l` on ao-operator after the working-tree triage.
3. **Findings file for item 6** at `~/Documents/ao-operator/run-artifacts/hermes-nightly-ao2/findings-2026-05-27-gap-backlog-stuck.md` — diagnosis + fix.
4. **Failed-apply notes for item 2** — if any `git apply --check` rejected, capture the rejection reason verbatim so I can rebuild the drop-in cleanly.
5. **Memory updates needed** — list any new memory entries claude should write based on what you learned during the sweep (e.g., new gotchas, schema decisions).

## Reference

- 3-repo audit findings (this session, 2026-05-27): summarized in the conversation that produced this handoff.
- Active memory at `~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/MEMORY.md`.
- Prior handoff (executed): `dogfood/sdd-planner-claude/HANDOFF-EXECUTE-PLANS.md`.
- Merge handoff (referenced by item 7): `dogfood/sdd-planner-claude/HANDOFF-MERGE-SDD-PLANNER-INTO-AO2.md`.
