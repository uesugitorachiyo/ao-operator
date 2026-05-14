# 93 - Agent OS RunSpec YAML Schema/Format Failure Injection

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS architecture implementation hardening

## Objective

Prove that byte-level malformations of the committed Agent OS RunSpec YAML are
refused fail-closed before they can reach the renderer, validator, role graph,
or AO Runtime. SDD 91 (DAG parity) and SDD 92 (semantic parity) protect the
*shape* and *contents* of a well-formed RunSpec; this gate protects the
*structure* of the YAML file itself.

## Scope

The gate lives at `scripts/check_agent_os_runspec_yaml_schema_injection.py`.

It reads:

- `ao/runspecs/agent-os-phase-draft.yaml`

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-yaml-schema-injection.json`

The gate is fully self-contained: it parses YAML with a minimal indent-based
parser specific to the RunSpec shape, then applies schema rules. It MUST NOT
import AO Runtime, invoke any provider CLI, or materialize approval files.

## Required Behavior

The committed RunSpec YAML MUST satisfy every rule below.

Top-level structure:

- Root MUST be a mapping with allowed keys
  `{apiVersion, kind, metadata, spec}` and required keys
  `{apiVersion, kind, spec}`.
- `apiVersion` MUST equal `ao.dev/v1`.
- `kind` MUST equal `Run`.
- `metadata` (when present) MUST be a mapping with allowed keys
  `{name, description}` and required key `{name}`.

Spec block:

- `spec` MUST be a mapping with allowed key `{tasks}` and required key `{tasks}`.
- `spec.tasks` MUST be a non-empty list.

Task entries:

- Each task MUST be a mapping with allowed keys `{id, kind, deps, spec}` and
  every one of those keys MUST be present.
- `task.id` MUST be a non-empty string.
- `task.kind` MUST equal `agent`.
- `task.deps` MUST be a list of non-empty strings.
- Task ids MUST be unique across the task list.

Task spec block:

- `task.spec` MUST be a mapping with allowed and required keys
  `{provider, agent, promptFile, workspace, policyProfile, dispatchAuthorized}`.
- `task.spec.dispatchAuthorized` MUST equal `false`.

Format-level rules:

- The YAML body MUST contain no tab characters.
- Every significant line MUST have balanced single- and double-quotes.

Mutation cases that MUST fail closed:

1. `malformed_yaml_refused` — unbalanced quote / tab character.
2. `duplicate_task_ids_refused` — two tasks share the same id.
3. `missing_spec_block_refused` — a task is missing its `spec:` block.
4. `bad_deps_type_refused` — a task's `deps` is a scalar instead of a list.
5. `unknown_task_field_refused` — a task carries an unrecognized top-level key.
6. `unsafe_dispatch_authorized_refused` — a task sets `dispatchAuthorized: true`.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT materialize approval files.
- MUST NOT treat schema/format violations as warnings.
- MUST NOT allow architecture implementation to proceed when this gate fails.
- `dispatch_authorized` and `live_providers_run` MUST remain `false` in the
  emitted artifact.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_runspec_yaml_schema_injection.py
python3 scripts/check_agent_os_runspec_yaml_schema_injection.py --write-output --json
python3 scripts/check_operator_guardrail_summary.py --write-output --json
python3 scripts/check_release_artifact_index.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `task_count = 7`.
- `task_ids` matches the renderer task ids in canonical order.
- `baseline_errors` is empty.
- `mutation_case_count = 6`.
- Every entry in `mutation_cases` has `observed_verdict = FAIL`.
- `mutation_case_ids` is exactly `["malformed_yaml_refused",
  "duplicate_task_ids_refused", "missing_spec_block_refused",
  "bad_deps_type_refused", "unknown_task_field_refused",
  "unsafe_dispatch_authorized_refused"]`.
- `allowed_top_keys = ["apiVersion", "kind", "metadata", "spec"]`.
- `allowed_task_keys = ["id", "kind", "deps", "spec"]`.
- `allowed_task_spec_keys =
  ["provider","agent","promptFile","workspace","policyProfile","dispatchAuthorized"]`.
- `dispatch_authorized = false`.
- `live_providers_run = false`.
