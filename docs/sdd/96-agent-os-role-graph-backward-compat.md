# 96 - Agent OS Role Graph Backward Compatibility

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture implementation

## Objective

Prove that legacy Agent OS state and role-graph artifacts written before
the Router v2 default flip (SDD 95) remain readable and migratable under
the new v2 default. Lock backward compatibility behind a fail-closed gate
so future refactors of `scripts/agent_os_state_v2.py` cannot silently
break legacy ingestion paths.

## Scope

`scripts/check_agent_os_role_graph_backward_compat.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph-backward-compat.json`

The gate exercises six deterministic fixture cases inside a temporary
work directory (no repo pollution):

- `legacy_v1_state_minimal_loadable`
- `legacy_v1_state_extra_unknown_fields_tolerated`
- `legacy_v1_state_no_role_graph_schema_injects_default`
- `legacy_v2_state_round_trip_preserves_previous_schema`
- `legacy_v1_role_graph_artifact_remains_loadable`
- `unknown_state_schema_refused`

Each case writes a synthetic state or role-graph JSON, calls
`agent_os_state_v2.load_or_migrate_state` (or re-reads the artifact
directly for the role-graph case), and records `observed_verdict`,
`observed_schema`, `previous_schema`, and `role_graph_schema`.

## Required Behavior

- `case_count` MUST be `6`.
- The five forward-compat cases MUST observe `PASS`; the
  `unknown_state_schema_refused` case MUST observe `FAIL`.
- Every loaded payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- Legacy v1 state JSONs MUST migrate to `ao-operator/agent-os-state/v2`
  with `previous_schema=ao-operator/agent-os-state/v1`.
- When a legacy v1 state has no `role_graph_schema` field, the loader
  MUST inject `ao-operator/agent-os-role-graph/v1` as the default.
- Unknown legacy fields MUST NOT block migration; canonical fields
  (`lane`, `route`, `blockers`) MUST round-trip intact.
- Legacy v1 role-graph artifacts MUST remain JSON-parseable with
  `schema=ao-operator/agent-os-role-graph/v1` and the seven core role
  ids preserved.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use tempfile).
- MUST NOT change the `agent_os_state_v2` migration semantics; the gate
  is observational only.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_role_graph_backward_compat.py
python3 scripts/check_agent_os_role_graph_backward_compat.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=6`.
- Five `legacy_*` cases observe `PASS`; `unknown_state_schema_refused`
  observes `FAIL`.
- `dispatch_authorized=false` and `live_providers_run=false`.
- No `.cache/` or repo-root scratch directory remains after running the
  gate.
