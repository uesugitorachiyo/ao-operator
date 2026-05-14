# 50 - Agent OS Router v2 State

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture implementation

## Objective

The mission router must be able to emit a native
`ao-operator/agent-os-state/v2` snapshot after the architecture readiness
summary passes, while keeping v1 output as the default compatibility path.

## Scope

`scripts/agent_os_router.py` gains:

- `--state-version v1|v2`
- `--architecture-readiness <path>`
- `build_state_snapshot_v2(...)`

The v2 path writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json` for
the existing mission-router brief.

## Required Behavior

- v1 remains the default CLI output.
- v2 requires `ao-operator/agent-os-architecture-readiness/v1` with
  `verdict=PASS` and `architecture_ready=true`.
- v2 links `role_graph_schema=ao-operator/agent-os-role-graph/v1`.
- v2 top-level `dispatch_authorized` is always false.
- v2 fails closed when readiness is missing, failing, or dispatch-authorized.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT authorize dispatch from a router state snapshot.
- MUST NOT break existing v1 mission-router tests or operator slice `40`.
- MUST NOT treat architecture readiness blockers as ignorable warnings.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_router.py
python3 scripts/agent_os_router.py --brief examples/agent-os/mission-router-state-brief.md --label release --state-version v2 --architecture-readiness run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json --write-state run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Router v2 state verdict is `PASS`.
- State schema is `ao-operator/agent-os-state/v2`.
- `architecture_ready=true`.
- `dispatch_authorized=false` and `live_providers_run=false`.
- Existing router v1 tests still pass.
