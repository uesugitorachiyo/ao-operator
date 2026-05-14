# Agent Tool-Argument Injection-Escape Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent tool call can escape its declared
argument schema via string-template breakout, nested-object
smuggling, polymorphic-type coercion, shell-metacharacter
injection, or tool-name spoofing smuggled inside argument
payloads. The gate is fail-closed against the five highest-risk
tool-call argument-boundary bypass channels: a string-template
breakout admit MUST be rejected; a nested-object smuggling admit
MUST be rejected; a polymorphic-type coercion admit MUST be
rejected; a shell-metacharacter injection admit MUST be rejected;
and a tool-name spoof admit MUST be rejected.

## Contract

`scripts/check_agent_tool_arg_injection_escape.py` emits
`ao-operator/agent-tool-arg-injection-escape/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process tool-call argument
injection-escape verifier with fixed synthetic placeholder
identifiers (`call::clean_alpha`, `call::clean_beta`,
`call::clean_gamma`, `call::string_breakout_alpha`,
`call::nested_smuggling_alpha`,
`call::polymorphic_coercion_alpha`,
`call::shell_metachar_alpha`, `call::tool_name_spoof_alpha`,
`tool::declared_alpha`, `tool::declared_beta`,
`tool::declared_gamma`, `tool::spoofed_target_alpha`,
`arg-payload::clean_alpha`, `arg-payload::clean_beta`,
`arg-payload::clean_gamma`,
`arg-payload::string_breakout_alpha`,
`arg-payload::nested_smuggling_alpha`,
`arg-payload::polymorphic_coercion_alpha`,
`arg-payload::shell_metachar_alpha`,
`arg-payload::tool_name_spoof_alpha`). Each case persists a
per-case `agent-tool-arg-injection-escape-transcript.json` to a
temporary work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Call classes: `clean_call`, `string_template_breakout`,
`nested_object_smuggling`, `polymorphic_type_coercion`,
`shell_metachar_injection`, `tool_name_spoof`.

Approved call classes: `clean_call`.

Hazard classes: `string_template_breakout_admit`,
`nested_object_smuggling_admit`,
`polymorphic_type_coercion_admit`,
`shell_metachar_injection_admit`, `tool_name_spoof_admit`.

Cases:

- `clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion`
  -- control: every registered tool call has well-formed
  arguments matching the declared schema with no breakout
  sequences, no nested smuggling, no type coercion, no shell
  metacharacters, and no tool-name spoof; the verifier produces
  no errors.
- `string_template_breakout_via_unescaped_quote_rejected` --
  mutation: a tool argument contains an unescaped quote or
  template delimiter that escapes its declared string slot; the
  verifier records `string_template_breakout_admit_rejection`.
- `json_arg_breakout_via_nested_object_smuggling_rejected` --
  mutation: a tool argument contains a nested object that
  smuggles fields beyond the declared schema; the verifier
  records `nested_object_smuggling_admit_rejection`.
- `polymorphic_argument_coercion_via_type_mismatch_rejected` --
  mutation: a tool argument coerces a declared scalar field into
  a list or object to bypass per-field validation; the verifier
  records `polymorphic_type_coercion_admit_rejection`.
- `shell_metachar_injection_via_unfiltered_string_arg_rejected`
  -- mutation: a tool argument destined for a shell-tool sink
  contains shell metacharacters that would chain or redirect the
  shell command; the verifier records
  `shell_metachar_injection_admit_rejection`.
- `tool_name_spoof_via_arg_smuggled_alternate_tool_rejected` --
  mutation: a tool argument contains a smuggled `tool_name`
  field that an unsafe dispatcher would honor as a redirect to
  an alternate tool; the verifier records
  `tool_name_spoof_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real tool dispatcher, model client, shell,
  or remote service -- the gate is a pure in-memory tool-call
  argument injection-escape verifier with synthetic call edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic call / tool / arg-payload identifiers.
- Do not derive tool calls from real model traces, live tool
  schemas, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_tool_arg_injection_escape.py
python3 scripts/check_agent_tool_arg_injection_escape.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-tool-arg-injection-escape.json
```
