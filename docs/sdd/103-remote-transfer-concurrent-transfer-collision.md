# Remote Transfer Concurrent Transfer Collision

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer concurrency layer is fail-closed
against multi-writer collision hazards: two writers must not write to
the same bundle without holding the bundle lock; the same chunk must
not be overwritten by a different writer; finalize must occur at most
once per locked session; a writer whose lock has expired must not
continue to write or finalize without re-acquiring the lock.

## Contract

`scripts/check_remote_transfer_concurrent_transfer_collision.py`
emits `ao-operator/remote-transfer-concurrent-transfer-collision/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process lock / write_chunk / finalize /
release_lock / lock_expire state machine. Each case persists a
per-case `collision-transcript.json` to a temporary work directory
and records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_serialized_concurrent_transfers_passes` — control: writer A
  acquires the lock, writes/finalizes/releases; writer B then
  acquires the same bundle lock and serially performs its own
  write/finalize/release; no overwrites, no double finalize.
- `parallel_transfers_no_lock_corrupts_state_rejected` — mutation:
  both writers skip lock acquisition; the verifier records
  `write_without_lock` and `finalize_without_lock`.
- `simultaneous_finalize_double_completes_bundle_rejected` —
  mutation: writer A finalizes under the lock, writer B finalizes
  the same bundle without holding the lock; the verifier records
  `finalize_without_lock`.
- `lost_writer_overwrites_winner_bundle_rejected` — mutation: writer
  B writes the same chunk_index without holding the lock; the
  verifier records `write_without_lock` (and protects against
  `chunk_overwrite_by_other_writer`).
- `stale_lock_holder_resumes_after_handoff_rejected` — mutation:
  writer A's lock expires, writer B takes over, writer A returns and
  writes; the verifier records `stale_lock_holder_write`.

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
python3 -m pytest -q tests/test_check_remote_transfer_concurrent_transfer_collision.py
python3 scripts/check_remote_transfer_concurrent_transfer_collision.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-concurrent-transfer-collision.json
```
