# 47 - Agent OS State v2 Persistence

Classification: MODERATE
Shape: refactor

## Scope

This slice adds a persisted Agent OS state v2 reader/writer. It migrates legacy
state snapshots to `ao-operator/agent-os-state/v2`, links the committed role
graph schema, preserves route/blocker/evidence fields, and resets execution
authorization fields during load.

The goal is to give future router architecture changes a deterministic state
compatibility baseline before they start writing new state.

## Output

- State v2 evidence:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`

## Required Behavior

- v1 state snapshots migrate to v2.
- v2 state snapshots load and rewrite deterministically.
- Unsupported schemas fail closed.
- `dispatch_authorized=false` and `live_providers_run=false` are always
  top-level values after load or migration, even when old route data contains a
  stale dispatch flag.
- `role_graph_schema=ao-operator/agent-os-role-graph/v1` is recorded.

## Negative Constraints

- MUST NOT run AO providers.
- MUST NOT authorize Agent OS execution.
- MUST NOT trust legacy dispatch flags as approval.
- MUST NOT drop blockers or evidence paths during migration.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_state_v2.py
python3 scripts/agent_os_state_v2.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

Acceptance requires `verdict=PASS`, `schema=ao-operator/agent-os-state/v2`,
`role_graph_schema=ao-operator/agent-os-role-graph/v1`,
`dispatch_authorized=false`, and `live_providers_run=false`.
