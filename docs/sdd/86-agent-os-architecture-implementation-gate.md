# 86 - Agent OS Architecture Implementation Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture implementation

## Objective

Before changing the Agent OS role graph, router, state layer, or RunSpec
generation again, AO Operator needs one machine-checkable gate that proves the
current implementation surfaces are coherent and still non-dispatching.

## Scope

The gate lives at
`scripts/check_agent_os_architecture_implementation_gate.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-provider-boundary-matrix.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-execution-hygiene.json`

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-implementation-gate.json`

## Required Behavior

- All input reports must be `PASS`.
- All input reports must keep `dispatch_authorized=false`.
- All input reports must keep `live_providers_run=false`.
- Architecture readiness must have `architecture_ready=true`.
- Router v2 state must point to `ao-operator/agent-os-role-graph/v1`.
- Renderer output must prove `state_baseline_checked=true`.
- Renderer output must bridge `ao-operator/agent-os-state/v2`.
- Role graph roles, handoff packet roles, and RunSpec task ids must align.
- Every rendered RunSpec task must have `dispatchAuthorized=false`.
- Provider boundary matrix must include Codex-only, Claude-only, mixed, and
  substitution-refusal coverage.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch.
- MUST NOT proceed when any implementation surface is missing.
- MUST NOT treat role graph, handoff, or RunSpec drift as a warning.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_architecture_implementation_gate.py
python3 scripts/check_agent_os_architecture_implementation_gate.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `implementation_ready=true`.
- `role_count=7`.
- `handoff_packet_count=7`.
- `runspec_task_count=7`.
- `role_handoff_runspec_alignment=PASS`.
- `dispatch_authorized=false` and `live_providers_run=false`.
