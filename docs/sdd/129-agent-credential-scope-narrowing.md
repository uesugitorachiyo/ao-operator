# Agent Credential Scope Narrowing Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent can widen a scoped credential at
use time via scope substitution, scope append, audience relabel,
expiry extension, or principal mint. The gate is fail-closed
against the five highest-risk credential-widening channels: a
credential-scope-substitution admit MUST be rejected; a
credential-scope-append admit MUST be rejected; a credential-
audience-relabel admit MUST be rejected; a credential-expiry-
extension admit MUST be rejected; and a credential-principal-
mint admit MUST be rejected.

## Contract

`scripts/check_agent_credential_scope_narrowing.py` emits
`ao-operator/agent-credential-scope-narrowing/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process credential scope-narrowing
verifier with fixed synthetic placeholder identifiers
(`cred::clean_alpha`, `cred::clean_beta`, `cred::clean_gamma`,
`cred::scope_substituted_alpha`, `cred::scope_appended_alpha`,
`cred::audience_relabel_alpha`, `cred::expiry_extension_alpha`,
`cred::principal_mint_alpha`, `scope::read_alpha`,
`scope::read_beta`, `scope::read_gamma`, `scope::admin_root`,
`scope::write_extra`, `aud::tenant_alpha`, `aud::tenant_beta`,
`aud::tenant_gamma`, `principal::user_alpha`,
`principal::admin_root`). Each case persists a per-case
`agent-credential-scope-narrowing-transcript.json` to a temporary
work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Credential classes: `clean_credential`,
`credential_scope_substitution`, `credential_scope_append`,
`credential_audience_relabel`, `credential_expiry_extension`,
`credential_principal_mint`.

Approved credential classes: `clean_credential`.

Hazard classes: `credential_scope_substitution_admit`,
`credential_scope_append_admit`,
`credential_audience_relabel_admit`,
`credential_expiry_extension_admit`,
`credential_principal_mint_admit`.

Cases:

- `clean_no_credential_scope_widening` -- control: every
  registered credential carries only the originally declared
  scope, audience, expiry, and principal; no widening, no
  appended scopes, no relabel, no expiry push, no principal
  mint; the verifier produces no errors.
- `credential_scope_substitution_admit_rejected` -- mutation: a
  credential payload swaps the declared scope for a broader
  scope; the verifier records
  `credential_scope_substitution_admit_rejection`.
- `credential_scope_append_admit_rejected` -- mutation: a
  credential payload appends an extra scope beyond the declared
  scope; the verifier records
  `credential_scope_append_admit_rejection`.
- `credential_audience_relabel_admit_rejected` -- mutation: a
  credential payload relabels the declared audience to a
  different tenant; the verifier records
  `credential_audience_relabel_admit_rejection`.
- `credential_expiry_extension_admit_rejected` -- mutation: a
  credential payload pushes its expiry past the declared TTL;
  the verifier records
  `credential_expiry_extension_admit_rejection`.
- `credential_principal_mint_admit_rejected` -- mutation: a
  credential payload mints a higher-privilege principal beyond
  the declared principal; the verifier records
  `credential_principal_mint_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real credential broker, identity provider,
  or remote signing endpoint -- the gate is a pure in-memory
  credential scope-narrowing verifier with synthetic credential
  edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic credential / scope / audience / expiry /
  principal identifiers.
- Do not derive outputs from real credentials, live signing
  keys, or production tenant audience traces.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_credential_scope_narrowing.py
python3 scripts/check_agent_credential_scope_narrowing.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-credential-scope-narrowing.json
```
