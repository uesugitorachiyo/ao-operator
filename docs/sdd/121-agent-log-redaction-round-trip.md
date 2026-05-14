# Agent Log Redaction Round-Trip Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent log line containing a sensitive
token can be turned back into the original token by reading the
redacted public artifact. The gate is fail-closed against the
five highest-risk round-trip recovery channels: a partial-pattern
match leak MUST be rejected; a base64 round-trip leak MUST be
rejected; a path-normalization alias leak MUST be rejected; a
case-insensitive miss leak MUST be rejected; and a JSON-string-
escape miss leak MUST be rejected.

## Contract

`scripts/check_agent_log_redaction_round_trip.py` emits
`ao-operator/agent-log-redaction-round-trip/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process round-trip recovery
verifier with fixed synthetic placeholder identifiers
(`log::clean_alpha`, `log::clean_beta`, `log::clean_gamma`,
`log::partial_match_leak_alpha`, `log::base64_leak_alpha`,
`log::path_normalization_leak_alpha`,
`log::case_miss_leak_alpha`,
`log::json_string_escape_leak_alpha`,
`redaction::operator_root_alpha`, `token::secret_alpha`,
`token::path_alpha`). Each case persists a per-case
`agent-log-redaction-round-trip-transcript.json` to a temporary
work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Log classes: `clean_log`, `partial_match_leak`, `base64_leak`,
`path_normalization_leak`, `case_miss_leak`,
`json_string_escape_leak`.

Approved log classes: `clean_log`.

Hazard classes: `partial_match_leak_admit`, `base64_leak_admit`,
`path_normalization_leak_admit`, `case_miss_leak_admit`,
`json_string_escape_leak_admit`.

Cases:

- `clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output` --
  control: every registered log entry is in an approved
  redaction class with the original token absent from the
  redacted output across the raw, base64, normalized-alias,
  case-variant, and JSON-string-escape recovery channels; the
  verifier produces no errors.
- `partial_pattern_match_leaves_original_substring_rejected` --
  mutation: a redaction pattern matches only the prefix of the
  synthetic secret token and leaves the tail substring visible
  in the redacted output; the verifier records
  `partial_pattern_match_admit_rejection`.
- `base64_encoded_secret_unredacted_in_round_trip_rejected` --
  mutation: a base64-encoded copy of the synthetic secret token
  survives redaction in the round-tripped artifact; the verifier
  records `base64_encoded_secret_admit_rejection`.
- `path_normalization_alias_unredacted_in_round_trip_rejected` --
  mutation: a tilde-normalized alias of the synthetic personal
  path survives redaction in the round-tripped artifact; the
  verifier records `path_normalization_alias_admit_rejection`.
- `case_insensitive_token_unredacted_in_round_trip_rejected` --
  mutation: an uppercase variant of the synthetic secret token
  survives the case-sensitive redaction pass; the verifier
  records `case_insensitive_token_admit_rejection`.
- `json_string_escape_token_unredacted_in_round_trip_rejected` --
  mutation: a JSON-string-escaped form of the synthetic secret
  token survives redaction in the round-tripped artifact; the
  verifier records `json_string_escape_token_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not read or write any real agent log file or invoke the
  production redaction script -- the gate is a pure in-memory
  round-trip recovery verifier with synthetic log entries.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic with
  fixed synthetic log / redaction / token identifiers.
- Do not derive log entries from real production agent logs,
  signed audit history, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_log_redaction_round_trip.py
python3 scripts/check_agent_log_redaction_round_trip.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-log-redaction-round-trip.json
```
