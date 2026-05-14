# Agent OS Approval Lifecycle

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Add a fail-closed approval lifecycle gate so Agent OS execution approvals cannot
be reused after expiry, after RunSpec hash drift, or without explicit operator
and risk fields.

## Contract

`scripts/check_agent_os_approval_lifecycle.py` emits
`ao-operator/agent-os-approval-lifecycle/v1`.

The default repository state has no approval file. That state must pass as a
safe non-dispatching posture with:

- `approval_state=ABSENT`
- `approval_usable=false`
- `dispatch_authorized=false`
- `live_providers_run=false`

When an approval file is present, the lifecycle gate must require:

- schema `ao-operator/agent-os-runspec-execution-approval/v1`
- `approved=true`
- non-empty `operator`
- non-empty `accepted_risk`
- `approved_at <= now < expires_at`
- approval RunSpec path, SHA-256, and task count match the approval gate
- current RunSpec SHA-256 matches the approval file

Expired approvals, future-dated approvals, malformed approvals, and RunSpec hash
drift must produce `verdict=FAIL` and `approval_usable=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not create approval files from this checker.
- Do not treat missing approval as execution approval.
- Do not treat expired approval as recoverable without rematerialization.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_approval_lifecycle.py
python3 scripts/check_agent_os_approval_lifecycle.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-lifecycle.json
```
