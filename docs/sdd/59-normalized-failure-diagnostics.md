# 59 - Normalized Failure Diagnostics

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture safety

## Objective

Surface AO Runtime `normalized_reason` failure signals through AO Operator event
summaries and evaluator evidence so failed provider runs remain understandable
after router, RunSpec, and operator architecture changes.

## Scope

The baseline is checked by `scripts/check_normalized_failure_diagnostics.py`.
It verifies the provider-free path through:

- `scripts/summarize_ao_failure.py`
- `scripts/factory_run.py` event summaries
- Factory evaluator evidence lines

It writes
`run-artifacts/remote-transfer-v2-stress-live/normalized-failure-diagnostics.json`.

## Required Behavior

- AO `task.failed` events with explicit or inferred normalized reasons must
  produce normalized reason counts.
- Event markdown must include normalized reason counts and the primary
  normalized reason.
- Evaluator evidence must include normalized failure reason counts and primary
  reason when failed task events exist.
- The checker must be provider-free and non-dispatching.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT authorize dispatch.
- MUST NOT treat missing normalized failure reasons as live acceptance.
- MUST NOT commit raw AO homes.
- MUST NOT write machine-local paths to the committed report.

## Verification

```bash
python3 scripts/check_normalized_failure_diagnostics.py --write-output --json
python3 -m pytest -q tests/test_factory_run_failure_diagnostics.py tests/test_check_normalized_failure_diagnostics.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Normalized failure diagnostics verdict is `PASS`.
- `primary_normalized_reason=provider-rate-limit`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Release readiness includes the normalized failure diagnostics gate.
