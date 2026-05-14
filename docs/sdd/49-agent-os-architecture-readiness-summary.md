# 49 - Agent OS Architecture Readiness Summary

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture safety

## Objective

AO Operator needs one operator-facing summary that says whether Agent OS router
and RunSpec architecture implementation can start against the committed safety
baselines.

## Scope

The gate lives at `scripts/summarize_agent_os_architecture_readiness.py`.
It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json`

It writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json`.

## Required Checks

- Role graph is `PASS`, has 7 roles, and points to state v2.
- State v2 is `PASS` and points to the role graph schema.
- Commit guard is `PASS` and does not allow success or raw snapshot commits.
- Postrun route matrix is `PASS` with 6 cases.
- RunSpec compatibility matrix is `PASS` with 3 cases.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT authorize dispatch.
- MUST fail closed if any baseline is missing, not `PASS`, or
  `dispatch_authorized=true`.
- MUST NOT start architecture implementation from partial local-only evidence.

## Verification

```bash
python3 scripts/summarize_agent_os_architecture_readiness.py --write-output --json
python3 -m pytest -q tests/test_agent_os_architecture_readiness.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Summary verdict is `PASS`.
- `architecture_ready=true`.
- `baseline_count=5`.
- `dispatch_authorized=false` and `live_providers_run=false`.
- Next safe command starts router architecture implementation behind these
  compatibility baselines.
