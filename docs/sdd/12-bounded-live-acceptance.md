# Bounded Live Acceptance Gate

The Remote Transfer v2 stress lane has two separate acceptance lanes:

- dry-run stress materialization for the 1000-slice topology
- bounded live provider execution for the accepted 10-slice, 25-slice, and
  50-slice profiles
- isolated dry-run preparation for the next larger live profile

The dry-run lane is already accepted. The bounded live lane is accepted only for
the profile whose real AO run exits cleanly and whose evaluator evidence says
so. The current accepted live ceiling is the 50-slice / 107-task profile from AO
run `r-remote-transfer-v2-stress-live-1778099146422016025`, committed as
`9462231 Record accepted 50-slice live transfer run`. Dry-run preparation
reports are not live acceptance. Do not merge or describe failed or dry-run-only
artifacts as successful live evidence.

## Classification

- Task size: MEDIUM
- Shape: bug-fix
- Provider mode: live only for explicitly live operator slices
- Default posture: local preflight and validation only

This is treated as `bug-fix` because it corrects the previous unsafe operating
pattern: dispatching the 1000-slice stress topology live exceeded provider
limits. The fix is to route live proof through a bounded profile and explicit
acceptance gate.

## Slice Boundary

Slice `12-check-bounded-live-readiness` is the final local preflight gate before
dispatch packet generation. Slice `13-build-live-dispatch-packet` renders the
exact command, environment, stop rules, and acceptance commands without running
providers. Slice `14-verify-live-dispatch-packet` verifies that packet against
the current manifest and readiness summary. Slice
`15-check-live-dispatch-gate` composes readiness, packet verification, live
block enforcement, and expected pre-live acceptance into one final local gate.
Slice `16-check-live-approval-readiness` produces the local receipt that the
operator can use to decide whether to explicitly approve provider execution; it
does not authorize dispatch. Slice `17-run-bounded-live-10` is the first
provider-affecting slice. It may run only after:

1. `factory_doctor.py` passes with the intended AO Runtime path.
2. `validate_intake.py` passes for `spec-forge.live.contract.json`.
3. `validate_factory.py` passes for `ao-live-stress-topology.yaml`.
4. `run_operator_slice.py --slice 17-run-bounded-live-10` refuses the run unless
   the operator provides `--allow-live`.
5. `build_live_dispatch_packet.py --write-packet --json` returns `PASS` with
   `dispatch_authorized=false`.
6. `verify_live_dispatch_packet.py --json` returns `PASS`.
7. `check_live_dispatch_gate.py --write-gate --json` returns `PASS` with
   `ready_for_operator_approval=true` and `dispatch_authorized=false`.
8. `check_live_approval_readiness.py --write-output --json` returns `PASS` with
   `approval_request_ready=true` and `dispatch_authorized=false`.
9. The operator explicitly approves live provider usage for the current session.

Slice `18-classify-live-outcome` classifies post-live artifacts as `ACCEPTED`,
`PENDING_LIVE_RUN`, or `DIAGNOSTIC_REQUIRED`. Slice
`19-plan-live-failure-diagnostics` records the diagnostic preservation plan and
keeps raw AO homes out of commits. Slice
`20-preserve-live-failure-diagnostics` guards the actual preservation step and
writes sanitized summaries only when the diagnostics plan permits it. Slice
`21-route-live-postrun` checks that the classifier, diagnostics plan,
preservation report, and acceptance state agree on the next route. Slice
`22-guard-live-success-commit` refuses success commits unless routing and
acceptance both prove accepted live evidence. Slice
`23-verify-live-operator-sequence` verifies the live slice order and dispatch
artifact references. Slice `24-check-live-acceptance` is a local validation
slice. It may run only after slice `20` routes to `RUN_ACCEPTANCE` and slice
`23` passes. Slice `25-prepare-25-slice-profile` generates and dry-runs the
57-task profile. Slice `26-large-live-override-run` is the accepted 25-slice
provider run and requires `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1`. Slice
`27-prepare-50-slice-dry-run-profile` prepares the next 107-task live profile in
a temporary worktree and writes only a compact report into the main worktree.
It must not overwrite or replace accepted 25-slice live evidence. Slice
`28-check-50-slice-live-approval-gate` is a non-dispatching preflight gate for
the 50-slice live profile. It requires the committed 50-slice prep report,
accepted 25-slice live evidence, and `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1`, but
still writes `dispatch_authorized=false`. Slice
`29-record-50-slice-provider-budget` records the 107-task budget and abort
rules. Slice `30-rehearse-50-slice-live-sequence` proves the 50-slice live path
still refuses dispatch without an explicit approval file. Slice
`31-run-50-slice-live` is the actual live-provider slice and requires
`--allow-live`, `--allow-override`, the override env, a passing budget, a
passing approval gate, and an explicit approval JSON. Slice
`32-route-50-slice-postrun` prevents accepted 25-slice evidence from being
mistaken for accepted 50-slice evidence. Slice
`33-summarize-50-slice-operator-state` is the operator-facing status summary:
current state, blockers, approval status, next safe command, and evidence
paths.

