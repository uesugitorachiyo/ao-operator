# Agent OS Role Packet: slice-reviewer

Use only the scoped context below. Do not use full conversation history.

## Reads
- slice artifact
- acceptance criteria
- test evidence

## Writes
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
