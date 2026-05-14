# Agent OS Approval Materialization Runbook

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Provide an operator runbook for the real approval materialization sequence and a
deterministic checker that prevents stale, incomplete, or unsafe runbook text.

## Contract

`scripts/check_agent_os_approval_runbook.py` emits
`ao-operator/agent-os-approval-runbook/v1`.

The runbook must include:

- approval materialization command with `--write-approval-file`
- approval validation command
- approval lifecycle command
- launcher planning command
- approval cleanup command
- explicit negative constraints against AO/provider dispatch
- explicit instruction not to commit approval files

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not create approval files from the checker.
- Do not treat the runbook as approval.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_approval_runbook.py
python3 scripts/check_agent_os_approval_runbook.py --write-output --json
```

## Evidence

```text
docs/runbooks/agent-os-approval-materialization.md
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-runbook.json
```