## Required Environment

```bash
export FACTORY_V3_AO_RUNTIME_PATH=${FACTORY_V3_AO_RUNTIME_PATH}
export PATH="$FACTORY_V3_AO_RUNTIME_PATH/target/release:$PATH"
```

Forbidden provider API-key environment variables must remain absent:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Provider authentication must come from local OAuth CLI state.

## Preflight Commands

```bash
python3 scripts/check_bounded_live_readiness.py --json

python3 scripts/check_bounded_live_readiness.py --write-summary --json

python3 scripts/factory_doctor.py --json

python3 scripts/validate_intake.py \
  examples/remote-transfer-v2-stress/spec-forge.live.contract.json \
  --json

python3 scripts/validate_factory.py \
  --slug remote-transfer-v2-stress-live \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --contract examples/remote-transfer-v2-stress/spec-forge.live.contract.json \
  --json

python3 scripts/run_operator_slice.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --slice 17-run-bounded-live-10 \
  --json

python3 scripts/build_live_dispatch_packet.py \
  --write-packet \
  --json

python3 scripts/verify_live_dispatch_packet.py \
  --json

python3 scripts/check_live_dispatch_gate.py \
  --write-gate \
  --json

python3 scripts/classify_live_outcome.py \
  --write-output \
  --json

python3 scripts/plan_live_failure_diagnostics.py \
  --write-plan \
  --json

python3 scripts/preserve_live_failure_diagnostics.py \
  --write-report \
  --json

python3 scripts/route_live_postrun.py \
  --write-output \
  --json

python3 scripts/check_live_success_commit_guard.py \
  --write-output \
  --json

python3 scripts/check_live_operator_sequence.py \
  --write-output \
  --json

python3 scripts/check_live_approval_readiness.py \
  --write-output \
  --json
```

The `run_operator_slice.py --slice 17-run-bounded-live-10 --json` command must
return `verdict: BLOCKED` without `--allow-live`. That proves the live dispatch
cannot happen accidentally.

## Live Command

Run this only with explicit operator approval:

```bash
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief-live.md \
  --slug remote-transfer-v2-stress-live \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --run \
  --overwrite-artifacts \
  --scrub-root-context
```

Do not rerun immediately after a failure. Preserve diagnostics first.

## Acceptance Commands

```bash
python3 scripts/check_live_acceptance.py \
  --slug remote-transfer-v2-stress-live \
  --json

python3 scripts/validate_factory.py \
  --slug remote-transfer-v2-stress-live \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --contract examples/remote-transfer-v2-stress/spec-forge.live.contract.json \
  --json
```

## Escalation Ladder

Use these rungs in order:

1. Keep the 1000-slice lane dry-run-only unless a separate provider-limit plan
   has been accepted.
2. Accept a 10-slice live run only when `check_live_acceptance.py` and
   `validate_factory.py` both pass against real AO evidence.
3. Accept a 25-slice live run only with the large-run override, complete AO
   events, tracked role artifacts, and evaluator acceptance.
4. Prepare a 50-slice profile only with
   `scripts/prepare_live_profile_dry_run.py`; this runs in a temporary worktree
   and commits only the prep report plus the operator-run receipt.
5. Run `scripts/check_50_slice_live_approval_gate.py --write-output --json`
   only with `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1`. This proves the provider-limit
   evidence is present and keeps `dispatch_authorized=false`.
6. Run `scripts/check_50_slice_provider_budget.py --write-output --json` with
   the override env to record the 107-task budget and abort conditions.
7. Run `scripts/rehearse_50_slice_live_sequence.py --write-output --json` to
   prove the live slice and launcher still fail closed before explicit approval.
8. Run a 50-slice live profile only through slice `31-run-50-slice-live`, after
   the operator explicitly approves another large live run and writes the
   approval JSON.
9. Run `scripts/route_50_slice_live_postrun.py --write-output --json` after the
   50-slice live command exits.
