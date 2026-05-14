# 23 - Agent OS Closure Gate

Classification: MODERATE
Shape: greenfield

## Scope

This slice closes the local Agent OS lane only after the human UAT response
gate and release readiness gate both pass. It records a durable closure report
that distinguishes local Agent OS closure from any live-provider escalation.

The closure gate is validation-only. It must not dispatch AO providers, create
new live slices, mutate runtime role behavior, or treat operator acceptance as
approval for a larger live run.

## Closure Contract

The gate lives at `scripts/agent_os_closure_gate.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json`
- `run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-closure-gate.json`

The closure report uses schema `ao-operator/agent-os-closure-gate/v1`.

## Negative Constraints

- MUST NOT close Agent OS unless the UAT response gate has
  `closure_authorized=true`.
- MUST NOT close Agent OS unless release readiness has `ship_ready=true`.
- MUST NOT allow `dispatch_authorized=true`.
- MUST NOT allow `live_providers_run=true`.
- MUST NOT dispatch AO providers.
- MUST NOT create or imply approval for 75-slice live execution.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_closure_gate.py
python3 scripts/agent_os_closure_gate.py --write-output --json
```

## Acceptance Criteria

- Closure gate emits schema `ao-operator/agent-os-closure-gate/v1`.
- Passing UAT responses plus ship-ready release readiness set
  `agent_os_closed=true`.
- Missing UAT closure authorization keeps `agent_os_closed=false`.
- Readiness dispatch authorization fails the gate.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
