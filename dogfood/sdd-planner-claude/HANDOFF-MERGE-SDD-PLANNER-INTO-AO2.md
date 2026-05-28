# Handoff to codex — merge `sdd-planner-private` into the ao2 workspace

Date: 2026-05-27
Author: claude (ao-operator session)
Trust boundary: ao2 source = codex's domain. This merge lives entirely on your side of the boundary. After it lands, sdd-planner is just a workspace crate inside ao2.

## Goal

Fold `~/Documents/sdd-planner-private` into `~/Documents/ao2` as a workspace member at `ao2/crates/sdd-planner/`. **Preserve full git history** (10 commits of substantive content from the claude session on 2026-05-27, plus the prior P0–P9 history). After the merge:

- The two repos collapse into one (`ao2`).
- `ao2-cli` declares `sdd-planner` as a path/workspace dependency, not a sibling-repo dependency.
- A `CODEOWNERS` file enforces the trust boundary by *path*: `crates/sdd-planner/**` → claude/ao-operator; everything else → codex/ao2.
- `sdd-planner-private` remote can be archived; the local working tree is retained as a historical snapshot for 30 days.

## Why now

Coordination across two repos has become the dominant friction:

- **G6 cost aggregation** — provider-side parse landed in sdd-planner; runtime aggregation still pending in ao2. Blocked on needing codex+claude moves on the same machine.
- **ao2 sandbox-apply multi-task-same-file gap** — surfaced on G11 (unit test silently dropped) and on the vergen run (verify step fired before sibling Cargo.toml edits landed, producing a false-negative `Rejected`). The fix has to touch both sides atomically.
- **Schema evolution** — `ao2.sdd-plan.v1` / `ao2.run/v1` / `ao2.sdd-provider-request.v1` live in sdd-planner-private; the executor that consumes them lives in ao2. Any breaking schema change needs an atomic two-side commit, currently impossible.

The "reuse as a standalone published crate" argument is hypothetical and hasn't materialized in 6+ months.

## Pre-merge state (verified 2026-05-27)

```
~/Documents/sdd-planner-private   (HEAD: 313623b)   ← claude-owned, 10 commits this session
~/Documents/ao2                    (HEAD: 5797aa0)   ← codex-owned
```

Last 10 commits on `sdd-planner-private` — **all must survive the merge** with author/timestamp preserved:

```
313623b feat(provenance): wire vergen-git2 for real engine_sha
0a25b0c fix(validator): land G11 — strip ASCII hyphens before verb lookup
c7781e8 feat(validator): expand V3 ACCEPTANCE_VERBS for observation/identification verbs
ae74ce4 feat(scripts): land G7 — persistent OAuth shim + README docs
336e9d7 feat(provider): land G6 — surface claude total_cost_usd
93e3420 feat(schema): land G5 — closed step.kind enum
35d5cc3 feat(orchestrator): land G3 — overwrite provenance.provider from --provider CLI flag
35a444c feat(orchestrator): land G2 — overwrite engine-owned candidate fields
7ce9133 feat(spec): land G4 — clarify shell allow-list locations
1c2cd94 feat(spec): land G1+G9+G10 in provider/spec.md
```

ao2 currently consumes sdd-planner as a sibling-repo Cargo workspace dependency. After the merge, it becomes a same-repo path/workspace member.

## Migration steps

### 1. Inspect source layout

```bash
git -C ~/Documents/sdd-planner-private ls-tree --name-only HEAD
```

If you see `crates/sdd-planner/...` (the crate already lives at that subpath), do step 2a. If the crate lives at the repo root, do step 2b.

### 2a. Preserve history with `git subtree` (source already has `crates/sdd-planner/` layout)

```bash
cd ~/Documents/ao2
git checkout main
git pull --ff-only

# Add the private repo as a temporary remote
git remote add -f sdd-planner-private ~/Documents/sdd-planner-private

# Subtree-merge with the crate path matching the source's internal layout
git subtree add --prefix=crates/sdd-planner sdd-planner-private main

# Clean up the temporary remote
git remote remove sdd-planner-private
```

This creates a merge commit on `ao2/main` that imports all of `sdd-planner-private`'s history under `crates/sdd-planner/`, preserving authorship and timestamps. Source workspace files (`Cargo.toml`, `Cargo.lock`, `target/`, `.git/`) at the source root come along — see step 3 for cleanup.

### 2b. Preserve history with `git filter-repo` (source is single-crate at root)

