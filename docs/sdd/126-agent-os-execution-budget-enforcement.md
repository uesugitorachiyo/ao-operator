# Agent OS Execution Budget Enforcement Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent execution can exceed declared
budget caps via a token-budget overflow, a time-budget overflow,
a tool-call-count overflow, a cost-ceiling overflow, or a
mid-execution budget-reset bypass. The gate is fail-closed
against the five highest-risk execution-budget bypass channels:
a token-budget overflow admit MUST be rejected; a time-budget
overflow admit MUST be rejected; a tool-call-count overflow
admit MUST be rejected; a cost-ceiling overflow admit MUST be
rejected; and a budget-reset bypass admit MUST be rejected.

## Contract

`scripts/check_agent_os_execution_budget_enforcement.py` emits
`ao-operator/agent-os-execution-budget-enforcement/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process agent-os execution budget
enforcement verifier with fixed synthetic placeholder identifiers
(`execution::clean_alpha`, `execution::clean_beta`,
`execution::clean_gamma`, `execution::token_overflow_alpha`,
`execution::time_overflow_alpha`,
`execution::tool_call_overflow_alpha`,
`execution::cost_overflow_alpha`,
`execution::budget_reset_bypass_alpha`,
`budget::token_cap_alpha`, `budget::time_cap_alpha`,
`budget::tool_call_cap_alpha`, `budget::cost_cap_alpha`,
`budget::reset_token_alpha`). Each case persists a per-case
`agent-os-execution-budget-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Execution classes: `clean_execution`, `token_budget_overflow`,
`time_budget_overflow`, `tool_call_count_overflow`,
`cost_ceiling_overflow`, `budget_reset_bypass`.

Approved execution classes: `clean_execution`.

Hazard classes: `token_budget_overflow_admit`,
`time_budget_overflow_admit`, `tool_call_count_overflow_admit`,
`cost_ceiling_overflow_admit`, `budget_reset_bypass_admit`.

Cases:

- `clean_no_budget_overflow_or_reset_bypass` -- control: every
  registered execution stays within declared token, time,
  tool-call, and cost caps with no mid-execution budget reset;
  the verifier produces no errors.
- `token_budget_overflow_admit_rejected` -- mutation: an
  execution emits more tokens than the declared token cap; the
  verifier records `token_budget_overflow_admit_rejection`.
- `time_budget_overflow_admit_rejected` -- mutation: an
  execution runs longer than the declared time cap; the
  verifier records `time_budget_overflow_admit_rejection`.
- `tool_call_count_overflow_admit_rejected` -- mutation: an
  execution issues more tool calls than the declared tool-call
  cap; the verifier records
  `tool_call_count_overflow_admit_rejection`.
- `cost_ceiling_overflow_admit_rejected` -- mutation: an
  execution accumulates cost above the declared cost cap; the
  verifier records `cost_ceiling_overflow_admit_rejection`.
- `budget_reset_bypass_admit_rejected` -- mutation: an
  execution resets its budget mid-run to extend past the
  declared cap; the verifier records
  `budget_reset_bypass_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real execution scheduler, model client, or
  remote inference endpoint -- the gate is a pure in-memory
  agent-os execution budget enforcement verifier with synthetic
  execution edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic execution / budget / reset-token
  identifiers.
- Do not derive outputs from real execution traces, live
  scheduler queues, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_execution_budget_enforcement.py
python3 scripts/check_agent_os_execution_budget_enforcement.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-execution-budget-enforcement.json
```
