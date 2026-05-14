# 46 - Agent OS Postrun Route Matrix

Classification: MODERATE
Shape: refactor

## Scope

This slice adds a deterministic route matrix for Agent OS RunSpec postrun
routing. It proves the router classifies pending, accepted, failed, blocked,
invalid-gate, and missing-evaluator-acceptance states without launching AO or
touching provider credentials.

The matrix uses synthetic local artifacts and the real
`scripts/route_agent_os_runspec_postrun.py` router.

## Output

- Matrix evidence:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json`

## Required Behavior

- Missing execution report routes to `PENDING_RUN`.
- Completed execution with evaluator acceptance routes to `ACCEPTED` and allows
  success-evidence commit eligibility at the route layer.
- Failed execution routes to `DIAGNOSTIC_REQUIRED`.
- Explicit blocked execution routes to `BLOCKED`.
- Invalid approval gate fails closed to `BLOCKED`.
- Completed execution without evaluator acceptance routes to
  `DIAGNOSTIC_REQUIRED`.
- Non-accepted states must keep `commit_success_evidence_allowed=false`.

## Negative Constraints

- MUST NOT run AO providers.
- MUST NOT authorize Agent OS execution.
- MUST NOT persist raw synthetic temp artifacts.
- MUST NOT allow success-evidence commits for failed, blocked, pending, or
  missing-evaluator-acceptance states.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_postrun_route_matrix.py
python3 scripts/check_agent_os_postrun_route_matrix.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

Acceptance requires the report to show `case_count=6`, `verdict=PASS`,
`dispatch_authorized=false`, and `live_providers_run=false`.
