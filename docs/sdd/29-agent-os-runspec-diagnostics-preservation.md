# 29 - Agent OS RunSpec Diagnostics Preservation

Classification: MODERATE
Shape: greenfield

## Scope

This slice preserves sanitized diagnostics for future failed Agent OS RunSpec
executions. It writes a compact sanitized summary only when postrun routing says
diagnostics are required and an operator runs the preservation command with
`--execute`.

## Contract

The preservation guard lives at `scripts/preserve_agent_os_runspec_diagnostics.py`.
It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json`
and emits `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-diagnostics-preservation.json`.

## Negative Constraints

- MUST NOT copy raw AO homes into tracked evidence.
- MUST NOT preserve diagnostics unless the postrun route requires them.
- MUST redact AO home paths from sanitized summaries.
- MUST NOT authorize dispatch.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_prep.py
python3 scripts/preserve_agent_os_runspec_diagnostics.py --write-output --json
```

## Acceptance Criteria

- Non-diagnostic routes pass without writing a summary.
- Diagnostic routes block until `--execute`.
- Executed diagnostic preservation writes sanitized failure summaries.
- `raw_snapshot_commit_allowed=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
