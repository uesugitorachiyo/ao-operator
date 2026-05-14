# 06 - Implementation Checklist

Use this checklist to track AO Operator from the current seed to a full local
AO-backed factory.

## SDD Completion

- [x] `docs/sdd/README.md` exists and links all SDD documents.
- [x] `docs/sdd/01-architecture.md` defines the full local factory
      architecture.
- [x] `docs/sdd/02-implementation-plan.md` defines step-by-step implementation.
- [x] `docs/sdd/03-interfaces-and-contracts.md` defines CLI, artifact, RunSpec,
      role-output, and closure contracts.
- [x] `docs/sdd/04-verification-plan.md` defines deterministic tests.
- [x] `docs/sdd/05-rollout-and-risks.md` defines rollout phases and risks.
- [x] `docs/sdd/06-implementation-checklist.md` exists.
- [x] Root `README.md` links to `docs/sdd/`.
- [x] `ao-operator.md` names `docs/sdd/` as implementation source of truth.

## Baseline Preservation

- [x] Existing scaffold files remain present.
- [x] `README.md` embeds `images/ao-operator-architecture.svg`.
- [x] `.env.example` includes all role provider selectors.
- [x] `skills/` vendors the shared factory skills needed for intake, Spec
      Forge, context offload, closure verification, and mission monitor
      operations.
- [x] `skills.toml` tracks the vendored skill inventory.
- [x] Skill policy scripts are available under `scripts/`.
- [x] `docs/knowledge/README.md` defines the external knowledge boundary.
- [x] Valid providers are only `codex` and `claude`.
- [x] `OPENAI_API_KEY` is forbidden.
- [x] `ANTHROPIC_API_KEY` is forbidden.
- [x] Existing Codex live smoke path still works.

## Runtime CLI

- [x] `scripts/factory_run.py` exists.
- [x] `scripts/factory_run.py --brief <file> --slug <slug> --dry-run` works.
- [x] `scripts/factory_run.py --brief <file> --slug <slug> --run` works for
      Codex-selected roles.
- [x] CLI rejects missing brief files.
- [x] CLI rejects invalid provider values.
- [x] CLI fails when forbidden provider API-key env vars are present.
- [x] CLI exits non-zero when evaluator closure rejects the run.
- [x] CLI materializes a topology-driven DAG when `--topology` is supplied.
- [x] CLI infers a Spec Forge contract from topology `contractFile` when
      `--contract` is omitted.

## Generated Artifacts

- [x] Dry-run creates `docs/specs/<slug>-spec.md`.
- [x] Dry-run creates `docs/plans/<slug>-plan.md`.
- [x] Dry-run creates `run-artifacts/<slug>/<slug>.runspec.yaml`.
- [x] Dry-run creates `run-artifacts/<slug>/<slug>-status.md`.
- [x] Dry-run creates materialized prompts under
      `run-artifacts/<slug>/prompts/`.
- [x] Topology dry-run removes stale generated prompts before writing the
      selected task graph.
- [x] Live run creates `run-artifacts/<slug>/<slug>-ao-events.md`.
- [x] Live run creates role artifacts under `run-artifacts/<slug>/roles/`.
- [x] Live run creates `docs/evaluations/<slug>-evaluation.md`.

## Shape Gates

- [x] Greenfield tasks require outcome, scope, acceptance criteria, and scoped
      writes.
- [x] Bug-fix tasks require failing reproducer evidence before mutator dispatch.
- [x] Bug-fix closure requires red-to-green evidence.
- [x] Refactor tasks require pinning suite evidence before mutator dispatch.
- [x] Refactor closure requires behavior-preservation evidence.
- [x] Missing shape gate evidence produces a blocked evaluation.
- [x] Explicit `Shape: greenfield`, `Shape: bug-fix`, or `Shape: refactor`
      wording takes precedence over keyword heuristics in task briefs.

## Spec Forge And Ralph Loop

- [x] Example topology includes `spec-forge-contract` before `ralph-loop`.
- [x] Example topology includes `ralph-loop` before `plan-hardener`.
- [x] Example Spec Forge contract declares SHALLs, acceptance criteria,
      sensitive fields, negative constraints, and slice read/write ownership.
- [x] Validator checks the topology, contract, five factory branches, five
      reviewer branches, integrator fan-in, and generated RunSpec task list.

## Layered OpenClaw/AO Architecture

- [x] Recommended ownership boundary is documented in
      `docs/sdd/01-architecture.md`.
- [x] Interface contract for OpenClaw queue item, AO Operator gates, AO events,
      and AO Operator report is documented in
      `docs/sdd/03-interfaces-and-contracts.md`.
- [x] AO Operator mirror exists at `examples/layered-openclaw-ao/`.
- [x] AO Runtime example exists at
      `${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration`.
