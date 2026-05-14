# 04 - Verification Plan

## Existing Baseline Checks

These checks must continue to pass:

```bash
python3 scripts/validate_scaffold.py
python3 scripts/factory_doctor.py
python3 scripts/render_runspec.py --output /tmp/ao-operator-smoke.yaml
```

Expected:

- Scaffold validation passes.
- Doctor passes in clean OAuth CLI environment.
- Rendered RunSpec defaults to Codex.

## Negative Provider Tests

Invalid provider:

```bash
tmp=$(mktemp)
printf 'FACTORY_V3_DEFAULT_PROVIDER=bad\n' > "$tmp"
python3 scripts/render_runspec.py --env "$tmp" --output /tmp/should-not-render.yaml
```

Expected exit code: `2`.

Forbidden env:

```bash
env OPENAI_API_KEY '[dummy blocked value]' python3 scripts/factory_doctor.py
env ANTHROPIC_API_KEY '[dummy blocked value]' python3 scripts/factory_doctor.py
```

Expected: fail.

## SDD Package Checks

Add validation that confirms:

- `docs/sdd/README.md` exists.
- `docs/sdd/01-architecture.md` exists.
- `docs/sdd/02-implementation-plan.md` exists.
- `docs/sdd/03-interfaces-and-contracts.md` exists.
- `docs/sdd/04-verification-plan.md` exists.
- `docs/sdd/05-rollout-and-risks.md` exists.
- Root README links to `docs/sdd/`.
- `ao-operator.md` states the SDD is the implementation source of truth.

## Dry-Run Full Factory Tests

Command:

```bash
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --dry-run
```

Expected files:

```text
docs/specs/complex-app-smoke-spec.md
docs/plans/complex-app-smoke-plan.md
run-artifacts/complex-app-smoke/complex-app-smoke.runspec.yaml
run-artifacts/complex-app-smoke/complex-app-smoke-status.md
run-artifacts/complex-app-smoke/prompts/planner-intake.md
run-artifacts/complex-app-smoke/prompts/plan-hardener.md
run-artifacts/complex-app-smoke/prompts/factory-manager.md
run-artifacts/complex-app-smoke/prompts/implementer-slice.md
run-artifacts/complex-app-smoke/prompts/reviewer-slice.md
run-artifacts/complex-app-smoke/prompts/integrator.md
run-artifacts/complex-app-smoke/prompts/evaluator-closer.md
```

Assertions:

- Spec has classification and shape.
- Plan has provider map.
- RunSpec references materialized prompt files.
- Prompts do not contain full transcripts.
- No forbidden env values are written.

## Live Codex Full Factory Test

Command:

```bash
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --run --ao-home /tmp/ao-operator-complex-app-smoke
```

Expected:

- AO run completes or fails with explicit role evidence.
- Status artifact records AO run id.
- Event summary artifact exists.
- Role artifacts exist.
- Evaluation artifact exists.
- If accepted, evaluator evidence references spec, plan, AO run, and role
  artifacts.

## Claude Provider Test

Create a temporary provider env:

```dotenv
FACTORY_V3_DEFAULT_PROVIDER=codex
FACTORY_V3_SLICE_REVIEWER_PROVIDER=claude
FACTORY_V3_EVALUATOR_CLOSER_PROVIDER=claude
```

Expected until Claude AO path is implemented:

- Dry-run rendering succeeds.
- Live run executes through AO as `provider: claude` when Claude Code OAuth is
  available.

Silent substitution to Codex is a failure.

## Topology Fan-Out Test

Command:

```bash
python3 scripts/factory_run.py --brief examples/outperform-ai-teams-fanout/task-brief.md --slug outperform-ai-teams-fanout --provider-env examples/outperform-ai-teams-fanout/provider.env --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --dry-run
python3 scripts/validate_factory.py --slug outperform-ai-teams-fanout --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --contract examples/outperform-ai-teams-fanout/spec-forge.contract.json
```

Expected:

- Spec shape is `greenfield`.
- Plan includes Spec Forge and Ralph Loop control gates.
- RunSpec includes all 17 topology tasks.
- Prompt directory contains the topology task prompts without stale baseline
  prompts.
- Validator confirms five factory branches, five reviewer branches, integrator
  fan-in, and Spec Forge contract fields.

## Shape Gate Tests

Bug-fix brief without reproducer:

- Dry-run spec may be generated.
- Live mutator dispatch must block.
- Evaluation must be rejected or blocked with missing reproducer.

Refactor brief without pinning suite:

- Dry-run spec may be generated.
- Live mutator dispatch must block.
- Evaluation must be rejected or blocked with missing pinning suite.

Greenfield brief with acceptance criteria:

- Live execution may proceed.

## Closure Tests

For any live run:

- Missing evaluator file means failure.
- Evaluator `REJECTED` means final command exits non-zero.
- Evaluator `ACCEPTED` means final command exits zero.
- AO completed without evaluator acceptance is not enough.

## Regression Checks

After implementation, run:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/validate_scaffold.py
python3 scripts/validate_factory.py --slug complex-app-smoke
python3 scripts/validate_factory.py --slug outperform-ai-teams-fanout --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --contract examples/outperform-ai-teams-fanout/spec-forge.contract.json
python3 scripts/factory_doctor.py
```

If working from the ai-teams source repo, also run:

```bash
python3 scripts/verify_closure.py --repo . --with-pytest --json
```
