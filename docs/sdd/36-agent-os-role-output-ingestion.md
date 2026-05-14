# 36 - Agent OS Role Output Ingestion

Classification: MODERATE
Shape: greenfield

## Scope

This slice ingests Agent OS role outputs from AO-produced role artifact
markdown. It converts the top-level role status fields into
`ao-operator/agent-os-role-output/v1` JSON files, validates the generated JSON
with the role-output schema gate, and updates the execution report with the
ingested role-output paths.

Evaluator acceptance is derived only from the `evaluator-closer` role output.
The ingestion slice is local-only and must not run providers.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_execution_readiness.py
python3 scripts/ingest_agent_os_role_outputs.py --write-output --json
```

## Acceptance Criteria

- Markdown role artifacts are converted to schema-valid JSON role outputs.
- `evaluator_accepted=true` only when `evaluator-closer` has an accepted result
  and no blocker.
- Missing or blocked evaluator output fails closure readiness.
- The execution report is updated with `role_outputs` and
  `role_outputs_ingested`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
