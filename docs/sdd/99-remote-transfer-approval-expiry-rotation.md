# 99 - Remote Transfer Approval Expiry & Rotation

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Mac-to-Ubuntu remote transfer hardening

## Objective

Lock the AO Runtime ``signed_remote_approval_transfer`` lifecycle
contract behind a fail-closed local gate. SDD 97 proved the
chunk-cleanup contract is fail-closed; SDD 98 proved the integrity
layer above it is fail-closed. This SDD proves the approval lifecycle
layer above the integrity layer is also fail-closed. The four
lifecycle violations covered here (expired approval timestamp,
approval used after rotation cutover plus grace, signing key rotated
mid-flight without grace, approval reused beyond TTL) reproduce live
lifecycle-failure scenarios as a portable Python state machine so
future Mac-to-Ubuntu hardening cannot regress the approval-lifecycle
contract without tripping a deterministic gate.

This SDD is distinct from SDD 61's
``check_agent_os_approval_lifecycle.py``: that gate observes a single
live approval file's expiry at runtime decision time. This gate is a
mutation gate that synthesizes 5 cases and proves 4 deliberate
lifecycle violations are rejected fail-closed.

## Scope

`scripts/check_remote_transfer_approval_expiry_rotation.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-approval-expiry-rotation.json`

The gate exercises five deterministic cases inside a temporary work
directory (no repo pollution):

- `clean_approval_passes`
- `expired_approval_rejected`
- `approval_used_after_rotation_cutover_rejected`
- `signing_key_rotated_midflight_without_grace_rejected`
- `approval_reused_beyond_ttl_rejected`

Each case lays down a per-case approval payload with fields
``approval_id``, ``issued_at`` (ISO 8601 UTC), ``expires_at`` (ISO
8601 UTC), ``max_uses`` (int), ``nonce`` (str), HMAC-signs the
canonical approval JSON with a registered key id (``kid:hex_hmac``),
then runs the embedded verifier against a fixed reference clock
``NOW = 2026-05-08T12:00:00+00:00`` and an in-memory
``use_counts`` ledger. The verifier enforces five distilled lifecycle
invariants:

1. ``now < expires_at`` (expiry invariant).
2. The signature key id MUST be in the registered key registry and
   the HMAC of the canonical approval under that key MUST match the
   signature bytes (signing-identity invariant).
3. The signing kid MUST have been active at ``issued_at`` (no
   retroactive issuance with a key not yet valid).
4. The signing kid MUST still be active at ``now``, with rotation
   grace applied (rotation-cutover-with-grace invariant).
5. The number of presentations of an approval MUST NOT exceed its
   declared ``max_uses`` (TTL/use-counter invariant).

## Required Behavior

- `case_count` MUST be `5`.
- `mutation_case_count` MUST be `4`.
- `clean_approval_passes` MUST observe `PASS`; the four mutation
  cases MUST observe `FAIL`.
- Every case payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- `observed_errors` for each FAIL case MUST contain the corresponding
  invariant tag prefix (`approval_expired:`,
  `kid_inactive_at_use_time:`, `kid_inactive_at_use_time:`,
  `approval_reused_beyond_ttl:`).
- The gate MUST run with no provider dispatch, no AO invocation, no
  network access.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use
  tempfile).
- MUST NOT mutate AO Runtime source; the gate is observational and
  synthesizes its own lifecycle model.
- MUST NOT use real signing keys or real approval payloads; HMAC
  secrets in the synthetic key registry are test values only.
- MUST NOT key off wall-clock `datetime.now()` for verification:
  the verifier accepts an explicit ``now=`` argument so cases stay
  reproducible across hosts and dates.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_approval_expiry_rotation.py
python3 scripts/check_remote_transfer_approval_expiry_rotation.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=5`, `mutation_case_count=4`.
- `clean_approval_passes` observes `PASS`; the four mutation cases
  each observe `FAIL` with a matching invariant tag prefix.
- `dispatch_authorized=false` and `live_providers_run=false` on the
  top-level payload and on every per-case payload.
- No `.cache/` or repo-root scratch directory remains after running
  the gate.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-approval-expiry-rotation.json
```
