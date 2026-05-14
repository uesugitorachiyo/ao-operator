# 28 - Agent OS RunSpec Postrun Router

Classification: MODERATE
Shape: greenfield

## Scope

This slice routes future Agent OS RunSpec execution evidence after a run. It
does not execute AO; it classifies available evidence as `PENDING_RUN`,
`ACCEPTED`, `DIAGNOSTIC_REQUIRED`, or `BLOCKED`.

The current committed repository already contains an execution report proving
the launcher blocks without valid approval. Therefore the default operator
slice rerun routes that current evidence to `BLOCKED`; the synthetic test
matrix remains responsible for proving the missing-report `PENDING_RUN` case.

## Contract

The router lives at `scripts/route_agent_os_runspec_postrun.py`.
It reads the execution approval gate and optional execution report, then emits
`run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json`.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT commit success evidence unless execution and evaluator acceptance
  are both proven.
- MUST NOT hide failed execution evidence.
- MUST NOT authorize dispatch.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_prep.py
python3 scripts/route_agent_os_runspec_postrun.py --write-output --json
```

## Acceptance Criteria

- Missing execution report routes to `PENDING_RUN` in tests and the route
  matrix.
- Current blocked execution report routes to `BLOCKED` in the default operator
  slice.
- Failed execution report routes to `DIAGNOSTIC_REQUIRED`.
- Accepted execution report can allow success evidence.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
