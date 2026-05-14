# SDD 83: Mac Ubuntu Remote Approval Revocation Rollback

## Goal

Prove Ubuntu can receive the signed Agent OS approval bundle, create an
isolated approval fixture, apply revocation, restore the approval from a local
rollback copy, and delete all remote staging without touching the real repo
approval path or dispatching providers.

## Scope

- Transfer the signed approval bundle package from Mac to an isolated Ubuntu
  staging directory.
- Verify artifact hashes, canonical bundle signature, signature report, and
  identity proof on Ubuntu.
- Build an isolated fixture under the remote staging root.
- Materialize a fixture approval only inside that staging fixture.
- Apply `check_agent_os_approval_revocation.py --apply --force` only inside the
  fixture.
- Restore the fixture approval from a rollback copy and verify byte equality.
- Return a small non-secret manifest to Mac.
- Delete remote staging and prove it is absent.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write or preserve a real repo approval file.
- Do not run revocation against the real repo approval path.
- Do not copy private signing keys or provider credentials.
- Do not use opportunistic SSH host-key trust.
- Do not preserve remote staging after a passing run.

## Verification

```bash
python3 scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py --json
python3 -m pytest -q tests/test_check_mac_ubuntu_remote_approval_revocation_rollback.py
```

## Acceptance Criteria

- Remote revocation rollback report emits schema
  `ao-operator/mac-ubuntu-remote-approval-revocation-rollback/v1`.
- `remote_git_synced=true`.
- `signed_bundle_verified=true`.
- `signature_verified=true`.
- `identity_verified=true`.
- `fixture_approval_written=true`.
- `revocation_applied=true`.
- `approval_file_present_after_revocation=false`.
- `rollback_restore_verified=true`.
- `approval_file_restored_after=true`.
- `revocation_log_sanitized=true`.
- `remote_cleanup_absent=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- `provider_dispatch=false`.