10. Run `scripts/summarize_50_slice_operator_state.py --write-output --json`
    before asking for approval or dispatching providers.
11. Treat escalation beyond 50 slices as a new lane. Start with dry-run profile
    preparation, an approval gate, provider-budget evidence, no-provider
    rehearsal, and explicit operator approval before any live dispatch.
12. Treat 75-slice live execution as a separate approval milestone. Slice
    `38-record-75-slice-live-approval-sdd` records that the 75-slice lane is
    ready for operator approval while keeping `dispatch_authorized=false`,
    `live_providers_run=false`, and no 75-slice live slice in the manifest.
13. Close the local Agent OS validation lane only through slice
    `49-record-agent-os-closure-gate`, after the UAT response gate and release
    readiness gate both pass. This does not authorize live-provider escalation.
14. Render the next Agent OS execution shape only through slice
    `50-record-agent-os-runspec-renderer`. The slice emits a provider-profile-
    aware RunSpec draft and scoped prompt packets while keeping
    `dispatch_authorized=false` and `live_providers_run=false`.
15. Validate the rendered Agent OS RunSpec draft only through slice
    `51-record-agent-os-runspec-validation`. The slice checks prompt coverage,
    dependency references, provider posture, provider-profile alignment, and
    dispatch safety without executing AO.
16. Prepare future Agent OS RunSpec execution only through slices `52`-`55`:
    execution approval gate, no-provider rehearsal, postrun router, and
    diagnostics preservation. These slices must keep `dispatch_authorized=false`
    and must not run AO.
17. Add Agent OS execution readiness only through slices `56`-`60`: explicit
    approval validation, approval-only launcher refusal, evaluator closure,
    role-output schema, and hygiene checks. These slices must remain local and
    must not run providers while approval is absent.
18. Upgrade the Agent OS approved execution runner only through slice `61`.
    The runner may execute `ao run` only when explicit approval validates and
    `--execute` is present. Committed evidence must remain blocked while
    approval is absent.
19. Add Agent OS role-output ingestion only through slice `62`. Ingestion must
    convert existing AO role artifacts into schema-valid JSON and update the
    execution report without dispatching providers.
20. Add Agent OS role graph/state versioning only through slice `71`. The slice
    must record a deterministic core role graph and `ao-operator/agent-os-state/v2`
    compatibility baseline without changing runtime role behavior or
    dispatching providers.
21. Add Agent OS accepted-execution commit guard only through slice `72`. The
    guard must refuse success-evidence commits for pending, blocked, failed, or
    unclosed Agent OS execution artifacts without dispatching providers.
22. Add Agent OS postrun route matrix only through slice `73`. The matrix must
    prove pending, accepted, failed, blocked, invalid-gate, and
    missing-evaluator-acceptance states route safely without dispatching
    providers.
23. Add Agent OS state v2 persistence only through slice `74`. State load and
    migration must preserve route/blocker/evidence fields while forcing stale
    dispatch flags off.
24. Add Agent OS RunSpec compatibility matrix only through slice `75`. The
    matrix must prove current renderer/YAML evidence and legacy renderer v1
    shapes remain non-dispatching and task-compatible before router
    architecture changes.
25. Add Agent OS architecture readiness summary only through slice `76`. The
    summary must aggregate all architecture safety baselines and fail closed if
    any baseline is missing, not PASS, or dispatch-authorized.
26. Add Agent OS router v2 state only through slice `77`. The router must keep
    v1 as the default, require architecture readiness for v2, and force v2
    top-level dispatch flags off.
27. Add Agent OS state evidence hygiene only through slice `78`. The guard must
    reject stale dispatch flags, state blockers, schema drift, and untracked
    state diagnostics before more architecture work.

## Remaining Test Roadmap

The 50-slice live proof validates AO Operator's bounded AO provider lane. It
does not finish the real network-transfer product surface. Track the remaining
tests as SDD slices with explicit evidence, negative constraints, and closure
criteria:

1. **1000-slice guardrail lane** - revalidate 1000-slice dry-run after stale
   artifact fixes, then prove the 1000-slice live path refuses dispatch without
   separate provider-limit evidence and explicit approval. Current completed
   evidence:
   `run-artifacts/remote-transfer-v2-stress/1000-slice-guardrail.json`.
