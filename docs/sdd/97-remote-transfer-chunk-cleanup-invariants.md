# 97 - Remote Transfer Chunk Cleanup Invariants

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Mac-to-Ubuntu remote transfer hardening

## Objective

Lock the AO Runtime ``chunked_upload`` cleanup contract behind a
fail-closed local gate. The Phase 2b/3 evidence
``chunked-upload-validation-20260506T233808Z.md`` proves the live AO
Runtime cleans staging on commit, on chunk-hash mismatch, and on
total-hash mismatch — but the cleanup invariants live only in
Rust-side tests. This SDD reproduces those invariants as a portable
Python state machine and proves each is rejected when violated, so
future Mac-to-Ubuntu hardening cannot regress the cleanup contract
without tripping a deterministic gate.

## Scope

`scripts/check_remote_transfer_chunk_cleanup_invariants.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-chunk-cleanup-invariants.json`

The gate exercises six deterministic cases inside a temporary work
directory (no repo pollution):

- `clean_upload_commit_passes`
- `orphaned_chunk_after_abort_detected`
- `missing_finalize_detected`
- `stale_partial_stage_dir_detected`
- `double_commit_rejected`
- `retry_index_drift_detected`

Each case lays down on-disk staging state under the work dir,
populates an in-memory session record (``upload_id``, ``aborted``,
``finalize_count``, ``chunks_uploaded``, ``last_failed_chunk_index``,
``expected_failed_chunk_index``), and runs the embedded validator.
The validator enforces five distilled invariants:

1. After abort, no chunk file may remain on disk.
2. Successful chunk uploads must be followed by exactly one
   ``CommitWorkspaceUpload`` finalize call.
3. ``finalize_count > 1`` (double commit) is refused.
4. No ``partial-stage-*.marker`` from a prior upload may persist into
   a new upload's stage dir.
5. The retry chunk index reported on failure MUST match the actual
   failed chunk index (no drift).

After a successful finalize the stage dir must be empty; lingering
files imply incomplete cleanup and trip the validator.

## Required Behavior

- `case_count` MUST be `6`.
- `mutation_case_count` MUST be `5`.
- `clean_upload_commit_passes` MUST observe `PASS`; the five mutation
  cases MUST observe `FAIL`.
- Every case payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- `observed_errors` for each FAIL case MUST contain the corresponding
  invariant tag (`orphaned_chunks_after_abort:`,
  `missing_finalize_after_successful_chunks`,
  `stale_partial_stage_dir:`, `double_commit:`,
  `retry_index_drift:`).
- The gate MUST run with no provider dispatch, no AO invocation, no
  network access.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use
  tempfile).
- MUST NOT mutate AO Runtime source; the gate is observational and
  synthesizes its own invariant model.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_chunk_cleanup_invariants.py
python3 scripts/check_remote_transfer_chunk_cleanup_invariants.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=6`, `mutation_case_count=5`.
- `clean_upload_commit_passes` observes `PASS`; the five mutation
  cases each observe `FAIL` with a matching invariant tag.
- `dispatch_authorized=false` and `live_providers_run=false` on the
  top-level payload and on every per-case payload.
- No `.cache/` or repo-root scratch directory remains after running
  the gate.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-chunk-cleanup-invariants.json
```
