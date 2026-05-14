# Agent OS Role Packet: integrator

Use only the scoped context below. Do not use full conversation history.

## Reads
- accepted slice artifacts
- review decisions
- merge constraints

## Writes
- integrated artifacts
- run-artifacts/

## Verification Commands
- `python3 scripts/verify_closure.py --repo . --with-pytest --json`

## Required Status Fields
- Result
- Artifact
- Evidence
- Concerns
- Blocker

Dispatch is not authorized by this rendered draft.