2. **Next escalation lane** - prepare the next 75-slice or 100-slice profile as
   dry-run-only first, then add an operator slice, approval gate,
   provider-budget report, no-provider rehearsal, and optional live approval.
   Current 75-slice dry-run lane evidence:
   `run-artifacts/remote-transfer-v2-stress/profile-prep/75-slice-dry-run-prep.json`,
   `run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-approval-gate.json`,
   `run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-provider-budget.json`,
   `run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-rehearsal.json`,
   and
   `run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-summary.json`.
   The 75-slice live approval SDD is now recorded at
   `run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-live-approval-sdd.json`;
   it confirms the 157-task lane is ready for explicit operator approval but
   does not authorize dispatch and does not add a live provider slice.
3. **Clean-clone validation** - verify the accepted 50-slice evidence from a
   fresh Mac clone and a fresh Ubuntu clone so no local-only artifacts are
   required for acceptance.
4. **Mac-to-Ubuntu remote transfer** - test small bundle transfer, large
   chunked transfer, interrupted transfer resume, artifact return, and partial
   staging cleanup between the Mac controller and Ubuntu worker. Current
   completed evidence includes the deterministic small transfer, 64 MiB chunked
   transfer, interrupted cleanup smoke, AO workspace validation, manifest
   signing gate, bundle safety negative validation, and the Mac-signed
   Ubuntu-executed Codex smoke at
   `run-artifacts/remote-transfer-v2-stress-live/remote-codex-live-smoke-20260507T001859Z.md`.
   The Mac-to-Ubuntu gRPC Codex network smoke at
   `run-artifacts/remote-transfer-v2-stress-live/remote-codex-network-smoke-20260507T002614Z.md`
   also proves a Mac-side client can dispatch a signed bundle to an
   Ubuntu-hosted AO coordinator/executor and receive the declared artifact over
   the network. The durable worker-runtime smoke at
   `run-artifacts/remote-transfer-v2-stress-live/remote-codex-worker-runtime-smoke-20260507T004907Z.md`
   proves the Mac coordinator can route the signed Codex task to a registered
   Ubuntu worker RuntimeService endpoint.
5. **Remote worker readiness** - test Ubuntu Codex OAuth preflight, single-task
   remote smoke, multi-task remote smoke, timeout behavior, environment probing,
   and provider-auth redaction. The single-task signed remote Codex smoke has
   passed through AO Runtime bundle verification and Ubuntu ChatGPT CLI auth.
   The durable multi-node Mac coordinator to registered Ubuntu worker service
   smoke has passed. AO Runtime commit `340f1b3` adds provider-auth redaction
   for remote Codex stdout/stderr through the proxied worker path, with evidence
   in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase5c_provider_output_redaction.md`.
   AO Runtime commit `252a878` adds manifest-declared remote Codex provider
   timeouts, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase5d_provider_timeout.md`.
   AO Runtime commit `b22f9cf` adds deterministic multi-task registered-worker
   Codex coverage and sanitized environment probing, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase5e_environment_probe.md`
   and
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase5f_multi_task_smoke.md`.
   This readiness bucket is complete for deterministic coverage; larger live
   multi-task provider execution remains a separate approval-gated operator
   smoke.
6. **Manifest security** - test canonical manifests, signing, missing signature
   rejection, invalid signature rejection, key rotation, trust policy, and
   schema compatibility.
7. **Bundle safety** - test path traversal rejection, symlink handling, absolute
   path rejection, special file rejection, and provider secret exclusion from
   transfer bundles.
