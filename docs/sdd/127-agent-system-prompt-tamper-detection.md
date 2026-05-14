# Agent System Prompt Tamper Detection Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent execution can run with a system
prompt that has been tampered with via substitution, appended
instruction injection, truncation, unicode homoglyph confusable
characters, or role relabel from system to user/assistant. The
gate is fail-closed against the five highest-risk system-prompt
tamper channels: a system-prompt substitution admit MUST be
rejected; a system-prompt appended-instruction admit MUST be
rejected; a system-prompt truncation admit MUST be rejected; a
system-prompt unicode-homoglyph admit MUST be rejected; and a
system-prompt role-relabel admit MUST be rejected.

## Contract

`scripts/check_agent_system_prompt_tamper_detection.py` emits
`ao-operator/agent-system-prompt-tamper-detection/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process agent system-prompt
tamper-detection verifier with fixed synthetic placeholder
identifiers (`prompt::clean_alpha`, `prompt::clean_beta`,
`prompt::clean_gamma`, `prompt::substituted_alpha`,
`prompt::appended_alpha`, `prompt::truncated_alpha`,
`prompt::homoglyph_alpha`, `prompt::role_relabel_alpha`,
`baseline::sha256_alpha`, `baseline::sha256_beta`,
`baseline::sha256_gamma`). Each case persists a per-case
`agent-system-prompt-tamper-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Prompt classes: `clean_prompt`, `system_prompt_substitution`,
`system_prompt_appended_instruction`,
`system_prompt_truncation`, `system_prompt_unicode_homoglyph`,
`system_prompt_role_relabel`.

Approved prompt classes: `clean_prompt`.

Hazard classes: `system_prompt_substitution_admit`,
`system_prompt_appended_instruction_admit`,
`system_prompt_truncation_admit`,
`system_prompt_unicode_homoglyph_admit`,
`system_prompt_role_relabel_admit`.

Cases:

- `clean_no_system_prompt_tamper` -- control: every registered
  prompt matches its declared baseline hash with no appended
  instruction, no truncation, no homoglyph substitution, and the
  system role intact; the verifier produces no errors.
- `system_prompt_substitution_admit_rejected` -- mutation: a
  prompt payload swaps the system text for a different baseline;
  the verifier records
  `system_prompt_substitution_admit_rejection`.
- `system_prompt_appended_instruction_admit_rejected` --
  mutation: a prompt payload appends an extra adversarial
  instruction beyond the declared baseline; the verifier records
  `system_prompt_appended_instruction_admit_rejection`.
- `system_prompt_truncation_admit_rejected` -- mutation: a
  prompt payload truncates the declared baseline mid-instruction;
  the verifier records
  `system_prompt_truncation_admit_rejection`.
- `system_prompt_unicode_homoglyph_admit_rejected` -- mutation:
  a prompt payload substitutes ASCII characters with visually
  identical unicode homoglyphs; the verifier records
  `system_prompt_unicode_homoglyph_admit_rejection`.
- `system_prompt_role_relabel_admit_rejected` -- mutation: a
  prompt payload relabels the system role to user or assistant;
  the verifier records
  `system_prompt_role_relabel_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real prompt loader, model client, or remote
  inference endpoint -- the gate is a pure in-memory agent
  system-prompt tamper-detection verifier with synthetic prompt
  edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic prompt / baseline-hash identifiers.
- Do not derive outputs from real system prompts, live model
  traces, or production tokenizer samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_system_prompt_tamper_detection.py
python3 scripts/check_agent_system_prompt_tamper_detection.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-system-prompt-tamper-detection.json
```
