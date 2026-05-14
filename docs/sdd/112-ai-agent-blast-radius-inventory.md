# AI Agent Blast-Radius Inventory

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Enumerate and gate every AO Operator / AO Runtime path where an
agent can reach private data, credentials, filesystem writes,
network transfer, external commands, git mutation, release
artifacts, or provider dispatch. Prove the inventory is fail-closed
against the five highest-risk blast-radius hazards: an unclassified
high-blast-radius command path MUST be rejected; a destructive
action without an explicit approval gate MUST be rejected; a
credential-bearing path reachable from untrusted content or tool
output MUST be rejected; a provider dispatch path that can execute
without the existing approval and readiness posture MUST be
rejected; and a release/public artifact path that can include
instruction files, memory blocks, raw prompts, credentials, or
local-only diagnostics MUST be rejected.

## Contract

`scripts/check_ai_agent_blast_radius_inventory.py` emits
`ao-operator/ai-agent-blast-radius-inventory/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process blast-radius inventory state
machine with fixed synthetic placeholder identifiers
(`clean_command_path_alpha`, `clean_destructive_action_beta`,
`clean_credential_path_gamma`, `clean_provider_dispatch_path_delta`,
`clean_release_artifact_epsilon`) and fixed mutated-entry literals
(`mutated_unclassified_command_zeta`,
`mutated_destructive_action_eta`,
`mutated_credential_path_theta`,
`mutated_provider_dispatch_iota`,
`mutated_release_artifact_kappa`). Each case persists a per-case
`blast-radius-inventory-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Cases:

- `clean_inventory_classified_and_gated` — control: every
  agent-reachable path is classified by category
  (`command`, `destructive_action`, `credential`,
  `provider_dispatch`, `release_artifact`) and blast radius
  (`low`, `moderate`, `high`); destructive paths carry an explicit
  approval gate; credential paths are not reachable from untrusted
  input; provider dispatch paths require the approval and readiness
  posture (`approval_gate_present=true`, `readiness_gated=true`,
  `dispatch_authorized=false`); release/public artifact paths
  exclude instruction files, memory blocks, raw prompts,
  credentials, and local-only diagnostics; the verifier produces
  no errors.
- `unclassified_high_blast_radius_command_path_rejected` —
  mutation: a command path is registered with `category=None` and
  `blast_radius=None`; the verifier records
  `unclassified_high_blast_radius_path`.
- `destructive_action_without_approval_gate_rejected` —
  mutation: a destructive filesystem mutation, transfer, or git
  path is registered with `destructive=true` but
  `approval_gate_present=false`; the verifier records
  `destructive_action_missing_approval_gate`.
- `credential_path_reachable_from_untrusted_content_rejected` —
  mutation: a credential-bearing path is registered with
  `category=credential` and
  `reachable_from_untrusted_input=true`; the verifier records
  `credential_path_reachable_from_untrusted_input`.
- `provider_dispatch_without_approval_readiness_rejected` —
  mutation: a provider dispatch path is registered with
  `category=provider_dispatch`, `approval_gate_present=false`,
  `readiness_gated=false`, and `dispatch_authorized=true`; the
  verifier records
  `provider_dispatch_without_approval_readiness`.
- `release_artifact_includes_instruction_or_credentials_rejected`
  — mutation: a release/public artifact path is registered with
  `category=release_artifact` and every leak field
  (`includes_instruction_files`, `includes_memory_blocks`,
  `includes_raw_prompts`, `includes_credentials`,
  `includes_local_diagnostics`) set to `true`; the verifier records
  `release_artifact_includes_unsafe_payload`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic inventory entries and category/blast-radius
  literals.
- Do not derive inventory entries from real production paths,
  credentials, OAuth files, or provider dispatch endpoints.

## Verification

```bash
python3 -m pytest -q tests/test_check_ai_agent_blast_radius_inventory.py
python3 scripts/check_ai_agent_blast_radius_inventory.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/ai-agent-blast-radius-inventory.json
```
