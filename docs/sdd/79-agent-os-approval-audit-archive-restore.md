# SDD 79: Agent OS Approval Audit Archive Restore

## Goal

Prove approval audit logs can be archived and restored before any manual
archive-before-truncate operation.

## Scope

- Copy the committed audit JSONL into an isolated archive fixture.
- Restore the archive copy into an isolated restore fixture.
- Verify source, archive, and restored SHA-256 values match.
- Reuse compact audit-event validation to reject payload leakage.

## Negative Constraints

- Do not truncate the source audit log.
- Do not run AO.
- Do not dispatch provider CLIs.
- Do not archive nested approval payloads or accepted-risk text.

## Verification

```bash
python3 scripts/check_agent_os_approval_audit_archive_restore.py --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_audit_archive_restore.py
```
