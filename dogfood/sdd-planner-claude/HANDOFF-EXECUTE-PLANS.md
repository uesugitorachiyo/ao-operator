# Handoff to codex — execute the 7 sdd-planner self-build plans

Date: 2026-05-27
Trust boundary: sdd-planner-private is now editable by claude (this session); ao2 runtime is still codex's domain.

## What's done (claude session)

Dogfood of `ao2 sdd plan --provider claude` against `[SDD_PLANNER_REPO]` has reached **100% pass criterion**:

- `crates/sdd-planner/src/validator.rs` `ACCEPTANCE_VERBS` expanded from 200 → 218 (added `cite, demonstrate, denote, discover, explain, identify, illustrate, indicate, locate, maintain, mention, note, observe, place, point, recognize, reexport, reference`).
- `ao-operator/tools/claude-shim/claude` `SYSTEM_PROMPT` re-synced to the expanded list.
- Real-plan-1 against sdd-planner-private (G1+G9+G10 spec.md prompt) → exit 0, 1 attempt, $0.234. `ao2 sdd validate` → PASS.
- 7 plans total generated (one per gap in `findings.md`); 7 dispatched to both `ao2` and `ao-operator` runspecs in `/tmp/sdd-planner-dispatch/`. All 7 dispatches `status=dry_run_accepted`.

## Plans ready to execute

All seven are JSON candidates of schema `ao2.sdd-plan.v1`, validated PASS:

| Plan path                                | Title                                                                 | Steps | Validate |
| ---------------------------------------- | --------------------------------------------------------------------- | ----- | -------- |
| `/tmp/sdd-planner-real-plan-1.json`      | Surface V3 verb list, V10 title cap, and v1 skeleton in provider spec.md (G1+G9+G10) | 4 | PASS |
| `/tmp/sdd-planner-plan-G2.json`          | Overwrite engine-owned candidate fields in promote_candidate_to_plan  | 6     | PASS     |
| `/tmp/sdd-planner-plan-G3.json`          | G3: orchestrator overwrites provenance.provider from --provider flag  | 4     | PASS     |
| `/tmp/sdd-planner-plan-G4.json`          | G4: clarify shell allow-list locations in provider spec.md            | 1     | PASS     |
| `/tmp/sdd-planner-plan-G5.json`          | G5: enumerate closed step.kind enum in schema and provider spec       | 5     | PASS     |
| `/tmp/sdd-planner-plan-G6.json`          | G6: surface claude total_cost_usd on provider response and attempt log| 6     | PASS     |
| `/tmp/sdd-planner-plan-G7.json`          | G7: document OAuth shim discoverability in README and smoke           | 4     | PASS     |

Dispatched runspecs (both runners, `--dry-run`):

```
/tmp/sdd-planner-dispatch/real-plan-1.ao2.yaml         # G1+G9+G10
/tmp/sdd-planner-dispatch/real-plan-1.ao-operator.yaml
/tmp/sdd-planner-dispatch/plan-G2.ao2.yaml
/tmp/sdd-planner-dispatch/plan-G2.ao-operator.yaml
... (one ao2 + one ao-operator per plan, 14 files total)
```

## What I need codex to do

Execute the seven plans against `[SDD_PLANNER_REPO]`. **Recommended dependency order** (do not parallelize G2/G3/G5 against G1+G9+G10 — they touch overlapping files):

1. **First wave (parallelizable, spec.md-only):** `real-plan-1` (G1+G9+G10), `G4`. Both edit `crates/sdd-planner/src/provider/spec.md`. Merge sequentially to avoid conflicts.
2. **Second wave (orchestrator.rs, sequential):** `G2`, then `G3`. G2 lands the seven-field overwrite; G3 piggybacks on the same `promote_candidate_to_plan` site for the provider field.
3. **Third wave (schema.rs + spec.md):** `G5`. Closed `step.kind` enum.
4. **Fourth wave (claude provider + logging):** `G6`. Surface cost.
5. **Fifth wave (docs + scripts):** `G7`. Persist shim into upstream.

After each plan executes, re-run the dogfood to confirm no regression:

```bash
PATH=[AO_OPERATOR_REPO]/tools/claude-shim:$PATH \
  [AO2_REPO]/target/debug/ao2 sdd plan \
    --prompt 'smoke prompt' \
    --target [SDD_PLANNER_REPO] \
    --provider claude \
    --out /tmp/smoke.json
[AO2_REPO]/target/debug/ao2 sdd validate --plan /tmp/smoke.json
```

## Concrete command shape per plan

To execute one plan via `ao2 run`:

```bash
[AO2_REPO]/target/debug/ao2 run \
  --spec /tmp/sdd-planner-dispatch/real-plan-1.ao2.yaml \
  --target [SDD_PLANNER_REPO] \
  --provider claude \
  --provider-max-budget-usd 2.00
```

(Or `--provider codex` if codex is preferred for the actual implementation work.)

## Constraints that still hold

- Trust boundary on `sdd-planner-private` is **lifted** — claude (the planner-provider) may edit it, and codex (executor) may too. Both are commit-authoritative.
- ao2 runtime engine (the `ao2 run` machinery itself) remains codex's. Do not have claude modify `ao2`'s source.
- Pre-existing uncommitted work in `sdd-planner-private` (12 files, ~226 lines from the user, mtime 2026-05-27T13:05:21) is unrelated to my dogfood remediation. The validator.rs +19 line block (after `"zero",` at line 218) is mine; the rest is the user's parallel work. Commit each separately to keep blame clean.
- Per `feedback_ao2_precommit_rewrites_long_subject.md`: ao2-private hook rewrites long subject lines. Per `feedback_concurrent_watchdog_autocommits_during_long_tests.md`: verify HEAD before running `git commit` in `~/Documents/ao2`.
- Per `feedback_ao_claude_hooks_brick_operator_session.md`: do NOT merge `ao2 claude generate-hooks --runtime claude` output into `~/.claude/settings.json`.

## Verification after the full sweep

The post-build acceptance is the same dogfood that surfaced these gaps in the first place:

```bash
rm -rf /tmp/sdd-planner-claude-shim/logs && \
PATH=[AO_OPERATOR_REPO]/tools/claude-shim:$PATH \
  [AO2_REPO]/target/debug/ao2 sdd plan \
    --prompt 'Add a function bar() to crates/sdd-planner/src/lib.rs that returns "qux" and a unit test.' \
    --target [SDD_PLANNER_REPO] \
    --provider claude \
    --out /tmp/post-build-smoke.json

[AO2_REPO]/target/debug/ao2 sdd validate --plan /tmp/post-build-smoke.json
```

Pass criterion: exit 0, `attempts_used <= 2`, validate=PASS, all G2/G3/G5 fields populated by the engine (not "orchestrator-overrides"), candidate emits a closed `step.kind` value, attempt log includes `cost_usd`.

## Cost shape so far

7 plans + 1 retry attempt = 8 provider calls = ~$2.10 spent. Worst-case 7-plan execution via `ao2 run --provider claude` ≈ $10–$20 depending on step complexity. With `--provider codex` cost depends on codex billing.
