# Prompt-Injection Escape Boundary Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent prompt assembly can let attacker-
controlled content reorder, escape, or replace operator-trusted
instructions already placed in the system or developer slot.
The gate is fail-closed against the five highest-risk prompt-
injection escape hazards: an attacker-controlled section that
spoofs the system role MUST be rejected; a fenced block that
escapes the system-section boundary MUST be rejected; a JSON
payload that re-keys the operator-trusted system field MUST be
rejected; an attacker-controlled section that shadows an operator
allowlisted tool name MUST be rejected; and an attacker-controlled
section that smuggles instructions via a unicode homoglyph for an
operator-trusted role marker MUST be rejected.

## Contract

`scripts/check_prompt_injection_escape_boundary.py` emits
`ao-operator/prompt-injection-escape-boundary/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process prompt-injection escape
boundary verifier with fixed synthetic placeholder identifiers
(`section::operator_system_alpha`,
`section::operator_developer_alpha`,
`section::user_input_alpha`, `section::tool_result_alpha`,
`section::role_spoof_alpha`, `section::fence_escape_alpha`,
`section::json_injection_alpha`, `section::tool_shadow_alpha`,
`section::unicode_smuggle_alpha`,
`tool::operator_allowlisted_alpha`, `role::system`,
`role::developer`, `role::user`, `role::tool`). Each case
persists a per-case
`prompt-injection-escape-boundary-transcript.json` to a
temporary work directory and records `observed_verdict` next to
`expected_case_verdicts`.

Section classes: `operator_system`, `operator_developer`,
`user_input`, `tool_result`, `role_spoof`, `fence_escape`,
`json_injection`, `tool_shadow`, `unicode_smuggle`.

Approved section classes: `operator_system`, `operator_developer`,
`user_input`, `tool_result`.

Hazard classes: `role_spoof_admit`, `fence_escape_admit`,
`json_injection_admit`, `tool_shadow_admit`,
`unicode_smuggle_admit`.

Cases:

- `clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended`
  — control: every registered section is in an approved role
  with operator-trusted instructions placed strictly before any
  attacker-controlled content, no fence escape, no JSON
  replacement, no tool-name shadow, no unicode homoglyph
  smuggle; the verifier produces no errors.
- `attacker_role_spoofing_appended_after_user_content_rejected`
  — mutation: an attacker-controlled section spoofs the system
  role and appears after the operator-trusted system slot; the
  verifier records `attacker_role_spoof_admit_rejection`.
- `fenced_block_escape_breaking_system_boundary_rejected` —
  mutation: an attacker-controlled fenced block closes the
  system-section fence and re-opens with attacker instructions;
  the verifier records `fenced_block_escape_admit_rejection`.
- `json_injection_replacing_operator_instructions_rejected` —
  mutation: an attacker-controlled JSON payload re-keys the
  operator-trusted system field; the verifier records
  `json_injection_replacing_operator_instructions_admit_rejection`.
- `tool_name_shadowing_via_attacker_section_rejected` —
  mutation: an attacker-controlled section declares a tool name
  that shadows an operator-allowlisted tool; the verifier records
  `tool_name_shadowing_admit_rejection`.
- `instruction_smuggling_via_unicode_homoglyph_rejected` —
  mutation: an attacker-controlled section smuggles instructions
  using a unicode homoglyph for an operator-trusted role marker;
  the verifier records
  `instruction_smuggling_via_unicode_homoglyph_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not invoke any real LLM, prompt template engine, or remote
  evaluation — the gate is a pure in-memory escape-boundary
  verifier with synthetic prompt sections.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic section / role / tool / homoglyph identifiers.
- Do not derive prompt sections from real production prompt
  templates, captured user inputs, or vendor router payloads.

## Verification

```bash
python3 -m pytest -q tests/test_check_prompt_injection_escape_boundary.py
python3 scripts/check_prompt_injection_escape_boundary.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/prompt-injection-escape-boundary.json
```
