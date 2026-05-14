# AO Operator Full Implementation SDD

This SDD package is the source of truth for turning AO Operator from the current
validated seed into a full local AO-backed software factory.

AO Operator is not just a scaffold. The final implementation must accept a task
brief, classify and shape the work, create durable factory artifacts, render and
run AO `RunSpec` DAGs, pass scoped evidence between phases, and close only after
evaluator acceptance.

## Documents

- `01-architecture.md` - system architecture, control flow, data flow, provider
  model, and AO boundaries.
- `02-implementation-plan.md` - step-by-step implementation sequence.
- `03-interfaces-and-contracts.md` - CLI, `.env`, RunSpec, artifact, status,
  and role-output contracts.
- `04-verification-plan.md` - unit, integration, live AO, provider, auth, and
  closure tests.
- `05-rollout-and-risks.md` - rollout phases, known gaps, risks, fallback
  behavior, and acceptance gates.
- `06-implementation-checklist.md` - explicit checklist for implementation,
  validation, provider execution, artifact handoff, and closure.
- `10-stress-topology.md` - step-by-step SDD conduct guide for the large
  remote-transfer v2 stress topology and its validation gates.
- `11-operator-slices.md` - machine-checkable operator slice manifest contract
  for diagnostics, validation, dry-run materialization, live runs, and gated
  escalation.
- `12-bounded-live-acceptance.md` - explicit acceptance gate for the bounded
  live Remote Transfer v2 profile and its failure-preservation rules.
- `13-agent-os.md` - doc-only SDD for the planned Agent OS layer above AO
  Runtime: mission routing, state, capabilities, specialists, phase
  compilation, UAT, learning, and operator cockpit.
- `14-agent-os-mission-router-state.md` - first Agent OS implementation slice:
  deterministic mission routing and state snapshot evidence without provider
  dispatch.
- `15-agent-os-codebase-specialists.md` - deterministic codebase surface map
  and specialist-role recommendation evidence.
- `16-agent-os-capability-validation.md` - core role capability contract and
  skill validation with non-executable specialist recommendations.
- `17-agent-os-phase-compiler.md` - deterministic phase plan compilation and
  verification matrix emission without provider dispatch.
- `18-agent-os-phase-handoff.md` - scoped role handoff packet generation from
  the compiled phase plan without RunSpec rendering or provider dispatch.
- `19-agent-os-uat-state.md` - durable pending UAT acceptance state generated
  from scoped handoff packets without closure authorization.
- `20-agent-os-learning-extract.md` - durable lesson and blocker extraction
  from pending UAT state without closure authorization.
- `21-agent-os-operator-cockpit.md` - unified operator cockpit snapshot for
  Agent OS blockers, UAT, readiness, and evidence paths.
- `22-agent-os-uat-response-gate.md` - human UAT response template and closure
  authorization gate.
- `23-agent-os-closure-gate.md` - final local Agent OS closure gate composed
  from accepted UAT responses and release readiness.
- `24-agent-os-runspec-renderer.md` - non-dispatching AO RunSpec draft
  renderer from scoped Agent OS handoff packets.
- `25-agent-os-runspec-validation.md` - validation gate for the rendered
  Agent OS RunSpec draft, prompt packets, and dispatch safety flags.
- `26-agent-os-runspec-execution-approval-gate.md` - non-dispatching approval
  posture and exact future execution command for Agent OS RunSpec execution.
- `27-agent-os-runspec-no-provider-rehearsal.md` - no-provider rehearsal that
  proves Agent OS RunSpec execution refuses missing approval.
- `28-agent-os-runspec-postrun-router.md` - postrun route classifier for future
  Agent OS RunSpec execution evidence.
- `29-agent-os-runspec-diagnostics-preservation.md` - sanitized diagnostics
  preservation guard for future failed Agent OS RunSpec executions.
- `30-agent-os-execution-approval-contract.md` - explicit approval JSON
  validator for future Agent OS RunSpec execution.
- `31-agent-os-approval-only-execution-launcher.md` - execution launcher that
  blocks unless explicit approval validates.
- `32-agent-os-evaluator-closure-contract.md` - Agent OS-specific evaluator
  closure contract for accepted execution evidence.
- `33-agent-os-role-output-schema.md` - role-output status field schema
  validator.
- `34-agent-os-execution-hygiene.md` - prompt and role-output hygiene gate for
  transcript, secret, and stale-context leakage.
- `35-agent-os-approved-execution-runner.md` - approved `ao run` launcher
  behavior with non-dispatching committed evidence.
- `36-agent-os-role-output-ingestion.md` - ingestion from AO role artifacts into
  Agent OS role-output JSON and execution-report closure fields.
- `37-public-release-security-and-dast.md` - public-release text and AST
  security gate plus no-provider DAST lane for the SDLC.
