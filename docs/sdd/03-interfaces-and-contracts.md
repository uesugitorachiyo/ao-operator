# 03 - Interfaces And Contracts

## CLI Contract

### `scripts/factory_run.py`

Purpose: execute the full AO Operator pipeline.

Required mode:

```bash
python3 scripts/factory_run.py --brief <path> --slug <slug> --dry-run
python3 scripts/factory_run.py --brief <path> --slug <slug> --run
```

Arguments:

- `--brief <path>`: required task brief markdown.
- `--slug <slug>`: optional stable artifact slug.
- `--dry-run`: generate artifacts and RunSpec only.
- `--run`: execute AO after rendering.
- `--provider-env <path>`: optional `.env` path.
- `--ao-home <path>`: optional AO state path.
- `--workspace <path>`: optional target workspace, default current root.
- `--topology <path>`: optional AO topology YAML. When supplied, the CLI
  materializes that task graph instead of the baseline seven-role DAG.
- `--contract <path>`: optional Spec Forge contract JSON. If omitted and the
  topology contains `contractFile`, the CLI uses that contract automatically.

`--dry-run` and `--run` are mutually exclusive.

### `scripts/render_runspec.py`

Purpose: low-level RunSpec renderer.

Existing smoke mode remains valid. Full mode should support:

```bash
python3 scripts/render_runspec.py --plan docs/plans/<slug>-plan.md --prompts run-artifacts/<slug>/prompts --output run-artifacts/<slug>/<slug>.runspec.yaml
```

### `scripts/factory_doctor.py`

Purpose: environment and readiness verification.

It must report:

- Provider env validity.
- Forbidden env vars.
- CLI availability.
- AO Runtime path and binary.
- ai-teams source path.
- Claude live AO support status.
- Codex auth status.

### `scripts/validate.py`

Purpose: validate the vendored AO Operator skill package and policy scripts.

It must confirm:

- `skills.toml` is valid.
- Every `skills/*/SKILL.md` has frontmatter, name, and description.
- Every `skills.toml` entry points at an existing skill.
- Policy scripts pass self-tests.

### Skill Policy Scripts

AO Operator vendors the shared policy helpers:

```text
scripts/validate_intake.py
scripts/verify_closure.py
scripts/code_smell_analyzer.py
scripts/install_global.py
```

`install_global.py` may link the local `skills/` package into both Claude Code
and Codex global skill directories, but global install is explicit and not
required for scaffold validation.

## Environment Contract

`.env` provider values:

```dotenv
FACTORY_V3_DEFAULT_PROVIDER=codex
FACTORY_V3_PLANNER_PROVIDER=codex
FACTORY_V3_SPEC_FORGE_PROVIDER=claude
FACTORY_V3_RALPH_LOOP_PROVIDER=claude
FACTORY_V3_PLAN_HARDENER_PROVIDER=claude
FACTORY_V3_FACTORY_MANAGER_PROVIDER=codex
FACTORY_V3_IMPLEMENTER_PROVIDER=codex
FACTORY_V3_SLICE_REVIEWER_PROVIDER=claude
FACTORY_V3_INTEGRATOR_PROVIDER=codex
FACTORY_V3_EVALUATOR_CLOSER_PROVIDER=claude

# Optional exact topology task overrides:
FACTORY_V3_BACKEND_FACTORY_PROVIDER=codex
FACTORY_V3_FRONTEND_FACTORY_PROVIDER=claude
FACTORY_V3_BACKEND_REVIEWER_PROVIDER=claude
```

Valid values:

```text
codex
claude
```

Resolution order:

1. Exact task id variable, for example `FACTORY_V3_BACKEND_FACTORY_PROVIDER`.
2. Role-specific variable, for example `FACTORY_V3_IMPLEMENTER_PROVIDER`.
3. `FACTORY_V3_DEFAULT_PROVIDER`.
4. Topology `provider` field, when present.
5. Built-in default `codex`.

Forbidden env vars:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

If either is present, doctor and live factory run must fail.

## Artifact Contract

Generated artifacts use a stable slug.

Required files for a dry-run:

```text
docs/specs/<slug>-spec.md
docs/plans/<slug>-plan.md
run-artifacts/<slug>/<slug>.runspec.yaml
run-artifacts/<slug>/<slug>-status.md
run-artifacts/<slug>/prompts/*.md
```

