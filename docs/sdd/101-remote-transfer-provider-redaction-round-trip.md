# 101 - Remote Transfer Provider Redaction Round-Trip

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Mac-to-Ubuntu remote transfer hardening

## Objective

Lock the AO Runtime ``provider_redaction_round_trip`` data-safety
contract behind a fail-closed local gate. SDD 97 proved the
chunk-cleanup contract is fail-closed; SDD 98 proved the integrity
layer above it is fail-closed; SDD 99 proved the approval lifecycle
layer above integrity is fail-closed; SDD 100 proved the streaming
and resume layer beneath integrity is fail-closed. This SDD proves
the provider-data-safety layer that rides *inside* the bundle is also
fail-closed. The four redaction-layer violations covered here
(redaction marker stripped before transmit, sensitive field leaks
past the redaction filter, double-redaction corrupts the payload,
provider response leaks the redacted plaintext value back) reproduce
live data-leak scenarios as a portable Python state machine so future
Mac-to-Ubuntu hardening cannot regress the redaction contract without
tripping a deterministic gate.

This SDD is distinct from
``redact_strict_public_artifacts.py`` (repo-tree static redaction)
and from SDD 100's
``check_remote_transfer_bundle_ordering_resume.py`` (streaming-layer
ordering): this gate is a mutation gate over the request → redact →
transmit → provider → response → verify pipeline, focused on
sensitive-value confidentiality across the round-trip.

## Scope

`scripts/check_remote_transfer_provider_redaction_round_trip.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-provider-redaction-round-trip.json`

The gate exercises five deterministic cases inside a temporary work
directory (no repo pollution):

- `clean_round_trip_passes`
- `redaction_marker_stripped_before_transmit_rejected`
- `sensitive_field_leaks_past_redaction_filter_rejected`
- `double_redaction_corrupts_payload_rejected`
- `provider_response_leaks_redacted_value_back_rejected`

Each case lays down a per-case ``round-trip-transcript.json``
capturing the request, the transmitted (redacted) form, and the
synthetic provider response. The verifier embedded in the gate
enforces five distilled redaction invariants:

1. Every value of a registered sensitive field MUST be replaced with
   a redaction marker before transmit (pre-transmit invariant).
2. The redaction marker MUST match the canonical pattern
   ``[REDACTED:<token>]`` (marker-shape invariant).
3. The transmitted payload, serialized to JSON, MUST NOT contain any
   plaintext sensitive value anywhere (redaction-coverage
   invariant).
4. Re-running the redactor over an already-redacted payload MUST
   leave it unchanged (deterministic-redaction invariant).
5. The provider response, serialized to JSON, MUST NOT contain any
   plaintext sensitive value (response-leak invariant).

## Required Behavior

- `case_count` MUST be `5`.
- `mutation_case_count` MUST be `4`.
- `clean_round_trip_passes` MUST observe `PASS`; the four mutation
  cases MUST observe `FAIL`.
- Every case payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- `observed_errors` for each FAIL case MUST contain the corresponding
  invariant tag prefix (``plaintext_sensitive_value_in_transmit:`` /
  ``redaction_marker_missing_or_malformed:`` for the marker-strip and
  filter-leak cases, ``double_redaction_not_idempotent:`` for the
  corruption case, and ``plaintext_sensitive_value_in_response:`` for
  the response-leak case).
- The gate MUST run with no provider dispatch, no AO invocation, no
  network access.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use
  tempfile).
- MUST NOT mutate AO Runtime source; the gate is observational and
  synthesizes its own redaction model.
- MUST NOT use real api keys, real customer emails, or any real
  sensitive data; all sensitive-field values are synthetic test
  values only.
- MUST NOT couple to wall-clock time; the verifier is purely
  payload-driven and reproducible across hosts.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_provider_redaction_round_trip.py
python3 scripts/check_remote_transfer_provider_redaction_round_trip.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=5`, `mutation_case_count=4`.
- `clean_round_trip_passes` observes `PASS`; the four mutation cases
  each observe `FAIL` with a matching invariant tag prefix.
- `dispatch_authorized=false` and `live_providers_run=false` on the
  top-level payload and on every per-case payload.
- No `.cache/` or repo-root scratch directory remains after running
  the gate.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-provider-redaction-round-trip.json
```
