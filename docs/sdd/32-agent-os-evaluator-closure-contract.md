# 32 - Agent OS Evaluator Closure Contract

Classification: MODERATE
Shape: greenfield

## Scope

This slice defines deterministic evaluator closure for future Agent OS RunSpec
execution evidence. It is distinct from generic AO Operator closure and requires
completed AO execution plus evaluator acceptance.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/validate_agent_os_runspec_evaluator_closure.py --write-output --json
```

## Acceptance Criteria

- Accepted execution requires `ao_completed=true`.
- Accepted execution requires `evaluator_accepted=true`.
- Failed, blocked, or pending execution cannot authorize closure.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
