# Agent OS Router Migration Matrix

## Classification

- Size: MODERATE
- Shape: refactor
- Live provider: false
- Dispatch authorized: false

## Goal

Prove Agent OS router state can move between v1 and v2 compatibility baselines
without stale dispatch flags, lost blockers, or schema drift before deeper
router and RunSpec architecture changes.

## Matrix Cases

- Router v1 state migrates to state v2.
- Router v2 state reloads through the state-v2 normalizer.
- Stale v2 `dispatch_authorized=true` and `live_providers_run=true` are reset.
- Live-provider route blockers survive migration.
- Invalid state schema fails closed.
- Missing architecture readiness fails closed for router v2 output.

## Negative Constraints

- Do not run AO.
- Do not run live providers.
- Do not authorize dispatch from any matrix case.
- Do not allow stale v2 flags to survive normalization.
- Do not continue architecture implementation if invalid schema or missing
  readiness passes open.

## Verification

```bash
python3 scripts/check_agent_os_router_migration_matrix.py --write-output --json
python3 -m pytest -q tests/test_agent_os_router_migration_matrix.py
python3 scripts/validate_factory.py --json
```
