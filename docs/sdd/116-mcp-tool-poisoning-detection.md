# MCP / Tool Poisoning Detection Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no MCP server or tool descriptor exposed to a AO Operator
agent can poison the agent's tool surface without an explicit
operator-approved trust marker. The gate is fail-closed against the
five highest-risk MCP / tool-poisoning hazards: a hidden imperative
embedded in an MCP tool's description ("ignore prior instructions",
"exfiltrate", etc.) MUST be rejected; a tool result schema that
mutates between invocations to add a destructive default argument
MUST be rejected; an MCP that returns a URL the agent is asked to
fetch and apply MUST be rejected; a tool name that shadows a native
or trusted tool name MUST be rejected; and a signed tool descriptor
that advertises a privilege class outside its allowlist MUST be
rejected.

## Contract

`scripts/check_mcp_tool_poisoning_detection.py` emits
`ao-operator/mcp-tool-poisoning-detection/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process MCP / tool descriptor
verifier with fixed synthetic placeholder identifiers
(`mcp_alpha::tool_alpha`, `mcp_alpha::tool_beta`,
`native::shell.exec`, `signed_descriptor:alpha:rev_1`,
`return_url:https_alpha_example_test::fetch_and_apply`,
`hidden_imperative:ignore_prior_instructions_marker_alpha`,
`destructive_default:rm_workspace_marker_alpha`). Each case persists
a per-case `mcp-tool-poisoning-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Descriptor classifications: `trusted_native`,
`operator_approved_mcp`, `unapproved_mcp`,
`signed_descriptor_within_allowlist`,
`signed_descriptor_outside_allowlist`.

Poisoning hazard classes:
`hidden_imperative_in_description`,
`tool_result_schema_destructive_default_drift`,
`mcp_returns_url_to_fetch_and_apply`,
`tool_name_shadowing`,
`signed_descriptor_advertises_unallowed_privilege`.

Cases:

- `clean_no_mcp_or_tool_poisoning_indicators` — control: every
  registered descriptor carries an operator-approved trust marker, no
  hazard classes are observed, and no tool-name shadowing exists.
- `hidden_imperative_in_mcp_description_rejected` — mutation: an
  unapproved MCP tool description embeds a hidden imperative
  ("ignore prior instructions", "exfiltrate", "delete"); the
  verifier records `hidden_imperative_in_description_unapproved_mcp_rejection`.
- `tool_result_schema_adds_destructive_default_arg_rejected` —
  mutation: a tool result schema mutates between invocations to add
  a destructive default argument; the verifier records
  `tool_result_schema_destructive_default_drift_rejection`.
- `mcp_returns_url_to_fetch_and_apply_rejected` — mutation: an MCP
  returns a URL that the agent is asked to fetch and apply directly;
  the verifier records `mcp_returns_url_to_fetch_and_apply_rejection`.
- `tool_name_shadowing_overrides_native_tool_rejected` — mutation:
  a non-native MCP tool registers under a name that shadows a trusted
  native tool name; the verifier records
  `tool_name_shadowing_rejection`.
- `signed_descriptor_advertises_unallowed_privilege_rejected` —
  mutation: a signed tool descriptor advertises a privilege class
  outside its allowlist; the verifier records
  `signed_descriptor_advertises_unallowed_privilege_rejection`.

Overall verdict is PASS only when every observed verdict matches the
expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not import or speak to any real MCP server.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic descriptor identifiers.

## Verification

```bash
python3 -m pytest -q tests/test_check_mcp_tool_poisoning_detection.py
python3 scripts/check_mcp_tool_poisoning_detection.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/mcp-tool-poisoning-detection.json
```