8. **Distributed worker lifecycle** - test worker enrollment, heartbeat,
   stale-worker timeout, capability matching, queue lease/reclaim, task claim,
   task cancellation, and backpressure. AO Runtime commit `e52adce` adds
   deterministic capability matching and heartbeat-based backpressure before
   registered-worker proxy dispatch, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6a_capability_backpressure.md`.
   AO Runtime commit `60c8b27` adds the deterministic task ledger foundation for
   task claim, expired lease reclaim, cancellation, and stale terminal-write
   protection, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6b_task_ledger.md`.
   AO Runtime commit `0b7c3b6` wires that ledger into RuntimeService dispatch so
   local and proxied tasks are claimed, marked running, and terminalized from
   runtime events, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6c_dispatch_ledger_integration.md`.
   AO Runtime commit `8bd875f` persists task lifecycle mutations to the
   coordinator WAL and replays them into replicas, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6d_task_lifecycle_wal.md`.
   AO Runtime commit `39e0882` exposes typed `GetTask` and `CancelTask`
   RuntimeService controls over the task ledger, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6e_task_controls.md`.
   AO Runtime commit `cd8c4e0` propagates coordinator cancellations to proxied
   worker RuntimeService endpoints and keeps control RPCs responsive while
   Codex provider commands run, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6f_cancel_propagation.md`.
   AO Runtime commit `43d1fce` adds coordinator-ledger backpressure so a worker
   with active leased work rejects new proxied dispatch even if heartbeat
   `running_tasks` is stale, with evidence in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6g_ledger_backpressure.md`.
   AO Runtime commit `6c60ce5` terminates the remote provider process tree on
   explicit cancellation or timeout and reports `cancelled_propagated_killed`
   when the coordinator confirms the worker killed the provider, with evidence
   in
   `${FACTORY_V3_AO_RUNTIME_PATH}/progress/slice-reports/remote_transfer_v2_phase6h_provider_process_termination.md`.
   The deterministic distributed worker lifecycle bucket is complete for
   enrollment, heartbeat, stale-worker projection, capability matching,
   queue/claim ledgering, cancellation propagation, provider process
   termination, and backpressure.
9. **Failure diagnostics** - surface AO Runtime `normalized_reason` in Factory
   summaries and evaluator output for provider timeout, rate limit, auth,
   network, path, and sandbox failures. Current completed evidence:
   `run-artifacts/remote-transfer-v2-stress-live/normalized-failure-diagnostics-20260507T005217Z.md`
   and
   `run-artifacts/remote-transfer-v2-stress-live/normalized-failure-diagnostics.json`.
   Architecture implementation must pass
   `python3 scripts/check_normalized_failure_diagnostics.py --write-output --json`
   through operator slice `86-check-normalized-failure-diagnostics`.
10. **Repeated-run hygiene** - run same-slug dry-run-after-live,
    live-after-failed-live, and reroute-after-accepted-live scenarios to prove
    stale role patches, stale events, and stale evaluations cannot contaminate
    acceptance. Current completed evidence:
    `run-artifacts/remote-transfer-v2-stress-live/repeated-run-hygiene-20260507T005501Z.md`
    and
    `run-artifacts/remote-transfer-v2-stress-live/dispatch/repeated-run-hygiene.json`.
    Architecture implementation must pass
    `python3 scripts/check_repeated_run_hygiene.py --write-output --json`
    through operator slice `85-check-repeated-run-hygiene`.
11. **Operator controls** - promote and test `submit`, `status`, `observe`,
    `cancel`, and `approval` entrypoints with audit logs and next-safe-command
    output. Current completed evidence:
    `run-artifacts/remote-transfer-v2-stress-live/operator-controls-20260507T010107Z.md`.
12. **Operator summary UX** - keep a single command that reports current run
    state, blockers, approval status, evidence paths, and the next safe command.
    Current completed evidence:
    `run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json`
    reports `ACCEPTED_50_SLICE_LIVE` and blocks larger live dispatch until a new
    gated escalation lane exists.
13. **Provider boundary tests** - verify Codex-only, Claude-only, supported
    mixed-provider topologies, provider substitution refusal, and API-key env
    hard failures.
14. **Resource and performance tests** - measure disk growth, worktree cleanup,
    AO home cleanup, concurrency behavior, rate-limit behavior, wallclock
    budget, and provider-budget tracking across repeated runs. Current
    completed evidence:
    `docs/sdd/63-resource-performance-guardrails.md` and
    `run-artifacts/remote-transfer-v2-stress-live/resource-performance-gate.json`.
14a. **Remote transfer hardening evidence gate** - verify signed-manifest,
     chunk cleanup, large-transfer smoke, and signed worker-runtime smoke
     evidence from AO Operator and AO Runtime without provider dispatch. Current
     completed evidence:
     `docs/sdd/62-remote-transfer-hardening-evidence-gate.md` and
     `run-artifacts/remote-transfer-v2-stress-live/remote-transfer-hardening.json`.
14b. **Agent OS approval bundle ergonomics** - generate a template-only
     execution approval bundle with the current RunSpec SHA-256, operator,
     accepted-risk, and expiry fields. Current completed evidence:
     `docs/sdd/64-agent-os-execution-approval-bundle.md` and
     `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json`.
14c. **Operator guardrail summary** - aggregate cockpit, remote-transfer
     hardening, resource/performance, approval bundle, release readiness, and
     no-provider rehearsal evidence in one non-dispatching report. Current
     completed evidence: `docs/sdd/65-operator-guardrail-summary.md` and
     `run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json`.
14d. **Agent OS approval materialization dry-run** - validate approval bundle,
     approval gate, and current RunSpec SHA-256 without writing an approval file
     by default. Current completed evidence:
     `docs/sdd/66-agent-os-approval-materialization.md` and
     `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-materialization.json`.
14e. **Release artifact index** - link SDD 62-67 to their PASS status artifacts
     so the release posture is inspectable as a single evidence map. Current
     completed evidence: `docs/sdd/67-release-artifact-index.md` and
     `run-artifacts/remote-transfer-v2-stress-live/release-artifact-index.json`.
15. **Release/readiness gate** - add one command that checks git sync, tests,
    docs freshness, dirty generated artifacts, provider auth posture, AO Runtime
    path, accepted evidence, clean-clone readiness, and ship readiness. The
    release gate invokes `scripts/check_clean_clone_readiness.py --skip-closure`
    as a first-class subgate so clean-clone architecture baselines are visible
    in the release report without recursively running another full closure.
    Current completed evidence:
    `run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json`.

16. **Clean-clone readiness gate** - verify the accepted 50-slice foundation
    from a temporary clean clone before architecture implementation. The gate
    runs the 50-slice operator summary, live acceptance check, factory
    validation, Agent OS router migration matrix, RunSpec provider-boundary
    matrix, provider-profile RunSpec validation, state stale cleanup, closure/
    pytest, strict-public redaction, and status JSON integrity from the clone,
    and requires `accepted_50_current_state=ACCEPTED_50_SLICE_LIVE`. Current
    completed evidence:
    `run-artifacts/remote-transfer-v2-stress-live/dispatch/clean-clone-readiness.json`.

## Planned Follow-On Milestone: AO Operator Agent OS

After the Remote Transfer v2 validation roadmap is closed cleanly, start a
separate Agent OS milestone. Do not use this milestone to justify changes to the
current bounded-live acceptance lane. Its purpose is to improve AO Operator's
agent structure above AO Runtime: AO remains the execution engine, while Factory
v3 becomes a typed, stateful, specialist-aware agent organization.

Goal: add the method discipline, project memory, and specialist judgment that
Superpowers, GSD, and GStack provide, while preserving AO Operator's AO-native
orchestration, scoped artifacts, and evaluator closure.

Planned phases:

1. **Agent OS SDD** - define the mission router, project state layer, role
   capability schema, specialist registry, verification matrix, UAT gate,
   learning loop, and operator cockpit contract. Current completed evidence:
   `docs/sdd/13-agent-os.md`,
   `docs/contracts/ao-operator-agent-os.contract.json`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-sdd-validation.json`.
