# 55 - Agent OS State Stale Cleanup

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture safety

## Objective

Provide a safe operator command for removing stale untracked Agent OS state
diagnostic JSON files after the hygiene guard detects them.

## Scope

The command lives at `scripts/cleanup_agent_os_state_artifacts.py`.
It inspects untracked git porcelain lines and only targets files matching:

- under `run-artifacts/`
- filename starts with `agent-os`
- filename contains `state`
- filename ends with `.json`

It writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json`.

## Required Behavior

- Default mode must be dry-run and must not remove files.
- `--apply` may remove only selected untracked diagnostic candidates.
- Tracked or modified canonical state evidence must never be selected.
- Missing candidates in apply mode must fail closed.
- Output must record candidate count, removed count, blockers, and next command.

## Negative Constraints

- MUST NOT run AO or provider CLIs.
- MUST NOT remove tracked state evidence.
- MUST NOT remove files outside `run-artifacts/`.
- MUST NOT authorize dispatch or mark live providers as run.

## Verification

```bash
python3 scripts/cleanup_agent_os_state_artifacts.py --write-output --json
python3 -m pytest -q tests/test_cleanup_agent_os_state_artifacts.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Cleanup report verdict is `PASS`.
- Dry-run report records `mode=dry-run`.
- `dispatch_authorized=false` and `live_providers_run=false`.
- Targeted tests prove selected diagnostics are removed only with `--apply`.
