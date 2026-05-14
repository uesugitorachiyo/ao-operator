# Agent OS Approval Audit History

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Record compact append-only approval audit events from approval materialization,
cleanup, and proof reports without copying sensitive approval payloads.

## Contract

`scripts/check_agent_os_approval_audit_history.py` emits
`ao-operator/agent-os-approval-audit-history/v1` and appends event lines using
`ao-operator/agent-os-approval-audit-event/v1` only when `--append` is explicit.

Required behavior:

- Default summary mode must not modify the audit log.
- `--append` appends one JSONL event derived from a source report.
- Events must keep `dispatch_authorized=false`.
- Events must keep `live_providers_run=false`.
- Events must not copy nested approval payloads.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not use audit events as execution approval.
- Do not mutate previous audit lines.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_approval_audit_history.py
python3 scripts/check_agent_os_approval_audit_history.py --append --write-output --json
```

## Evidence

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit.json
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit.jsonl
```