2. **Mission router and state layer** - add a role before `planner-intake` that
   routes work by shape and risk (`fast`, `quick`, `phase`, `live-provider`,
   `remote-worker`, `security-sensitive`, `frontend`, `release`), and introduce
   persistent `PROJECT`, `REQUIREMENTS`, `ROADMAP`, `STATE`, `DECISIONS`, and
   `LEARNINGS` artifacts. Current completed evidence:
   `docs/sdd/14-agent-os-mission-router-state.md`,
   `scripts/agent_os_router.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-mission-router-state.json`.
3. **Codebase mapper and specialist roles** - add compact codebase intelligence
   plus optional product, engineering-manager, security, QA/browser, design,
   devex, docs-release, and release-manager roles. Current completed evidence:
   `docs/sdd/15-agent-os-codebase-specialists.md`,
   `scripts/agent_os_codebase_map.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-codebase-specialists.json`.
4. **Capability and skill validation** - require each role contract to declare
   capabilities, allowed tools, required skills, reads, writes, risk level, and
   verification command, and validate those declarations before dispatch.
   Current completed evidence:
   `docs/sdd/16-agent-os-capability-validation.md`,
   `docs/contracts/ao-operator-agent-capabilities.json`,
   `scripts/agent_os_capability_validator.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-capability-validation.json`.
5. **Phase compiler and verification matrix** - compile roadmap phases into
   state-v2-bound AO waves and route verification by risk: tests, browser QA,
   security review, docs check, release check, live-provider evidence, and
   artifact hygiene.
   Current completed evidence:
   `docs/sdd/17-agent-os-phase-compiler.md`,
   `scripts/agent_os_phase_compiler.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json`.
6. **Phase execution handoff** - turn the compiled phase plan into scoped role
   packets with status contracts, verification commands, risk gates, and full
   transcript refusal. Current completed evidence:
   `docs/sdd/18-agent-os-phase-handoff.md`,
   `scripts/agent_os_phase_handoff.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`.
