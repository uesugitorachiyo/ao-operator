# 02 - Implementation Plan

This is the step-by-step plan to turn the current AO Operator seed into a full
local factory.

## Phase 0 - Preserve Current Baseline

Keep the current working seed:

- Root docs.
- SVG diagrams.
- `.env.example`.
- Role TOMLs.
- AO prompt samples.
- Codex live smoke path.
- `validate_scaffold.py`.
- `factory_doctor.py`.
- `render_runspec.py`.

Do not remove the seed smoke. It remains the fast provider-launch check.

## Phase 1 - Add Task Intake CLI

Add:

```text
scripts/factory_run.py
```

Required arguments:

```text
--brief <path>
--slug <slug>       optional
--dry-run           render artifacts but do not launch AO
--run               launch AO after rendering artifacts
--provider-env <path> optional, defaults to .env
--ao-home <path>      optional, defaults to /tmp/ao-operator-ao-<slug>
```

Behavior:

1. Read the brief.
2. Create a slug from `--slug` or the brief filename.
3. Create a run directory:

   ```text
   run-artifacts/<slug>/
   ```

4. Generate initial spec, plan placeholder, rendered RunSpec, and status file.
5. In `--dry-run`, stop after writing artifacts.
6. In `--run`, execute AO and summarize events.

Exit codes:

- `0`: successful dry-run or accepted run.
- `1`: validation or closure failure.
- `2`: invalid arguments, invalid provider, or missing required input.
- `3`: AO execution failure.

## Phase 2 - Implement Shape-Aware Spec Generation

Add a spec builder module, either inside `factory_run.py` or as:

```text
scripts/factory_lib/specs.py
```

Spec generation must include:

- Title.
- Slug.
- Date.
- Classification.
- Shape.
- Goal.
- Inputs.
- In scope.
- Out of scope.
- Acceptance criteria.
- Scoped reads.
- Scoped writes.
- Negative constraints.
- Sensitive fields.
- Verification plan.

Classification rules for v1:

- `TRIVIAL`: one role, no source mutation, validation-only.
- `MODERATE`: one implementation slice plus review/closure.
- `COMPLEX`: multiple slices, cross-domain work, or factory-of-factories.

Shape rules for v1:

- Default to `greenfield` unless brief explicitly describes fixing existing
  behavior or preserving behavior during structural change.
- If brief says bug, failing, regression, error, broken, or fix, classify as
  `bug-fix`.
- If brief says refactor, reorganize, preserve behavior, cleanup, or migrate
  without behavior change, classify as `refactor`.

The generated spec may be conservative. When required shape evidence is absent,
it must mark execution as blocked.

## Phase 3 - Implement Plan Hardening

Add a plan builder that consumes the spec and produces:

```text
docs/plans/<slug>-plan.md
```

The plan must include:

- Execution mode.
- Role DAG.
- Slice ownership.
- Reads/writes per role.
- Review gates.
- Verification gates.
- Rollback or recovery.
- Provider map.
- Blockers.

Gate behavior:

- `bug-fix` blocks mutator dispatch until reproducer evidence is provided.
- `refactor` blocks mutator dispatch until pinning-suite evidence is provided.
- `greenfield` can proceed when acceptance criteria and scoped writes exist.

## Phase 4 - Materialize Role Prompts

Add prompt materialization:

```text
run-artifacts/<slug>/prompts/<task-id>.md
```

Each prompt must include:

- Role identity.
- Task slug.
- Classification and shape.
- Current artifact paths.
- Scoped reads.
- Scoped writes.
- Required output format.
- Prior artifact summary, if applicable.

Each prompt must exclude:

- Full transcript.
- Secret values.
- Raw environment dump.
- Unbounded repo context.

## Phase 5 - Render Full AO RunSpec

Extend `render_runspec.py` or add a full renderer module.

Inputs:

- Plan artifact.
- Provider env.
- Prompt directory.
- Policy profile.
- Workspace path.

Outputs:

```text
run-artifacts/<slug>/<slug>.runspec.yaml
```

For each role task:

- Resolve provider from `.env`.
- Validate provider is `codex` or `claude`.
- Use provider-specific agent manifest.
- Attach the materialized prompt file.
- Attach dependencies from the plan.

For v1, if Claude execution is not available in AO Runtime, the renderer must
fail when any live task resolves to `claude`, unless the run is `--dry-run`.

## Phase 6 - Execute AO And Capture Events

In `--run` mode:

1. Ensure `AO_HOME` exists or initialize it.
2. Run:

   ```bash
   AO_HOME=<ao-home> <ao-bin> run <runspec>
   ```

3. Capture:

   ```text
   AO run id
   AO run status
   AO events
   task completed/failed events
   agent stdout/stderr event counts
   policy decisions
   ```

4. Write:

   ```text
   run-artifacts/<slug>/<slug>-ao-events.md
   run-artifacts/<slug>/<slug>-status.md
   ```

If AO returns failed, AO Operator must stop before evaluator acceptance and
write a blocked evaluation.

## Phase 7 - Extract Role Artifacts

Parse AO events and create role artifacts:

```text
run-artifacts/<slug>/roles/planner-intake.md
run-artifacts/<slug>/roles/plan-hardener.md
run-artifacts/<slug>/roles/factory-manager.md
run-artifacts/<slug>/roles/implementer-slice.md
run-artifacts/<slug>/roles/reviewer-slice.md
run-artifacts/<slug>/roles/integrator.md
run-artifacts/<slug>/roles/evaluator-closer.md
```

Each artifact must include:

- Result.
- Artifact source.
- Evidence.
- Concerns.
- Blocker.
- Source AO event ids or line references where practical.

## Phase 8 - Durable Evaluator Closure

Create:

```text
docs/evaluations/<slug>-evaluation.md
```

Evaluator accepts only if:

- Spec exists.
- Hardened plan exists.
- AO run completed.
- Required role artifacts exist.
- Required verification passed or blocker is explicit.
- Auth/provider constraints passed.
- No forbidden full-context handoff is detected.

If any criterion fails, write `REJECTED` with blockers.

## Phase 9 - Extend Validation

Extend `validate_scaffold.py` or add:

```text
scripts/validate_factory.py
```

It must verify:

- SDD docs exist.
- Required runtime scripts exist.
- `.env` provider values are valid.
- Prompt templates include scoped-context warnings.
- Generated artifacts for a given slug are complete.
- Evaluator closure exists for completed runs.

## Phase 10 - Full Smoke Tests

Add full smoke commands:

```bash
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --dry-run
python3 scripts/validate_factory.py --slug complex-app-smoke
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --run
```

Expected:

- Dry-run creates artifacts and RunSpec.
- Live run executes AO.
- Status/evaluation artifacts are created.
- Closure is accepted or rejected with explicit evidence.

## Phase 11 - Claude Provider Completion

Current evidence shows Codex live AO execution works. The full implementation
must close the Claude gap.

Accepted outcomes:

1. Implement AO-compatible local Claude provider execution and live-test it.
2. If AO Runtime does not support local `provider: claude`, block live Claude
   runs before AO dispatch with a clear doctor/runtime message.

It is not acceptable to silently substitute Codex for Claude.

## Phase 12 - Documentation Update

Update:

- `README.md`
- `SETUP.md`
- `ao-operator.md`
- `PROMPT_SAMPLES.md`

They must describe AO Operator as a full local factory and link to `docs/sdd/`.

