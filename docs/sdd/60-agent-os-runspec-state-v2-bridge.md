# 60 - Agent OS RunSpec State v2 Bridge

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture implementation

## Objective

The Agent OS RunSpec renderer must consume the committed router v2 state
baseline before producing AO-facing RunSpec evidence. This bridges the
architecture readiness/state-v2 lane into RunSpec generation without
authorizing live provider dispatch.

## Scope

`scripts/agent_os_runspec_renderer.py` gains an optional `--state-baseline`
input. When provided, the renderer records state metadata and fails closed if
the state baseline is stale, unsafe, or not architecture-ready.

Operator slice `87-render-agent-os-runspec-with-state-v2` rerenders the
existing Agent OS draft using:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`
- `.env.example`

## Required Behavior

- State baseline schema must be `ao-operator/agent-os-state/v2`.
- State baseline verdict must be `PASS`.
- State baseline `architecture_ready` must be true.
- State baseline `role_graph_schema` must be
  `ao-operator/agent-os-role-graph/v1`.
- State baseline `dispatch_authorized` and `live_providers_run` must be false.
- Renderer output must expose `state_baseline_checked`,
  `state_schema_version`, `role_graph_schema`, and `architecture_ready`.
- Existing handoff-only renderer behavior remains supported for compatibility.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run live providers.
- MUST NOT authorize dispatch from renderer state.
- MUST NOT render from a state baseline with stale dispatch flags.
- MUST NOT treat missing architecture readiness as a warning.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_runspec_renderer.py
python3 scripts/agent_os_runspec_renderer.py --provider-profile .env.example --state-baseline run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json --write-output --write-runspec --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Renderer state-v2 tests pass.
- Operator slice 87 validates and records state-v2 evidence.
- Renderer report records `state_baseline_checked=true`.
- Renderer report records `state_schema_version=ao-operator/agent-os-state/v2`.
- Renderer report records `architecture_ready=true`.
- `dispatch_authorized=false` and `live_providers_run=false`.
