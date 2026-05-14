# Agent OS RunSpec AO Preflight Compatibility

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove the rendered Agent OS RunSpec at `ao/runspecs/agent-os-phase-draft.yaml`
is acceptable to AO Runtime by validating it against the canonical AO
`RunSpec` contract extracted directly from
`${FACTORY_V3_AO_RUNTIME_PATH}/crates/ao-core/src/{api_version,run_spec,task}.rs`
at gate time. The gate runs without invoking the AO CLI and without
dispatching providers.

## Scope

- Reads `ao/runspecs/agent-os-phase-draft.yaml`.
- Reads three AO source files to extract the contract:
  - `crates/ao-core/src/api_version.rs` — serde-renamed `ApiVersion` variants.
  - `crates/ao-core/src/run_spec.rs` — `RunSpecKind` variant names.
  - `crates/ao-core/src/task.rs` — `TaskKind` enum (with `rename_all`).
- Writes the durable status artifact at
  `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-ao-preflight-compatibility.json`.
- Schema: `ao-operator/agent-os-runspec-ao-preflight-compatibility/v1`.

## Required Behavior

The gate validates that the parsed RunSpec satisfies, at minimum:

- `apiVersion` is one of the AO `ApiVersion` serde-rename values.
- Top-level `kind` is one of the AO `RunSpecKind` variants.
- `metadata.name` is a non-empty string.
- `spec.tasks` is a non-empty list.
- Every task `id` is a non-empty unique string.
- Every task `kind` is one of the AO `TaskKind` variants (after the
  `rename_all = "lowercase"` transform).
- Every `deps` entry references a known task `id`.
- The DAG is acyclic.

## Mutation Cases

Each of the following mutations is applied to the baseline RunSpec body
and re-evaluated. Every case must report `observed_verdict=FAIL`:

1. `wrong_api_version_refused` — `apiVersion: ao.dev/v1` → `apiVersion: ao.dev/v2`.
2. `wrong_runspec_kind_refused` — top-level `kind: Run` → `kind: Job`.
3. `unknown_task_kind_refused` — first task `kind: agent` → `kind: shellscript`.
4. `unknown_dependency_refused` — first inline `deps: ["…"]` rewritten to point at
   `agent-os-ghost-task` (a task id that does not exist).
5. `dag_cycle_refused` — entry task `agent-os-planner` made to depend on the
   terminal task `agent-os-evaluator-closer`, creating a cycle.

## Negative Constraints

- Do not invoke `ao run` or any other AO subcommand that would dispatch.
- Do not run providers (codex, claude, gemini, …) or the AO daemon.
- Do not modify `ao/runspecs/agent-os-phase-draft.yaml` on disk.
- Do not edit AO source files; the gate only reads them to extract the
  contract.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_runspec_ao_preflight_compatibility.py
python3 scripts/check_agent_os_runspec_ao_preflight_compatibility.py --write-output --json
```

## Acceptance Criteria

- The standalone gate exits `0` with `verdict=PASS`.
- `dispatch_authorized=false` and `live_providers_run=false` are present
  on every emitted record (top-level + each mutation case).
- `mutation_case_count == 5`; every recorded mutation case has
  `observed_verdict == "FAIL"`.
- `task_count == 7` and `task_ids` lists the seven Agent OS roles in DAG
  order.
- `ao_contract.api_versions == ["ao.dev/v1"]`,
  `ao_contract.runspec_kinds == ["Run"]`,
  `ao_contract.task_kinds == ["shell", "agent", "review", "test"]` so long
  as the AO source files declare exactly those serde-renamed variants;
  drift in the AO contract surfaces as a baseline failure.

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-ao-preflight-compatibility.json
```
