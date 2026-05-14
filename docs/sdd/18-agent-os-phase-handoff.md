# 18 - Agent OS Phase Execution Handoff

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds a local Agent OS phase handoff contract. It reads the compiled
phase plan and verification matrix, then emits scoped role packets that can be
used by a future AO RunSpec renderer. It does not render or dispatch an AO
RunSpec.

## Handoff Contract

The handoff builder lives at `scripts/agent_os_phase_handoff.py`.

It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json`
and emits
`run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`.

Each handoff packet must include:

- role id and packet id
- dependency list
- scoped reads, writes, and capabilities
- risk level and dispatch mode
- exit gate
- required `Result`, `Artifact`, `Evidence`, `Concerns`, and `Blocker` status
  fields
- verification commands
- risk gates
- `full_transcript_allowed=false`

## Negative Constraints

- MUST NOT dispatch AO providers from handoff generation.
- MUST NOT render a RunSpec from this slice.
- MUST NOT include full conversation transcripts in handoff packets.
- MUST NOT activate specialist roles.
- MUST NOT authorize live provider runs.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_phase_handoff.py
python3 scripts/agent_os_phase_handoff.py --write-output --json
```

## Acceptance Criteria

- Handoff report emits schema `ao-operator/agent-os-phase-handoff/v1`.
- Every phase step becomes one scoped handoff packet.
- Every handoff packet forbids full transcripts.
- Every handoff packet declares required status fields.
- Every handoff packet carries verification commands.
- Specialist activation remains gated.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
