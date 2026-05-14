# 90 - Agent OS RunSpec DAG Edge Coverage

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture implementation hardening

## Objective

Prove the rendered Agent OS RunSpec dependency DAG is aligned with the
versioned role graph before changing role graph, router, state, or RunSpec
generation internals.

## Scope

The gate lives at `scripts/check_agent_os_runspec_dag_edge_coverage.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-dag-edge-coverage.json`

## Required Behavior

- Validate a single entry task and a single terminal task.
- Validate the RunSpec direct dependency edges match role graph edges.
- Validate the topological task order matches role graph role order.
- Validate unknown dependency, cycle, missing edge, duplicate entry, and
  terminal fork mutations fail closed.
- Keep all checks non-dispatching.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT materialize approval files.
- MUST NOT treat edge drift as a warning.
- MUST NOT allow architecture implementation to proceed when this gate fails.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_runspec_dag_edge_coverage.py
python3 scripts/check_agent_os_runspec_dag_edge_coverage.py --write-output --json
python3 scripts/check_operator_guardrail_summary.py --write-output --json
python3 scripts/check_release_artifact_index.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `task_count=7`.
- `edge_count=6`.
- `role_graph_alignment=true`.
- `entry_task_ids=["agent-os-planner"]`.
- `terminal_task_ids=["agent-os-evaluator-closer"]`.
- `mutation_case_count=5`.
- Every mutation case observes `FAIL`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
