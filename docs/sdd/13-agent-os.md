# 13 - AO Operator Agent OS

Classification: COMPLEX
Shape: greenfield

## Scope

AO Operator Agent OS is the next layer above AO Runtime. AO remains the
execution substrate; Agent OS adds typed intake, persistent project state,
specialist capability routing, phase compilation, verification, UAT, learning
capture, and one operator cockpit.

This SDD is a doc-only contract. It MUST NOT dispatch AO providers, mutate
runtime role behavior, change provider auth paths, or add live provider slices.

## Mission Router

The mission router is the first AO Operator control point for every task. It
classifies size and shape, identifies route labels, selects verification gates,
and refuses dispatch when a task lacks required evidence.

Routes:

- `fast` for trivial local edits.
- `quick` for bounded single-slice changes.
- `phase` for multi-slice implementation.
- `live-provider` for any AO provider dispatch.
- `remote-worker` for Mac-to-Ubuntu or distributed worker flows.
- `security-sensitive` for auth, secrets, credentials, signing, or trust.
- `frontend` for browser or UI validation.
- `release` for ship/readiness posture.

## Project State Layer

Agent OS needs durable state files that survive context resets and machine
handoffs. The state layer records project intent, requirements, roadmap,
active phase, decisions, open blockers, verification evidence, and lessons.

Required artifacts:

- `PROJECT.md` for product and system intent.
- `REQUIREMENTS.md` for user-visible obligations.
- `ROADMAP.md` for phase ordering.
- `STATE.md` for current active lane, blockers, and next safe command.
- `DECISIONS.md` for accepted tradeoffs.
- `LEARNINGS.md` for reusable operational lessons.

## Role Capability Schema

Every role contract must declare capabilities, allowed tools, reads, writes,
risk level, dispatch mode, provider boundary, and verification command. The
capability validator must reject roles that request undeclared tools, overlap
writes unsafely, or touch sensitive fields without a matching route.

Required role fields:

- `capabilities`
- `allowed_tools`
- `reads`
- `writes`
- `risk_level`
- `dispatch_mode`
- `provider_boundary`
- `verification`

## Specialist Registry

Specialists are optional roles selected by route and risk. The initial registry
should include product, engineering-manager, security, QA/browser, design,
developer-experience, documentation-release, and release-manager specialists.
Each specialist returns evidence, concerns, and blocker state.

## Phase Compiler

The phase compiler turns roadmap phases into AO-ready waves. It maps phase
requirements to role tasks, dependency edges, strict write ownership, approval
gates, and verification gates before AO dispatch. It must preserve the existing
AO Operator handoff boundary: AO artifacts are the contract between roles.

## Verification Matrix

Every phase must compile into a verification matrix that names deterministic
checks for code, docs, security, provider posture, browser behavior, live
evidence, artifact hygiene, and release readiness. The matrix must identify the
minimum closure command and any higher-risk supplemental checks.

## UAT Gate

User acceptance testing is explicit state, not chat residue. Agent OS should
record UAT prompts, user responses, unresolved questions, accepted behaviors,
and rejected behaviors. UAT must block closure when acceptance criteria require
human confirmation.

## Learning Loop

After closure, Agent OS extracts decisions, process lessons, test gaps, and
failure modes into durable learning artifacts. Lessons must be scoped and
inspectable; they must not inject unrelated context into future prompts.

## Operator Cockpit

The operator cockpit is the single current view for active milestone, current
lane, failed role, normalized blocker reason, approval status, next safe
command, evidence paths, dispatch state, and ship readiness.

## Negative Constraints

- MUST NOT dispatch AO providers from this SDD.
- MUST NOT change runtime role behavior in the doc-only slice.
- MUST NOT introduce provider API-key auth paths.
- MUST NOT append generated context to `AGENTS.md`.
- MUST NOT require the detached `llm-wiki` checkout for normal validation.
- MUST NOT hide live-provider approval behind a generic local validation pass.

## Implementation Slices

1. Agent OS SDD and contract: create this SDD, the validation contract, and a
   local validator. No runtime behavior changes.
2. Mission router and state layer: add route classification and durable project
   state artifacts. Current completed evidence:
   `docs/sdd/14-agent-os-mission-router-state.md`,
   `scripts/agent_os_router.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-mission-router-state.json`.
3. Codebase mapper and specialist roles: add compact codebase intelligence and
   optional specialists. Current completed evidence:
   `docs/sdd/15-agent-os-codebase-specialists.md`,
   `scripts/agent_os_codebase_map.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-codebase-specialists.json`.
