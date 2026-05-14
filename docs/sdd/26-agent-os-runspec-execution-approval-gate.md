# 26 - Agent OS RunSpec Execution Approval Gate

Classification: MODERATE
Shape: greenfield

## Scope

This slice prepares the future Agent OS RunSpec execution approval posture
without running AO. It records the exact execution command, approval file
schema, RunSpec SHA-256 lock, stop rules, provider-profile alignment, and
validation prerequisites while keeping dispatch blocked.

## Contract

The gate lives at `scripts/check_agent_os_runspec_execution_approval_gate.py`.
It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json`
and emits `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT authorize dispatch.
- MUST NOT treat approval-file presence as execution permission.
- MUST NOT proceed unless RunSpec validation is PASS.
- MUST NOT proceed unless RunSpec provider-profile alignment is PASS.
- MUST NOT prepare approval when the rendered RunSpec file is missing.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_prep.py
python3 scripts/check_agent_os_runspec_execution_approval_gate.py --write-output --json
```

## Acceptance Criteria

- `approval_request_ready=true` only after RunSpec validation passes.
- `provider_profile_checked=true` and `provider_profile_matches=true` are
  required before approval readiness.
- Exact future `ao run` command is recorded.
- `runspec_sha256` and `runspec_lock.algorithm=sha256` are recorded.
- Approval schema and approval file path are recorded.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
