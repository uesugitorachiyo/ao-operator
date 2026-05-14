# 48 - Agent OS RunSpec Compatibility Matrix

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture safety

## Objective

Before router or RunSpec architecture changes, AO Operator must preserve a
deterministic compatibility baseline for the Agent OS RunSpec renderer output
and committed YAML draft.

## Scope

The gate lives at `scripts/check_agent_os_runspec_compatibility_matrix.py`.
It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
and `ao/runspecs/agent-os-phase-draft.yaml`, then writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json`.

## Required Cases

1. Current renderer report must be schema-valid, PASS, non-dispatching, and
   have unique task ids with prompt coverage.
2. Current YAML draft must remain `kind: Run`, non-dispatching, and contain the
   same task ids as the renderer report.
3. Legacy renderer v1 fixture must remain accepted so architecture changes do
   not break the existing persisted renderer shape.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT set `dispatch_authorized=true`.
- MUST NOT treat YAML-only evidence as accepted when it diverges from the
  renderer report.
- MUST fail closed if any task-level `dispatchAuthorized` flag is true.

## Verification

```bash
python3 scripts/check_agent_os_runspec_compatibility_matrix.py --write-output --json
python3 -m pytest -q tests/test_agent_os_runspec_compatibility_matrix.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Matrix verdict is `PASS`.
- `case_count=3`.
- Current renderer and YAML task ids match.
- Legacy renderer v1 fixture remains accepted.
- `dispatch_authorized=false` and `live_providers_run=false`.
