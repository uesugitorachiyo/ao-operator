# Approval Clock-Skew Defense Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent approval can be admitted past its
expiry, replayed, or reactivated by a wall-clock rewind, an NTP
step-back, a leap-second jump, a TZ-tagged-as-UTC mismatch, or a
stale signed freshness token. The gate is fail-closed against
the five highest-risk clock-skew hazards: an NTP rewind admit
MUST be rejected; a leap-second jump admit MUST be rejected; a
TZ-tagged-as-UTC admit MUST be rejected; an expired-but-cached
admit MUST be rejected; and a signed-token replay admit MUST be
rejected.

## Contract

`scripts/check_approval_clock_skew_defense.py` emits
`ao-operator/approval-clock-skew-defense/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process clock-skew defense
verifier with fixed synthetic placeholder identifiers
(`approval::operator_signed_alpha`,
`approval::operator_signed_beta`,
`approval::operator_allowlisted_alpha`,
`approval::ntp_rewind_alpha`,
`approval::leap_second_jump_alpha`,
`approval::tz_mismatch_alpha`,
`approval::expired_cached_alpha`,
`approval::replay_token_alpha`,
`monotonic::reference_alpha`, `tz::utc`,
`signature::operator_root_alpha`,
`token::operator_fresh_alpha`,
`token::operator_consumed_alpha`). Each case persists a per-case
`approval-clock-skew-defense-transcript.json` to a temporary
work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Approval classes: `operator_signed`, `operator_allowlisted`,
`ntp_rewind`, `leap_second_jump`, `tz_mismatch`,
`expired_cached`, `replay_token`.

Approved approval classes: `operator_signed`,
`operator_allowlisted`.

Hazard classes: `ntp_rewind_admit`, `leap_second_jump_admit`,
`tz_mismatch_admit`, `expired_cached_admit`,
`replay_token_admit`.

Cases:

- `clean_no_clock_skew_or_replay_or_stale_freshness_edges` —
  control: every registered approval edge is in an approved
  freshness class anchored to the monotonic clock with zero
  wall-clock skew, a UTC tz tag, fresh signature, and unused
  replay token; the verifier produces no errors.
- `ntp_rewind_admits_expired_approval_rejected` — mutation: an
  approval is admitted after an NTP step-back so its expiry no
  longer applies; the verifier records
  `ntp_rewind_admit_rejection`.
- `leap_second_jump_admits_expired_approval_rejected` —
  mutation: an approval is admitted across a leap-second jump
  that invalidates its monotonic basis; the verifier records
  `leap_second_jump_admit_rejection`.
- `tz_tagged_as_utc_admits_expired_approval_rejected` —
  mutation: an approval is admitted with a non-UTC instant
  whose tz tag falsely claims UTC; the verifier records
  `tz_tagged_as_utc_admit_rejection`.
- `expired_but_cached_admits_replay_rejected` — mutation: an
  approval is admitted from a cached envelope past its expiry;
  the verifier records `expired_but_cached_admit_rejection`.
- `signed_token_replay_admits_reactivation_rejected` —
  mutation: an approval is admitted by replaying a previously
  consumed signed freshness token; the verifier records
  `signed_token_replay_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not query any real clock service, NTP server, or signing
  authority — the gate is a pure in-memory clock-skew defense
  verifier with synthetic approval edges.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic approval / monotonic / tz / signature / token
  identifiers.
- Do not derive approval edges from real production approval
  envelopes, signed audit history, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_approval_clock_skew_defense.py
python3 scripts/check_approval_clock_skew_defense.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/approval-clock-skew-defense.json
```
