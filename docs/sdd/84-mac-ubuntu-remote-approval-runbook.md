# SDD 84: Mac Ubuntu Remote Approval Runbook

## Goal

Provide a deterministic operator runbook for the no-provider Mac-to-Ubuntu
approval evidence sequence after signed transfer, remote materialization
dry-run, revocation, rollback restore, and cleanup proofs exist.

## Scope

- Document the exact command order for remote approval evidence refresh.
- Require `FACTORY_V3_REMOTE_HOST` before remote commands.
- Require release readiness before remote approval operations.
- Require parity, signed transfer, remote materialization dry-run, remote
  revocation rollback, operator summary, JSON integrity, and redaction checks.
- Validate the runbook with a machine-checkable report.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write a real repo approval file.
- Do not copy private signing keys or provider credentials.
- Do not preserve remote staging.
- Do not commit failed evidence.

## Verification

```bash
python3 -m pytest -q tests/test_check_mac_ubuntu_remote_approval_runbook.py
python3 scripts/check_mac_ubuntu_remote_approval_runbook.py --write-output --json
python3 scripts/check_mac_ubuntu_remote_approval_runbook.py --json
```

## Acceptance Criteria

- Report emits schema `ao-operator/mac-ubuntu-remote-approval-runbook/v1`.
- `verdict=PASS`.
- `required_item_count` covers the required command and stop-rule set.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Operator summary and release artifact index include the report.
