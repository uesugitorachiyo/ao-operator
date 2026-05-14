# Agent Supply-Chain Integrity Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent dependency, lock-file digest, or
post-install hook can admit unauthorized provenance into the
working tree without an explicit operator-approved trust marker.
The gate is fail-closed against the five highest-risk supply-
chain hazards: an unsigned package admitted without a signature
MUST be rejected; a lock-file digest mismatch admitted MUST be
rejected; a dependency-confusion install via a shadow registry
MUST be rejected; a post-install script with network egress MUST
be rejected; and a transitive yank without a re-pin MUST be
rejected.

## Contract

`scripts/check_agent_supply_chain_integrity.py` emits
`ao-operator/agent-supply-chain-integrity/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process supply-chain integrity
verifier with fixed synthetic placeholder identifiers
(`pkg::operator_signed_alpha`, `pkg::operator_signed_beta`,
`pkg::unsigned_alpha`, `pkg::digest_mismatch_alpha`,
`pkg::shadow_registry_alpha`, `pkg::post_install_egress_alpha`,
`pkg::transitive_yank_alpha`,
`registry::operator_allowlisted_alpha`,
`registry::shadow_alpha`,
`signature::operator_root_alpha`,
`hook::network_egress_alpha`,
`yank::transitive_unrepinned_alpha`). Each case persists a per-
case `agent-supply-chain-integrity-transcript.json` to a
temporary work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Provenance classes: `operator_signed`, `operator_allowlisted`,
`unsigned`, `digest_mismatch`, `shadow_registry`,
`post_install_egress`, `transitive_yank_unrepinned`.

Approved provenance classes: `operator_signed`,
`operator_allowlisted`.

Hazard classes: `unsigned_admit`, `digest_mismatch_admit`,
`dependency_confusion_admit`, `post_install_egress_admit`,
`transitive_yank_unrepinned_admit`.

Cases:

- `clean_no_unauthorized_provenance_or_unsigned_package_edges` —
  control: every registered package edge is in an approved
  provenance class with a matching lock-file digest, ships from
  an operator-allowlisted registry, has no post-install network
  egress, and has been re-pinned past any upstream yank; the
  verifier produces no errors.
- `unsigned_package_admitted_without_signature_rejected` —
  mutation: an unsigned package is admitted without an
  operator-approved signature; the verifier records
  `unsigned_package_admit_rejection`.
- `lock_file_digest_mismatch_admitted_rejected` — mutation: a
  package is admitted with a lock-file digest that does not
  match the registered digest; the verifier records
  `lock_file_digest_mismatch_admit_rejection`.
- `dependency_confusion_via_shadow_registry_rejected` — mutation:
  a package is admitted from a shadow registry not on the
  operator allowlist; the verifier records
  `dependency_confusion_via_shadow_registry_admit_rejection`.
- `post_install_script_with_network_egress_rejected` — mutation:
  a package whose post-install script performs network egress
  is admitted; the verifier records
  `post_install_script_with_network_egress_admit_rejection`.
- `transitive_yank_without_repin_rejected` — mutation: a
  package whose transitive dependency was yanked upstream but
  has not been re-pinned is admitted; the verifier records
  `transitive_yank_without_repin_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real package manager, registry probe, or
  network call — the gate is a pure in-memory provenance
  verifier with synthetic supply-chain edges.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic package / registry / signature / hook / yank
  identifiers.
- Do not derive supply-chain edges from real production lock
  files, vendor archives, or upstream registry data.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_supply_chain_integrity.py
python3 scripts/check_agent_supply_chain_integrity.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-supply-chain-integrity.json
```
