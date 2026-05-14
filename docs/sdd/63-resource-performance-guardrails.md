# 63 - Resource Performance Guardrails

Classification: MODERATE
Shape: refactor

## Scope

This slice adds a non-live resource/performance gate for the accepted 50-slice
baseline. It checks dry-run wallclock evidence, provider-budget abort
conditions, accepted operator summary state, and local temp footprint for AO
home/worktree paths if those paths exist.

## Contract

The checker lives at `scripts/check_resource_performance_gate.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json`
- `run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json`
- `run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json`
- `/tmp/ao-operator-worktrees/remote-transfer-v2-stress-live` when present
- `/tmp/ao-operator-ao-remote-transfer-v2-stress-live` when present

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/resource-performance-gate.json`

## Negative Constraints

- MUST NOT dispatch AO providers.
- MUST NOT start AO.
- MUST NOT fail only because temp AO/worktree paths are absent.
- MUST fail if accepted 50-slice state is not represented.
- MUST fail if provider-budget evidence omits rate-limit or stalled-event abort
  conditions.

## Verification

```bash
python3 -m pytest -q tests/test_check_resource_performance_gate.py
python3 scripts/check_resource_performance_gate.py --write-output --json
```

## Acceptance Criteria

- Dry-run wallclock evidence is PASS and under the configured limit.
- Provider-budget evidence is PASS and includes 429/rate-limit and stalled AO
  event abort conditions.
- Accepted 50-slice operator summary is PASS.
- Temp worktree and AO home footprints are absent or under documented limits.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