- `38-security-sdlc-roadmap.md` - security roadmap for SEI CERT-aligned code
  review, threat model/data-flow analysis, and gated penetration testing.
- `39-security-threat-model-data-flow.md` - STRIDE threat model and data-flow
  trust boundaries for remote worker, AO, provider, and artifact surfaces.
- `40-manual-penetration-test-gate.md` - approval-only manual penetration test
  scope, evidence, and stop rules.
- `41-host-key-evidence-gate.md` - host-key pinning and `known_hosts`
  evidence requirements before remote DAST approval.
- `42-manual-pentest-report-classifier.md` - manual pentest report template
  classifier and non-authorizing evidence contract.
- `43-supply-chain-audit-gate.md` - dependency manifest, lockfile, advisory,
  license, and pinning gate for release posture.
- `44-agent-os-role-graph-state-versioning.md` - deterministic Agent OS role
  graph and state v2 compatibility baseline before router/RunSpec architecture
  changes.
- `45-agent-os-accepted-execution-commit-guard.md` - success-evidence commit
  guard for Agent OS execution reports, postrun routing, and evaluator closure.
- `46-agent-os-postrun-route-matrix.md` - deterministic postrun routing matrix
  for pending, accepted, failed, blocked, and invalid Agent OS execution states.
- `47-agent-os-state-v2-persistence.md` - persisted Agent OS state v2
  reader/writer and v1 migration guard with fail-closed dispatch flags.
- `48-agent-os-runspec-compatibility-matrix.md` - current and legacy Agent OS
  RunSpec compatibility matrix before router architecture changes.
- `49-agent-os-architecture-readiness-summary.md` - operator-facing summary of
  role graph, state v2, commit, route, and RunSpec architecture baselines.
- `50-agent-os-router-v2-state.md` - opt-in mission-router state v2 output
  behind architecture readiness.
- `51-agent-os-state-evidence-hygiene.md` - state v2 artifact hygiene guard
  for stale dispatch flags and untracked state diagnostics.
- `52-agent-os-approved-execution-fixture.md` - provider-free approved
  execution happy-path fixture that cannot count as live success evidence.
- `53-agent-os-router-migration-matrix.md` - v1/v2 router state migration
  regression matrix before deeper architecture changes.
- `54-agent-os-runspec-provider-boundary-matrix.md` - Codex/Claude/mixed
  provider-boundary matrix for Agent OS RunSpec tasks.
- `55-agent-os-state-stale-cleanup.md` - safe dry-run/apply cleanup command
  for untracked Agent OS state diagnostic artifacts.
- `56-agent-os-failed-diagnostics-fixture.md` - provider-free failed execution
  diagnostics preservation fixture.
- `57-agent-os-approval-alignment-drift.md` - provider alignment drift checker
  for approval and execution artifacts.
- `58-repeated-run-hygiene-baseline.md` - same-slug dry-run, failed-live, and
  reroute hygiene baseline before deeper architecture changes.
- `59-normalized-failure-diagnostics.md` - AO normalized failure reasons in
  Factory event summaries and evaluator evidence.
- `60-agent-os-runspec-state-v2-bridge.md` - RunSpec renderer bridge from
  router state v2 into AO-facing draft evidence.
- `61-agent-os-runspec-execution-plan-lock.md` - SHA-256 RunSpec approval lock
  across approval gate, approval validation, and execution launcher.
- `62-remote-transfer-hardening-evidence-gate.md` - Factory-side evidence gate
  for signed manifests, chunk cleanup, large transfer smoke, and signed worker
  runtime smoke.
- `63-resource-performance-guardrails.md` - non-live guardrails for dry-run
  wallclock, provider-budget abort conditions, and temp AO/worktree footprint.
- `64-agent-os-execution-approval-bundle.md` - template-only approval bundle
  with RunSpec hash, operator, risk, and expiry fields.
- `65-operator-guardrail-summary.md` - aggregate operator cockpit, hardening,
  resource, approval, readiness, and no-provider rehearsal guardrail summary.
- `66-agent-os-approval-materialization.md` - explicit approval-file
  materializer with default dry-run posture and RunSpec hash drift refusal.
- `67-release-artifact-index.md` - durable index that links the latest SDD
  guardrail lanes to their PASS status artifacts.
- `68-agent-os-approval-lifecycle.md` - approval lifecycle gate that fails
  closed for expired approval files and RunSpec hash drift.
- `69-agent-os-approved-launch-proof.md` - isolated positive approval-path
  proof that reaches launcher `PLAN` without provider dispatch.
- `70-agent-os-approval-cleanup.md` - safe approval-file cleanup command for
  expired, invalid, or explicitly force-cleared approvals.
- `71-agent-os-approval-audit-history.md` - append-only audit summary for
  approval materialization and cleanup events.
