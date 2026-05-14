# Remote Transfer Resource Exhaustion Guard

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
resource-exhaustion abuse: a sender that announces a chunk count
above the receiver's per-bundle quota must be rejected before any
chunk is consumed; a sender that announces an aggregate byte total
above the receiver's per-bundle byte quota must be rejected; an
individual chunk whose payload exceeds the receiver's per-chunk
byte ceiling must be rejected even when the announcement was
within quota; and a sender that ships more chunks than it
announced must have the surplus rejected rather than silently
appended.

## Contract

`scripts/check_remote_transfer_resource_exhaustion_guard.py`
emits `ao-operator/remote-transfer-resource-exhaustion-guard/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process announce / chunk-validate
state machine. Each case persists a per-case
`quota-transcript.json` to a temporary work directory and records
`observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_within_quota_passes` — control: sender announces 100
  chunks of 1024 bytes (well within the receiver's quotas of 1000
  chunks / 10 MiB total / 1 MiB per chunk); chunks stream within
  bounds and `receiver_validate_chunk` records no errors.
- `announced_chunk_count_exceeds_quota_rejected` — mutation:
  sender announces 5000 chunks while the receiver caps at 1000;
  the receiver force-accepts the announcement; the verifier
  records `force_accepted_chunk_count_over_quota`.
- `announced_total_size_exceeds_quota_rejected` — mutation:
  sender announces 100_000_000 total bytes while the receiver
  caps at 10_485_760; the receiver force-accepts; the verifier
  records `force_accepted_total_bytes_over_quota`.
- `per_chunk_size_exceeds_max_rejected` — mutation: chunk 0
  carries 4_194_304 bytes while the receiver caps per-chunk at
  1_048_576; the receiver force-accepts the oversize chunk; the
  verifier records `force_accepted_oversize_chunk`.
- `transfer_exceeds_announced_count_rejected` — mutation: sender
  announces 3 chunks, ships chunks 0/1/2 normally then a surplus
  chunk 3; the receiver force-accepts the overrun; the verifier
  records `force_accepted_overrun_chunk`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic.
- Do not allocate real oversize buffers — sizes are recorded as
  integers; chunk payload bodies are short synthetic fixtures.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_resource_exhaustion_guard.py
python3 scripts/check_remote_transfer_resource_exhaustion_guard.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-resource-exhaustion-guard.json
```
