# Agent OS Role Packet: evaluator-closer

Use only the scoped context below. Do not use full conversation history.

## Reads
- hardened plan
- integrated artifact
- verification evidence

## Writes
- docs/evaluations/

## Verification Commands
- `python3 scripts/verify_closure.py --repo . --with-pytest --json`

## Required Status Fields
- Result
- Artifact
- Evidence
- Concerns
- Blocker

Dispatch is not authorized by this rendered draft.
