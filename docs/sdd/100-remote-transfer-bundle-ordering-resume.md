# 100 - Remote Transfer Bundle Ordering & Resume

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Mac-to-Ubuntu remote transfer hardening

## Objective

Lock the AO Runtime ``signed_remote_approval_transfer`` streaming and
resume contract behind a fail-closed local gate. SDD 97 proved the
chunk-cleanup contract is fail-closed; SDD 98 proved the integrity
layer above it is fail-closed; SDD 99 proved the approval lifecycle
layer above integrity is fail-closed. This SDD proves the streaming
and resume layer beneath integrity is also fail-closed. The four
streaming-layer violations covered here (chunk delivered out of
order, partial resume drops a middle chunk, resume cursor lies
about its high-water mark, duplicate chunk delivery) reproduce live
streaming-failure scenarios as a portable Python state machine so
future Mac-to-Ubuntu hardening cannot regress the bundle-ordering
contract without tripping a deterministic gate.

This SDD is distinct from SDD 98's
``check_remote_transfer_signed_bundle_tamper.py``: that gate proves
the integrity-layer signing/HMAC contract over a finalized bundle.
This gate is a mutation gate over the streaming/resume state
machine *underneath* integrity: it proves the deliver/resume/finalize
ordering contract rejects four deliberate streaming violations.

## Scope

`scripts/check_remote_transfer_bundle_ordering_resume.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-ordering-resume.json`

The gate exercises five deterministic cases inside a temporary work
directory (no repo pollution):

- `clean_ordered_delivery_passes`
- `out_of_order_chunk_rejected`
- `partial_resume_drops_middle_chunk_rejected`
- `resume_cursor_lies_about_high_water_rejected`
- `duplicate_chunk_delivery_rejected`

Each case lays down a per-case ``delivery-transcript.json`` capturing
the ordered list of streaming operations (``deliver(index, payload)``,
``resume(claimed_cursor)``, ``finalize()``), then drives the embedded
``_DeliveryVerifier`` state machine through that transcript. The
verifier enforces five distilled streaming invariants:

1. Each ``deliver`` MUST advance the chunk cursor by exactly one and
   MUST NOT skip an index (cursor strict-ascending invariant).
2. The same chunk index MUST NOT be delivered twice (no-duplicate
   invariant; surfaced as ``out_of_order_chunk`` once the cursor has
   already advanced past it).
3. A ``resume`` MUST NOT claim a cursor higher than the
   already-confirmed high-water mark (``resume_cursor_exceeds_confirmed_high_water``
   invariant).
4. ``finalize`` MUST be called only when the cursor equals
   ``total_chunks`` (no early finalize invariant).
5. Every chunk index in ``[0, total_chunks)`` MUST have been delivered
   before ``finalize`` (no-missing-chunk invariant).

## Required Behavior

- `case_count` MUST be `5`.
- `mutation_case_count` MUST be `4`.
- `clean_ordered_delivery_passes` MUST observe `PASS`; the four
  mutation cases MUST observe `FAIL`.
- Every case payload MUST report `dispatch_authorized=false` and
  `live_providers_run=false`.
- `observed_errors` for each FAIL case MUST contain the corresponding
  invariant tag prefix (``out_of_order_chunk:``,
  ``missing_chunk_at_finalize:`` /
  ``finalize_before_all_chunks_delivered:`` /
  ``out_of_order_chunk:``,
  ``resume_cursor_exceeds_confirmed_high_water:``,
  ``out_of_order_chunk:``).
- The gate MUST run with no provider dispatch, no AO invocation, no
  network access.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT write fixture artifacts under the repo root (use
  tempfile).
- MUST NOT mutate AO Runtime source; the gate is observational and
  synthesizes its own streaming model.
- MUST NOT use real provider chunk payloads; the verifier consumes
  synthetic per-case ``payload`` strings only.
- MUST NOT couple to wall-clock time; the verifier is purely
  ordering-driven and reproducible across hosts.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_bundle_ordering_resume.py
python3 scripts/check_remote_transfer_bundle_ordering_resume.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=5`, `mutation_case_count=4`.
- `clean_ordered_delivery_passes` observes `PASS`; the four mutation
  cases each observe `FAIL` with a matching invariant tag prefix.
- `dispatch_authorized=false` and `live_providers_run=false` on the
  top-level payload and on every per-case payload.
- No `.cache/` or repo-root scratch directory remains after running
  the gate.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-ordering-resume.json
```
