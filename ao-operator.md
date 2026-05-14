# AO Operator Architecture

> GitHub repo slug: `ao-operator`. Legacy compatibility slug: `ao-operator`.
> Formerly known as "AO Operator" / "Plain Factory".

AO Operator moves agent-workflow orchestration from prompt-governed convention
to executable orchestration. The full implementation source of truth is the SDD
package under `docs/sdd/`.

## Composition

- ai-teams is the operating discipline: role contracts, shape gates, artifact
  conventions, and evidence-first closure. AO Operator vendors the
  needed profiles, roles, skills, and prompts in this repo; no separate
  `ai-teams` checkout is required to operate it.
- AO Runtime provides DAG scheduling, policy evaluation, provider launch,
  event logs, workspace isolation, and artifacts.
- AO Operator binds them with a deterministic Operator Runner
  (`scripts/factory_run.py`, retained as the legacy script name) that
  accepts task briefs, generates artifacts, renders provider-aware `RunSpec`
  files from `.env`, executes AO, summarizes events, and requires evaluator
  closure.

## Control Plane Boundary

AO Operator uses a deterministic runner outside the agent DAG and
bounded agentic roles inside the DAG.

```text
Human/operator
  -> Operator Runner (`scripts/factory_run.py`)
    -> AO Runtime
      -> planner / hardener / factory-manager / implementer / reviewer / integrator / evaluator
```

- **Control plane:** `scripts/factory_run.py` and its helper modules. The
  runner classifies task shape, resolves providers, materializes prompts,
  renders RunSpecs, invokes AO Runtime, collects events, writes evidence, and
  enforces closure gates.
- **Execution plane:** AO Runtime. AO schedules the DAG, launches provider
  adapters, applies policy, records events, isolates workspaces, and stores
  artifacts.
- **Agent plane:** role prompts and profiles. Agents reason inside scoped
  roles; they may recommend fan-out, integration, or closure outcomes, but the
  runner materializes and enforces the actual control decisions.

There is no outer "orchestrator agent." The `factory-manager` role is a DAG
participant, not the process that launches or accepts the run.

## Default Lifecycle

```text
planner-intake
  -> plan-hardener
  -> factory-manager
  -> implementer-slice
  -> reviewer-slice
  -> integrator
  -> evaluator-closer
```

For larger work, the `factory-manager` role may fan out independent work
branches, such as frontend, backend, and quality lanes. AO owns dependency
ordering and fan-in.

## Task Shapes

- `greenfield`: new behavior or scaffolded capability.
- `bug-fix`: existing defect; requires a reproducer and red-to-green evidence.
- `refactor`: behavior-preserving structural change; requires a pinning suite
  and expected-diff boundaries.

## Handoff Model

Roles pass:

- Scoped prompt context.
- Declared reads and writes.
- Durable artifacts.
- Verification evidence.
- Concerns and blockers.

They do not pass whole conversation histories.
