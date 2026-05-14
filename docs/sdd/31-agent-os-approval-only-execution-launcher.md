# 31 - Agent OS Approval-Only Execution Launcher

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds the approval-only Agent OS RunSpec execution launcher. The
launcher must refuse execution unless the explicit approval validation report is
valid, carries provider-profile alignment from the approval gate, and passes a
fresh approval lifecycle check at launch time. It may plan the approved command
without dispatch and may run AO only when explicit approval validates,
provider-profile alignment is still `PASS`, the approval file is still active,
and the operator passes `--execute`. Before dispatch, it recomputes the current
RunSpec SHA-256 and compares it with the approved hash.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/run_agent_os_runspec_execution.py --write-output --json
```

## Acceptance Criteria

- Missing or invalid approval returns `BLOCKED`.
- Missing, false, or mismatched provider-profile alignment returns `BLOCKED`.
- Missing, expired, future-dated, or drifted approval lifecycle returns
  `BLOCKED`.
- The launcher records the execution command it would run.
- The launcher records `current_runspec_sha256`.
- The launcher records approval lifecycle state in `approval_lifecycle`.
- A current-vs-approved RunSpec hash mismatch returns `BLOCKED`.
- Valid approval without `--execute` returns `PLAN`.
- Valid approval with `--execute` runs the command as a list, not a shell.
- `would_run_provider=false` while approval is invalid.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
