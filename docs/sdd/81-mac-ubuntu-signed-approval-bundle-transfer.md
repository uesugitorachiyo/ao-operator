# SDD 81: Mac Ubuntu Signed Approval Bundle Transfer

## Goal

Prove the signed Agent OS approval bundle can be copied from Mac to Ubuntu,
verified on Ubuntu, and cleaned from remote staging before any remote approval
materialization work.

## Scope

- Package only bounded public approval artifacts:
  - approval bundle
  - approval bundle signature sidecar
  - approval bundle signature report
  - identity signature proof report
- Copy the package into an isolated Ubuntu staging directory.
- Verify artifact hashes, canonical signature sidecar, signature report, and
  identity proof on Ubuntu.
- Return a small non-secret result manifest to Mac.
- Delete the remote staging directory and record cleanup evidence.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not materialize a real approval file.
- Do not copy private signing keys or provider credentials.
- Do not use opportunistic SSH host-key trust.
- Do not preserve remote staging after a passing run.

## Verification

```bash
python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py --json
python3 -m pytest -q tests/test_check_mac_ubuntu_signed_approval_bundle_transfer.py
```

## Acceptance Criteria

- Signed approval bundle transfer report emits schema
  `ao-operator/mac-ubuntu-signed-approval-bundle-transfer/v1`.
- `artifact_parity=true`.
- `signature_verified=true`.
- `identity_verified=true`.
- `remote_git_synced=true`.
- `remote_cleanup_absent=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- `provider_dispatch=false`.
