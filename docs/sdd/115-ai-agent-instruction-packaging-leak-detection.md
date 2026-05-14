# AI Agent Instruction & Release Packaging Leak Detection Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no leak-bearing source (agent instruction file content
from CLAUDE.md / AGENTS.md / GEMINI.md / Cursor rules, agent memory
snippet, raw user prompt, provider API key, or private /tmp
diagnostic path) can reach a public artifact class (public status
report, public operator slice evidence, public evaluation
transcript, public doc, public release artifact) without an
explicit redaction-at-emission step. The gate is fail-closed against
the five highest-risk instruction & release packaging leak hazards:
a CLAUDE.md / AGENTS.md instruction directive copied verbatim into
a public status report MUST be rejected; an agent memory snippet
copy-pasted into a public doc MUST be rejected; a raw user prompt
logged verbatim into operator slice evidence MUST be rejected; a
provider API key (ANTHROPIC_API_KEY / FACTORY_PROVIDER_API_KEY)
surfaced verbatim in an evaluation transcript MUST be rejected; and
a private /tmp diagnostic path included verbatim in a public release
artifact MUST be rejected.

## Contract

`scripts/check_ai_agent_instruction_packaging_leak_detection.py`
emits
`ao-operator/ai-agent-instruction-packaging-leak-detection/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process leak-detection state machine
with fixed synthetic placeholder identifiers
(`CLAUDE.md::section_factory_alpha`,
`memory_alpha:auto-memory:user_role`,
`raw_user_prompt:lane_alpha:turn_42`,
`provider_api_key:anthropic:redacted_marker_alpha`,
`/tmp/factory_alpha/diagnostics/run-2026-05-08.log`,
`docs/public/welcome_alpha.md::release_notes`). Each case persists a
per-case `instruction-packaging-leak-transcript.json` to a temporary
work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Source classifications: `sanitized_internal`,
`agent_instruction_file`, `agent_memory_snippet`, `raw_user_prompt`,
`provider_api_key`, `tmp_diagnostic_path`.

Public artifact classes: `public_status_report`,
`public_operator_slice_evidence`,
`public_evaluation_transcript`, `public_doc`,
`public_release_artifact`.

Cases:

- `clean_no_instruction_or_packaging_leaks_in_public_artifacts` —
  control: every emission edge is either non-leak-bearing or
  redacted at emission; the verifier produces no errors.
- `claude_md_directives_leaked_into_status_report_rejected` —
  mutation: a CLAUDE.md / AGENTS.md instruction file directive is
  copied verbatim into a public status report; the verifier records
  `agent_instruction_file_public_status_report_unredacted_emission`.
- `agent_memory_snippet_copy_pasted_into_public_doc_rejected` —
  mutation: an agent memory snippet (auto-memory or persistent
  memory) is copy-pasted into a public doc artifact; the verifier
  records `agent_memory_snippet_public_doc_unredacted_emission`.
- `raw_user_prompt_logged_in_operator_slice_evidence_rejected` —
  mutation: a raw user prompt is logged verbatim into an operator
  slice evidence record; the verifier records
  `raw_user_prompt_public_operator_slice_evidence_unredacted_emission`.
- `anthropic_api_key_surfaced_in_evaluation_transcript_rejected` —
  mutation: a provider API key (ANTHROPIC_API_KEY /
  FACTORY_PROVIDER_API_KEY) is surfaced verbatim in an evaluation
  transcript; the verifier records
  `provider_api_key_public_evaluation_transcript_unredacted_emission`.
- `tmp_diagnostic_path_included_in_public_artifact_rejected` —
  mutation: a private /tmp diagnostic path is included verbatim in a
  public release artifact; the verifier records
  `tmp_diagnostic_path_public_release_artifact_unredacted_emission`.

Overall verdict is PASS only when every observed verdict matches the
expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic source/artifact identifiers.
- Do not derive emission edges from real production agent
  instruction files, agent memory snippets, raw user prompts,
  provider API keys, or private /tmp diagnostic paths.

## Verification

```bash
python3 -m pytest -q tests/test_check_ai_agent_instruction_packaging_leak_detection.py
python3 scripts/check_ai_agent_instruction_packaging_leak_detection.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/ai-agent-instruction-packaging-leak-detection.json
```
