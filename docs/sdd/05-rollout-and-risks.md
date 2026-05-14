# 05 - Rollout And Risks

## Rollout Phases

### Phase A - SDD Complete

Acceptance:

- Full SDD package exists under `docs/sdd/`.
- Root docs link to it.
- Existing scaffold checks still pass.

### Phase B - Dry-Run Factory

Acceptance:

- `factory_run.py --dry-run` creates spec, plan, prompts, status, and RunSpec.
- Generated prompts are scoped.
- Provider resolution is enforced.
- Shape gates are represented.

### Phase C - Live Codex Factory

Acceptance:

- `factory_run.py --run` executes AO with Codex provider roles.
- AO events are summarized.
- Role artifacts are extracted.
- Evaluation artifact is written.
- Completion depends on evaluator verdict.

### Phase D - Mixed Provider Readiness

Acceptance:

- Mixed-provider dry-run works.
- Claude live execution is either implemented and tested or blocked before AO
  dispatch with an explicit unsupported-provider message.
- No silent fallback from Claude to Codex exists.

### Phase E - Factory-Of-Factories

Acceptance:

- Multiple independent implementer branches can be represented.
- Disjoint write ownership is required.
- Integrator fan-in is explicit.
- Evaluator closure remains mandatory.

## Known Risks

### AO Claude Provider Gap

Current observed behavior indicates Codex live AO execution works. Local Claude
provider execution may not be wired in the current AO daemon path.

Mitigation:

- Keep `.env` rendering for Claude.
- Block live Claude roles until an AO-compatible execution path is implemented.
- Document the provider status in `factory_doctor.py`.

### Prompt Overreach

Agents may inspect too much context if prompts are loose.

Mitigation:

- Materialize scoped prompts.
- Include explicit no-full-transcript constraints.
- Validate generated prompt size and forbidden content.

### False Completion

AO can complete a DAG even if evaluator text rejects the task.

Mitigation:

- Parse evaluator artifact.
- Treat only explicit `Verdict: ACCEPTED` as success.
- Exit non-zero on missing or rejected evaluation.

### Weak Shape Gates

Bug-fix and refactor tasks can be unsafe without reproducer or pinning evidence.

Mitigation:

- Block mutator dispatch when gates are missing.
- Write blocked evaluation with exact missing evidence.

### API-Key Regression

Docs or scripts could accidentally reintroduce provider API-key paths.

Mitigation:

- Doctor fails on `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Validation searches docs/scripts for API-key setup language.
- Setup docs state OAuth CLI only.

### Artifact Drift

Spec, plan, RunSpec, and status files can disagree.

Mitigation:

- Use a single slug.
- Generate artifacts in one run directory.
- Include artifact path references in all downstream prompts.
- Add validation that checks slug and provider consistency.

## Fallback Behavior

- Invalid provider: fail before rendering or dispatch.
- Forbidden env var: fail doctor and live run.
- Missing AO binary: fail doctor and live run.
- Missing Codex auth: fail doctor when Codex is selected.
- Missing Claude live support: fail live run before AO dispatch.
- AO run failed: write rejected evaluation with AO failure reason.
- Evaluator rejected: command exits non-zero.

## Acceptance Gates For Full Factory v1

Factory v1 is accepted only when:

- Full SDD package exists and is linked.
- Dry-run full factory works.
- Live Codex full factory works.
- Provider validation works.
- API-key rejection works.
- Shape-gate blocking works.
- Evaluator closure controls final success.
- Generated prompts remain scoped.

