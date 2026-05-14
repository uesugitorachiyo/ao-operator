# Operator Slice Manifests

AO Operator operator work that can affect providers, AO homes, generated
artifacts, or SDD evidence should have a machine-checkable slice manifest. The
manifest is the operational companion to the prose SDD: it defines ordered
steps, scoped reads and writes, commands, evidence, stop rules, and live-provider
guardrails.

The Remote Transfer v2 stress lane uses:

```text
examples/remote-transfer-v2-stress/operator-slices.json
```

Validate it with:

```bash
python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --json
```

List local-only slices:

```bash
python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --list-slices \
  --local-only \
  --json
```

Print the commands for one slice:

```bash
python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --commands-for 02-validate-bounded-live-profile
```

Plan safe local execution through a slice:

```bash
python3 scripts/run_operator_slice.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --from 01-ao-runtime-doctor \
  --through 11-review-runtime-guardrail-batch \
  --local-only \
  --json
```

Execute one local slice and write an operator-run report:

```bash
python3 scripts/run_operator_slice.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --slice 02-validate-bounded-live-profile \
  --execute \
  --json
```

Executed operator-run reports redact provider auth paths, token/API-key shaped
values, and raw AO home paths from command text and captured output before the
report is written. Treat those reports as operator execution summaries, not raw
provider transcripts.

Live-provider slices are refused unless `--allow-live` is present. Override-gated
slices are refused unless both `--allow-override` and
`FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1` are present.

Slices may declare `env` values for local command execution. Use `PATH_PREPEND`
for ordered path additions, for example the AO Runtime release directory needed
by `factory_doctor.py`.

## Required Shape

Each manifest declares:

- `classification` and `shape`
- negative constraints and sensitive fields
- ordered `slices`
- per-slice `mode`, `reads`, `writes`, `commands`, `evidence`, and `stop_rules`
- optional per-slice `env`
- `live_provider` and `task_count` for provider-affecting slices

Live-provider slices above `FACTORY_V3_MAX_LIVE_TASKS` default `50` must declare:

- `requires_override: true`
- `approval_env: FACTORY_V3_ALLOW_LARGE_LIVE_RUN`

Non-live slices may not include `--run` unless they are explicit
`expected_blocked` preflight proof slices with `expected_exit: 1`.

## Remote Transfer v2 Stress Slices

The current stress manifest intentionally separates these operator concerns:

1. Preserve provider-limit diagnostics.
2. Run AO Runtime and provider doctor checks.
3. Validate the bounded live profile.
4. Materialize the 1000-slice profile as dry-run evidence only.
5. Prove the large live guardrail blocks before AO dispatch.
6. Materialize the bounded live profile as dry-run evidence.
7. Verify generated artifact hygiene with `git diff --check`.
8. Plan commit-ready evidence bundles without staging files.
9. Plan staged commit sequence with per-group pathspec files.
10. Verify staged commit pathspecs keep failed-live diagnostics out of success batches.
11. Rehearse staging the first two safe batches with a temporary Git index.
12. Review the runtime guardrails/tests batch pathspec before real staging.
13. Check bounded-live readiness with `scripts/check_bounded_live_readiness.py`.
14. Build a local live dispatch packet with `scripts/build_live_dispatch_packet.py`.
15. Verify the live dispatch packet with `scripts/verify_live_dispatch_packet.py`.
16. Check the final live dispatch gate with `scripts/check_live_dispatch_gate.py`.
17. Check approval readiness with `scripts/check_live_approval_readiness.py`.
18. Run the bounded 10-slice live profile.
19. Classify post-live artifacts with `scripts/classify_live_outcome.py`.
20. Plan failure diagnostics with `scripts/plan_live_failure_diagnostics.py`.
21. Guard diagnostic preservation with
    `scripts/preserve_live_failure_diagnostics.py`.
22. Route post-live artifacts with `scripts/route_live_postrun.py`.
23. Guard success-evidence commits with
    `scripts/check_live_success_commit_guard.py`.
24. Verify live operator ordering with `scripts/check_live_operator_sequence.py`.
25. Check live acceptance artifacts with `scripts/check_live_acceptance.py`.
26. Prepare a 25-slice profile after acceptance by regenerating the live
    profile, dry-run materializing the 57-task prompt/RunSpec artifact set, and
    then validating intake plus Factory topology evidence.
27. Run above 50 live tasks only with explicit override evidence.

This gives operators a durable queue of tasks that can be run one at a time
without reinterpreting the full SDD prose under provider pressure.