4. Capability and skill validation: validate role contracts before dispatch.
   Current completed evidence:
   `docs/sdd/16-agent-os-capability-validation.md`,
   `docs/contracts/ao-operator-agent-capabilities.json`,
   `scripts/agent_os_capability_validator.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-capability-validation.json`.
5. Phase compiler and verification matrix: compile roadmap phases into AO
   waves with closure gates. Current completed evidence:
   `docs/sdd/17-agent-os-phase-compiler.md`,
   `scripts/agent_os_phase_compiler.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json`.
6. Phase execution handoff: generate scoped role packets from the compiled
   phase plan without RunSpec rendering or provider dispatch. Current completed
   evidence:
   `docs/sdd/18-agent-os-phase-handoff.md`,
   `scripts/agent_os_phase_handoff.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json`.
7. UAT acceptance state: generate pending human acceptance items from scoped
   handoff packets while keeping closure blocked. Current completed evidence:
   `docs/sdd/19-agent-os-uat-state.md`,
   `scripts/agent_os_uat_state.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json`.
8. Learning extraction: record lessons, negative learnings, role evidence
   needs, and open blockers from UAT state without closure authorization.
   Current completed evidence:
   `docs/sdd/20-agent-os-learning-extract.md`,
   `scripts/agent_os_learning_extract.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json`.
9. Operator cockpit: add one operator view. Current completed evidence:
   `docs/sdd/21-agent-os-operator-cockpit.md`,
   `scripts/agent_os_operator_cockpit.py`, and
   `run-artifacts/remote-transfer-v2-stress-live/agent-os-operator-cockpit.json`.
10. UAT response gate: generate human response templates and authorize closure
    only when all required UAT items are explicitly accepted. Current completed
    evidence:
    `docs/sdd/22-agent-os-uat-response-gate.md`,
    `scripts/agent_os_uat_response_gate.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json`.
11. Closure gate: close the local Agent OS lane only after UAT responses and
    release readiness both pass. Current completed evidence:
    `docs/sdd/23-agent-os-closure-gate.md`,
    `scripts/agent_os_closure_gate.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-closure-gate.json`.
12. RunSpec renderer: render a provider-profile-aware, non-dispatching AO
    RunSpec draft and scoped prompt packet set from phase handoff evidence.
    Current completed evidence:
    `docs/sdd/24-agent-os-runspec-renderer.md`,
    `scripts/agent_os_runspec_renderer.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`.
13. RunSpec validation gate: validate the rendered RunSpec draft, prompt packet
    coverage, dependency graph, provider posture, provider-profile alignment,
    and dispatch safety flags. Current completed evidence:
    `docs/sdd/25-agent-os-runspec-validation.md`,
    `scripts/agent_os_runspec_validator.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json`.
14. Execution approval gate: record exact future AO execution command and
    approval-file contract without dispatch. Current completed evidence:
    `docs/sdd/26-agent-os-runspec-execution-approval-gate.md`,
    `scripts/check_agent_os_runspec_execution_approval_gate.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`.
15. No-provider execution rehearsal: prove Agent OS RunSpec execution refuses
    missing approval. Current completed evidence:
    `docs/sdd/27-agent-os-runspec-no-provider-rehearsal.md`,
    `scripts/rehearse_agent_os_runspec_execution.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-rehearsal.json`.
16. Postrun router: route future execution evidence as pending, accepted,
    diagnostic, or blocked. Current completed evidence:
    `docs/sdd/28-agent-os-runspec-postrun-router.md`,
    `scripts/route_agent_os_runspec_postrun.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json`.
17. Diagnostics preservation: preserve sanitized future failure diagnostics
    without raw AO homes. Current completed evidence:
    `docs/sdd/29-agent-os-runspec-diagnostics-preservation.md`,
    `scripts/preserve_agent_os_runspec_diagnostics.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-diagnostics-preservation.json`.
18. Execution approval contract: validate explicit approval JSON before any
    Agent OS execution. Current completed evidence:
    `docs/sdd/30-agent-os-execution-approval-contract.md`,
    `scripts/validate_agent_os_runspec_execution_approval.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json`.
19. Approval-only execution launcher: block Agent OS execution unless approval
    validation is valid. Current completed evidence:
    `docs/sdd/31-agent-os-approval-only-execution-launcher.md`,
    `scripts/run_agent_os_runspec_execution.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json`.
20. Evaluator closure contract: require AO completion and evaluator acceptance
    before Agent OS closure. Current completed evidence:
    `docs/sdd/32-agent-os-evaluator-closure-contract.md`,
    `scripts/validate_agent_os_runspec_evaluator_closure.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-evaluator-closure.json`.
