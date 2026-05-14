# Remote Transfer Clock Skew Tolerance

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
clock-skew abuse between sender and receiver: a bundle whose
`not_before` is more than `max_skew_seconds` after the receiver's
clock must be rejected; a bundle whose `not_after` is more than
`max_skew_seconds` before the receiver's clock must be rejected; a
sender that deliberately stamps a `not_before` far in the receiver's
future must not have that timestamp silently clamped to the
receiver's own clock and treated as currently valid; and the
validity window must not be silently extended by adding the
receiver's `max_skew_seconds` tolerance to `not_after`.

## Contract

`scripts/check_remote_transfer_clock_skew_tolerance.py`
emits `ao-operator/remote-transfer-clock-skew-tolerance/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process timestamp validation state
machine with synthetic anchor `receiver_now=2026-01-15T12:00:00Z`
and `max_skew_seconds=60`. Each case persists a per-case
`clock-skew-transcript.json` to a temporary work directory and
records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_within_skew_tolerance_passes` — control: sender stamps
  `not_before` 30 seconds before `receiver_now` and `not_after`
  300 seconds after; the receiver opens the window after applying
  skew tolerance; `receiver_validate_window` records no errors.
- `sender_clock_ahead_of_receiver_rejected` — mutation: sender
  clock runs 600 seconds ahead of the receiver; sender stamps
  `not_before` 600 s past `receiver_now` (skew tolerance is 60 s);
  the receiver force-accepts; the verifier records
  `force_accepted_not_before_beyond_skew`.
- `sender_clock_behind_receiver_rejected` — mutation: sender clock
  runs 600 seconds behind the receiver; sender stamps `not_after`
  600 s before `receiver_now`; the receiver force-accepts; the
  verifier records `force_accepted_not_after_beyond_skew`.
- `future_dated_bundle_accepted_as_currently_valid_rejected` —
  mutation: sender stamps `not_before` 24 hours in the receiver's
  future; the receiver silently clamps `not_before` to its own
  clock and treats the bundle as currently valid; the verifier
  records `silently_clamped_future_not_before`.
- `ttl_window_straddling_skew_silently_extended_rejected` —
  mutation: sender stamps a 30-second TTL window with `not_after`
  15 seconds before `receiver_now`; the receiver silently extends
  the window by `max_skew_seconds=60` so the bundle is accepted as
  still-valid; the verifier records
  `silently_extended_ttl_by_skew`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with a
  fixed `receiver_now` anchor.
- Do not use `datetime.now()` to derive case timestamps; the gate
  uses a synthetic anchor so that future test runs do not drift
  behavior.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_clock_skew_tolerance.py
python3 scripts/check_remote_transfer_clock_skew_tolerance.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-clock-skew-tolerance.json
```
