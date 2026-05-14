# Remote Transfer Per-Tenant Quota Isolation

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
cross-tenant quota leakage: a chunk debit MUST be charged against
the bundle's own tenant bucket and MUST NOT be misrouted to another
tenant's bucket; per-tenant quotas MUST stay strictly partitioned and
MUST NOT be merged into a single shared bucket; a bundle that arrives
without a verified tenant identity MUST be rejected and MUST NOT be
silently coerced to a default tenant; and abort refunds MUST credit
each bundle exactly once and MUST NOT be double-credited so as to
inflate a tenant's effective quota past the per-tenant cap.

## Contract

`scripts/check_remote_transfer_per_tenant_quota_isolation.py`
emits `ao-operator/remote-transfer-per-tenant-quota-isolation/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process per-tenant accounting state
machine with a fixed per-tenant chunk quota (`4`) and a fixed known-
tenant set (`tenant_a`, `tenant_b`). Each case persists a per-case
`tenant-quota-transcript.json` to a temporary work directory and
records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_per_tenant_within_quota_passes` — control: tenant_a charges
  2 chunks against its own bucket and tenant_b charges 3 chunks
  against its own bucket; both stay under the per-tenant cap and
  `receiver_charge_tenant` produces no errors.
- `tenant_a_overflows_tenant_b_quota_slot_rejected` — mutation:
  tenant_a's bundle is misrouted so the chunk debit lands in
  tenant_b's bucket; the verifier records
  `cross_tenant_charge_debited_wrong_bucket`.
- `aggregated_quota_across_tenants_merged_rejected` — mutation: the
  receiver merges all tenants into one shared bucket whose total
  exceeds the per-tenant cap; the verifier records
  `aggregated_quota_across_tenants`.
- `tenant_identity_stripped_silently_coerced_to_default_rejected`
  — mutation: a bundle arrives with no tenant identity and the
  receiver silently coerces it to a default tenant; the verifier
  records `missing_tenant_identity_silently_coerced_to_default`.
- `quota_refund_on_abort_double_credited_rejected` — mutation:
  tenant_a aborts a bundle and the receiver issues two refunds for
  the same bundle id; the verifier records `double_refund_on_abort`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic tenant identities, bundle ids, and chunk counts.
- Do not derive tenant identities or quota numbers from real
  production traffic.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_per_tenant_quota_isolation.py
python3 scripts/check_remote_transfer_per_tenant_quota_isolation.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-per-tenant-quota-isolation.json
```