Required additional files for a live run:

```text
run-artifacts/<slug>/<slug>-ao-events.md
run-artifacts/<slug>/roles/*.md
run-artifacts/<slug>/patches/*.patch
run-artifacts/<slug>/patches/*.json
docs/evaluations/<slug>-evaluation.md
```

## Spec Contract

Spec frontmatter or header must include:

```text
Slug:
Classification:
Shape:
Status:
```

Body sections:

- Intent.
- Scope.
- Non-goals.
- Acceptance criteria.
- Scoped reads.
- Scoped writes.
- Sensitive fields.
- Negative constraints.
- Verification.
- Shape gate.

## Plan Contract

Plan must include:

- Approach.
- Control gates.
- DAG.
- Role ownership.
- Provider map.
- Artifact handoffs.
- Verification gates.
- Blockers.
- Recovery.

## Prompt Contract

Every generated role prompt must include:

- Scoped context.
- Injected upstream artifact contents where available.
- Embedded task brief.
- Scoped reads and writes.
- Relevant local skill references under `skills/*/SKILL.md`.
- Boundaries and required STATUS block.

## Role Output Contract

Every role artifact must include:

```text
Result: DONE | DONE_WITH_CONCERNS | BLOCKED | REJECTED
Artifact: <path or event reference>
Evidence: <bullet list>
Concerns: <bullet list or none>
Blocker: <required input or none>
```

Role outputs that omit evidence or blocker state are incomplete.

## Patch Bundle Contract

Every mutator task, including `implementer-slice` and topology tasks ending in
`-factory`, must produce runtime capture files:

```text
run-artifacts/<slug>/patches/<task-id>.patch
run-artifacts/<slug>/patches/<task-id>.json
run-artifacts/<slug>/patches/<task-id>-events.txt
```

The JSON metadata records task id, workspace, scoped writes, STATUS capture
state, diff byte count, git status, and the raw task event artifact. Evaluator
closure must reject missing mutator patch bundles, empty mutator patches when an
implementation was expected, missing parseable STATUS, or any role that resolves
to `BLOCKED` or `REJECTED`.

## RunSpec Contract

AO task shape:

```yaml
- id: <role-task-id>
  kind: agent
  deps: [...]
  spec:
    provider: codex | claude
    agent: <provider>-default
    promptFile: <materialized prompt>
    workspace: .
    policyProfile: ao/policy/local-dev.yaml
```

For fan-out:

- Spec Forge must emit the machine-checkable contract before Ralph Loop.
- Ralph Loop must accept readiness before plan-hardener and factory-manager
  dispatch.
- Implementer tasks may run in parallel only with disjoint writes.
- Reviewer tasks depend on their matching implementer task.
- Integrator depends on all accepted review tasks.
- Evaluator depends on integrator.

## Event Summary Contract

Event summary must include:

- Run id.
- Run status.
- Task count.
- Per-task state.
- Policy decisions.
- Provider command.
- Prompt file.
- stdout/stderr event counts.
- Failure reason if any.

## Layered OpenClaw/AO Contract

When AO Operator is invoked through OpenClaw, the integration contract is:

```text
OpenClaw queue item
  -> AO Operator Spec Forge contract and gate report
  -> AO Runtime RunSpec and event stream
  -> AO Operator evaluator report
  -> OpenClaw observe/delivery update
```

OpenClaw queue items must carry a stable slug, source trust label, schedule
metadata, cancellation handle, report delivery target, and either a AO Operator
contract path or enough bounded input for AO Operator to create one.

AO Operator must reject or block before AO provider dispatch when the submitted
item lacks required shape-gate evidence, sensitive-field declarations, trigger
hints, acceptance oracles, or slice read/write ownership.

AO Runtime must expose run id, task state, policy decisions, provider command,
prompt file, workspace, and failure reason as event evidence. AO Operator may
summarize those events, but OpenClaw should observe the AO Operator report rather
than raw provider transcripts.

The reference example is:

```text
${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration
```

## Closure Contract

Evaluation file must include:

```text
Verdict: ACCEPTED | REJECTED
Slug:
AO Run:
Spec:
Plan:
Evidence:
Concerns:
Blockers:
```

No final answer may claim completion unless verdict is `ACCEPTED`.
