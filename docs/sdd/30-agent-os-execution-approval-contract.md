# 30 - Agent OS Execution Approval Contract

Classification: MODERATE
Shape: greenfield

## Scope

This slice validates the explicit approval JSON required before any Agent OS
RunSpec execution can proceed. Missing approval is a safe `NOT_APPROVED` state,
not an error, and does not authorize dispatch. When approval is present, it
must match the approval gate's `runspec_sha256`.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/validate_agent_os_runspec_execution_approval.py --write-output --json
```

## Acceptance Criteria

- Approval validator emits schema
  `ao-operator/agent-os-runspec-execution-approval-validation/v1`.
- Missing approval records `approval_valid=false`.
- Valid approval records operator, timestamp, expiration, runspec path, task
  count, `runspec_sha256`, and accepted risk.
- Approval with a mismatched `runspec_sha256` is invalid.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
