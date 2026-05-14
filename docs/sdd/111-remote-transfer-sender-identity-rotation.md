# Remote Transfer Sender Identity Rotation

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer receiver is fail-closed against
sender-identity-rotation hazards: a rotation announcement MUST carry
a continuity signature produced by the prior active identity and
MUST NOT be silently accepted when that signature is missing; a
rotation announcement's `effective_at` timestamp MUST be at or
before now plus the receiver's clock-skew tolerance window and MUST
NOT be silently activated when the timestamp is far in the future;
once the rotation grace window expires the receiver MUST reject any
bundle signed by the retired identity and MUST NOT silently accept
it; and the receiver MUST close the dual-acceptance window once the
grace window expires and MUST NOT continue to honor both the old
and the new identity simultaneously.

## Contract

`scripts/check_remote_transfer_sender_identity_rotation.py` emits
`ao-operator/remote-transfer-sender-identity-rotation/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process sender-identity-rotation
state machine with a fixed rotation grace window (`300` seconds), a
fixed clock-skew tolerance (`60` seconds), a fixed continuity
signature literal (`old_signature_continuity_proof`), and fixed
synthetic 64-character fingerprint placeholders for the old and new
identities of a single sender (`sender_alpha`). Each case persists
a per-case `sender-identity-rotation-transcript.json` to a
temporary work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Cases:

- `clean_post_rotation_bundle_accepted` — control: sender publishes
  a rotation announcement signed by the old identity at
  `effective_at=2026-05-08T00:00:00+00:00`, the receiver activates
  the new identity, and a bundle signed by the new identity at
  `now=2026-05-08T00:01:00+00:00` is accepted; the verifier produces
  no errors.
- `retired_identity_silently_accepted_rejected` — mutation: the
  rotation completes cleanly, then a bundle signed by the retired
  identity is submitted past the grace window and the receiver
  silently accepts; the verifier records
  `silently_accepted_retired_identity`.
- `rotation_announcement_unsigned_silently_accepted_rejected` —
  mutation: the rotation announcement carries no continuity
  signature from the old identity and the receiver silently
  activates the new identity; the verifier records
  `silently_accepted_unsigned_rotation_announcement`.
- `future_rotation_effective_at_silently_accepted_rejected` —
  mutation: the rotation announcement's `effective_at` timestamp
  is one hour in the future
  (`2026-05-08T01:00:00+00:00` vs `now=2026-05-08T00:00:00+00:00`)
  and the receiver silently activates the new identity early; the
  verifier records
  `silently_accepted_future_rotation_effective_at`.
- `dual_acceptance_window_silently_left_open_rejected` — mutation:
  the receiver caches both the old and the new identity 600
  seconds past the 300-second rotation grace window and accepts
  bundles signed by either; the verifier records
  `silently_left_dual_acceptance_window_open`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic identity fingerprints, ISO 8601 timestamps, and
  continuity-signature literals.
- Do not derive identity fingerprints, signatures, or rotation
  events from real production senders.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_sender_identity_rotation.py
python3 scripts/check_remote_transfer_sender_identity_rotation.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-sender-identity-rotation.json
```
