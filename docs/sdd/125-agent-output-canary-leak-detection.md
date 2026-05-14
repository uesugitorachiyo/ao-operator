# Agent Output Canary-Leak Detection Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent final output can leak a canary
token or marked-secret value originating in retrieved context,
whether literally, base64-encoded, with unicode homoglyph
substitution, reassembled from fragments, or relabeled via a
different output field. The gate is fail-closed against the five
highest-risk agent-output exfiltration channels: a literal
canary leak admit MUST be rejected; a base64-encoded canary leak
admit MUST be rejected; a unicode-homoglyph canary substitution
admit MUST be rejected; a fragment canary concatenation admit
MUST be rejected; and a marked-secret relabel passthrough admit
MUST be rejected.

## Contract

`scripts/check_agent_output_canary_leak_detection.py` emits
`ao-operator/agent-output-canary-leak-detection/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process agent-output canary-leak
detection verifier with fixed synthetic placeholder identifiers
(`output::clean_alpha`, `output::clean_beta`,
`output::clean_gamma`, `output::literal_canary_alpha`,
`output::base64_canary_alpha`,
`output::homoglyph_canary_alpha`,
`output::fragment_canary_alpha`,
`output::marked_secret_relabel_alpha`, `canary::token_alpha`,
`canary::token_beta`, `secret::marked_alpha`,
`field-label::declared_alpha`,
`field-label::declared_beta`). Each case persists a per-case
`agent-output-canary-leak-detection-transcript.json` to a
temporary work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Output classes: `clean_output`, `literal_canary_leak`,
`base64_canary_leak`, `homoglyph_canary_leak`,
`fragment_canary_leak`, `marked_secret_relabel_leak`.

Approved output classes: `clean_output`.

Hazard classes: `literal_canary_leak_admit`,
`base64_canary_leak_admit`, `homoglyph_canary_leak_admit`,
`fragment_canary_leak_admit`,
`marked_secret_relabel_leak_admit`.

Cases:

- `clean_no_canary_or_marked_secret_leak_in_output` -- control:
  every registered output contains only declared non-canary,
  non-secret tokens; the verifier produces no errors.
- `literal_canary_token_in_output_rejected` -- mutation: a
  canary token from retrieved context appears literally in the
  output; the verifier records
  `literal_canary_leak_admit_rejection`.
- `base64_encoded_canary_token_in_output_rejected` -- mutation:
  a canary token is base64-encoded in the output as a
  side-channel; the verifier records
  `base64_canary_leak_admit_rejection`.
- `unicode_homoglyph_canary_substitution_in_output_rejected` --
  mutation: a canary token with unicode homoglyph substitution
  appears in the output; the verifier records
  `homoglyph_canary_leak_admit_rejection`.
- `partial_canary_fragment_concatenation_in_output_rejected` --
  mutation: canary-token fragments are concatenated across the
  output to reassemble the original token; the verifier records
  `fragment_canary_leak_admit_rejection`.
- `marked_secret_passthrough_via_field_label_rejected` --
  mutation: a marked secret appears in the output under a
  different field label as a relabeled passthrough; the
  verifier records `marked_secret_relabel_leak_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real model client, retrieval service, or
  remote inference endpoint -- the gate is a pure in-memory
  agent-output canary-leak detection verifier with synthetic
  output edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic output / canary / secret / field-label
  identifiers.
- Do not derive outputs from real model traces, live retrieval
  corpora, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_output_canary_leak_detection.py
python3 scripts/check_agent_output_canary_leak_detection.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-output-canary-leak-detection.json
```
