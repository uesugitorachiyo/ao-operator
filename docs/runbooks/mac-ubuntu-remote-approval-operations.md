# Mac Ubuntu Remote Approval Operations Runbook

This runbook coordinates the no-provider Mac-to-Ubuntu approval evidence flow.
It does not authorize Agent OS execution, AO dispatch, or provider CLI use.

## Preconditions

- Confirm Mac and Ubuntu are on the same `origin/main` commit.
- Set `FACTORY_V3_REMOTE_HOST` to the Ubuntu host before running remote checks.
- Confirm `python3 scripts/pr_ready.py --ci --json`
  reports `verdict=PASS`.
- Confirm the real approval file is absent before and after this sequence.

## Command Sequence

```bash
export FACTORY_V3_REMOTE_HOST="${FACTORY_V3_REMOTE_HOST}"

python3 scripts/pr_ready.py --ci --json

python3 scripts/check_mac_ubuntu_approval_artifact_parity.py \
  --remote-host "$FACTORY_V3_REMOTE_HOST" \
  --write-output \
  --json

python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py \
  --remote-host "$FACTORY_V3_REMOTE_HOST" \
  --write-output \
  --json

python3 scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py \
  --remote-host "$FACTORY_V3_REMOTE_HOST" \
  --write-output \
  --json

python3 scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py \
  --remote-host "$FACTORY_V3_REMOTE_HOST" \
  --write-output \
  --json

python3 scripts/check_operator_guardrail_summary.py --write-output --json
python3 scripts/check_status_json_integrity.py --json
python3 scripts/redact_strict_public_artifacts.py --fail-on-changes --json
```

## Expected Evidence

- `remote_git_synced=true`
- `remote_cleanup_absent=true`
- `signed_bundle_verified=true`
- `signature_verified=true`
- `identity_verified=true`
- `materialization_dry_run_passed=true`
- `fixture_approval_written=true`
- `revocation_applied=true`
- `rollback_restore_verified=true`
- `provider_dispatch=false`
- `dispatch_authorized=false`
- `live_providers_run=false`

## Negative Constraints

- Do not run AO from this runbook.
- Do not dispatch provider CLIs from this runbook.
- Do not write a real repo approval file from this runbook.
- Do not copy private signing keys or provider credentials.
- Do not preserve remote staging.
- Do not treat fixture approval evidence as real execution approval.
- Commit only PASS evidence.

## Evidence Paths

- `run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-approval-artifact-parity.json`
- `run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-signed-approval-bundle-transfer.json`
- `run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-remote-approval-materialization-dry-run.json`
- `run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-remote-approval-revocation-rollback.json`
- `run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json`
