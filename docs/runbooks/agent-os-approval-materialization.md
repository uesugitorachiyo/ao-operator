# Agent OS Approval Materialization Runbook

This runbook describes the manual approval sequence for one Agent OS RunSpec
execution. It does not authorize execution by itself.

## Preconditions

- Confirm `python3 scripts/check_release_readiness.py --skip-closure --json`
  reports `verdict=PASS`.
- Confirm `python3 scripts/check_agent_os_approval_lifecycle.py --json`
  reports `approval_state=ABSENT`.
- Confirm the RunSpec hash in
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`
  matches `ao/runspecs/agent-os-phase-draft.yaml`.

## Commands

Materialize the approval file only when the operator intentionally accepts the
risk and the RunSpec hash is current:

```bash
python3 scripts/materialize_agent_os_approval.py \
  --write-approval-file \
  --approved \
  --operator OPERATOR \
  --accepted-risk RISK \
  --write-output \
  --json
```

Validate the approval before any launcher use:

```bash
python3 scripts/validate_agent_os_runspec_execution_approval.py --json
python3 scripts/check_agent_os_approval_lifecycle.py --json
```

Plan the launcher state before execution:

```bash
python3 scripts/run_agent_os_runspec_execution.py --json
```

Clean up approval after use, expiry, cancellation, or aborted launch:

```bash
python3 scripts/cleanup_agent_os_approval.py --apply --force --json
python3 scripts/check_agent_os_approval_lifecycle.py --json
```

## Negative Constraints

- Do not run AO from this runbook.
- Do not dispatch provider CLIs from this runbook.
- Do not commit approval files.
- Do not skip lifecycle validation.
- Do not leave approval files active after use.

## Evidence

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-materialization.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-lifecycle.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-cleanup.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit.json`
