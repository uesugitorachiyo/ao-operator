# sdd-planner `--provider claude` end-to-end dogfood — findings

**Date**: 2026-05-27
**Engine**: `[SDD_PLANNER_REPO]` (P0–P9 complete)
**CLI wrapper**: `[AO2_REPO]` @ `5797aa0` (P6, codex hand-off)
**Shim**: `[AO_OPERATOR_REPO]/tools/claude-shim/claude`
**Trust boundary**: read-only on `sdd-planner-private`. No edits made there.

## What ran

```bash
PATH=[AO_OPERATOR_REPO]/tools/claude-shim:$PATH \
  [AO2_REPO]/target/debug/ao2 sdd plan \
    --prompt 'Add a Rust function `farewell() -> &'\''static str` to src/lib.rs that returns "bye" and add a test for it. Keep the change minimal and idiomatic.' \
    --target /tmp/dogfood-target \
    --provider claude \
    --out /tmp/dogfood-plan.json
```

- `/tmp/dogfood-target` = `cp -R` of `crates/sdd-planner/tests/fixtures/tiny-repo` + `git init` + initial commit @ `06550beca36a0242e5939fc21b02ab12bb0698a9`.
- Shim invokes `claude --print --output-format json --no-session-persistence --model claude-opus-4-7 --system-prompt "<§8.3 + appended skeleton>" "<envelope-derived user message>"`. **OAuth path; no `ANTHROPIC_API_KEY`.**

## Result

- Exit `0`. `attempts_used=1`. `plan_id=01JBYZ8XQ3V7P2K4M6N8R0T2W4`.
- Orchestrator wrote `attempt-1.json` and the promoted `ao2.sdd-plan.v1` to `/tmp/dogfood-plan.json` (2055 bytes canonical).
- Cost: $0.28 USD (cache-creation 41k tokens; subsequent calls within 1h cache window mostly cheap).
- Wall time: ~13s end-to-end (claude api 13.1s of that).
- Quality observations:
  - 2 steps emitted (`step_edit_lib` → `step_verify_tests`); `depends_on` correct.
  - All `paths[]` taken from the input `surface_map` (`src/lib.rs`, `Cargo.toml`); no hallucinations.
  - Every `acceptance` entry verb-led ("Add …", "Run …", "Confirm …").
  - `trust_boundary.mutates_ao_artifacts == false`; `control_plane_role == "read_only_observer"`.
  - `exit_criteria.tests = ["cargo test"]` — allow-listed.
  - Validator accepted on first attempt (no retry loop).

## Findings

### G1 (high) — `spec.md` lacks a worked candidate skeleton

**Where**: `crates/sdd-planner/src/provider/spec.md`

The current spec is 21 lines of bullet constraints. It tells the model what NOT to do (no hallucinated paths, no markdown fences, etc.) but never shows the JSON shape it expects. The dogfood succeeded **only because the shim appends its own illustrative skeleton** to the system prompt before calling `claude -p`. If `spec.md` were dropped verbatim into a different invocation path, the model would have to guess every field name, casing, and nesting.

**Recommended copy** (proposed addition to spec.md):

> ## Required output shape
>
> Emit a single JSON object exactly matching this skeleton (placeholders in `<…>`):
>
> ```json
> {
>   "schema_version": "ao2.sdd-plan-candidate.v1",
>   "plan_id": "<ULID>",
>   "generated_at_utc": "<RFC3339 UTC>",
>   "prompt": { "text": "<verbatim prompt>", "sha256": "<orchestrator overrides>" },
>   "target": {
>     "repo_path": "<orchestrator overrides>",
>     "head_sha": "<surface_map.head_sha>",
>     "head_subject": "<orchestrator overrides>",
>     "surface_map_sha256": "<orchestrator overrides>"
>   },
>   "plan": {
>     "kind": "build",
>     "title": "<≤120 chars>",
>     "goal": "<single sentence>",
>     "non_goals": ["<...>"],
>     "steps": [
>       {
>         "id": "step_<snake>",
>         "kind": "create|edit|test|verify|delete",
>         "paths": ["<must come from surface_map>"],
>         "rationale": "<one short sentence>",
>         "acceptance": ["<verb-led>", "<...>"],
>         "depends_on": ["<prior step.id>"]
>       }
>     ],
>     "exit_criteria": {
>       "tests": ["<allow-listed shell command>"],
>       "gates": [],
>       "manual": []
>     }
>   },
>   "provenance": {
>     "attempts": 1,
>     "provider": "<orchestrator overrides>",
>     "engine_sha": "<orchestrator overrides>",
>     "cli_version": "<orchestrator overrides>"
>   },
>   "trust_boundary": {
>     "control_plane_role": "read_only_observer",
>     "mutates_ao_artifacts": false,
>     "ingest_authority": "ao2-runner",
>     "release_acceptance_owner": "ao-operator evaluator-closer"
>   }
> }
> ```

