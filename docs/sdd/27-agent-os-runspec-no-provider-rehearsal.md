# 27 - Agent OS RunSpec No-Provider Rehearsal

Classification: MODERATE
Shape: greenfield

## Scope

This slice rehearses the Agent OS RunSpec execution path without providers. It
proves the path refuses execution while no explicit approval file is present.

## Contract

The rehearsal lives at `scripts/rehearse_agent_os_runspec_execution.py`.
It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`
and emits `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-rehearsal.json`.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run providers.
- MUST NOT pass if an approval file is already present.
- MUST NOT set dispatch authorization.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_prep.py
python3 scripts/rehearse_agent_os_runspec_execution.py --write-output --json
```

## Acceptance Criteria

- Missing approval file is recorded as a refusal.
- `would_run_provider=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