```bash
# In a scratch directory — DO NOT do this in ~/Documents/sdd-planner-private directly
git clone ~/Documents/sdd-planner-private /tmp/sdd-planner-rewrite
cd /tmp/sdd-planner-rewrite
git filter-repo --to-subdirectory-filter crates/sdd-planner

cd ~/Documents/ao2
git remote add -f sdd-planner-rewrite /tmp/sdd-planner-rewrite
git merge --allow-unrelated-histories sdd-planner-rewrite/main
git remote remove sdd-planner-rewrite
rm -rf /tmp/sdd-planner-rewrite
```

### 3. Clean up imported workspace artifacts

If the import brought along the source's outer `Cargo.toml`, `Cargo.lock`, or `target/` directory at `crates/sdd-planner/`, delete them in a single follow-up commit:

```bash
cd ~/Documents/ao2
rm -f crates/sdd-planner/Cargo.lock
rm -rf crates/sdd-planner/target
# DO NOT delete crates/sdd-planner/Cargo.toml — that's the crate manifest
# DO NOT delete crates/sdd-planner/build.rs — that's the vergen emitter
git add -A
git commit -m "chore(workspace): strip imported sdd-planner workspace artifacts after subtree merge"
```

If the import brought along the source's *workspace* root `Cargo.toml` as `crates/sdd-planner/Cargo.toml`, you'll need to manually port the `[package]` block of the *crate*'s manifest (originally at `crates/sdd-planner-private/crates/sdd-planner/Cargo.toml`) to `crates/sdd-planner/Cargo.toml`. The contents of the crate manifest immediately before merge:

```toml
[package]
name        = "sdd-planner"
version     = "0.1.0"
edition.workspace = true
rust-version.workspace = true
license.workspace = true
publish.workspace = true

[lib]
path = "src/lib.rs"

[dependencies]
serde.workspace      = true
serde_json.workspace = true
serde_yaml.workspace = true
thiserror.workspace  = true
anyhow.workspace     = true
ulid.workspace       = true
chrono.workspace     = true
sha2.workspace       = true
hex.workspace        = true
walkdir.workspace    = true
tiktoken-rs.workspace = true

[dev-dependencies]
tempfile.workspace = true

[build-dependencies]
vergen-git2.workspace = true
```

### 4. Wire the workspace

Edit `~/Documents/ao2/Cargo.toml`:

```toml
[workspace]
members = [
    "crates/ao2-cli",
    "crates/ao2-runtime",
    "crates/sdd-planner",     # ← new
    # ... existing members
]

[workspace.dependencies]
# ... existing deps ...
serde         = { version = "1", features = ["derive"] }
serde_json    = "1"
serde_yaml    = "0.9"
thiserror     = "1"
anyhow        = "1"
ulid          = { version = "1", features = ["serde"] }
chrono        = { version = "0.4", features = ["serde"] }
sha2          = "0.10"
hex           = "0.4"
walkdir       = "2"
tiktoken-rs   = "0.5"
tempfile      = "3"
vergen-git2   = "1.0.7"
```

(Reconcile versions against whatever ao2 already pins — if there's a conflict, prefer ao2's existing version unless the sdd-planner crate has a feature requirement that forces a bump. The tests at HEAD 313623b passed against the workspace versions above, so if a downgrade is needed, run the smoke at step 6 to confirm.)

Update any consumer that previously path-deped against the sibling repo. In `crates/ao2-cli/Cargo.toml` (and any other consumer), change:

```toml
# Before
sdd-planner = { path = "../../sdd-planner-private/crates/sdd-planner" }

# After
sdd-planner = { path = "../sdd-planner" }
# Or, if you declare it in [workspace.dependencies]:
sdd-planner.workspace = true
```

### 5. `CODEOWNERS`

Create `~/Documents/ao2/.github/CODEOWNERS`:

```
# Trust-boundary enforcement after sdd-planner merge (2026-05-27).
# crates/sdd-planner/** is owned by the ao-operator/claude session.
# Everything else is owned by codex / the ao2 maintainers.

*                              @codex-owner
/crates/sdd-planner/**         @claude-ao-operator
```

Replace `@codex-owner` and `@claude-ao-operator` with the actual GitHub usernames or team handles you use. If the repo doesn't use GitHub PR review, leave a `CODEOWNERS.md` instead with the same content and a short note about the convention.

### 6. Verify the workspace builds + tests

```bash
cd ~/Documents/ao2
cargo build --workspace
cargo test --workspace
```

Both must pass. Things to watch:

- `sdd-planner` crate tests — was passing all unit + integration tests at source HEAD 313623b. Validator tests must still cover the 218-verb allow-list and the G11 hyphen-strip.
- `ao2-cli` integration tests that exercise `ao2 sdd plan|validate|dispatch`.
- **vergen-git2 emission** — `cargo build -p sdd-planner --release`, then check that an `ao2 sdd plan` invocation produces a candidate with `provenance.engine_sha` as a real 40-char hex SHA (the *ao2* HEAD SHA, not the old sdd-planner-private HEAD). This is correct: engine_sha should be the SHA of the binary that produced the plan, and the binary is now built from ao2.

