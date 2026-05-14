# 51 - Agent OS State Evidence Hygiene

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture safety

## Objective

Before continuing router/RunSpec architecture work, AO Operator must reject
stale or dirty Agent OS state evidence that could make local architecture
validation pass only on the machine that generated it.

## Scope

The guard lives at `scripts/check_agent_os_state_evidence_hygiene.py`.
It checks:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`
- untracked Agent OS state JSON artifacts under `run-artifacts/`

It writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-state-evidence-hygiene.json`.

## Required Behavior

- State evidence schema must be `ao-operator/agent-os-state/v2`.
- `role_graph_schema` must be `ao-operator/agent-os-role-graph/v1`.
- Top-level `dispatch_authorized=false`.
- Top-level `live_providers_run=false`.
- State blockers must be empty.
- Untracked Agent OS state diagnostics must be cleaned or intentionally staged.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT mutate state evidence except when writing this guard report.
- MUST NOT ignore untracked `agent-os*state*.json` diagnostics under
  `run-artifacts/`.
- MUST NOT allow stale dispatch flags to survive as warnings.

## Verification

```bash
python3 scripts/check_agent_os_state_evidence_hygiene.py --write-output --json
python3 -m pytest -q tests/test_agent_os_state_evidence_hygiene.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Guard verdict is `PASS`.
- `state_file_count=2`.
- `dirty_state_artifacts=[]`.
- `dispatch_authorized=false` and `live_providers_run=false`.
