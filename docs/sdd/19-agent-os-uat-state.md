# 19 - Agent OS UAT Acceptance State

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds durable UAT acceptance state for Agent OS. It reads scoped phase
handoff packets and creates pending human acceptance items for every role. It
does not authorize closure, render a RunSpec, or dispatch providers.

## UAT Contract

The UAT state builder lives at `scripts/agent_os_uat_state.py`.

It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`
and emits `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json`.

Each UAT item must include:

- packet id and role id
- acceptance question
- required human response flag
- pending status
- accepted flag set to false
- evidence requirements
- verification commands
- risk gates

## Negative Constraints

- MUST NOT authorize closure from a generated UAT template.
- MUST NOT dispatch AO providers from UAT state generation.
- MUST NOT mark acceptance as complete without a recorded human response.
- MUST NOT hide pending UAT behind a passing validation verdict.
- MUST NOT activate specialist roles.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_uat_state.py
python3 scripts/agent_os_uat_state.py --write-output --json
```

## Acceptance Criteria

- UAT report emits schema `ao-operator/agent-os-uat-state/v1`.
- Every handoff packet becomes one UAT item.
- Every UAT item starts as `pending-human-acceptance`.
- Every UAT item requires a human response.
- `closure_authorized=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Pending UAT is recorded as a blocker, while the template generation verdict
  remains `PASS`.
