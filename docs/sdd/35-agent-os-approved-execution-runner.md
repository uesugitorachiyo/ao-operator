# 35 - Agent OS Approved Execution Runner

Classification: MODERATE
Shape: refactor

## Scope

This slice upgrades the Agent OS RunSpec launcher from a placeholder into a
real gated runner. The runner may invoke `ao run` only when the approval
validation report is valid, provider-profile alignment is checked and matches,
and the operator passes `--execute`. The command must be executed as an
argument list, never through a shell.

The runner also enforces the Agent OS RunSpec execution plan lock from
`docs/sdd/61-agent-os-runspec-execution-plan-lock.md`: approval must name the
same `runspec_sha256` that the launcher recomputes from the current RunSpec
file before dispatch.

The committed operator evidence remains non-dispatching because the explicit
approval file is absent.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/run_agent_os_runspec_execution.py --write-output run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json --json
```

## Acceptance Criteria

- Missing or invalid approval returns `BLOCKED`.
- Missing, false, or mismatched provider-profile alignment returns `BLOCKED`.
- Valid approval without `--execute` returns `PLAN`.
- Valid approval with `--execute` runs the approved `ao run` command as a list.
- RunSpec hash drift after approval returns `BLOCKED`.
- Provider stdout and stderr are captured only as bounded tails.
- Failed AO execution records `diagnostics_required=true`.
- The committed slice does not run providers while approval is absent.
