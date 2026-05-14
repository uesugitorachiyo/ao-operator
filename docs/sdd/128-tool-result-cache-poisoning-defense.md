# Tool-Result Cache Poisoning Defense Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent execution can serve a poisoned
tool-result cache entry via cache-key collision, stale cache
serve after invalidation, TTL extension via admin replay, forged
response signature, or cross-tenant cache share. The gate is
fail-closed against the five highest-risk tool-result cache
poisoning channels: a cache-key collision admit MUST be rejected;
a stale-cache-serve-after-invalidation admit MUST be rejected; a
TTL-extension-via-admin-replay admit MUST be rejected; a
forged-response-signature admit MUST be rejected; and a
cross-tenant cache-share admit MUST be rejected.

## Contract

`scripts/check_tool_result_cache_poisoning_defense.py` emits
`ao-operator/tool-result-cache-poisoning-defense/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process tool-result cache poisoning
verifier with fixed synthetic placeholder identifiers
(`cache::clean_alpha`, `cache::clean_beta`, `cache::clean_gamma`,
`cache::key_collision_alpha`, `cache::stale_serve_alpha`,
`cache::ttl_extension_alpha`, `cache::forged_signature_alpha`,
`cache::cross_tenant_alpha`, `key::cache_alpha`,
`key::cache_beta`, `key::cache_gamma`,
`invalidation::token_alpha`, `signing::key_alpha`). Each case
persists a per-case
`tool-result-cache-poisoning-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Entry classes: `clean_entry`, `cache_key_collision`,
`stale_cache_serve_after_invalidation`,
`ttl_extension_via_admin_replay`, `forged_response_signature`,
`cross_tenant_cache_share`.

Approved entry classes: `clean_entry`.

Hazard classes: `cache_key_collision_admit`,
`stale_cache_serve_after_invalidation_admit`,
`ttl_extension_via_admin_replay_admit`,
`forged_response_signature_admit`,
`cross_tenant_cache_share_admit`.

Cases:

- `clean_no_tool_result_cache_poisoning` -- control: every
  registered cache entry has a unique key, an unexpired TTL, an
  intact response signature, no replay of admin invalidation
  tokens, and no cross-tenant share; the verifier produces no
  errors.
- `cache_key_collision_admit_rejected` -- mutation: a cache
  entry payload reuses a cache key already bound to a different
  tenant/tool input pair; the verifier records
  `cache_key_collision_admit_rejection`.
- `stale_cache_serve_after_invalidation_admit_rejected` --
  mutation: a cache entry payload serves a response after its
  invalidation token has been issued; the verifier records
  `stale_cache_serve_after_invalidation_admit_rejection`.
- `ttl_extension_via_admin_replay_admit_rejected` -- mutation: a
  cache entry payload extends its TTL by replaying an
  administrator-only refresh signal; the verifier records
  `ttl_extension_via_admin_replay_admit_rejection`.
- `forged_response_signature_admit_rejected` -- mutation: a
  cache entry payload carries a response signature that does not
  verify against the declared signing key; the verifier records
  `forged_response_signature_admit_rejection`.
- `cross_tenant_cache_share_admit_rejected` -- mutation: a cache
  entry payload exposes a tenant A response under a tenant B
  cache lookup; the verifier records
  `cross_tenant_cache_share_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real cache backend, response signer, or
  remote tool runner -- the gate is a pure in-memory tool-result
  cache poisoning verifier with synthetic cache edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic cache / key / invalidation-token /
  signing-key identifiers.
- Do not derive outputs from real cache logs, live signing keys,
  or production tenant cache traces.

## Verification

```bash
python3 -m pytest -q tests/test_check_tool_result_cache_poisoning_defense.py
python3 scripts/check_tool_result_cache_poisoning_defense.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/tool-result-cache-poisoning-defense.json
```
