# Operator Safe Next Command

## Objective

Provide one durable operator-facing report that states the current accepted
state, approval posture, release readiness, evidence paths, and the next safe
command without authorizing provider dispatch.

## Scope

The checker lives at `scripts/check_operator_safe_next_command.py` and emits
schema `ao-operator/operator-safe-next-command/v1`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json`
- `run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json`
- `run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json`
- `run-artifacts/remote-transfer-v2-stress-live/release-artifact-index.json`

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/operator-safe-next-command.json`

## Requirements

- MUST report `current_state`, `approval_state`, `ship_ready`, blockers,
  evidence paths, recommended commands, and a human-readable
  `next_safe_command`.
- MUST keep `dispatch_authorized=false`.
- MUST keep `live_providers_run=false`.
- MUST fail closed if any source report is missing, failing, dispatching, or
  records live-provider execution.
- MUST require release readiness and operator guardrails to be ship-ready
  before recommending the next gated SDD lane.
- MUST NOT materialize approval files, run AO, run live providers, or mutate
  remote state.

## Verification

```bash
python3 -m pytest -q tests/test_check_operator_safe_next_command.py
python3 scripts/check_operator_safe_next_command.py --write-output --json
python3 scripts/check_release_artifact_index.py --write-output --json
python3 scripts/check_release_readiness.py --write-output --json
```

## Acceptance Evidence

The committed report must have:

- `schema=ao-operator/operator-safe-next-command/v1`
- `verdict=PASS`
- `safe_action=START_NEXT_GATED_SDD_LANE`
- `dispatch_authorized=false`
- `live_providers_run=false`