21. Role-output schema validator: enforce role status fields and reject full
    transcript payloads. Current completed evidence:
    `docs/sdd/33-agent-os-role-output-schema.md`,
    `scripts/check_agent_os_role_output_schema.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-output-schema-validation.json`.
22. Execution hygiene gate: scan prompts and outputs for secrets, stale context,
    detached wiki context, and transcript leakage. Current completed evidence:
    `docs/sdd/34-agent-os-execution-hygiene.md`,
    `scripts/check_agent_os_execution_hygiene.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-execution-hygiene.json`.
23. Approved execution runner: run the validated Agent OS RunSpec command only
    after explicit approval and `--execute`, while committed evidence remains
    blocked without approval. Current completed evidence:
    `docs/sdd/35-agent-os-approved-execution-runner.md`,
    `scripts/run_agent_os_runspec_execution.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json`.
24. Role-output ingestion: convert AO-produced role artifact markdown into
    Agent OS role-output JSON and update execution-report closure fields.
    Current completed evidence:
    `docs/sdd/36-agent-os-role-output-ingestion.md`,
    `scripts/ingest_agent_os_role_outputs.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-output-ingestion.json`.
25. Role graph and state versioning: record the deterministic core role graph
    and v2 state compatibility baseline before router or RunSpec architecture
    changes. Current completed evidence:
    `docs/sdd/44-agent-os-role-graph-state-versioning.md`,
    `scripts/agent_os_role_graph.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json`.
26. Accepted execution commit guard: block success-evidence commits unless the
    postrun route, execution report, and evaluator closure all accept together.
    Current completed evidence:
    `docs/sdd/45-agent-os-accepted-execution-commit-guard.md`,
    `scripts/check_agent_os_accepted_execution_commit_guard.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json`.
27. Postrun route matrix: prove pending, accepted, failed, blocked,
    invalid-gate, and missing-evaluator-acceptance states route safely. Current
    completed evidence:
    `docs/sdd/46-agent-os-postrun-route-matrix.md`,
    `scripts/check_agent_os_postrun_route_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-postrun-route-matrix.json`.
28. State v2 persistence: load, migrate, and write Agent OS state v2 snapshots
    while forcing stale dispatch flags off. Current completed evidence:
    `docs/sdd/47-agent-os-state-v2-persistence.md`,
    `scripts/agent_os_state_v2.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json`.
29. RunSpec compatibility matrix: prove current renderer/YAML evidence and the
    legacy renderer v1 shape stay non-dispatching and task-compatible before
    router architecture changes. Current completed evidence:
    `docs/sdd/48-agent-os-runspec-compatibility-matrix.md`,
    `scripts/check_agent_os_runspec_compatibility_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-compatibility-matrix.json`.
30. Architecture readiness summary: aggregate role graph, state v2, commit
    guard, route matrix, and RunSpec compatibility baselines into one
    operator-facing go/no-go summary. Current completed evidence:
    `docs/sdd/49-agent-os-architecture-readiness-summary.md`,
    `scripts/summarize_agent_os_architecture_readiness.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json`.
31. Router v2 state: emit native state v2 from the mission router only after
    architecture readiness passes, while preserving v1 as the default output.
    Current completed evidence:
    `docs/sdd/50-agent-os-router-v2-state.md`,
    `scripts/agent_os_router.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json`.
32. State evidence hygiene: reject stale dispatch flags, blockers, schema drift,
    and untracked Agent OS state diagnostics before more architecture work.
    Current completed evidence:
    `docs/sdd/51-agent-os-state-evidence-hygiene.md`,
    `scripts/check_agent_os_state_evidence_hygiene.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-evidence-hygiene.json`.
33. Approved execution fixture: exercise the approved execution happy path
    without providers while proving fixture-only output cannot be committed as
    live success evidence. Current completed evidence:
    `docs/sdd/52-agent-os-approved-execution-fixture.md`,
    `scripts/check_agent_os_approved_execution_fixture.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-fixture.json`.
34. Router migration matrix: prove v1-to-v2 and v2 reload behavior fail closed
    across stale flags, live-provider blockers, invalid schemas, and missing
    architecture readiness. Current completed evidence:
    `docs/sdd/53-agent-os-router-migration-matrix.md`,
    `scripts/check_agent_os_router_migration_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-migration-matrix.json`.
35. RunSpec provider boundary matrix: prove Codex-only, Claude-only, mixed,
    rendered-YAML, and provider-substitution-refusal cases stay explicit and
    non-dispatching.
    Current completed evidence:
    `docs/sdd/54-agent-os-runspec-provider-boundary-matrix.md`,
    `scripts/check_agent_os_runspec_provider_boundary_matrix.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-provider-boundary-matrix.json`.
