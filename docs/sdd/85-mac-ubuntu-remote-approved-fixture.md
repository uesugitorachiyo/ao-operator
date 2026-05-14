# SDD 85: Mac Ubuntu Remote Approved Fixture

## Goal

Prove Ubuntu can receive the signed Agent OS approval bundle, materialize an
approved fixture inside isolated staging, validate that approval, and stop at
launcher `PLAN` without AO execution or provider dispatch.

## Scope

- Transfer the signed approval bundle package to Ubuntu.
- Verify artifact hashes, canonical signature sidecar, signature report, and
  identity proof.
- Create a staging-only fixture with copied RunSpec, approval gate, and
  approval bundle.
- Materialize a fixture approval with `--write-approval-file` only inside the
  staging fixture.
- Validate the fixture approval.
- Run the approval launcher without live execution and require `verdict=PLAN`.
- Delete remote staging and prove it is absent.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not pass live execution flags to the launcher.
- Do not write a real repo approval file.
- Do not copy private signing keys or provider credentials.
- Do not preserve remote staging.

## Verification

```bash
python3 -m pytest -q tests/test_check_mac_ubuntu_remote_approved_fixture.py
python3 scripts/check_mac_ubuntu_remote_approved_fixture.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_remote_approved_fixture.py --json
```

## Acceptance Criteria

- Report emits schema `ao-operator/mac-ubuntu-remote-approved-fixture/v1`.
- `remote_git_synced=true`.
- `signed_bundle_verified=true`.
- `signature_verified=true`.
- `identity_verified=true`.
- `fixture_approval_written=true`.
- `approval_valid=true`.
- `launcher_plan_verified=true`.
- `would_run_provider=false`.
- `approval_file_present_after=true` inside the fixture only.
- `remote_cleanup_absent=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- `provider_dispatch=false`.
