# SDD 74: Agent OS Approval Audit Retention

## Goal

Add a non-dispatching retention gate for Agent OS approval audit history so the
append-only JSONL log remains compact, payload-free, and ready for manual
archive-before-truncate rotation.

## Scope

- Validate `agent-os-approval-audit.jsonl` exists and contains only compact
  audit events.
- Reject nested approval payloads and accepted-risk text in audit events.
- Report `rotation_due=true` when event count or byte thresholds are exceeded.
- Keep rotation advisory-only; the checker never deletes or truncates audit
  history.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not copy full approval payloads into retention reports.
- Do not rotate or delete audit logs from the default checker.

## Verification

```bash
python3 scripts/check_agent_os_approval_audit_retention.py --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_audit_retention.py
```
