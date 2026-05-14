# 87 - Agent OS Router Transition Matrix

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture hardening

## Objective

Prove the Agent OS mission router remains deterministic across the current
classification, label, shape-gate, live-provider, and state v2 transition
edges before deeper router or role-graph implementation changes.

## Scope

The gate lives at `scripts/check_agent_os_router_transition_matrix.py`.

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-transition-matrix.json`

## Required Behavior

- Cover trivial, moderate, complex, frontend, security-sensitive,
  live-provider, unknown-label, shape-gate-blocked, and state v2 release
  transitions.
- Preserve live-provider blockers.
- Preserve bug-fix shape-gate blockers when reproducer evidence is missing.
- Prove unknown labels are ignored rather than creating implicit routes.
- Prove the matrix artifact itself keeps `dispatch_authorized=false` and
  `live_providers_run=false`.
- Prove the release refactor case can emit `ao-operator/agent-os-state/v2`
  with a PASS verdict.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from the matrix artifact.
- MUST NOT treat live-provider routes as safe without explicit approval.
- MUST NOT treat unknown labels as valid routing labels.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_router_transition_matrix.py
python3 scripts/check_agent_os_router_transition_matrix.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=9`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Live-provider route has at least one blocker.
- Missing bug-fix reproducer route has at least one blocker.
- Release refactor state v2 case has `state_verdict=PASS`.