36. State stale cleanup: provide a safe dry-run/apply command for untracked
    Agent OS state diagnostics so hygiene failures have a repeatable cleanup
    path. Current completed evidence:
    `docs/sdd/55-agent-os-state-stale-cleanup.md`,
    `scripts/cleanup_agent_os_state_artifacts.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json`.
37. Repeated-run hygiene baseline: prove same-slug dry-run-after-live,
    live-after-failed-live, and reroute-after-accepted-live scenarios fail
    closed without providers. Current completed evidence:
    `docs/sdd/58-repeated-run-hygiene-baseline.md`,
    `scripts/check_repeated_run_hygiene.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/dispatch/repeated-run-hygiene.json`.
38. Normalized failure diagnostics: surface AO Runtime normalized failure
    reasons in Factory event summaries and evaluator evidence. Current
    completed evidence:
    `docs/sdd/59-normalized-failure-diagnostics.md`,
    `scripts/check_normalized_failure_diagnostics.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/normalized-failure-diagnostics.json`.
39. RunSpec state v2 bridge: require the Agent OS RunSpec renderer to consume
    committed router state v2 metadata before producing AO-facing draft
    evidence. Current completed evidence:
    `docs/sdd/60-agent-os-runspec-state-v2-bridge.md`,
    `scripts/agent_os_runspec_renderer.py`, and
    `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json`.
40. RunSpec execution plan lock: bind approval and execution to the exact
    rendered RunSpec SHA-256 so path/task-count approval cannot survive YAML
    drift. Current completed evidence:
    `docs/sdd/61-agent-os-runspec-execution-plan-lock.md`,
    `scripts/check_agent_os_runspec_execution_approval_gate.py`,
    `scripts/validate_agent_os_runspec_execution_approval.py`, and
    `scripts/run_agent_os_runspec_execution.py`.

## Acceptance Criteria

- Agent OS SDD exists and declares classification, shape, required sections,
  and negative constraints.
- Validation contract exists with SHALL statements, acceptance criteria,
  sensitive fields, trigger hints, and implementation slices.
- `scripts/check_agent_os_sdd.py --write-output --json` returns `PASS`.
- `scripts/agent_os_role_graph.py --write-output --json` returns `PASS`.
- `scripts/check_agent_os_accepted_execution_commit_guard.py --write-output --json`
  returns `PASS`.
- `scripts/check_agent_os_postrun_route_matrix.py --write-output --json`
  returns `PASS`.
- `scripts/agent_os_state_v2.py --write-output --json` returns `PASS`.
- `scripts/check_agent_os_runspec_compatibility_matrix.py --write-output --json`
  returns `PASS`.
- `scripts/summarize_agent_os_architecture_readiness.py --write-output --json`
  returns `PASS`.
- `scripts/agent_os_router.py --state-version v2 ... --write-state ... --json`
  returns `PASS`.
- `scripts/check_agent_os_state_evidence_hygiene.py --write-output --json`
  returns `PASS`.
- `scripts/check_agent_os_approved_execution_fixture.py --write-output --json`
  returns `PASS`.
- `scripts/check_agent_os_router_migration_matrix.py --write-output --json`
  returns `PASS`.
- `scripts/check_agent_os_runspec_provider_boundary_matrix.py --write-output --json`
  returns `PASS`.
- `scripts/agent_os_runspec_validator.py --provider-profile .env.example --write-output --json`
  returns `PASS` with `provider_profile_matches=true`.
- `scripts/cleanup_agent_os_state_artifacts.py --write-output --json`
  returns `PASS`.
- `scripts/check_agent_os_failed_diagnostics_fixture.py --write-output --json`
  returns `PASS` with `primary_normalized_reason=provider-rate-limit`.
- `scripts/check_agent_os_approval_alignment_drift.py --write-output --json`
  returns `PASS` with provider alignment fields present across approval
  artifacts.
- `scripts/check_repeated_run_hygiene.py --write-output --json` returns
  `PASS` with all same-slug rerun scenarios passing closed.
- `scripts/check_normalized_failure_diagnostics.py --write-output --json`
  returns `PASS` with normalized reason counts and evaluator evidence present.
- `scripts/agent_os_runspec_renderer.py --provider-profile .env.example --state-baseline run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json --write-output --write-runspec --json`
  returns `PASS` with `state_baseline_checked=true` and
  `state_schema_version=ao-operator/agent-os-state/v2`.
- Agent OS approval gate and approval validation evidence carry a matching
  non-empty `runspec_sha256`, and the execution launcher records
  `current_runspec_sha256`.
- `dispatch_authorized=false` and `live_providers_run=false` remain true for
  this SDD lane.
- Standard AO Operator validation and closure pass on Mac and Ubuntu.