- `72-agent-os-post-approval-cleanup-route.md` - isolated proof that simulated
  accepted postrun routing is followed by approval cleanup.
- `73-agent-os-approval-materialization-runbook.md` - operator runbook and
  checker for real approval materialization.
- `74-agent-os-approval-audit-retention.md` - audit retention and rotation
  posture checker for compact approval event history.
- `75-agent-os-approval-bundle-signature.md` - tamper-evident approval bundle
  signature sidecar and verification gate.
- `76-agent-os-approval-revocation.md` - operator approval revocation and
  rollback flow with compact revocation events.
- `77-agent-os-approval-identity-signature.md` - isolated `ssh-keygen -Y`
  identity-bound approval bundle signature proof.
- `78-agent-os-approval-revocation-apply-proof.md` - isolated proof that
  revocation `--apply --force` removes approval files and sanitizes logs.
- `79-agent-os-approval-audit-archive-restore.md` - isolated archive/restore
  proof for compact approval audit history.
- `80-mac-ubuntu-approval-artifact-parity.md` - Mac-to-Ubuntu approval artifact
  parity smoke with matching Git heads and remote non-dispatching proof checks.
- `81-mac-ubuntu-signed-approval-bundle-transfer.md` - signed approval bundle
  transfer and Ubuntu-side verification with remote staging cleanup.
- `82-mac-ubuntu-remote-approval-materialization-dry-run.md` - Ubuntu-side
  approval materialization dry-run from the signed bundle with no approval-file
  write and remote staging cleanup.
- `83-mac-ubuntu-remote-approval-revocation-rollback.md` - Ubuntu-side isolated
  approval revocation apply and rollback restore proof with remote staging
  cleanup.
- `84-mac-ubuntu-remote-approval-runbook.md` - operator runbook for the
  no-provider Mac-to-Ubuntu approval evidence sequence and stop rules.
- `85-mac-ubuntu-remote-approved-fixture.md` - Ubuntu-side isolated positive
  approval fixture that reaches launcher `PLAN` without provider dispatch.
- `86-agent-os-architecture-implementation-gate.md` - coherent no-provider
  gate across architecture readiness, role graph, router v2 state, handoff,
  RunSpec renderer/validator, provider boundary, and hygiene evidence.
- `87-agent-os-router-transition-matrix.md` - deterministic mission-router
  transition matrix for classification, labels, shape gates, live-provider
  blocking, and state v2 release routing.
- `88-agent-os-runspec-failure-injection-matrix.md` - provider-free RunSpec
  failure-injection matrix for stale hashes, missing prompts, dispatch flag
  mutation, provider drift, invalid providers, and missing state baselines.
- `89-operator-safe-next-command.md` - one operator-facing report for current
  state, approval posture, release readiness, evidence paths, and the next safe
  non-dispatching command.
- `90-agent-os-runspec-dag-edge-coverage.md` - role graph to RunSpec DAG edge
  coverage with fail-closed cycle, missing edge, unknown dependency, duplicate
  entry, and terminal fork mutations.
- `91-agent-os-runspec-yaml-dag-parity.md` - committed RunSpec YAML DAG parity
  against renderer JSON and the role graph with fail-closed YAML-only
  mutations.
- `92-agent-os-runspec-yaml-semantic-parity.md` - committed RunSpec YAML
  semantic parity for provider, promptFile, workspace, policyProfile, kind,
  and dispatchAuthorized with fail-closed mutations for each field.
- `93-agent-os-runspec-yaml-schema-injection.md` - committed RunSpec YAML
  schema/format failure injection covering malformed YAML, duplicate task
  ids, missing spec block, bad deps type, unknown task field, and unsafe
  dispatchAuthorized; every mutation MUST fail closed.
- `94-agent-os-runspec-ao-preflight-compatibility.md` - committed RunSpec
  AO Runtime preflight compatibility extracted from ao-core source
  (ApiVersion, RunSpecKind, TaskKind) with fail-closed mutations covering
  wrong apiVersion, wrong kind, unknown task kind, unknown dependency, and
  DAG cycle; never invokes AO and never dispatches providers.
- `95-agent-os-router-default-state-version.md` - mission router CLI
  defaults to state v2 while preserving explicit `--state-version v1`
  back-compat; argparse default and schema-on-write are gated and the gate
  fails closed without dispatch.
- `96-agent-os-role-graph-backward-compat.md` - legacy v1 router state and
  role-graph artifacts migrate cleanly under the v2 default while unknown
  schemas are refused; six fixtures exercise minimal v1 state, extra v1
  fields, missing role-graph schema, v2 round-trip, legacy role-graph JSON,
  and the unknown-schema refusal path; never invokes AO and never
  dispatches providers.