- [x] AO Runtime example includes a contract, RunSpec, prompts, expected
      behavior, flow docs, and embedded SVG image.
- [x] AO Runtime example includes static validation that does not launch live
      providers.
- [x] The layered profile keeps mixed Codex/Claude as a recommended default,
      while exact task providers remain `.env` selectable.

## Provider Execution

- [x] Codex provider resolves from `.env`.
- [x] Codex live AO execution passes with local OAuth/subscription auth.
- [x] Claude provider resolves from `.env`.
- [x] Claude live execution is implemented and tested through AO
      `provider: claude`.
- [x] No live run silently substitutes one provider for another.

## Cross-Task Worker Pool

- [x] `scripts/factory_queue.py` implements the filesystem queue contract:
      `pending/`, `in-flight/`, `done/`, and `failed/`.
- [x] `scripts/worker_pool.py enqueue` copies briefs into the pending queue.
- [x] `scripts/worker_pool.py run-once` atomically claims one queued task.
- [x] `scripts/worker_pool.py pool` processes worker-sized batches
      concurrently.
- [x] `pool --mode run` defaults to per-task isolated worker worktrees.
- [x] `run-once --mode run` defaults to a per-task isolated worker worktree.
- [x] Live worker defaults promote generated Factory evidence back to
      `--workspace`.
- [x] Failed isolated workers promote diagnostic artifacts back to
      `--workspace`.
- [x] `--shared-workspace`, `--shared-workspaces`, and
      `--no-promote-artifacts` provide explicit opt-outs.
- [x] Stale `in-flight` recovery is available through
      `--recover-stale-after`.
- [x] Fresh `in-flight` tasks and pending filename collisions are not
      overwritten by recovery.
- [x] Provider rate-limit signals are recorded as compact queue telemetry
      without raw provider transcripts.
- [x] Recent rate-limit telemetry lowers `provider_rate_limit_floor` and
      shrinks worker batch sizing.
- [x] Queue status JSON reports recent provider-rate telemetry and the
      derived floor.
- [x] `scripts/worker_pool.py report` emits an operator queue report with
      stale in-flight detection, provider-rate telemetry, suggested action,
      and suggested command.
- [x] `scripts/worker_pile_canary.py` runs a deterministic six-task,
      three-worker synthetic pile canary.
- [x] `scripts/worker_pile_canary.py --mode live` is guarded by the explicit
      `launch-live-providers` confirmation token.
- [x] Guarded live canary mode uses worker-pool live defaults: isolated
      worktrees and artifact promotion.
- [x] Documented worker-pile canary CLI entrypoint loads under system
      `python3` before live promotion.
- [x] Worker-pile canary evidence records AO binary and AO runtime worktree
      provenance.
- [x] Confirmed live worker-pile canary refuses dirty AO runtime baseline
      launches unless explicitly overridden.
- [x] Two-task live default worker smoke accepted with final queue
      `pending=0 in-flight=0 done=2 failed=0`.

## Artifact Handoff

- [x] Downstream prompts include scoped summaries and artifact paths.
- [x] Downstream prompts include relevant local skill references.
- [x] Downstream prompts do not include full transcripts.
- [x] Downstream prompts do not include secret values.
- [x] Role outputs include `Result`, `Artifact`, `Evidence`, `Concerns`, and
      `Blocker`.
- [x] AO events are summarized into durable status artifacts.

## Evaluator Closure

- [x] Evaluator artifact exists for every live run.
- [x] Evaluator artifact includes `Verdict: ACCEPTED | REJECTED`.
- [x] AO completion without evaluator acceptance is treated as incomplete.
- [x] Rejected evaluation exits non-zero.
- [x] Accepted evaluation references spec, plan, AO run, role artifacts, and
      verification evidence.

## Verification Commands

- [x] `python3 -m py_compile scripts/*.py`
- [x] `python3 scripts/validate_scaffold.py`
- [x] `python3 scripts/validate.py`
- [x] `python3 scripts/factory_doctor.py`
- [x] `python3 scripts/validate_provider_profiles.py`
- [x] `python3 scripts/prepare_ao_runtime_big_task.py --json`
- [x] `python3 scripts/render_runspec.py --output /tmp/ao-operator-smoke.yaml`
- [x] `python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --dry-run`
- [x] `python3 scripts/validate_factory.py --slug complex-app-smoke`
- [x] `python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --run`
- [x] `python3 scripts/factory_run.py --brief examples/outperform-ai-teams-fanout/task-brief.md --slug outperform-ai-teams-fanout --provider-env examples/outperform-ai-teams-fanout/provider.env --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --dry-run`
- [x] `python3 scripts/validate_factory.py --slug outperform-ai-teams-fanout --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --contract examples/outperform-ai-teams-fanout/spec-forge.contract.json --json`
- [x] `python3 scripts/validate_intake.py examples/outperform-ai-teams-fanout/spec-forge.contract.json --json`
- [x] `bash ${FACTORY_V3_AO_RUNTIME_PATH}/scripts/factory_v3_layered_orchestration_check.sh`
- [x] `python3 scripts/validate_intake.py ${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration/TASK-CONTRACT.json --json`

