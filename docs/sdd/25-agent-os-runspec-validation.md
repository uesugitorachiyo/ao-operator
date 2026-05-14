# 25 - Agent OS RunSpec Validation Gate

Classification: MODERATE
Shape: greenfield

## Scope

This slice validates the non-dispatching Agent OS RunSpec draft and generated
prompt packet set before any execution slice exists. It checks the renderer
status report, RunSpec YAML task graph, provider posture, prompt-file coverage,
and dispatch safety flags.

The gate is validation-only. It must not run AO, dispatch providers, rewrite
the RunSpec, or treat validation as approval to execute the draft.

## Validation Contract

The validator lives at `scripts/agent_os_runspec_validator.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
- `ao/runspecs/agent-os-phase-draft.yaml`
- `ao/prompts/agent-os-phase/*.md`
- `.env.example` or an explicit `--provider-profile` file when profile-aware
  validation is requested

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json`

The validation report uses schema
`ao-operator/agent-os-runspec-validation/v1`.

## Negative Constraints

- MUST NOT dispatch AO providers.
- MUST NOT authorize live providers.
- MUST NOT accept a RunSpec that contains `dispatchAuthorized: true`.
- MUST NOT accept missing prompt packets.
- MUST NOT accept prompt packets that lack scoped-context and no-dispatch
  warnings.
- MUST NOT accept provider substitutions that conflict with the selected
  provider profile.
- MUST NOT accept unsupported provider values in provider profiles.
- MUST NOT treat validation as execution evidence.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_runspec_validator.py
python3 scripts/agent_os_runspec_validator.py --provider-profile .env.example --write-output --json
```

## Acceptance Criteria

- Validator emits schema `ao-operator/agent-os-runspec-validation/v1`.
- RunSpec YAML task ids match the renderer report.
- Every task dependency resolves to a rendered task.
- Every task has a supported provider, policy profile, prompt file, and
  `dispatchAuthorized=false`.
- When `--provider-profile` is supplied, every task provider matches the role
  provider resolved from that profile.
- Unknown provider profile values fail closed.
- Every prompt file exists and preserves scoped-context and no-dispatch text.
- Dispatch-enabled RunSpec input fails closed.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