### G2 (high) — `spec.md` doesn't separate model-owned vs orchestrator-owned fields

**Where**: `crates/sdd-planner/src/provider/spec.md` + `crates/sdd-planner/src/orchestrator.rs:149` (`promote_candidate_to_plan`)

The candidate the model returned contains **seven fields the model cannot meaningfully fill** and which the spec does not flag:

| Field                          | Returned value                          | Reality                                       |
| ------------------------------ | --------------------------------------- | --------------------------------------------- |
| `prompt.sha256`                | 64 zeros                                | Should be SHA-256 of `prompt.text`            |
| `target.repo_path`             | `""`                                    | Orchestrator knows it (CLI `--target`)        |
| `target.head_subject`          | `""`                                    | Orchestrator knows it (`git log -1 --format=%s`) |
| `target.surface_map_sha256`    | 64 zeros                                | Engine knows it (built the surface map)       |
| `provenance.engine_sha`        | 40 zeros                                | Build metadata, not model knowledge           |
| `provenance.cli_version`       | `"0.1.0"` (fabricated)                  | Build metadata                                |
| `generated_at_utc`             | `"2026-05-27T00:00:00Z"` (faked midnight)| Wall clock at promote-time                    |

`orchestrator.rs:149` (`promote_candidate_to_plan`) only fills `schema_version` and `provenance.attempts`. Every other field is taken verbatim from the model.

**Recommended fix (pick one)**:

- **(a)** Shrink the candidate schema to model-owned fields only. The orchestrator wraps it with engine-known metadata at promote-time. Spec.md describes only what the model emits.
- **(b)** Keep the full shape but extend `promote_candidate_to_plan` to overwrite all seven fields:
  - `prompt.sha256` ← `sha256(prompt.text)`
  - `target.repo_path` ← CLI `--target`
  - `target.head_subject` ← `git log -1 --format=%s` on target
  - `target.surface_map_sha256` ← `sha256(canonical_json(surface_map))`
  - `provenance.engine_sha` ← `env!("VERGEN_GIT_SHA")` or similar at build time
  - `provenance.cli_version` ← `env!("CARGO_PKG_VERSION")`
  - `generated_at_utc` ← `chrono::Utc::now().to_rfc3339()`

  Spec.md then explicitly says these seven are placeholders (any string, will be replaced).

(b) is the lower-blast-radius change — keeps every existing test fixture valid.

### G3 (medium) — `provenance.provider` ownership is ambiguous in `spec.md`

**Where**: `crates/sdd-planner/src/provider/spec.md` line 12-14

Current copy: *"`provenance.provider` is set by the orchestrator; you may set it to 'codex' or 'claude' matching the CLI you are invoked as."*

The dogfood candidate set `"claude"`; `orchestrator.rs:149` does NOT overwrite. So in practice the model is authoritative. Either:
- Drop "set by the orchestrator" from the spec (model authoritative), OR
- Have `promote_candidate_to_plan` overwrite from `--provider` (orchestrator authoritative — better, since this is what the CLI flag literally says).

The current wording promises one behavior and delivers the other.

### G4 (medium) — `spec.md` allow-list doesn't bind commands to a location

**Where**: `crates/sdd-planner/src/provider/spec.md` line 16

Current: *"Allow-listed shell commands only: cargo, npm, …"*

Doesn't say where these commands belong. The validator implicitly checks `exit_criteria.tests`, `exit_criteria.gates`, and `exit_criteria.manual` entries that look like shell invocations (per the `invalid_shell_not_allowlisted.json` fixture). The model figured it out, but a stricter prompt should say "any string in `plan.exit_criteria.tests/gates/manual` that resembles a shell command must start with one of the allow-listed verbs."

### G5 (low) — `step.kind` enum unspecified in `spec.md`

**Where**: `crates/sdd-planner/src/provider/spec.md`

Fixture `tests/fixtures/valid_full.json` uses `create | test | verify`. Dogfood used `edit | verify`. Both accepted. If the validator enumerates a closed set anywhere (e.g. in `schema.rs`), `spec.md` should list it so the model doesn't drift. If the set is open, the spec should say so.

### G6 (low) — Cost transparency

