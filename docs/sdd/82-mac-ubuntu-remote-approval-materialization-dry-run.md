# SDD 82: Mac Ubuntu Remote Approval Materialization Dry Run

## Goal

Prove Ubuntu can consume the signed Agent OS approval bundle and run approval
materialization in dry-run mode without writing an approval file, dispatching
providers, or preserving remote staging.

## Scope

- Transfer the signed approval bundle package from Mac to an isolated Ubuntu
  staging directory.
- Verify artifact hashes, canonical bundle signature, signature report, and
  identity proof on Ubuntu.
- Run `materialize_agent_os_approval.py` on Ubuntu with the transferred bundle
  and the committed approval gate.
- Keep materialization in dry-run mode only.
- Return a small non-secret manifest to Mac.
- Delete remote staging and prove it is absent.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not pass `--write-approval-file`.
- Do not write or preserve a real approval file.
- Do not copy private signing keys or provider credentials.
- Do not use opportunistic SSH host-key trust.
- Do not preserve remote staging after a passing run.

## Verification

```bash
python3 scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py --json
python3 -m pytest -q tests/test_check_mac_ubuntu_remote_approval_materialization_dry_run.py
```

## Acceptance Criteria

- Remote materialization dry-run report emits schema
  `ao-operator/mac-ubuntu-remote-approval-materialization-dry-run/v1`.
- `remote_git_synced=true`.
- `signed_bundle_verified=true`.
- `signature_verified=true`.
- `identity_verified=true`.
- `materialization_dry_run_passed=true`.
- `approval_file_written=false`.
- `approval_valid=false`.
- `approval_file_present_after=false`.
- `remote_cleanup_absent=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- `provider_dispatch=false`.