- `97-remote-transfer-chunk-cleanup-invariants.md` - AO Runtime
  ``chunked_upload`` cleanup invariants are reproduced as a portable Python
  state machine with five mutation cases (orphaned chunk after abort,
  missing finalize, stale partial-stage marker, double commit, retry-index
  drift) plus a clean-commit control; each mutation must be rejected fail
  closed; runs in a tempfile work dir, never invokes AO and never
  dispatches providers.
- `98-remote-transfer-signed-bundle-tamper.md` - AO Runtime
  ``signed_bundle_transfer`` integrity invariants are reproduced as a
  portable Python state machine with five mutation cases (truncated
  bundle, swapped chunk payloads, unregistered signing key, replayed
  nonce, manifest digest mismatch) plus a clean-bundle control; each
  mutation must be rejected fail closed; runs in a tempfile work dir,
  uses synthetic HMAC keys only, never invokes AO and never dispatches
  providers.
- `99-remote-transfer-approval-expiry-rotation.md` - AO Runtime
  ``signed_remote_approval_transfer`` lifecycle invariants are
  reproduced as a portable Python state machine with four mutation
  cases (expired approval timestamp, approval used after rotation
  cutover plus grace, signing key rotated mid-flight without grace,
  approval reused beyond TTL) plus a clean-approval control; each
  mutation must be rejected fail closed; runs in a tempfile work dir,
  uses synthetic HMAC keys only, anchors verification to a fixed
  reference clock, never invokes AO and never dispatches providers.
- `100-remote-transfer-bundle-ordering-resume.md` - AO Runtime
  ``signed_remote_approval_transfer`` streaming and resume invariants
  are reproduced as a portable Python state machine with four mutation
  cases (chunk delivered out of order, partial resume drops a middle
  chunk, resume cursor lies about its high-water mark, duplicate chunk
  delivery) plus a clean-ordered-delivery control; each mutation must
  be rejected fail closed; runs in a tempfile work dir, uses synthetic
  per-case payloads only, never invokes AO and never dispatches
  providers.
- `101-remote-transfer-provider-redaction-round-trip.md` - AO Runtime
  ``provider_redaction_round_trip`` data-safety invariants are
  reproduced as a portable Python state machine with four mutation
  cases (redaction marker stripped before transmit, sensitive field
  leaks past the redaction filter, double-redaction corrupts the
  payload, provider response leaks the redacted plaintext value
  back) plus a clean-round-trip control; each mutation must be
  rejected fail closed; runs in a tempfile work dir, uses synthetic
  api keys and emails only, never invokes AO and never dispatches
  providers.
- `102-remote-transfer-network-retry-idempotency.md` - AO Runtime
  ``network_retry_idempotency`` resilience invariants are reproduced
  as a portable Python state machine with four mutation cases (retry
  mints a new nonce so the receiver cannot dedupe, partial flush on
  network drop finalizes without an ack, lost ack causes the receiver
  to double-commit the same nonce, sender timeout shorter than the
  response window leaves an orphaned commit on the receiver) plus a
  clean-retry-round-trip control; each mutation must be rejected fail
  closed; runs in a tempfile work dir, uses synthetic ops/chunk_index/
  nonce values only, never invokes AO and never dispatches providers.
- `103-remote-transfer-concurrent-transfer-collision.md` - AO Runtime
  ``concurrent_transfer_collision`` lock-and-finalize invariants are
  reproduced as a portable Python state machine with four mutation
  cases (parallel transfers without lock corrupt shared state,
  simultaneous finalize double-completes the bundle, lost writer
  overwrites the winner's bundle, stale lock holder resumes after
  handoff) plus a clean-serialized-concurrent-transfers control; each
  mutation must be rejected fail closed; runs in a tempfile work dir,
  uses synthetic ops/chunk_index/lock_holder/writer_id values only,
  never invokes AO and never dispatches providers.
- `104-remote-transfer-bundle-schema-version-skew.md` - AO Runtime
  ``bundle_schema_version_skew`` wire-boundary invariants are
  reproduced as a portable Python state machine with four mutation
  cases (sender ships a down-rev bundle below the receiver's minimum
  supported version, sender ships a forward bundle above the
  receiver's maximum that the receiver silently downgrades, sender
  advertises an extension the receiver does not know but the
  receiver still accepts, sender omits the schema_version field and
  the receiver assumes a default) plus a clean-matched-schema-
  version control; each mutation must be rejected fail closed; runs
  in a tempfile work dir, uses synthetic semvers and extension
  names only, never invokes AO and never dispatches providers.
