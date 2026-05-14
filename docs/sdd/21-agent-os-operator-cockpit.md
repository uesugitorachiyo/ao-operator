# 21 - Agent OS Operator Cockpit

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds a local Agent OS operator cockpit snapshot. It combines learning
extraction, UAT blocker state, release readiness, Agent OS state-v2 readiness,
RunSpec rendering state, execution approval lock state, and evidence paths into
one operator-facing JSON artifact. It does not dispatch providers or authorize
closure.

## Cockpit Contract

The cockpit builder lives at `scripts/agent_os_operator_cockpit.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json`
- `run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-operator-cockpit.json`

The cockpit must include:

- active milestone
- blockers
- UAT pending count and closure state
- readiness verdict and ship-ready state
- Agent OS state-v2 verdict and architecture-ready state
- rendered RunSpec path, task count, and state-v2 baseline check
- execution lock algorithm, RunSpec SHA-256, approval state, runner verdict, and provider-run posture
- evidence paths
- next safe command

## Negative Constraints

- MUST NOT dispatch AO providers.
- MUST NOT authorize closure while UAT remains pending.
- MUST NOT hide UAT blockers behind ship readiness.
- MUST NOT present Agent OS execution as ready when approval is absent or invalid.
- MUST NOT accept a missing RunSpec SHA-256 lock as cockpit-ready.
- MUST NOT mutate runtime role behavior.
- MUST NOT inject generated context into instruction files.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_operator_cockpit.py
python3 scripts/agent_os_operator_cockpit.py --write-output --json
```

## Acceptance Criteria

- Cockpit report emits schema `ao-operator/agent-os-operator-cockpit/v1`.
- Cockpit records active milestone.
- Cockpit records UAT pending count and blockers.
- Cockpit records release readiness state.
- Cockpit records Agent OS state-v2 readiness.
- Cockpit records rendered RunSpec path and task count.
- Cockpit records SHA-256 RunSpec execution lock state.
- Cockpit shows execution blocked until explicit approval is valid.
- Cockpit records evidence paths.
- `closure_authorized=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
