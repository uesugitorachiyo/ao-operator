# claude-shim

OAuth wrapper that lets AO2's `sdd-planner` workspace crate use `--provider claude` through the real Claude Code CLI without an `ANTHROPIC_API_KEY`.

## Why

AO2's `sdd-planner` crate spawns `claude` from `$PATH` and expects it to honor §8.1 (read JSON envelope from stdin) and §8.2 (write JSON candidate to stdout). The real Claude Code CLI is interactive by default; even in `-p`/`--print` mode it doesn't speak that contract directly. This shim sits in front of it.

## What it does

1. Reads the `ao2.sdd-provider-request.v1` envelope on stdin.
2. Composes a user message that embeds the prompt, the `surface_map` (the only legal `paths[]` values), the `expected_output` schema/max_steps, and any `prior_errors`.
3. Invokes `claude --print --output-format json --no-session-persistence --model claude-opus-4-7 --system-prompt "<§8.3 + augmentations>"` with that user message as argv.
4. Pulls the `.result` text out of the wrapper, extracts the first balanced JSON object, validates it parses, and writes it to stdout.

OAuth path — uses the user's existing Claude Code session. **Do not pass `--bare`**; that flag forces `ANTHROPIC_API_KEY`-only auth and would defeat the no-API-key constraint.

## System-prompt deviations from upstream `spec.md`

The shim's `SYSTEM_PROMPT` constant mirrors `crates/sdd-planner/src/provider/spec.md` with three intentional additions that simulate upstream fixes the dogfood revealed are necessary:

| ID  | What's added                                                       | Why                                                            |
| --- | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| G1  | A worked `ao2.sdd-plan-candidate.v1` skeleton with placeholders     | spec.md is 21 lines of constraints with no shape; model needs the shape |
| G9  | The full V3 verb allow-list (verbatim from `validator.rs`) | Without it, the model picks idiomatic English (`Re-export`, `keep`) that the validator rejects, exhausting the 3-attempt retry budget |
| G10 | The V10 title cap (≤80 chars) stated explicitly                     | Otherwise the model overshoots and burns one retry learning the cap |

Pass-3 of the dogfood (refactor prompt, 3 steps) succeeded in 2 attempts at $0.36 with these augmentations. The same prompt against verbatim spec.md exhausted the budget at $0.40–$0.90 with no plan emitted.

Full gap analysis: `../../dogfood/sdd-planner-claude/findings.md`.

**Re-sync**: If AO2 updates `crates/sdd-planner/src/provider/spec.md`, `validator.rs`'s verb list, or the V10 cap, mirror the changes into `claude`'s `SYSTEM_PROMPT` (the constant is heavily commented at the top of the file). Keep these in sync until the provider spec is enough by itself — at which point the shim's augmentation block can shrink back to just the contract.

## Logs

Every invocation writes 8 numbered artifacts under `/tmp/sdd-planner-claude-shim/logs/<unix-ts>-<uuid>-NN-*`:

| `NN` | Content                                       |
| ---- | --------------------------------------------- |
| 01   | The §8.1 envelope read from stdin             |
| 02   | The user message composed for `claude -p`     |
| 03   | The full `claude` argv (system prompt + args) |
| 04   | `claude --output-format json` raw stdout      |
| 05   | `claude` stderr                               |
| 06   | `claude` exit code                            |
| 07   | The `.result` text extracted from the wrapper |
| 08   | The parsed candidate JSON (the shim's stdout) |

`dogfood.sh` clears the dir before each run; direct invocations append.

## Usage

```bash
# Direct (rare — usually via the planner)
echo '{"schema_version":"ao2.sdd-provider-request.v1", ...}' | ./claude

# Via the planner — prepend this dir to PATH
PATH="$PWD:$PATH" [AO2_REPO]/target/debug/ao2 sdd plan \
  --prompt 'Your prompt' \
  --target /tmp/dogfood-target \
  --provider claude \
  --out /tmp/dogfood-plan.json

# Or use the wrapper (recreates /tmp/dogfood-target from the tiny-repo fixture)
./dogfood.sh "Your prompt"
```

## Cost

First call after a cache-cold start: ≈$0.18–$0.28 (cache-creation dominates — Claude Code's default system prompt + memory injection accounts for most of it). Within the 1h ephemeral cache window, subsequent calls cost ~$0.17–$0.20 (cache reads still cost something, output tokens dominate). Worst-case cold 3-attempt retry budget: ≈$0.55–$0.85.

## Trust boundary

The shim does NOT modify AO2 or AO artifacts. The §8.3 contract mirrored here was extracted from `[AO2_REPO]/crates/sdd-planner/src/provider/spec.md`; the verb list, V10 cap, and candidate skeleton are extracted from `validator.rs` and `tests/fixtures/claude-candidate.json`. Re-sync on AO2 changes; do not patch AO2 from this shim.
