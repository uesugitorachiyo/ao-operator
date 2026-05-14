# DeepSec Diff-Review Advisory SAST Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no agent-generated diff can introduce a tainted dataflow
edge from an untrusted-input source to a dangerous sink without an
explicit operator-approved sanitization step. The gate is fail-
closed against the five highest-risk untrusted-input → dangerous-
sink hazards: an untrusted input flowing into a shell command MUST
be rejected; an untrusted input flowing into a filesystem write
outside the workspace MUST be rejected; an untrusted input flowing
into network egress MUST be rejected; eval / exec on retrieved
content MUST be rejected; and a dynamic import from an agent-
controlled path MUST be rejected.

## Contract

`scripts/check_deepsec_diff_review_advisory_sast.py` emits
`ao-operator/deepsec-diff-review-advisory-sast/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process diff-review SAST verifier
with fixed synthetic placeholder identifiers
(`untrusted::user_prompt_alpha`,
`untrusted::tool_result_alpha`, `untrusted::web_fetch_alpha`,
`untrusted::retrieved_content_alpha`,
`untrusted::agent_controlled_path_alpha`,
`sink::shell_exec_alpha`,
`sink::fs_write_outside_workspace_alpha`,
`sink::network_egress_alpha`,
`sink::eval_exec_alpha`,
`sink::dynamic_import_alpha`,
`sanitizer::shell_argv_quote_alpha`). Each case persists a per-case
`deepsec-diff-review-advisory-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Untrusted input sources: `user_prompt`, `tool_result`,
`web_fetch_body`, `retrieved_content`, `agent_controlled_path`.

Dangerous sink classes: `shell_exec`,
`fs_write_outside_workspace`, `network_egress`, `eval_exec`,
`dynamic_import`.

Cases:

- `clean_no_untrusted_to_dangerous_sink_edges` — control: every
  registered taint edge is either non-untrusted or carries an
  explicit operator-approved sanitizer; the verifier produces no
  errors.
- `untrusted_input_flows_into_shell_command_rejected` — mutation:
  an untrusted input flows directly into `sink::shell_exec_alpha`
  without sanitization; the verifier records
  `untrusted_to_shell_exec_unsanitized_edge_rejection`.
- `untrusted_input_flows_into_fs_write_outside_workspace_rejected` —
  mutation: an untrusted input flows into
  `sink::fs_write_outside_workspace_alpha` without sanitization;
  the verifier records
  `untrusted_to_fs_write_outside_workspace_unsanitized_edge_rejection`.
- `untrusted_input_flows_into_network_egress_rejected` —
  mutation: an untrusted input flows into
  `sink::network_egress_alpha` without sanitization; the verifier
  records `untrusted_to_network_egress_unsanitized_edge_rejection`.
- `eval_or_exec_on_retrieved_content_rejected` — mutation: an
  untrusted retrieved-content payload flows into
  `sink::eval_exec_alpha` without sanitization; the verifier
  records `untrusted_to_eval_exec_unsanitized_edge_rejection`.
- `dynamic_import_from_agent_controlled_path_rejected` —
  mutation: an untrusted agent-controlled path flows into
  `sink::dynamic_import_alpha` without sanitization; the verifier
  records `untrusted_to_dynamic_import_unsanitized_edge_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real SAST scanner against the working tree —
  the gate is a pure in-memory dataflow verifier with synthetic
  taint edges.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic source/sink/sanitizer identifiers.
- Do not derive taint edges from real production agent diffs,
  user prompts, tool results, retrieved content, or agent-
  controlled paths.

## Verification

```bash
python3 -m pytest -q tests/test_check_deepsec_diff_review_advisory_sast.py
python3 scripts/check_deepsec_diff_review_advisory_sast.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/deepsec-diff-review-advisory-sast.json
```
