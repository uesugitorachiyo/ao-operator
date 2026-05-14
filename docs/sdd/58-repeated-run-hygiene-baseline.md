# 58 - Repeated-Run Hygiene Baseline

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture safety

## Objective

Promote repeated-run hygiene into a durable Agent OS architecture baseline so
same-slug dry-runs, failed live reruns, and postrun reroutes cannot reuse stale
accepted live evidence while router and RunSpec internals continue changing.

## Scope

The baseline command is `scripts/check_repeated_run_hygiene.py`.

It covers three deterministic no-provider scenarios:

- same-slug dry-run after accepted live evidence
- same-slug failed live events after accepted live evidence
- postrun reroute after accepted live evidence

It writes
`run-artifacts/remote-transfer-v2-stress-live/dispatch/repeated-run-hygiene.json`.

## Required Behavior

- Every scenario must return `PASS`.
- The output must use `${FACTORY_V3_ROOT}` instead of machine-local root paths.
- `dispatch_authorized=false` and `live_providers_run=false` must be present.
- Release readiness must include the hygiene command.
- Operator slice `85-check-repeated-run-hygiene` must make the baseline
  repeatable.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT mark stale accepted evidence as current success.
- MUST NOT allow dry-run or failed-live evidence to satisfy live acceptance.
- MUST NOT authorize dispatch from the hygiene report.
- MUST NOT commit machine-local temporary paths in the report.

## Verification

```bash
python3 scripts/check_repeated_run_hygiene.py --write-output --json
python3 -m pytest -q tests/test_check_repeated_run_hygiene.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Repeated-run hygiene verdict is `PASS`.
- Scenario verdicts are all `PASS`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Release readiness includes the hygiene command.
