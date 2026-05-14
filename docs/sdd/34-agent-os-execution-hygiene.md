# 34 - Agent OS Execution Hygiene

Classification: MODERATE
Shape: greenfield

## Scope

This slice checks generated prompts and future role outputs for unsafe context
leakage: full transcripts, provider secret markers, stale `llm-wiki` references,
and injected memory context blocks.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/check_agent_os_execution_hygiene.py --prompt ao/prompts/agent-os-phase/01-planner.md --write-output --json
```

## Acceptance Criteria

- Secret markers fail validation.
- Full transcript payloads fail validation.
- Stale memory or detached wiki context markers fail validation.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