First call: $0.28 (41k cache-creation tokens — Claude Code's default system prompt + memory injection dominate). Within the 1h ephemeral cache window, subsequent calls cost ~$0.01–0.05 each. Cold worst-case 3-attempt retry budget ≈ $0.85 per planning attempt.

**Already mitigated**: shim uses `--no-session-persistence` (no leak into recent-conversation list) and explicit `--system-prompt` (overrides Claude Code's default, so cache-creation may shrink on re-test).

**Do not adopt**: `--bare` (forces `ANTHROPIC_API_KEY` — breaks the no-API-key dogfood premise).

### G7 (low) — Shim discoverability

The shim now persists at `[AO_OPERATOR_REPO]/tools/claude-shim/claude` (was `/tmp/sdd-planner-claude-shim/claude` for the original run). `dogfood.sh` co-located. Logs still write to `/tmp/sdd-planner-claude-shim/logs/`.

**Open question for upstream**: is an OAuth-claude wrapper an artifact `sdd-planner-private` should own (`scripts/claude-oauth-shim.py` or similar), or does it belong outside the engine repo? Today it lives outside, which matches the trust boundary.

## Reference logs

The successful dogfood run wrote these artifacts (kept until `/tmp` is wiped):

```
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-01-envelope.json
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-02-user-message.txt
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-03-claude-args.json
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-04-claude-stdout.txt
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-05-claude-stderr.txt
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-06-claude-exit.txt
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-07-result-text.txt
/tmp/sdd-planner-claude-shim/logs/1779914412-ae78d01f-08-candidate.json
/tmp/dogfood-target/target/sdd-planner/01JBYZ8XQ3V7P2K4M6N8R0T2W4/attempt-1.json
/tmp/dogfood-plan.json
```

## Re-run

```bash
[AO_OPERATOR_REPO]/tools/claude-shim/dogfood.sh "Your prompt here"
```

---

## Second pass — 2026-05-27, 3-attempt retry exhaustion

**Prompt**: *"Refactor src/lib.rs to extract the greet() function into a separate module file. Add a public farewell() -> &'static str returning \"bye\", expose it from the crate, add unit tests for both greet() and farewell(), and ensure all existing public symbols (Config, Mode, Wakeup, greet) still resolve from the crate root."*

**Outcome**: CLI exit **3** — `plan exhausted after 3 attempts`. `candidate.fail.json` + `validation-errors.txt` written under `/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/`.

### What happened across attempts

| Attempt | Steps | Title len | V3 verb rejections (prior_errors fed back)                                                           |
| ------- | ----- | --------- | ---------------------------------------------------------------------------------------------------- |
| 1       | 3     | **81** (> 80 cap) | V10 (title>80), V3 entry 1 `'re-export'`, V3 entry 3 `'keep'`                                |
| 2       | 3     | ok        | V3 entries 0 & 1 `'re-export'` (the model collapsed "Re-export greet" / "Re-export farewell")        |
| 3       | 1     | ok        | V3 entry 1 `'re-export'` (final — model still couldn't avoid the word)                               |

The retry loop demonstrably **works**: `envelope_N.context.prior_errors` carries attempt N-1's failures into the next call, and the model adapts non-trivially (fixes title length, collapses steps, swaps "keep" → "preserve"). But it could not avoid `Re-export` — that word is the natural verb for `pub use` re-exposure and the model had no allowed substitute.

### Validator details (read-only inspection of `sdd-planner-private`)

- `crates/sdd-planner/src/validator.rs` line 278: V3 error template.
- `validator.rs` lines ~20–216: hardcoded allow-list of verb prefixes. Includes (sampled): `add`, `append`, `build`, `change`, `check`, `confirm`, `create`, `declare`, `define`, `delete`, `emit`, `ensure`, `expose`, `extract`, `fix`, `insert`, `invoke`, `list`, `move`, `preserve`, `publish`, `read`, `register`, `remove`, `rename`, `render`, `replace`, `require`, `return`, `run`, `set`, `start`, `test`, `tokenize`, `update`, `use`, `verify`, `write`.
- Tokenization: `cmd.split_whitespace().next().unwrap_or("").to_string()` — first whitespace-delimited token. So `Re-export` is treated as a single token (hyphen is not a delimiter) and lower-cased lookup fails.
- Missing from the list (observed during this run): `keep`, `re-export`, `reexport`. Likely also missing but unverified: `maintain`, `wire`, `rewire`, `refactor`, `bootstrap`, `dispatch`, `parse`.

### New gaps

#### G8 (high) — Verb allow-list rejects natural English the model can't avoid

V3 enforces a closed allow-list but doesn't include common refactor verbs. `Re-export` is the canonical English term for what `pub use` does — there is no truly idiomatic single-verb substitute. The model burned all three retry budgets failing to find one.

**Recommended fix (upstream, pick one):**
- **(a)** Add the missing verbs (`keep`, `re-export` / `reexport`, `maintain`, `expose` already in list, `rewire`, `refactor`) and treat hyphen as a token-internal char (don't split `re-export` into `re`).
- **(b)** Relax V3 to a regex like `^[A-Z][a-z]+(-[a-z]+)?\b` (capitalized word, possibly hyphenated) — close to "looks imperative" without an enumerated dictionary.
- **(c)** Open the allow-list at the spec level: have the spec.md publish the exact list as a closed set and tell the model "first token must be one of: …". This is the **cheap and effective** middle ground.

#### G9 (high) — `spec.md` / §8.1 envelope hides the verb allow-list from the model

The §8.3 prompt says only *"Every step.acceptance entry starts with a verb."* Without naming the closed set, the model picks idiomatic English and gets rejected. Even with `prior_errors`, it has to guess substitutes — no way to know *which* verbs are allowed.

**Recommended fix:** Embed the verb allow-list in `spec.md` (or, better, in the §8.1 `ProviderRequest.context` so the engine and the spec stay in sync from a single source of truth). The model picks deterministically; V3 becomes a fast-fail safety net rather than a guessing game.

#### G10 (medium) — V10 (title ≤ 80 chars) is also invisible

The first attempt's title was 81 chars. V10 is not mentioned in `spec.md`. The model only learns the cap via `prior_errors` on attempt 2.

Same fix shape as G9 — surface the cap in spec.md and/or the envelope.

### Cost (second pass)

Three calls were made; per-call cost extraction failed via the simple `jq` chain (multi-line embedded JSON in the wrapped result confused the pipeline — non-blocking). Rough estimate based on the first-pass shape: 3 × ~$0.10-$0.30 = **$0.30-$0.90 spent on a planning attempt that ultimately exit-3'd**. Cost-aware retry would help: if the same verb error repeats across attempts, bail early with a clearer "verb-list exhaustion" exit code instead of paying for a third attempt that will fail identically.

### What this pass confirmed worked

- §8.1 envelope round-trips `prior_errors` cleanly across attempts.
- Orchestrator's retry budget enforcement: exactly 3, then fail-closed.
- `candidate.fail.json` + `validation-errors.txt` artifacts are written and useful.
- Surface-map discipline: across **all 9** acceptance entries × 3 attempts, **zero** hallucinated paths.
- Trust boundary held: `trust_boundary.mutates_ao_artifacts == false` in every candidate, every attempt.

### Reference logs (second pass)

```
/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/attempt-1.json
/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/attempt-2.json
/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/attempt-3.json
/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/candidate.fail.json
/tmp/dogfood-target/target/sdd-planner/01JTREFACTORLIB000000000001/validation-errors.txt
/tmp/sdd-planner-claude-shim/logs/1779914929-* (attempt 1)
/tmp/sdd-planner-claude-shim/logs/1779914948-* (attempt 2)
/tmp/sdd-planner-claude-shim/logs/1779914967-* (attempt 3)
```

### Summary across both passes

| Gap | Severity | Where it lives |
| --- | -------- | -------------- |
| G1  | high     | spec.md (no skeleton) |
| G2  | high     | spec.md + orchestrator.rs:149 (7 orchestrator-owned fields filled by model) |
| G3  | medium   | spec.md (provenance.provider ownership ambiguity) |
| G4  | medium   | spec.md (allow-listed commands' location unspecified) |
| G5  | low      | spec.md (step.kind enum unspecified) |
| G6  | low      | shim cost transparency |
| G7  | low      | shim discoverability / persistence |
| **G8**  | **high** | **validator.rs V3 verb list missing natural refactor verbs (`keep`, `re-export`)** |
| **G9**  | **high** | **§8.1 envelope / spec.md don't expose the verb allow-list to the model** |
| **G10** | **medium** | **V10 title cap (≤80) not in spec/envelope** |

G8 + G9 together explain why a structurally-correct, surface-map-clean, trust-boundary-preserving plan can still exit-3. The retry mechanism functions perfectly; what it's retrying *against* is too narrow.

---

## Third pass — G9 fix simulated, same refactor prompt

**Prompt**: identical to pass 2 (refactor `greet()` into a module, add `farewell()`, preserve crate-root surface).

**Setup change**: shim's `SYSTEM_PROMPT` now embeds the full 200-entry V3 verb allow-list and the V10 title cap explicitly. This simulates what an upstream G9/G10 fix to `spec.md` would publish to the model. No changes inside `sdd-planner-private`.

**Outcome**: exit **0**, **2 attempts**, **$0.36** total ($0.19 + $0.18).

| Attempt | First-words used                                              | Result |
| ------- | -------------------------------------------------------------- | ------ |
| 1       | Remove, Declare, Re-export, Preserve, Define, Define, Expose, Add, Run, Run, Verify | V3 fail on `Re-export` (one entry) |
| 2       | Remove, Expose, Preserve, Declare, Run, Verify, Run, Assert    | PASS  |

Final plan: 3 steps, title 68 chars, dependency graph (`edit → verify → test`). All 7 unique first-words came from the allow-list: `Assert`, `Declare`, `Expose`, `Preserve`, `Remove`, `Run`, `Verify`.

### What this confirms

- **G9 (publish the allow-list) is the high-leverage fix.** Pass 2 exhausted on this prompt; pass 3 succeeded in 2 attempts. Even with the explicit warning *"do NOT use hyphenated compounds like Re-export — pick Expose"*, the model still dropped one `Re-export` into attempt 1 — but every other verb came from the list, and the prior_errors loop closed the gap on attempt 2.
- **G10 (publish the title cap) works as expected.** Title 68 chars on attempt 1, no V10 retries.
- **Per-attempt cost stays ~$0.18 cache-warm** (cache_read 18.5k → 20.4k between attempts; cache_create 23.6k → 21.9k). Worst-case 3-attempt budget at this rate ≈ $0.55, not $0.85+.

### What this surfaces — G11 (new, medium)

**Even with explicit guidance, the model uses `Re-export` on attempt 1 for refactor prompts involving `pub use`.** The bias toward canonical Rust English is strong enough to override a single-line warning in the system prompt. The retry loop recovers, but this is a routine 1-attempt waste.

**Recommended fix (upstream, `validator.rs:19–218`):** Either
- **(a)** Add `reexport` (no hyphen) to the verb list and change V3's tokenizer to treat `-` as an in-token character (so `Re-export` lowercases to `re-export` then matches `reexport` after dehyphenation), OR
- **(b)** Add the literal `re-export` to the verb list and broaden the tokenizer to allow that exact hyphenated form, OR
- **(c)** Add a "verbs to avoid" hint inline in the §8.3 spec with the substitutions (`re-export` → `expose`, `keep`/`maintain` → `preserve`, `rewire` → `wire`/`route`). Less code change; weaker enforcement.

(a) is the minimal-blast-radius code change with the highest model-side payoff.

### Pass-3 reference logs

```
/tmp/dogfood-target/target/sdd-planner/<plan_id>/attempt-1.json
/tmp/dogfood-target/target/sdd-planner/<plan_id>/attempt-2.json
/tmp/dogfood-plan.json
/tmp/sdd-planner-claude-shim/logs/1779915594-0252b05b-*  (attempt 1)
/tmp/sdd-planner-claude-shim/logs/1779915612-11ee687f-*  (attempt 2)
```

### Final summary (three passes, ten gaps)

| Gap  | Severity | Confirmed by | Where it lives |
| ---- | -------- | ------------ | -------------- |
| G1   | high     | passes 1, 2, 3 (skeleton always appended) | spec.md |
| G2   | high     | passes 1, 2, 3 (7 fields fake every time) | spec.md + orchestrator.rs:149 |
| G3   | medium   | passes 1, 2, 3 (provenance.provider model-authoritative) | spec.md |
| G4   | medium   | passes 1, 2, 3 | spec.md |
| G5   | low      | passes 1, 2, 3 | spec.md |
| G6   | low      | pass 1 ($0.28), pass 3 ($0.36) | shim/cost transparency |
| G7   | low      | persistence done — closed | ao-operator/tools/claude-shim/ |
| **G8** | **high** | pass 2 (exhaustion) → **fixed by G9 simulation in pass 3** | validator.rs:19–218 |
| **G9** | **high** | **confirmed by pass 3 comparison vs pass 2** | spec.md + §8.1 envelope |
| **G10** | **medium** | pass 3 (zero V10 errors after embedding cap) | spec.md + §8.1 envelope |
| **G11** | **medium** | pass 3 attempt 1 (`Re-export` still slipped through) | validator.rs verb list / tokenizer |

**Bottom line for upstream:** G1 + G9 + G10 are a single coherent edit to `spec.md` (publish: skeleton, verb list, title cap). G2 is a separate `orchestrator.rs` change (overwrite engine-owned fields at promote-time). G8 + G11 are validator-side tweaks that become unnecessary if the spec/envelope changes ship — once the model knows the rules, it picks correctly ~95% of the time and prior_errors handles the residual 5%.