- `105-remote-transfer-resource-exhaustion-guard.md` - AO Runtime
  ``resource_exhaustion_guard`` per-bundle quota invariants are
  reproduced as a portable Python state machine with four mutation
  cases (sender announces a chunk count above the receiver's
  per-bundle quota, sender announces an aggregate byte total above
  the receiver's per-bundle byte quota, an individual chunk's
  payload exceeds the receiver's per-chunk byte ceiling, and the
  sender ships a surplus chunk beyond the announced count) plus a
  clean-within-quota control; each mutation must be rejected fail
  closed; runs in a tempfile work dir, uses synthetic chunk counts
  and byte totals only, never invokes AO and never dispatches
  providers.
- `106-remote-transfer-clock-skew-tolerance.md` - AO Runtime
  receiver-side clock skew invariants are reproduced as a portable
  Python state machine with four mutation cases (sender clock ahead
  of receiver beyond the bounded skew tolerance, sender clock behind
  receiver beyond the bounded skew tolerance, future-dated bundle
  silently force-accepted as currently valid, and a TTL window
  straddling the skew envelope silently extended past not_after)
  plus a clean-within-skew-tolerance control; each mutation must be
  rejected fail closed; runs in a tempfile work dir, uses a
  synthetic UTC anchor and synthetic skew bound only, never invokes
  AO and never dispatches providers.
- `107-remote-transfer-bundle-id-uniqueness.md` - AO Runtime
  receiver-side bundle-id uniqueness invariants are reproduced as a
  portable Python state machine with four mutation cases (a sender
  re-submits the same bundle_id within one session with different
  content, two distinct senders submit colliding bundle_ids that
  the receiver silently merges, two distinct full bundle_ids
  collapse under a truncated index prefix, and a sender replays a
  previously-completed bundle_id after the in-flight ledger is
  cleared) plus a clean-unique-bundle-ids control; each mutation
  must be rejected fail closed; runs in a tempfile work dir, uses
  synthetic 64-hex-character bundle_id literals only, never invokes
  AO and never dispatches providers.
- `108-remote-transfer-bundle-content-type-allowlist.md` - AO
  Runtime receiver-side bundle content-type allowlist invariants
  are reproduced as a portable Python state machine with four
  mutation cases (an unknown content_type silently coerced to the
  default allowlisted MIME, an extension/payload-magic mismatch
  dispatched without sniffing, an unknown content_encoding silently
  fallen back to identity, and a charset parameter smuggling a
  path-traversal token concatenated into a derived path) plus a
  clean-allowlisted-content-type control; each mutation must be
  rejected fail closed; runs in a tempfile work dir, uses synthetic
  content_type/encoding/charset literals only, never invokes AO
  and never dispatches providers.
- `109-remote-transfer-per-tenant-quota-isolation.md` - AO Runtime
  receiver-side per-tenant quota isolation invariants are reproduced
  as a portable Python state machine with four mutation cases (one
  tenant's bundle debit misrouted into another tenant's bucket, all
  tenants merged into a single shared bucket whose total exceeds the
  per-tenant cap, a missing tenant identity silently coerced to a
  default tenant, and an abort refund double-credited so the bucket
  recovers more than it was charged) plus a clean-per-tenant-within-
  quota control; each mutation must be rejected fail closed; runs
  in a tempfile work dir, uses synthetic tenant identities and
  quota numbers only, never invokes AO and never dispatches
  providers.
- `110-remote-transfer-wire-encryption-required.md` - AO Runtime
  receiver-side wire-encryption invariants are reproduced as a
  portable Python state machine with four mutation cases (a bundle
  shipped over a cleartext socket and silently accepted, a downgraded
  TLS transport version negotiated outside the allowlist and silently
  accepted, a NULL or otherwise denied cipher suite negotiated and
  silently accepted, and a per-bundle encrypted=true header stripped
  by a man-in-the-middle after handshake and silently accepted) plus
  a clean-encrypted-bundle-accepted control; each mutation must be
  rejected fail closed; runs in a tempfile work dir, uses synthetic
  transport names and cipher-suite identifiers only, never invokes
  AO and never dispatches providers.
- `111-remote-transfer-sender-identity-rotation.md` - AO Runtime
  receiver-side sender-identity-rotation invariants are reproduced
  as a portable Python state machine with four mutation cases (a
  bundle signed by a retired identity silently accepted past the
  rotation grace window, a rotation announcement silently activated
  without a continuity signature from the prior identity, a
  rotation announcement silently activated when its effective_at
  timestamp is far in the future beyond the clock-skew tolerance,
  and a dual-acceptance window silently left open past the grace
  window) plus a clean-post-rotation-bundle-accepted control; each
  mutation must be rejected fail closed; runs in a tempfile work
  dir, uses synthetic identity fingerprints, ISO 8601 timestamps,
  and continuity-signature literals only, never invokes AO and
  never dispatches providers.
