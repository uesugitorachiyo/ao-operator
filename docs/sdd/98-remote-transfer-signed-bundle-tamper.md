# 98 - Remote Transfer Signed Bundle Tamper

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Mac-to-Ubuntu remote transfer hardening

## Objective

Lock the AO Runtime ``signed_bundle_transfer`` integrity contract
behind a fail-closed local gate. SDD 97 proved the chunk-cleanup
contract is fail-closed; this SDD proves the integrity layer above it
is also fail-closed. The five tamper modes covered here (truncated
bundle, swapped chunk, wrong signing key, replayed bundle, manifest
digest mismatch) reproduce live integrity-failure scenarios as a
portable Python state machine so future Mac-to-Ubuntu hardening cannot
regress the bundle-verification contract without tripping a
deterministic gate.

## Scope

`scripts/check_remote_transfer_signed_bundle_tamper.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-signed-bundle-tamper.json`

The gate exercises six deterministic cases inside a temporary work
directory (no repo pollution):

- `clean_signed_bundle_passes`
- `truncated_bundle_rejected`
- `swapped_chunk_rejected`
- `wrong_signing_key_rejected`
- `replayed_bundle_rejected`
- `manifest_digest_mismatch_rejected`

Each case lays down a per-case bundle dir with `chunk-NNNN.bin`
payloads, builds a manifest in memory (``approval_id``, ``nonce``,
``chunks=[{index, size, sha256}]``), HMAC-signs the canonical manifest
JSON with a registered key id, then runs the embedded verifier
against an in-memory `seen_nonces` replay window. The verifier
enforces five distilled invariants:

1. Each chunk's actual byte length MUST equal its manifest-declared
   size (truncation invariant).
2. Each chunk's actual sha256 MUST equal its manifest-declared digest
   (per-chunk integrity invariant — also catches swaps).
3. The signature key id MUST be in `REGISTERED_KEYS` and the HMAC of
   the canonical manifest under that key MUST match the signature
   bytes (signing-identity invariant).
4. The bundle nonce MUST be a non-empty string AND MUST NOT appear in
   the seen-nonces replay window (replay invariant).
5. The signature payload MUST be of the form ``kid:hex`` and parse
   cleanly (well-formedness invariant).

## Required Behavior

- `case_count` MUST be `6`.
- `mutation_case_count` MUST be `5`.
- `clean_signed_bundle_passes` MUST observe `PASS`; the five mutation
  cases MUST observe `FAIL`.
- Every case payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- `observed_errors` for each FAIL case MUST contain the corresponding
  invariant tag prefix (`truncated_or_oversize_chunk:`,
  `chunk_digest_mismatch:`, `unregistered_signing_key:`,
  `nonce_replayed:`, `chunk_digest_mismatch:`).
- The gate MUST run with no provider dispatch, no AO invocation, no
  network access.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use
  tempfile).
- MUST NOT mutate AO Runtime source; the gate is observational and
  synthesizes its own invariant model.
- MUST NOT use real signing keys or real approval bundles; HMAC
  secrets in `REGISTERED_KEYS` are synthetic test values only.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_signed_bundle_tamper.py
python3 scripts/check_remote_transfer_signed_bundle_tamper.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=6`, `mutation_case_count=5`.
- `clean_signed_bundle_passes` observes `PASS`; the five mutation
  cases each observe `FAIL` with a matching invariant tag prefix.
- `dispatch_authorized=false` and `live_providers_run=false` on the
  top-level payload and on every per-case payload.
- No `.cache/` or repo-root scratch directory remains after running
  the gate.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-signed-bundle-tamper.json
```
