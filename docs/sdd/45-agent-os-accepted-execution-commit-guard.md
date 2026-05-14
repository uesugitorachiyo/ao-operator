# 45 - Agent OS Accepted Execution Commit Guard

Classification: MODERATE
Shape: refactor

## Scope

This slice adds a local commit guard for Agent OS execution evidence. It
prevents an operator from treating pending, blocked, failed, or diagnostic
Agent OS execution artifacts as accepted success evidence. The guard composes
the postrun route, execution report, and evaluator closure report.

This is a non-dispatching validation slice. It does not run AO, does not
authorize execution, and does not change runtime role behavior.

## Inputs

- Postrun route:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json`
- Execution report:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json`
- Evaluator closure report:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-evaluator-closure.json`

## Output

- Commit guard evidence:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json`

## Required Behavior

- Current pending or blocked Agent OS execution evidence must produce
  `verdict=PASS` while keeping `commit_success_evidence_allowed=false`.
- An `ACCEPTED` postrun route must not allow success commit unless the execution
  report shows AO completed and evaluator accepted.
- An `ACCEPTED` postrun route must not allow success commit unless the execution
  report shows a real live provider run and is not `fixture_only=true`.
- An `ACCEPTED` postrun route must not allow success commit unless evaluator
  closure reports `closure_authorized=true`.
- Raw AO snapshots must remain non-committable.
- `dispatch_authorized=false` and `live_providers_run=false` must remain true
  for the guard itself.

## Negative Constraints

- MUST NOT run AO providers.
- MUST NOT authorize Agent OS execution.
- MUST NOT commit failed or diagnostic execution evidence as success.
- MUST NOT allow raw AO home snapshots to be committed.
- MUST NOT allow route-only acceptance to bypass evaluator closure.
- MUST NOT allow provider-free fixture output to become live success evidence.

## Verification

Run these commands before accepting the slice:

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/check_agent_os_accepted_execution_commit_guard.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

The committed output is expected to keep `commit_success_evidence_allowed=false`
until a future explicit execution approval, AO completion, accepted postrun
route, and evaluator closure all exist together.

## Acceptance Criteria

- The guard script is compiled by PR readiness.
- The guard script is required by Factory validation.
- The operator slice manifest includes a non-live commit-guard slice.
- Tests cover pending/blocked refusal, accepted-route-without-closure failure,
  synthetic no-provider rejection, and accepted completed execution success.
- The committed current-state guard artifact is non-authorizing.
