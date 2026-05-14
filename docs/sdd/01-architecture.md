# 01 - Architecture

## Intent

AO Operator is a local AO-backed software factory. It converts a user task brief
into a verified software-factory run with durable artifacts.

The user-facing promise:

```text
brief -> spec -> hardened plan -> AO DAG execution -> review/integration -> evaluator closure
```

The implementation must make this executable, not merely documented.

## System Planes

### 1. Intake Plane

Input is a user-authored task brief file.

The intake plane:

- Reads the brief.
- Assigns a stable task slug.
- Classifies task size: `TRIVIAL`, `MODERATE`, or `COMPLEX`.
- Classifies task shape: `greenfield`, `bug-fix`, or `refactor`.
- Creates the initial spec artifact.

Output:

```text
docs/specs/<slug>-spec.md
```

### 2. Planning Plane

The planning plane turns the spec into an execution-ready plan.

It must define:

- Goal and acceptance criteria.
- Scoped reads and writes.
- Negative constraints.
- Sensitive fields.
- Trigger hints.
- Shape gates.
- Verification commands.
- Rollback or recovery notes.

Output:

```text
docs/plans/<slug>-plan.md
```

### 3. AO Execution Plane

AO Runtime executes role tasks as a DAG.

Default local full-factory DAG:

```text
planner-intake
  -> plan-hardener
  -> factory-manager
  -> implementer-slice(s)
  -> reviewer-slice(s)
  -> integrator
  -> evaluator-closer
```

Topology-driven complex application DAG:

```text
planner-intake
  -> spec-forge-contract
  -> ralph-loop
  -> plan-hardener
  -> factory-manager
  -> parallel factory branches
  -> parallel reviewer branches
  -> integrator
  -> evaluator-closer
```

When `--topology` is supplied, AO Operator materializes the topology task list
instead of the baseline DAG. The topology may also point at a Spec Forge
contract file; that contract becomes a required handoff artifact for prompts,
plans, status, and validation.

AO is responsible for:

- Dependency ordering.
- Local provider launch.
- Policy decisions.
- Event logs.
- Task success/failure state.

AO Operator is responsible for:

- Rendering correct RunSpecs.
- Creating scoped prompts.
- Supplying provider-specific manifests.
- Summarizing AO events into durable artifacts.
- Enforcing closure rules.

Outputs:

```text
run-artifacts/<slug>-status.md
docs/evaluations/<slug>-evaluation.md
```

### 4. Artifact Handoff Plane

Every role must produce an artifact. Downstream roles receive scoped summaries
and artifact paths, not full transcripts.

AO Operator materializes role prompts with selected upstream artifact contents
when those artifacts are available before dispatch. At minimum, downstream
prompts receive the generated spec, hardened plan, configured contract, prior
role artifact paths, expected patch bundle paths, and bounded role instructions.

Allowed handoff inputs:

- Task slug.
- Role name.
- Shape and classification.
- Relevant spec/plan sections.
- Prior role artifact summary.
- File paths to prior artifacts.
- Verification evidence.

Forbidden handoff inputs:

- Full conversation dumps.
- Raw provider transcripts except as AO event evidence.
- Secret values.
- API keys.
- Unbounded repository context.

### 5. Closure Plane

Evaluator closure is mandatory.

Completion requires:

- AO run completed.
- Required artifacts exist.
- Verification commands ran or a blocker is explicit.
- Evaluator accepted the result.
- Remaining concerns are documented.

AO task completion alone is not completion.

Mutator completion also requires runtime capture:

- Isolated workspace or worktree metadata.
- Raw task-scoped AO events.
- Parseable role STATUS, or an explicit degraded fallback.
- Patch bundle from git diff.
- Write-scope and verification evidence.

## Provider Model

AO Operator supports per-role and exact per-agent provider selection through
`.env`. A topology task such as `backend-factory` may use
`FACTORY_V3_BACKEND_FACTORY_PROVIDER=codex` or
`FACTORY_V3_BACKEND_FACTORY_PROVIDER=claude`; if that exact key is absent, the
role-level implementer setting applies.

Valid providers:

```text
codex
claude
```

Provider semantics:

- `codex`: local Codex CLI with OAuth/subscription auth.
- `claude`: local Claude Code CLI with OAuth auth.

Forbidden:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- Any provider API-key fallback.

If a role resolves to a provider that is not live-capable in the current AO
Runtime checkout, AO Operator must fail clearly before execution or route through
an implemented AO-compatible provider path. It must not silently downgrade to a
different provider.

Mixed Codex/Claude profiles are examples only. The architecture must also
support all-Codex and all-Claude profiles.

## Shape Gates

### Greenfield

Required before implementation:

- Concrete outcome.
- In/out of scope.
- Acceptance criteria.
- Verification commands.
- Scoped writes.

### Bug Fix

Required before fixer dispatch:

- Failing reproducer on current HEAD.
- Suspect ranking.
- Blast-radius note.
- Red-to-green verification plan.

### Refactor

Required before refactor dispatch:

- Pinning suite green on current HEAD.
- Expected-diff allowlist.
- Revertible slice plan.
- Behavior-preservation check.

## Data Flow

```text
brief file
  -> spec artifact
  -> hardened plan artifact
  -> role prompt materialization
  -> rendered RunSpec
  -> AO events
  -> role status artifacts
  -> integration summary
  -> evaluator report
```

Each generated artifact must include the task slug and role or phase name.

## Factory-Of-Factories

For complex application work, AO Operator may create sibling factory branches
only when:

- Spec Forge has emitted machine-checkable SHALLs, acceptance criteria,
  sensitive fields, negative constraints, and slice read/write ownership.
- Ralph Loop has accepted the contract before factory-manager dispatch.
- Slices have disjoint write ownership.
- Integration points are explicit.
- Each branch has its own review gate.
- Fan-in occurs through integrator and evaluator-closer.

Example branches:

```text
frontend-factory
backend-factory
quality-factory
```

The baseline implementation keeps a single implementer slice by default, while
the topology path supports a 17-task factory-of-factories run for the
`examples/outperform-ai-teams-fanout` workload.

## Layered Runtime Ownership

The recommended production boundary is layered:

```text
OpenClaw:  submit / schedule / observe
AO Operator: contract / gate / route / evaluate / report
AO Runtime: execute providers / enforce policy / emit events
```

OpenClaw is the user and automation surface. It owns chat, cron, webhooks,
approvals, cancellation, delivery, and status observation. It does not expand
implementation prompts or launch Codex/Claude providers directly.

AO Operator is the factory brain. It owns Spec Forge, Ralph Loop, shape gates,
slice ownership, provider routing, artifact handoffs, evaluator closure, and
compact reports back to OpenClaw.

AO Runtime is the execution substrate. It owns DAG execution, provider launch,
policy decisions, workspace boundaries, task state, and event logs. It should
not become the source of product or factory semantics.

The Hermes queue pattern remains useful as a throughput mechanic: durable queue
items, atomic claims, isolated workers, and morning reports. AO Operator should
reuse that queue discipline only after AO Operator gates have accepted the work
item. Scheduled work that bypasses the AO Operator contract and closure gates is
not considered a AO Operator run.

The concrete AO Runtime example for this boundary lives at:

```text
${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration
```