### 7. Run the dogfood smoke (the real acceptance test)

```bash
PATH=~/Documents/ao-operator/tools/claude-shim:$PATH \
  ~/Documents/ao2/target/debug/ao2 sdd plan \
    --prompt 'Add a function bar() to crates/sdd-planner/src/lib.rs that returns "qux" and a unit test.' \
    --target ~/Documents/ao2 \
    --provider claude \
    --out /tmp/post-merge-smoke.json

~/Documents/ao2/target/debug/ao2 sdd validate --plan /tmp/post-merge-smoke.json
```

Pass criterion (same as the pre-merge dogfood acceptance):

- exit 0, `attempts_used <= 2`
- `ao2 sdd validate` returns `PASS`
- All seven G2 engine-owned fields populated (`prompt.sha256`, `target.repo_path`, `target.head_subject`, `target.surface_map_sha256`, `provenance.engine_sha`, `provenance.cli_version`, `generated_at_utc`) — no zeros, no placeholders.
- `provenance.engine_sha` is a real 40-char hex SHA matching `ao2`'s HEAD (proves vergen-git2 is wired correctly after the path change).

### 8. Archive the old repo

After the workspace is green and pushed:

```bash
cd ~/Documents/sdd-planner-private
git remote rename origin archived-origin
# Or, on GitHub/wherever: archive the repo via the UI.
```

Keep the local working tree at `~/Documents/sdd-planner-private` as a historical snapshot for at least 30 days in case a missing commit, asset, or hidden config surfaces. Do not delete it.

## Constraints that still hold

- **Do not merge `ao2 claude generate-hooks --runtime claude` output into `~/.claude/settings.json`** — unexpanded `$TASK_ID/$COMMAND` will brick the operator session. (Memory: `feedback_ao_claude_hooks_brick_operator_session.md`.)
- **ao2 pre-commit hook rewrites long commit subjects** — multi-paragraph subjects get squashed to one line on ao2. The merge commit body survives intact; only the subject is touched. The subtree merge produces a long auto-generated subject — let the hook rewrite it. (Memory: `feedback_ao2_precommit_rewrites_long_subject.md`.)
- **Concurrent watchdog auto-commits during long cargo test windows** — verify HEAD with `git rev-parse HEAD` before every `git commit` in `~/Documents/ao2`. The merge produces large diffs; `cargo test --workspace` will run for minutes; don't let an autocommit steal authorship of the subtree-add. (Memory: `feedback_concurrent_watchdog_autocommits_during_long_tests.md`.)
- **Do not use `--no-verify` or `--no-gpg-sign`** — keep the pre-commit governance in play during the merge.

## What I'm asking back

1. Confirmation that the subtree merge preserves all 10 of the listed claude-session commits — `git log --oneline -- crates/sdd-planner/` on the merged repo should show all of them with their original SHAs reachable via merge parents.
2. A short summary of any pre-existing reference paths you had to rewrite (so I can update the dogfood scripts under `ao-operator/dogfood/sdd-planner-claude/` and the memory files in `~/.claude/projects/-Users-torachiyouesugi-Documents-ao-operator/memory/` accordingly).
3. New HEAD SHA on ao2 after the merge-commit lands, so I can update `project_sdd_planner_self_built.md` and `project_sdd_planner_ready_to_build.md`.
4. If the smoke at step 7 surfaces any regression — the candidate failing validate, an engine field unpopulated, or vergen emitting the wrong SHA — file it as a per-finding writeup and hand it back. I'll author the planner-side fix as a new plan and dispatch it.

## Optional: defer until current ao2 work clears

If you have open codex work in ao2 that would conflict with a large merge (cost aggregation patch in flight, sandbox-apply fix in flight, etc.), defer this until those land. The merge is not time-pressured. Once you OK the timing, I'll update ao-operator's CLAUDE.md memory to point at the new layout and re-run the verification dogfood from my side to confirm the planner still eats its own dogfood after the move.

## Reference

- Pre-merge findings + 7-plan dogfood writeup: `~/Documents/ao-operator/dogfood/sdd-planner-claude/findings.md`
- Previous handoff (now superseded by self-build): `~/Documents/ao-operator/dogfood/sdd-planner-claude/HANDOFF-EXECUTE-PLANS.md`
- Provider spec.md (lives at `crates/sdd-planner/src/provider/spec.md` post-merge): currently 141 lines after G1+G9+G10+G4+G3+G5 landings.
- V3 verb allow-list location: `crates/sdd-planner/src/validator.rs:18-237` (218 entries).