- `112-ai-agent-blast-radius-inventory.md` - AO Operator + AO Runtime
  agent-reachable surface is enumerated and gated as a portable
  Python inventory state machine with five mutation cases (an
  unclassified high-blast-radius command path silently accepted, a
  destructive action silently accepted without an explicit approval
  gate, a credential-bearing path silently accepted while reachable
  from untrusted content or tool output, a provider dispatch path
  silently accepted while executable without the existing approval
  and readiness posture, and a release/public artifact path
  silently accepted while including instruction files, memory
  blocks, raw prompts, credentials, or local-only diagnostics) plus
  a clean-inventory-classified-and-gated control; each mutation
  must be rejected fail closed; runs in a tempfile work dir, uses
  synthetic placeholder identifiers and category/blast-radius
  literals only, never invokes AO and never dispatches providers.
- `113-ai-agent-destructive-action-approval.md` - AO Operator + AO
  Runtime destructive-action approval state machine is gated as a
  portable Python in-memory verifier with five mutation cases (a
  stale approval reused after expiry, an approval whose scope is
  widened at execute time, the same approval consumed twice for
  distinct destructive ops, a destructive op that runs with a
  policy-only declaration instead of a materialized token, and a
  parent process approval inherited by a child without
  re-confirmation) plus a clean-destructive-action-with-fresh-
  scoped-approval-executes control; each mutation must be rejected
  fail closed; runs in a tempfile work dir, uses synthetic operator,
  token, op, target, blast-radius, and ISO 8601 timestamp literals
  only, never invokes AO and never dispatches providers.
- `114-ai-agent-credential-reachability.md` - AO Operator + AO
  Runtime credential-reachability dataflow taint analysis is gated
  as a portable Python in-memory state machine with five mutation
  cases (an untrusted user prompt concatenated into a subprocess
  argv touching the credential directory, an agent tool output
  piped to a git/scp/rsync shell pipeline targeting the ssh
  directory, an MCP tool result included verbatim in a role-handoff
  state envelope that carries session token paths, a web-fetch
  payload reflected into a shell command resolving an env variable
  carrying a credential, and a prompt-injection-tainted source
  triggering a filesystem read of a credential path while the
  egress redaction step is bypassed) plus a clean-no-untrusted-to-
  credential-reachable-path control; each mutation must be rejected
  fail closed; runs in a tempfile work dir, uses synthetic source/
  sink/target identifiers only, never invokes AO and never
  dispatches providers.
- `115-ai-agent-instruction-packaging-leak-detection.md` -
  AO Operator + AO Runtime instruction & release packaging leak
  detection is gated as a portable Python in-memory state machine
  with five mutation cases (a CLAUDE.md / AGENTS.md instruction
  directive copied verbatim into a public status report, an agent
  memory snippet copy-pasted into a public doc, a raw user prompt
  logged verbatim into operator slice evidence, a provider API key
  surfaced verbatim in an evaluation transcript, and a private /tmp
  diagnostic path included verbatim in a public release artifact)
  plus a clean-no-instruction-or-packaging-leaks-in-public-
  artifacts control; each mutation must be rejected fail closed;
  runs in a tempfile work dir, uses synthetic source / artifact /
  redaction identifiers only, never invokes AO and never dispatches
  providers.
- `116-mcp-tool-poisoning-detection.md` - AO Operator + AO Runtime
  MCP / Tool poisoning detection is gated as a portable Python
  in-memory descriptor verifier with five mutation cases (a hidden
  imperative embedded in an MCP tool description, a tool result
  schema mutating between invocations to add a destructive default
  argument, an MCP returning a URL the agent is asked to fetch and
  apply, a tool name shadowing a trusted native tool, and a signed
  tool descriptor advertising a privilege class outside its
  allowlist) plus a clean-no-mcp-or-tool-poisoning-indicators
  control; each mutation must be rejected fail closed; runs in a
  tempfile work dir, uses synthetic descriptor / hazard / tool-name
  identifiers only, never invokes AO, never dispatches providers,
  and never contacts a real MCP server.
- `117-deepsec-diff-review-advisory-sast.md` - AO Operator + AO Runtime
  DeepSec diff-review advisory SAST is gated as a portable Python
  in-memory dataflow verifier with five mutation cases (an untrusted
  input flowing into a shell command, an untrusted input flowing
  into a filesystem write outside the workspace, an untrusted input
  flowing into network egress, eval/exec on retrieved content, and
  a dynamic import from an agent-controlled path) plus a
  clean-no-untrusted-to-dangerous-sink-edges control; each mutation
  must be rejected fail closed; runs in a tempfile work dir, uses
  synthetic untrusted-input / dangerous-sink / sanitizer identifiers
  only, never invokes AO, never dispatches providers, and never
  invokes any real SAST scanner against the working tree.
