# 92 - Agent OS RunSpec YAML Semantic Parity

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture implementation hardening

## Objective

Prove the committed Agent OS RunSpec YAML carries the same per-task semantic
fields as the renderer JSON before changing role graph, router, state, or
RunSpec generation internals. DAG parity (SDD 91) protects task ids and edges;
this gate protects task semantics.

## Scope

The gate lives at `scripts/check_agent_os_runspec_yaml_semantic_parity.py`.

It reads:

- `ao/runspecs/agent-os-phase-draft.yaml`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-yaml-semantic-parity.json`

## Required Behavior

For every task that exists in both the YAML and the renderer JSON, the
following fields MUST match exactly:

- `provider`
- `promptFile`
- `workspace`
- `policyProfile`
- `kind`
- `dispatchAuthorized`

Additional behavior:

- `dispatchAuthorized` MUST remain `false` for every task.
- The set of YAML task ids MUST match the renderer task ids.
- Provider drift, prompt drift, workspace drift, policy drift, task kind drift,
  and `dispatchAuthorized=true` mutations MUST fail closed.
- All checks MUST stay non-dispatching.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT materialize approval files.
- MUST NOT treat semantic drift as a warning.
- MUST NOT allow architecture implementation to proceed when this gate fails.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_runspec_yaml_semantic_parity.py
python3 scripts/check_agent_os_runspec_yaml_semantic_parity.py --write-output --json
python3 scripts/check_operator_guardrail_summary.py --write-output --json
python3 scripts/check_release_artifact_index.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `task_count=7`.
- `renderer_task_count=7`.
- `common_task_count=7`.
- `aligned_task_count=7`.
- `drifted_task_count=0`.
- `all_aligned=true`.
- `fields_checked` is `["provider","promptFile","workspace","policyProfile","kind","dispatchAuthorized"]`.
- Every entry in `field_drift` is empty.
- `mutation_case_count=6`.
- Every mutation case observes `FAIL`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
