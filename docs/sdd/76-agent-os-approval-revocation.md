# SDD 76: Agent OS Approval Revocation

## Goal

Add an operator revocation and rollback lane for materialized Agent OS approval
files so a stale or unsafe approval can be invalidated without dispatch.

## Scope

- Default mode is non-mutating and reports the revocation plan.
- `--apply --force` removes the approval file only with operator and reason.
- Applied revocation appends a compact event to a JSONL revocation log.
- Revocation events omit nested approval payloads and accepted-risk text.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not remove approval files without `--apply --force`.
- Do not log approval payloads or accepted-risk detail into revocation history.

## Verification

```bash
python3 scripts/check_agent_os_approval_revocation.py --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_revocation.py
```