- `118-agent-supply-chain-integrity.md` - AO Operator + AO Runtime
  Agent supply-chain integrity is gated as a portable Python in-
  memory provenance verifier with five mutation cases (an unsigned
  package admitted without a signature, a lock-file digest
  mismatch admitted, a dependency-confusion install via a shadow
  registry, a post-install script with network egress, and a
  transitive yank without a re-pin) plus a clean-no-unauthorized-
  provenance-or-unsigned-package-edges control; each mutation must
  be rejected fail closed; runs in a tempfile work dir, uses
  synthetic package / registry / signature / hook / yank
  identifiers only, never invokes AO, never dispatches providers,
  and never invokes any real package manager, registry probe, or
  network call.
- `119-prompt-injection-escape-boundary.md` - AO Operator + AO Runtime
  Prompt-injection escape boundary is gated as a portable Python
  in-memory escape-boundary verifier with five mutation cases (an
  attacker-controlled section that spoofs the system role appended
  after the operator-trusted system slot, a fenced block that
  closes the system-section fence and re-opens with attacker
  instructions, a JSON payload that re-keys the operator-trusted
  system field, an attacker-controlled section that shadows an
  operator-allowlisted tool name, and an attacker-controlled
  section that smuggles instructions via a unicode homoglyph for
  an operator-trusted role marker) plus a clean-no-role-spoofing-
  or-attacker-controlled-system-prompt-appended control; each
  mutation must be rejected fail closed; runs in a tempfile work
  dir, uses synthetic section / role / tool / homoglyph identifiers
  only, never invokes AO, never dispatches providers, and never
  invokes any real LLM, prompt template engine, or remote
  evaluation.
- `120-approval-clock-skew-defense.md` - AO Operator + AO Runtime
  Approval clock-skew defense is gated as a portable Python
  in-memory clock-skew defense verifier with five mutation cases
  (an NTP rewind admit, a leap-second jump admit, a TZ-tagged-as-
  UTC admit, an expired-but-cached admit, and a signed-token
  replay admit) plus a clean-no-clock-skew-or-replay-or-stale-
  freshness-edges control; each mutation must be rejected fail
  closed; runs in a tempfile work dir, uses synthetic approval /
  monotonic / tz / signature / token identifiers only, never
  invokes AO, never dispatches providers, and never invokes any
  real clock service, NTP server, or signing authority.
- `121-agent-log-redaction-round-trip.md` - AO Operator + AO Runtime
  Agent log redaction round-trip is gated as a portable Python
  in-memory round-trip recovery verifier with five mutation cases
  (a partial-pattern match leak, a base64 round-trip leak, a
  path-normalization alias leak, a case-insensitive miss leak,
  and a JSON-string-escape miss leak) plus a clean-no-round-trip-
  recoverable-secret-or-personal-path-in-redacted-output control;
  each mutation must be rejected fail closed; runs in a tempfile
  work dir, uses synthetic log / redaction / token identifiers
  only, never invokes AO, never dispatches providers, and never
  reads or writes any real agent log file or invokes the
  production redaction script.
- `122-per-tenant-blast-radius-cap.md` - AO Operator + AO Runtime
  Per-tenant blast-radius cap is gated as a portable Python
  in-memory per-tenant blast-radius verifier with five mutation
  cases (a cross-tenant fanout admit, a missing-tenant-tag
  admit, a tenant-tag-spoof admit, an allowlist-bypass admit,
  and a quota-overflow leak admit) plus a clean-no-cross-tenant-
  or-unallowlisted-or-quota-overflow-action-edges control; each
  mutation must be rejected fail closed; runs in a tempfile
  work dir, uses synthetic action / tenant / target identifiers
  only, never invokes AO, never dispatches providers, and never
  reads or writes any real tenant-boundary policy file or
  invokes a production allowlist or quota service.
- `123-sandbox-egress-allowlist.md` - AO Operator + AO Runtime
  Sandbox egress allowlist is gated as a portable Python
  in-memory egress verifier with five mutation cases (an
  unallowlisted-host admit, an IP-literal bypass admit, a
  DNS-rebind bypass admit, a proxy-chain bypass admit, and a
  raw-socket bypass admit) plus a clean-no-unallowlisted-or-
  bypassed-egress-attempts control; each mutation must be
  rejected fail closed; runs in a tempfile work dir, uses
  synthetic egress / host / proxy / socket identifiers only,
  never invokes AO, never dispatches providers, and never reads
  or writes any real sandbox egress allowlist file or opens a
  real network connection.
- `124-agent-tool-arg-injection-escape.md` - AO Operator + AO Runtime
  Agent tool-argument injection-escape is gated as a portable
  Python in-memory tool-call argument verifier with five mutation
  cases (a string-template breakout admit, a nested-object
  smuggling admit, a polymorphic-type coercion admit, a
  shell-metacharacter injection admit, and a tool-name spoof
  admit) plus a clean-no-tool-arg-injection-or-breakout-or-
  polymorphic-coercion control; each mutation must be rejected
  fail closed; runs in a tempfile work dir, uses synthetic call /
  tool / arg-payload identifiers only, never invokes AO, never
  dispatches providers, and never invokes any real tool
  dispatcher, model client, shell, or remote service.
