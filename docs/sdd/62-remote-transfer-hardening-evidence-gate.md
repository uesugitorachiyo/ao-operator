# 62 - Remote Transfer Hardening Evidence Gate

Classification: MODERATE
Shape: refactor

## Scope

This slice adds a Factory-side evidence gate for Remote Transfer v2 hardening.
It verifies that the current public release evidence includes signed-manifest
verification, chunked upload cleanup, large Mac-to-Ubuntu transfer smoke, and
signed worker-runtime smoke coverage. The gate is read-only and does not run AO
or providers.

## Contract

The checker lives at `scripts/check_remote_transfer_hardening.py`.

It reads AO Runtime evidence from the configured AO Runtime checkout:

- `progress/slice-reports/remote_transfer_v2_phase3_signed_manifest_verification.md`
- `progress/slice-reports/remote_transfer_v2_phase2b_grpc_chunked_upload.md`
- `docs/remote-worker-workspace-transfer-spec.md`

It reads AO Operator evidence:

- `run-artifacts/remote-transfer-v2-stress-live/chunked-upload-validation-20260506T233808Z.md`
- `run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-remote-smoke-large-64m-20260506T233645Z.json`
- `run-artifacts/remote-transfer-v2-stress-live/remote-codex-worker-runtime-smoke-20260507T004907Z.md`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-hardening.json`

## Negative Constraints

- MUST NOT dispatch AO providers.
- MUST NOT start remote services.
- MUST NOT treat unsigned compatibility as sufficient for signed-manifest
  hardening.
- MUST NOT ignore chunk cleanup on failed or partial uploads.
- MUST NOT expose machine-local paths in committed evidence.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_hardening.py
python3 scripts/check_remote_transfer_hardening.py --write-output --json
```

## Acceptance Criteria

- Manifest signing evidence is present and includes Ed25519, canonical signing
  payloads, required-signature rejection, and key-file env handling.
- Chunked upload evidence is present and includes begin/chunk/commit,
  failed-chunk retry index, and partial staging cleanup.
- Large transfer smoke evidence is PASS, provider-free, and records cleanup.
- Signed worker-runtime smoke evidence is PASS and records signed bundle
  verification.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
