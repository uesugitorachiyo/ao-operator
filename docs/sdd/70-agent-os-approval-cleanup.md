# Agent OS Approval Cleanup

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Provide a safe cleanup command for Agent OS execution approval files so expired
or intentionally cleared approvals do not remain available for later launcher
runs.

## Contract

`scripts/cleanup_agent_os_approval.py` emits
`ao-operator/agent-os-approval-cleanup/v1`.

Default behavior:

- inspect the approval file path
- report `approval_state=ABSENT` when no approval file exists
- report expired approval files as cleanup candidates
- keep `removed=false`
- keep `dispatch_authorized=false`
- keep `live_providers_run=false`

Apply behavior:

- `--apply` removes expired or invalid approval files
- `--apply --force` may remove active or future-dated approval files
- cleanup is restricted to
  `run-artifacts/**/agent-os-runspec-execution-approval.json`

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not remove unrelated status artifacts.
- Do not remove active approvals without `--force`.
- Do not remove files outside `run-artifacts/`.

## Verification

```bash
python3 -m pytest -q tests/test_cleanup_agent_os_approval.py
python3 scripts/cleanup_agent_os_approval.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-cleanup.json
```
