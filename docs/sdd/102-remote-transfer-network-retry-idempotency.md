# Remote Transfer Network Retry Idempotency

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer resilience layer is fail-closed against
network-retry hazards: a retried chunk must reuse its original nonce so
the receiver can dedupe, the receiver must commit each nonce exactly
once, partial flushes on network drops must not pass `finalize`, and a
nonce that the sender has already timed out must never be committed
late by a slow receiver.

## Contract

`scripts/check_remote_transfer_network_retry_idempotency.py` emits
`ao-operator/remote-transfer-network-retry-idempotency/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process send / receive_commit / ack /
timeout / finalize state machine. Each case persists a per-case
`retry-transcript.json` to a temporary work directory and records
`observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_retry_round_trip_passes` — control: chunk 0 retried with the
  same nonce, well-behaved receiver dedupes (replays cached ack rather
  than re-committing); chunk 1 acked normally; finalize sees no
  in-flight nonces.
- `retry_without_nonce_dedup_rejected` — mutation: retry mints a new
  nonce for an already-sent chunk; the sender records
  `retry_minted_new_nonce`.
- `partial_flush_on_network_drop_rejected` — mutation: a chunk is sent
  but never committed/acked before finalize; the sender records
  `finalize_with_in_flight_nonces` and `finalize_without_commit`.
- `ack_lost_causes_double_commit_rejected` — mutation: ack lost; the
  receiver re-commits the same nonce on retry, violating commit-once;
  the receiver records `double_commit_for_nonce`.
- `timeout_shorter_than_response_causes_orphan_rejected` — mutation:
  the sender times out a nonce and the slow receiver later commits it;
  the receiver records `orphan_commit_after_timeout`.

Overall verdict is PASS only when every observed verdict matches the
expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_network_retry_idempotency.py
python3 scripts/check_remote_transfer_network_retry_idempotency.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-network-retry-idempotency.json
```
