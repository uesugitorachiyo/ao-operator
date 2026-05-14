# 33 - Agent OS Role Output Schema

Classification: MODERATE
Shape: greenfield

## Scope

This slice validates Agent OS role-output packets. Every role output must carry
the status fields `Result`, `Artifact`, `Evidence`, `Concerns`, and `Blocker`,
and must not include full transcript payloads.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/check_agent_os_role_output_schema.py --write-output --json
```

## Acceptance Criteria

- Role output validator emits schema
  `ao-operator/agent-os-role-output-schema-validation/v1`.
- Missing required fields fail validation.
- Full transcript payloads fail validation.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