## Completion Evidence

- Full live Codex AO run accepted:
  `r-complex-app-smoke-1777700006668059000`.
- Baseline Codex smoke RunSpec completed:
  `r-ao-operator-smoke-1777698514832269000`.
- Full live Claude AO run accepted:
  `r-claude-full-smoke-1777699824091200000`.
- Accepted evaluator artifact:
  `docs/evaluations/complex-app-smoke-evaluation.md`.
- Live event summary:
  `run-artifacts/complex-app-smoke/complex-app-smoke-ao-events.md`.
- Generated role artifacts:
  `run-artifacts/complex-app-smoke/roles/`.
- Dry-run and live artifacts:
  `docs/specs/complex-app-smoke-spec.md`,
  `docs/plans/complex-app-smoke-plan.md`,
  `run-artifacts/complex-app-smoke/complex-app-smoke.runspec.yaml`,
  `run-artifacts/complex-app-smoke/prompts/`.
- Missing bug-fix reproducer evidence verified non-zero with blocked evaluation:
  `docs/evaluations/bug-missing-reproducer-evaluation.md`.
- Missing refactor pinning-suite evidence verified non-zero with blocked
  evaluation: `docs/evaluations/refactor-missing-pinning-evaluation.md`.
- Claude-selected live task verified without provider substitution:
  `docs/evaluations/claude-full-smoke-evaluation.md`.
- Phase 2 worker queue scaffold verified:
  `run-artifacts/task-21-worker-queue-scaffold.md`.
- Phase 2 dry-run pile drain verified:
  `run-artifacts/task-22-dry-run-pile-drain.md`.
- Phase 2 live concurrent worker smoke verified:
  `run-artifacts/task-25-live-concurrent-worker-smoke.md`.
- Per-task worker workspace isolation verified:
  `run-artifacts/task-26-worker-workspace-isolation.md`.
- Isolated worker artifact promotion verified:
  `run-artifacts/task-27-isolated-artifact-promotion.md`.
- Live isolated promotion verified with accepted Factory verdict:
  `run-artifacts/task-28-live-isolated-promotion-smoke.md`.
- Live workers default to isolated promotion:
  `run-artifacts/task-29-live-workers-isolated-default.md`.
- Stale `in-flight` recovery verified:
  `run-artifacts/task-30-stale-inflight-recovery.md`.
- Two-task live default isolated worker smoke accepted:
  `run-artifacts/task-31-live-default-isolated-smoke.md`.
- Provider-rate telemetry verified:
  `run-artifacts/task-33-provider-rate-telemetry.md`.
- Operator queue report verified:
  `run-artifacts/task-34-worker-queue-report.md`.
- Synthetic larger pile canary verified:
  `run-artifacts/task-35-worker-pile-canary.md`.
- Guarded live pile canary mode verified:
  `run-artifacts/task-37-live-pile-canary-guard.md`.
- System `python3` worker-pile canary entrypoint verified:
  `run-artifacts/task-38-python39-canary-entrypoint.md`.
- Worker-pile canary runtime provenance verified:
  `run-artifacts/task-39-canary-runtime-provenance.md`.
- Live canary clean AO runtime guard verified:
  `run-artifacts/task-40-live-canary-clean-runtime-guard.md`.
- All-Codex provider profile validation verified:
  `run-artifacts/task-41-all-codex-provider-profile-validation.md`.
- AO Runtime big-task harness dry-run verified:
  `run-artifacts/task-42-ao-runtime-big-task-harness.md`.
- Topology fan-out dry-run verified:
  `run-artifacts/outperform-ai-teams-fanout/outperform-ai-teams-fanout.runspec.yaml`.
- Topology fan-out validation completed with PASS:
  `python3 scripts/validate_factory.py --slug outperform-ai-teams-fanout --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --contract examples/outperform-ai-teams-fanout/spec-forge.contract.json --json`.
- Vendored skill package validation completed with PASS:
  `python3 scripts/validate.py`.
- Final validation commands completed with PASS:
  `python3 -m py_compile scripts/*.py`,
  `python3 scripts/validate_scaffold.py --json`,
  `python3 scripts/factory_doctor.py --json`,
  `python3 scripts/render_runspec.py --output /tmp/ao-operator-smoke.yaml`,
  `python3 scripts/validate_factory.py --slug complex-app-smoke --json`.
- Layered OpenClaw/AO example validated with PASS:
  `bash ${FACTORY_V3_AO_RUNTIME_PATH}/scripts/factory_v3_layered_orchestration_check.sh`.
