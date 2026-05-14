# 24 - Agent OS RunSpec Renderer

Classification: MODERATE
Shape: greenfield

## Scope

This slice renders a provider-profile-aware, non-dispatching AO RunSpec draft
from scoped Agent OS handoff packets. It converts the validated phase handoff
into an inspectable RunSpec and prompt packet set so the next Agent OS lane can
review execution shape before any provider dispatch.

The renderer is validation-only. It must not run AO, authorize dispatch, create
live-provider approval, or treat the draft RunSpec as accepted execution
evidence.

## Renderer Contract

The renderer lives at `scripts/agent_os_runspec_renderer.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`
- `.env.example`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
- `ao/runspecs/agent-os-phase-draft.yaml`
- `ao/prompts/agent-os-phase/*.md`

The status report uses schema `ao-operator/agent-os-runspec-renderer/v1`.
When `--provider-profile` is supplied, the report records
`provider_profile_checked=true`, and each rendered task uses the provider and
agent implied by the role-specific profile entry or
`FACTORY_V3_DEFAULT_PROVIDER`.

## Negative Constraints

- MUST NOT dispatch AO providers.
- MUST NOT write accepted AO run evidence.
- MUST NOT set `dispatch_authorized=true`.
- MUST NOT set `live_providers_run=true`.
- MUST NOT render from a handoff report that already authorizes dispatch.
- MUST fail closed if the provider profile contains unsupported provider
  values.
- MUST NOT include full conversation transcripts in generated prompts.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_runspec_renderer.py
python3 scripts/agent_os_runspec_renderer.py --provider-profile .env.example --write-output --write-runspec --json
```

## Acceptance Criteria

- Renderer emits schema `ao-operator/agent-os-runspec-renderer/v1`.
- Rendered RunSpec task count matches handoff packet count.
- Role dependencies are translated into AO task dependencies.
- Provider and agent values are rendered from `.env.example`.
- Provider profile handling rejects unsupported provider values before writing
  a dispatchable interpretation.
- Generated prompts contain scoped reads, scoped writes, and verification
  commands.
- Dispatch-authorized handoff input fails closed.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