7. **UAT acceptance state** - add pending human acceptance items from scoped
   handoff packets. Current completed evidence:
   `docs/sdd/19-agent-os-uat-state.md`,
   `scripts/agent_os_uat_state.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json`.
8. **Learning extraction** - record lessons, negative learnings, role evidence
   needs, and open blockers from pending UAT state. Current completed evidence:
   `docs/sdd/20-agent-os-learning-extract.md`,
   `scripts/agent_os_learning_extract.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json`.
9. **Operator cockpit** - add a unified operator view for active milestone,
   failed role, blocker reason, next safe command, approval state, and evidence
   paths. Current completed evidence:
   `docs/sdd/21-agent-os-operator-cockpit.md`,
   `scripts/agent_os_operator_cockpit.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-operator-cockpit.json`.
10. **UAT response gate** - generate human response templates and authorize
    closure only when every required UAT item is explicitly accepted. Current
    completed evidence:
    `docs/sdd/22-agent-os-uat-response-gate.md`,
    `scripts/agent_os_uat_response_gate.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json`.
11. **Role graph and state versioning** - record the core role dependency graph
    and state v2 compatibility baseline before router or RunSpec architecture
    changes. Current completed evidence:
    `docs/sdd/44-agent-os-role-graph-state-versioning.md`,
    `scripts/agent_os_role_graph.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`.
12. **Accepted execution commit guard** - prevent success-evidence commits
    unless postrun route, execution report, and evaluator closure all accept.
    Current completed evidence:
    `docs/sdd/45-agent-os-accepted-execution-commit-guard.md`,
    `scripts/check_agent_os_accepted_execution_commit_guard.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json`.
13. **Postrun route matrix** - prove all load-bearing postrun route states
    classify safely before execution architecture changes. Current completed
    evidence:
    `docs/sdd/46-agent-os-postrun-route-matrix.md`,
    `scripts/check_agent_os_postrun_route_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json`.
14. **State v2 persistence** - persist the router-compatible Agent OS state v2
    baseline and fail closed on unsupported schemas. Current completed
    evidence:
    `docs/sdd/47-agent-os-state-v2-persistence.md`,
    `scripts/agent_os_state_v2.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`.
15. **RunSpec compatibility matrix** - preserve the current renderer/YAML
    contract and legacy renderer v1 fixture before router architecture changes.
    Current completed evidence:
    `docs/sdd/48-agent-os-runspec-compatibility-matrix.md`,
    `scripts/check_agent_os_runspec_compatibility_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json`.
16. **Architecture readiness summary** - aggregate role graph, state v2, commit
    guard, route matrix, and RunSpec compatibility into one operator-facing
    readiness command. Current completed evidence:
    `docs/sdd/49-agent-os-architecture-readiness-summary.md`,
    `scripts/summarize_agent_os_architecture_readiness.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json`.
17. **Router v2 state** - emit native state v2 from the mission router only
    behind architecture readiness, preserving v1 compatibility by default.
    Current completed evidence:
    `docs/sdd/50-agent-os-router-v2-state.md`,
    `scripts/agent_os_router.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`.
18. **State evidence hygiene** - reject stale/dirty state v2 evidence before
    more architecture work. Current completed evidence:
    `docs/sdd/51-agent-os-state-evidence-hygiene.md`,
    `scripts/check_agent_os_state_evidence_hygiene.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-evidence-hygiene.json`.
19. **Approved execution fixture** - exercise the accepted Agent OS execution
    route without providers while keeping fixture-only evidence blocked from
    success commits. Current completed evidence:
    `docs/sdd/52-agent-os-approved-execution-fixture.md`,
    `scripts/check_agent_os_approved_execution_fixture.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-fixture.json`.
20. **Router migration matrix** - prove router v1/v2 state migration preserves
    blockers and fails closed before deeper architecture changes. Current
    completed evidence:
    `docs/sdd/53-agent-os-router-migration-matrix.md`,
    `scripts/check_agent_os_router_migration_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-migration-matrix.json`.
21. **RunSpec provider boundary matrix** - prove Codex-only, Claude-only,
    mixed, rendered-YAML, and provider-substitution-refusal cases stay explicit
    and non-dispatching. Current completed evidence:
    `docs/sdd/54-agent-os-runspec-provider-boundary-matrix.md`,
    `scripts/check_agent_os_runspec_provider_boundary_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-provider-boundary-matrix.json`.
