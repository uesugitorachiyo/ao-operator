# 44 - Agent OS Role Graph And State Versioning

Classification: MODERATE
Shape: refactor

## Scope

This slice records a deterministic Agent OS role graph and a v2 state schema
baseline before AO Operator changes router, state, role graph, or RunSpec
architecture. It reads the existing Agent OS capability contract and emits a
non-dispatching compatibility artifact that names core roles, dependency edges,
state schema version, and next safe architecture command.

AO Runtime remains the execution substrate. This slice is local validation
only; it does not render a new live RunSpec, launch providers, or authorize
execution.

## Inputs

- Capability contract:
  `docs/contracts/ao-operator-agent-capabilities.json`
- Prior Agent OS state SDD:
  `docs/sdd/14-agent-os-mission-router-state.md`
- Role graph script:
  `scripts/agent_os_role_graph.py`

## Outputs

- Role graph evidence:
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`

The output schema is `ao-operator/agent-os-role-graph/v1`. The linked state
schema is `ao-operator/agent-os-state/v2`.

## Required Behavior

- Build the graph deterministically from the core role order:
  planner, plan-hardener, factory-manager, implementer, slice-reviewer,
  integrator, evaluator-closer.
- Preserve exactly one forward dependency edge between adjacent core roles.
- Reject missing core roles with a fail-closed verdict.
- Preserve `dispatch_authorized=false`.
- Preserve `live_providers_run=false`.
- Migrate v1 Agent OS state snapshots to v2 without trusting any prior
  dispatch flag.

## Negative Constraints

- MUST NOT run AO providers.
- MUST NOT change existing role behavior.
- MUST NOT authorize Agent OS RunSpec execution.
- MUST NOT treat v1 state dispatch flags as valid approval.
- MUST NOT depend on local-only untracked evidence.
- MUST NOT require the detached `llm-wiki` checkout.

## Verification

Run these commands before accepting the slice:

```bash
python3 -m pytest -q tests/test_agent_os_role_graph.py
python3 scripts/agent_os_role_graph.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

The slice is accepted only when all commands pass and the generated role graph
reports:

- `verdict=PASS`
- `state_schema_version=ao-operator/agent-os-state/v2`
- `dispatch_authorized=false`
- `live_providers_run=false`

## Acceptance Criteria

- The role graph artifact is committed and clean-clone visible.
- The operator slice manifest includes a non-live role graph state-versioning
  slice.
- Factory validation treats this SDD and script as required source-of-truth
  files.
- PR readiness compiles `scripts/agent_os_role_graph.py`.
- Future router/RunSpec architecture changes can reference this artifact as a
  compatibility baseline.
