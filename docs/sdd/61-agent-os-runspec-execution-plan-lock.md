# 61 - Agent OS RunSpec Execution Plan Lock

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS execution safety

## Objective

Agent OS execution approval must bind to the exact rendered RunSpec that will
be executed. A path and task count are not enough because the YAML can drift
after approval. The approval gate, approval validator, and execution launcher
therefore share a SHA-256 RunSpec lock.

## Scope

The lock is implemented across existing approval scripts:

- `scripts/check_agent_os_runspec_execution_approval_gate.py` records
  `runspec_sha256` and `runspec_lock`.
- `scripts/validate_agent_os_runspec_execution_approval.py` requires explicit
  approval JSON to carry the same `runspec_sha256`.
- `scripts/check_agent_os_approval_lifecycle.py` checks approval expiry and
  RunSpec hash drift at the current decision time.
- `scripts/run_agent_os_runspec_execution.py` recomputes the current RunSpec
  hash, runs the lifecycle check again, and refuses execution if the file
  changed or the approval expired after approval validation.
- `scripts/check_agent_os_approved_execution_fixture.py` includes the same
  lock in its provider-free happy-path fixture.

## Required Behavior

- Approval gate fails if the rendered RunSpec file is missing.
- Approval gate records `runspec_lock.algorithm=sha256`,
  `runspec_lock.path`, and `runspec_lock.sha256`.
- Explicit approval must include `runspec_sha256` matching the approval gate.
- Execution launcher must recompute the current RunSpec SHA-256 before any
  `--execute` dispatch.
- Execution launcher must recheck approval lifecycle before any `--execute`
  dispatch.
- Any current-vs-approved hash mismatch returns `BLOCKED`.
- Any expired approval returns `BLOCKED`.

## Negative Constraints

- MUST NOT run AO from the approval gate or approval validator.
- MUST NOT treat a matching path as sufficient approval.
- MUST NOT run providers when the current RunSpec hash differs from the
  approved hash.
- MUST NOT run providers when approval lifecycle is absent, expired, or
  otherwise unusable.
- MUST NOT let the provider-free fixture count as live success evidence.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_prep.py tests/test_agent_os_execution_readiness.py tests/test_agent_os_approved_execution_fixture.py
python3 scripts/check_agent_os_runspec_execution_approval_gate.py --write-output --json
python3 scripts/validate_agent_os_runspec_execution_approval.py --write-output --json
python3 scripts/check_agent_os_approval_lifecycle.py --write-output --json
python3 scripts/run_agent_os_runspec_execution.py --write-output run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json --json
```

## Acceptance Criteria

- Approval gate records a non-empty `runspec_sha256`.
- Approval validation carries `runspec_sha256` and fails explicit approval hash
  mismatches.
- Execution launcher records `current_runspec_sha256`.
- Execution launcher records `approval_lifecycle`.
- Execution launcher blocks if the current RunSpec changed after approval.
- Execution launcher blocks if approval lifecycle is expired or missing at
  launch time.
- `dispatch_authorized=false` and `live_providers_run=false` remain true for
  committed no-approval evidence.
