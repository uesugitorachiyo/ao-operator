# Remote Transfer Bundle Id Uniqueness

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
`bundle_id` collisions: a `bundle_id` already present in the
receiver's in-flight or completion ledger MUST NOT be accepted a
second time within the same session; two distinct senders MUST NOT
be allowed to silently merge into a single ledger entry under a
colliding `bundle_id`; a receiver MUST compare the full `bundle_id`
and MUST NOT collapse two distinct ids that share a truncated
prefix; and a `bundle_id` whose run has already completed MUST NOT
be replayable after the in-flight tracking is cleared, i.e. the
completion ledger must be durable.

## Contract

`scripts/check_remote_transfer_bundle_id_uniqueness.py`
emits `ao-operator/remote-transfer-bundle-id-uniqueness/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process bundle-id ledger state machine
with two ledgers (`in_flight`, `completed`) keyed on the full
`bundle_id` and a configurable `prefix_index_chars` (default 16) for
the truncation collapse mutation. Each case persists a per-case
`bundle-id-ledger-transcript.json` to a temporary work directory and
records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_unique_bundle_ids_pass` — control: a single sender submits
  three bundles whose `bundle_id` values differ in their distinct
  suffixes; the receiver records each into `in_flight` then promotes
  to `completed`; `receiver_record_unique` and `receiver_complete`
  produce no errors.
- `duplicate_bundle_id_within_session_rejected` — mutation: a sender
  re-announces a `bundle_id` that is already in `in_flight` with a
  different `content_digest`; the receiver force-accepts; the
  verifier records `force_accepted_duplicate_bundle_id`.
- `cross_sender_bundle_id_collision_rejected` — mutation: two
  distinct senders submit bundles whose `bundle_id` values collide
  while their `content_digest` values differ; the receiver collapses
  them into a single ledger entry; the verifier records
  `silently_collapsed_cross_sender_bundle_id`.
- `bundle_id_truncation_collision_rejected` — mutation: the receiver
  indexes by the first 16 hex characters of `bundle_id` and treats
  two distinct full ids that share that prefix as the same bundle;
  the verifier records `truncated_prefix_collision_collapsed`.
- `bundle_id_replayed_after_completion_rejected` — mutation: a
  sender replays a `bundle_id` that has already been promoted to
  `completed` after the receiver has cleared its `in_flight`
  ledger; the receiver force-accepts as if the id were fresh; the
  verifier records `force_accepted_completed_replay`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic `bundle_id` literals.
- Do not derive `bundle_id` values from real production traffic; the
  gate uses synthetic 64-hex-character literals only.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_bundle_id_uniqueness.py
python3 scripts/check_remote_transfer_bundle_id_uniqueness.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-id-uniqueness.json
```
