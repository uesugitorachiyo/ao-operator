# 56 - Agent OS Failed Diagnostics Fixture

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS execution safety

## Objective

Provide a deterministic, provider-free fixture that proves failed Agent OS
execution diagnostics can be preserved as sanitized evidence without committing
raw AO homes or running live providers.

## Scope

The fixture lives at `scripts/check_agent_os_failed_diagnostics_fixture.py`.
It creates a synthetic `DIAGNOSTIC_REQUIRED` postrun route and a local AO
events fixture, then calls the real
`scripts/preserve_agent_os_runspec_diagnostics.py` preservation path with
`execute=true`.

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-failed-diagnostics-fixture.json`
- `run-artifacts/remote-transfer-v2-stress-live/failed-diagnostics-fixture/`
- `run-artifacts/remote-transfer-v2-stress-live/failure-snapshots/agent-os-ao-home-20260507-000000-summary.json`

## Required Behavior

- Route must be `DIAGNOSTIC_REQUIRED`.
- Summary must be written from synthetic AO events.
- Primary normalized reason must be `provider-rate-limit`.
- Summary payload must redact local AO-home paths.
- Raw AO snapshots must remain blocked from commit.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT commit raw AO homes.
- MUST NOT authorize dispatch.
- MUST NOT mark live providers as run.

## Verification

```bash
python3 scripts/check_agent_os_failed_diagnostics_fixture.py --write-output --json
python3 -m pytest -q tests/test_agent_os_failed_diagnostics_fixture.py tests/test_agent_os_execution_prep.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Fixture report verdict is `PASS`.
- `fixture_only=true`.
- `primary_normalized_reason=provider-rate-limit`.
- `raw_snapshot_commit_allowed=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
