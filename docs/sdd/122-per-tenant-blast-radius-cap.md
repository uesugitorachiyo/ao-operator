# Per-Tenant Blast-Radius Cap Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent action originating in tenant ``A``
can reach a resource owned by tenant ``B`` and that no action
without a valid signed tenant tag, no action whose target is
outside the operator allowlist, and no action issued after the
per-tenant quota window has closed can be admitted. The gate is
fail-closed against the five highest-risk per-tenant blast-radius
expansion channels: a cross-tenant fanout admit MUST be rejected;
a missing-tenant-tag admit MUST be rejected; a tenant-tag-spoof
admit MUST be rejected; an allowlist-bypass admit MUST be
rejected; and a quota-overflow leak admit MUST be rejected.

## Contract

`scripts/check_per_tenant_blast_radius_cap.py` emits
`ao-operator/per-tenant-blast-radius-cap/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process per-tenant blast-radius
verifier with fixed synthetic placeholder identifiers
(`action::within_tenant_alpha`, `action::within_tenant_beta`,
`action::within_tenant_gamma`,
`action::cross_tenant_fanout_alpha`,
`action::missing_tenant_tag_alpha`,
`action::tenant_tag_spoof_alpha`,
`action::allowlist_bypass_alpha`,
`action::quota_overflow_leak_alpha`,
`tenant::operator_alpha`, `tenant::other_alpha`,
`target::operator_alpha`, `target::operator_beta`,
`target::operator_gamma`, `target::other_alpha`). Each case
persists a per-case
`per-tenant-blast-radius-cap-transcript.json` to a temporary
work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Action classes: `within_tenant`, `cross_tenant_fanout`,
`missing_tenant_tag`, `tenant_tag_spoof`, `allowlist_bypass`,
`quota_overflow_leak`.

Approved action classes: `within_tenant`.

Hazard classes: `cross_tenant_fanout_admit`,
`missing_tenant_tag_admit`, `tenant_tag_spoof_admit`,
`allowlist_bypass_admit`, `quota_overflow_leak_admit`.

Cases:

- `clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges` --
  control: every registered action stays within the operator
  tenant, carries a valid signed tenant tag, targets an
  allowlisted resource, and is observed inside the open quota
  window; the verifier produces no errors.
- `cross_tenant_fanout_to_unrelated_tenant_resource_rejected` --
  mutation: an action issued by the operator tenant reaches a
  resource owned by an unrelated tenant; the verifier records
  `cross_tenant_fanout_admit_rejection`.
- `missing_tenant_tag_admits_global_blast_radius_rejected` --
  mutation: an action is admitted without any tenant tag,
  letting the operator agent loop fan out across the global
  blast radius; the verifier records
  `missing_tenant_tag_admit_rejection`.
- `tenant_tag_spoof_admits_other_tenant_resource_rejected` --
  mutation: an action carries a tenant tag whose signature does
  not validate, spoofing access to another tenant's resource;
  the verifier records `tenant_tag_spoof_admit_rejection`.
- `allowlist_bypass_admits_unallowlisted_target_rejected` --
  mutation: an action targets a resource that is not on the
  operator allowlist; the verifier records
  `allowlist_bypass_admit_rejection`.
- `quota_overflow_leak_admits_post_window_action_rejected` --
  mutation: an action is admitted after the per-tenant quota
  window has closed and leaks blast-radius across windows; the
  verifier records `quota_overflow_leak_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not read or write any real tenant-boundary policy file or
  invoke a production allowlist or quota service -- the gate is
  a pure in-memory per-tenant blast-radius verifier with
  synthetic action edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic with
  fixed synthetic action / tenant / target identifiers.
- Do not derive actions from real operator audit logs, live
  tenant rosters, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_per_tenant_blast_radius_cap.py
python3 scripts/check_per_tenant_blast_radius_cap.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/per-tenant-blast-radius-cap.json
```
