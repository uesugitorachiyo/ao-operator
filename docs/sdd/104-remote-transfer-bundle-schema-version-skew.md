# Remote Transfer Bundle Schema Version Skew

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
schema-version skew between sender and receiver: a bundle whose
`schema_version` falls below the receiver's minimum supported version
must be rejected; a forward-version bundle above the receiver's
maximum supported version must not be silently downgraded onto an
older schema; a bundle that advertises an extension the receiver does
not know must be rejected when strict extensions are required; and a
bundle missing the `schema_version` field altogether must be rejected
rather than have a default version silently inferred.

## Contract

`scripts/check_remote_transfer_bundle_schema_version_skew.py`
emits `ao-operator/remote-transfer-bundle-schema-version-skew/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process emit / receiver_validate state
machine. Each case persists a per-case
`schema-skew-transcript.json` to a temporary work directory and
records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_matched_schema_version_passes` — control: sender emits a
  bundle at `3.0.0` advertising only `chunk_compression_v1`; the
  receiver supports `[2.0.0..3.0.0]` and `chunk_compression_v1` is in
  the known-extension set; `receiver_validate_and_accept` records no
  errors and the bundle is accepted at the emitted version.
- `receiver_below_min_version_rejected` — mutation: sender ships a
  `1.0.0` down-rev bundle while the receiver only supports
  `[2.0.0..3.0.0]`; the receiver accepts anyway; the verifier records
  `force_accepted_below_min`.
- `receiver_above_max_silently_downgrades_rejected` — mutation:
  sender ships a `4.0.0` forward bundle while the receiver only
  supports up to `3.0.0`; the receiver silently re-interprets the
  bundle as `3.0.0` instead of refusing; the verifier records
  `silent_downgrade`.
- `bundle_advertises_unknown_extension_field_rejected` — mutation:
  sender ships a `3.0.0` bundle advertising
  `experimental.encryption_v2`, which is not in the receiver's
  known-extension set; the receiver accepts; the verifier records
  `force_accepted_unknown_extension`.
- `schema_version_field_missing_rejected` — mutation: sender ships a
  bundle with no `schema_version` field; the receiver assumes a
  default version and accepts; the verifier records
  `force_accepted_missing_version`.

Overall verdict is PASS only when every observed verdict matches the
expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic.
- Do not use real bundle payloads — semvers and extension names are
  synthetic test values only.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_bundle_schema_version_skew.py
python3 scripts/check_remote_transfer_bundle_schema_version_skew.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-schema-version-skew.json
```