- `125-agent-output-canary-leak-detection.md` - AO Operator + AO Runtime
  Agent output canary-leak detection is gated as a portable
  Python in-memory output verifier with five mutation cases (a
  literal canary leak admit, a base64-encoded canary leak admit,
  a unicode-homoglyph canary substitution admit, a fragment
  canary concatenation admit, and a marked-secret relabel
  passthrough admit) plus a clean-no-canary-or-marked-secret-
  leak-in-output control; each mutation must be rejected fail
  closed; runs in a tempfile work dir, uses synthetic output /
  canary / secret / field-label identifiers only, never invokes
  AO, never dispatches providers, and never invokes any real
  model client, retrieval service, or remote inference endpoint.
- `126-agent-os-execution-budget-enforcement.md` - AO Operator + AO Runtime
  Agent OS execution budget enforcement is gated as a portable
  Python in-memory execution verifier with five mutation cases
  (a token-budget overflow admit, a time-budget overflow admit,
  a tool-call-count overflow admit, a cost-ceiling overflow
  admit, and a budget-reset bypass admit) plus a clean-no-
  budget-overflow-or-reset-bypass control; each mutation must
  be rejected fail closed; runs in a tempfile work dir, uses
  synthetic execution / budget / reset-token identifiers only,
  never invokes AO, never dispatches providers, and never
  invokes any real execution scheduler, model client, or remote
  inference endpoint.
- `127-agent-system-prompt-tamper-detection.md` - AO Operator + AO Runtime
  Agent system prompt tamper detection is gated as a portable
  Python in-memory tamper-detection verifier with five mutation
  cases (a system-prompt substitution admit, a system-prompt
  appended-instruction admit, a system-prompt truncation admit,
  a system-prompt unicode-homoglyph admit, and a system-prompt
  role-relabel admit) plus a clean-no-system-prompt-tamper
  control; each mutation must be rejected fail closed; runs in a
  tempfile work dir, uses synthetic prompt / baseline-hash
  identifiers only, never invokes AO, never dispatches providers,
  and never invokes any real prompt loader, model client, or
  remote inference endpoint.
- `128-tool-result-cache-poisoning-defense.md` - AO Operator + AO Runtime
  Tool-result cache poisoning defense is gated as a portable
  Python in-memory cache-poisoning verifier with five mutation
  cases (a cache-key collision admit, a stale-cache-serve-after-
  invalidation admit, a TTL-extension-via-admin-replay admit, a
  forged-response-signature admit, and a cross-tenant cache-share
  admit) plus a clean-no-tool-result-cache-poisoning control;
  each mutation must be rejected fail closed; runs in a tempfile
  work dir, uses synthetic cache / key / invalidation-token /
  signing-key identifiers only, never invokes AO, never dispatches
  providers, and never invokes any real cache backend, response
  signer, or remote tool runner.
- `129-agent-credential-scope-narrowing.md` - AO Operator + AO Runtime
  Agent credential scope narrowing is gated as a portable Python
  in-memory credential scope-narrowing verifier with five
  mutation cases (a credential-scope-substitution admit, a
  credential-scope-append admit, a credential-audience-relabel
  admit, a credential-expiry-extension admit, and a credential-
  principal-mint admit) plus a clean-no-credential-scope-
  widening control; each mutation must be rejected fail closed;
  runs in a tempfile work dir, uses synthetic credential / scope
  / audience / expiry / principal identifiers only, never
  invokes AO, never dispatches providers, and never invokes any
  real credential broker, identity provider, or remote signing
  endpoint.

## Implementation Target

```text
${FACTORY_V3_ROOT}
```

## External Dependencies

```text
${FACTORY_V3_AO_RUNTIME_PATH}
${FACTORY_V3_AI_TEAMS_PATH}
```

AO Runtime remains the execution substrate. ai-teams remains the operating
discipline source for task shape, role routing, scoped context, and closure
evidence.

## Current Baseline

The current repository already has:

- Per-role provider configuration in `.env.example`.
- Codex-default AO smoke rendering.
- A live Codex AO smoke path.
- Seed role prompts and role TOML files.
- Validation, doctor, and RunSpec rendering scripts.

The full implementation must add:

- Task intake CLI.
- Shape-aware spec and hardened plan generation.
- Artifact handoff and downstream prompt materialization.
- AO execution orchestration.
- Event summarization.
- Durable evaluator closure.
- Provider readiness handling for both Codex and Claude.