22. **State stale cleanup** - give operators a safe dry-run/apply command for
    removing untracked Agent OS state diagnostics after hygiene failures.
    Current completed evidence:
    `docs/sdd/55-agent-os-state-stale-cleanup.md`,
    `scripts/cleanup_agent_os_state_artifacts.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json`.
23. **Failed diagnostics fixture** - prove failed Agent OS execution
    diagnostics preservation through a provider-free synthetic AO events path.
    Current completed evidence:
    `docs/sdd/56-agent-os-failed-diagnostics-fixture.md`,
    `scripts/check_agent_os_failed_diagnostics_fixture.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-failed-diagnostics-fixture.json`.
24. **Approval alignment drift** - fail closed if approval/execution artifacts
    lose provider-profile alignment fields. Current completed evidence:
    `docs/sdd/57-agent-os-approval-alignment-drift.md`,
    `scripts/check_agent_os_approval_alignment_drift.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-alignment-drift.json`.

First slice status: complete. No role dispatch behavior changed. The next Agent
OS mission-router/state foundation, codebase-mapper/specialist planning, and
capability/skill validation are also complete as local, deterministic
validation slices. The phase compiler and verification matrix slice is also
complete as a local deterministic validation slice. The phase execution handoff
slice is also complete as a local deterministic validation slice. The UAT
acceptance state slice is also complete as a local deterministic validation
slice. The learning extraction slice is also complete as a local deterministic
validation slice. The operator cockpit slice is also complete as a local
deterministic validation slice. The UAT response gate is also complete as a
local deterministic validation slice. The role graph/state versioning baseline
is also complete as a local deterministic validation slice. The
accepted-execution commit guard is also complete as a local deterministic
validation slice. The postrun route matrix is also complete as a local
deterministic validation slice. The state v2 persistence slice is also complete
as a local deterministic validation slice. The RunSpec compatibility matrix is
also complete as a local deterministic validation slice. The architecture
readiness summary is also complete as a local deterministic validation slice.
The router v2 state slice is also complete as a local deterministic validation
slice. The approved execution fixture is also complete as a local deterministic
validation slice. The router migration matrix is also complete as a local
deterministic validation slice. The RunSpec provider boundary matrix is also
complete as a local deterministic validation slice. The state stale cleanup
slice is also complete as a local deterministic validation slice. The
repeated-run hygiene baseline is also complete as a local deterministic
validation slice. The normalized failure diagnostics baseline is also complete
as a local deterministic validation slice. The RunSpec state v2 bridge is also
complete as a local deterministic validation slice. The RunSpec execution plan
lock is also complete as a local deterministic validation slice. The next Agent
OS operation is to continue router/RunSpec architecture changes against the
committed role graph, commit guard, route-matrix, state v2, RunSpec
compatibility, state evidence hygiene, approved execution fixture, router
migration, provider boundary, stale-cleanup, repeated-run,
normalized-diagnostics, state-v2 RunSpec renderer, and execution-plan-lock
baselines.

## Acceptance Criteria

Live evidence is accepted only when all of these are true:

- `Verdict: ACCEPTED`
- `AO Run:` is a real run id, not `none` or `not-dispatched`
- `Mode: run`
- an AO events file exists
- `AO command exit=0`
- `AO completed=true`
- no blockers
- every load-bearing role artifact is tracked in git
- validation commands pass

`scripts/check_live_acceptance.py` checks the live artifact criteria directly
and exits non-zero until the accepted live evidence exists.

## Failure Handling

If any acceptance item fails:

1. Stop before rerun.
2. Run `scripts/classify_live_outcome.py --write-output --json`.
3. If classification is `DIAGNOSTIC_REQUIRED`, run
   `scripts/plan_live_failure_diagnostics.py --write-plan --json`.
4. Run `scripts/preserve_live_failure_diagnostics.py --write-report --json`.
5. Run `scripts/route_live_postrun.py --write-output --json`.
6. Run `scripts/check_live_success_commit_guard.py --write-output --json`.
7. Run `scripts/check_live_operator_sequence.py --write-output --json`.
8. Run `scripts/check_live_approval_readiness.py --write-output --json`.
9. Preserve the AO home or run diagnostics only when the preservation report
   allows it; use `--execute` and optionally `--copy-raw` after confirming the
   failed live attempt should be preserved.
10. Commit only sanitized diagnostic summaries; raw `ao-home-*` failure
   snapshots remain ignored.
11. Do not commit the failed run as successful live evidence.

The 1000-slice topology remains dry-run-only unless the operator supplies
separate provider-limit evidence and an explicit override.
