# SDD 131 — Evidence Pack v1

**Status:** Draft — Week 1 P0 deliverable, 2026-05-11
**Owner:** AO Operator (AO = AI Orchestration Operation)
**Wire-format namespace:** `ao-operator/evidence-pack/v1` (frozen once v0.7
ships)

## Goal

Define the on-disk and on-wire format for an *evidence pack*: the
artifact produced at the end of every Factory run that lets a third
party — auditor, compliance officer, regulator, downstream consumer —
verify what the run did, what artifacts it produced, and whether the
artifacts have been tampered with since.

An evidence pack is the unit of audit. It is the marketing claim
("auditable, replayable, signed") expressed as a file format.

## Non-Goals

- **Not a regulatory certification.** See
  `docs/compliance/what-we-are-not.md`.
- **Not a hosted store.** Evidence packs are files on the operator's
  disk by default; upload destinations are an integration concern.
- **Not a model output.** Provider model weights are out of scope; the
  pack records the provider name and version that produced each
  transcript.
- **Not bit-for-bit deterministic for LLM steps.** Determinism applies
  to non-LLM artifact replay only (see §7).

## Container Format

```text
evidence-pack-<run_id>.tar.zst
```

- `<run_id>` is the AO run id (lowercase hex, 16 bytes).
- `.tar` because every tool reads tar. `.zst` because zstd is the
  default modern compressor and faster than gzip with better ratios.
- One pack per run. No multi-run bundles in v1.

### Tar Layout (canonical order)

```text
evidence-pack-<run_id>/
  manifest.json                      # see §3
  events.ndjson                      # see §4
  transcripts/                       # see §5
    <task_id>.ndjson
    ...
  artifacts/                         # see §6
    <sha256>/<original_filename>
    ...
  signatures/
    pack.sig                         # HMAC/Ed25519 over manifest+merkle (§8)
    pubkey                           # HMAC key digest or Ed25519 public key
```

Order matters: `manifest.json` must be the first entry in the tarball.
This lets a reader inspect metadata without streaming the whole pack.

## §3 — `manifest.json`

```json
{
  "evidence_pack_version": "ao-operator/evidence-pack/v1",
  "run_id": "0123456789abcdef",
  "factory_version": "v0.7.0",
  "ao_runtime_version": "v0.2.0",
  "created_at": "2026-05-11T18:00:00+00:00",
  "completed_at": "2026-05-11T18:14:32+00:00",
  "operator": {
    "host_fingerprint": "sha256:abc...",
    "user_label": "operator-host-mac"
  },
  "profile": {
    "name": "financial-services:earnings-note",
    "version": "v1",
    "policy_digest": "sha256:def..."
  },
  "providers": [
    {"role": "implementer", "name": "codex", "version": "0.42.1"},
    {"role": "reviewer",    "name": "claude", "version": "0.9.3"}
  ],
  "tasks": [
    {
      "task_id": "intake",
      "role": "planner-intake",
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "transcript_path": "transcripts/intake.ndjson",
      "artifact_shas": ["sha256:...", "..."],
      "deterministic": true,
      "replay_command": ["python3", "scripts/replay_intake.py"],
      "replay_outputs": ["report.md"]
    }
  ],
  "merkle_root": "sha256:...",
  "schema_version": 1
}
```

- `evidence_pack_version` is the only field downstream consumers should
  branch on. Schema migrations bump it.
- `merkle_root` is the root of the Merkle tree over (events.ndjson,
  every transcript, every artifact, ordered lexicographically). The
  Ed25519 signature in §8 covers the manifest, which covers the root.
- All timestamps are ISO 8601 with timezone (UTC).
- `deterministic`, `replay_command`, and `replay_outputs` are optional additive
  task fields. They are present only for non-LLM tasks whose outputs can be
  replay-checked without calling Codex, Claude, AO, or external tools.

## §4 — `events.ndjson`

One AO event per line, in the order AO emitted them. Each line is a
JSON object with at minimum:

```json
{
  "ts": "2026-05-11T18:00:14.123+00:00",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "type": "task.started",
  "task_id": "intake",
  "attrs": { "...": "..." }
}
```

- Trace context is the W3C standard (16-byte trace id, 8-byte span id),
  produced by AO Runtime and unchanged on the way into the pack.
- Lines are sorted by `ts` ascending. Ties broken by span id.
- Every event referenced by `manifest.tasks[*]` MUST appear in
  `events.ndjson`. Verification fails if a task references a missing
  event.

## §5 — Transcripts

One file per task that invoked a provider. Format is NDJSON with one
provider turn per line:

```json
{"role": "user", "content": "...", "ts": "..."}
{"role": "assistant", "content": "...", "ts": "...", "tool_calls": [...]}
{"role": "tool", "name": "...", "content": "...", "ts": "..."}
```

- Role names ("user"/"assistant"/"tool") are normalized; vendor-
  specific naming (Codex/Claude) is converted on emit, never on read.
- Tool call payloads are included verbatim. Redaction is the operator's
  responsibility before the pack is shared externally.
- Per-task transcript files are independently signed in the Merkle tree
  so partial sharing is possible (share the manifest + the one
  transcript + its branch of the Merkle proof).

## §6 — Artifacts

Content-addressed storage. Filenames in the tar are
`artifacts/<sha256>/<original_filename>`. The directory acts as a
content namespace; the original filename is informational.

- `<sha256>` is the lowercase hex digest of the file contents.
- `manifest.tasks[*].artifact_shas` references these digests directly.
- Two tasks producing the same artifact share a single entry. The
  Merkle tree dedups by sha.

## §7 — Replay Determinism Contract

`factory replay <pack>` (new CLI subcommand, v0.7) re-executes the
**non-LLM steps** of the run and asserts that artifact digests match
the manifest. LLM-generated artifacts are not re-generated; they are
verified against their stored sha and transcript.

Current v1 replay emits `ao-operator/evidence-pack-replay/v1` and performs the
checks possible from the frozen v1 manifest. Replay assertions, in order:

1. Manifest signature verifies under `signatures/pubkey`.
2. Merkle root matches recomputation.
3. Every artifact in `artifacts/` matches its directory sha.
4. Every manifest task has at least one event in `events.ndjson`.
5. Every manifest `transcript_path` exists in the pack. Transcript bytes are
   covered by the Merkle root; no provider is called.
6. Every manifest `artifact_shas` reference resolves to a content-addressed
   artifact directory.
7. If a manifest task declares `deterministic: true`, replay validates that
   `replay_command` and `replay_outputs` are present and that every declared
   output resolves to one of the task's content-addressed artifacts. Provider
   transcripts remain verified-only; no LLM/provider is called.
8. If the operator adds `--execute-deterministic`, replay runs deterministic
   commands in a temporary working directory with no shell, a minimal
   environment, a timeout, denied common network clients, and output hash
   comparison against the task's content-addressed artifacts. This is opt-in so
   pack reads remain passive by default.
9. If no deterministic task declarations are present, deterministic non-LLM
   replay is reported as `SKIPPED` for backward-compatible v1 packs.

Replay determinism is the marketing claim in strategy v2 §1; this
section is the technical definition we will defend against challenge.

## §8 — Signatures

- Dev/local packs MAY use `HMAC-SHA256` with an operator-provided 32-byte
  secret. HMAC public material is stored as `sha256(secret)` in
  `signatures/pubkey` so verifiers can detect wrong-key use without storing the
  secret.
- Production packs SHOULD use one Ed25519 keypair per operator. The public key
  is shipped in `signatures/pubkey` as PEM-encoded SubjectPublicKeyInfo.
- Detached signature in `signatures/pack.sig` over the SHA-256 digest
  of `manifest.json` concatenated with the manifest's `merkle_root`
  bytes.
- Key rotation is allowed; the public key is recorded in the manifest
  via `operator.host_fingerprint = sha256(pubkey || host_label)`. A
  rotated key produces a different host_fingerprint; consumers
  needing identity continuity should compare host_label, not
  fingerprint.

## §9 — Threat Model

Threats this format defends against:

- **Artifact tampering after run.** Caught by Merkle root check.
- **Manifest tampering.** Caught by Ed25519 verification.
- **Selective omission.** Caught by event/task reference cross-check
  (events.ndjson MUST cover every task in the manifest).
- **Transcript edits.** Each transcript is a Merkle leaf; edits change
  the leaf hash and break the root.

Threats this format does NOT defend against:

- **LLM hallucination inside a transcript.** That is a profile
  evaluation concern, not an evidence concern.
- **Operator key compromise.** Out of scope; documented as a
  customer-owned risk in `docs/compliance/what-we-are-not.md`.
- **Side-channel leakage of secrets into a transcript.** Redaction
  responsibility lies upstream (provider adapters + role prompts).

## §10 — Implementation Plan

This SDD is the schema. The v1 implementation is now represented by:

1. **Writer** — `scripts/evidence_pack_writer.py`. Consumes AO events,
   role artifacts, transcripts, and task metadata already on disk. Emits
   `evidence-pack-<run_id>/` and, when `zstd` is available,
   `evidence-pack-<run_id>.tar.zst`.
2. **Verifier** — `scripts/evidence_pack_verify.py`. Reads a directory,
   `.tar`, or `.tar.zst` pack; verifies signatures, Merkle root, and
   artifact CAS integrity; returns non-zero on any failure.
3. **Replay CLI** — `python3 scripts/factory_run.py replay <pack>`.
   Emits `ao-operator/evidence-pack-replay/v1`, wraps the verifier, checks
   task/event coverage, transcript paths, and manifest artifact references,
   validates deterministic non-LLM task declarations when present, can execute
   them with `--execute-deterministic`, and can persist the report with
   `--write-report <path>`.
4. **Live-run hook** — `scripts/factory_run.py --run
   --evidence-hmac-key-hex <64-hex>` or
   `--evidence-ed25519-private-key <pem>` writes and verifies a pack under
   `run-artifacts/<slug>/evidence-packs/`, then records both `verify` and
   `replay` reports in `evidence-pack-<run_id>-summary.json`.
   `--evidence-execute-deterministic` additionally executes deterministic
   non-LLM replay commands before writing the live summary. Environment variable
   aliases are `FACTORY_V3_EVIDENCE_HMAC_KEY_HEX` and
   `FACTORY_V3_EVIDENCE_ED25519_PRIVATE_KEY`.
5. **Readiness gate** — `scripts/check_evidence_pack_readiness.py --json`
   writes a synthetic no-provider pack, creates the `.tar.zst`, verifies it,
   executes and replay-checks one deterministic task declaration, and is called by
   `scripts/pr_ready.py`.
6. **Live-summary gate** — `scripts/check_live_evidence_pack_replay.py --json`
   scans checked-in live evidence summaries, can persist
   `run-artifacts/remote-transfer-v2-stress-live/live-evidence-pack-replay-gate.json`
   with `--write-output`, and fails when any
   `ao-operator/evidence-pack-live-run/v1` summary lacks
   `replay.verdict == "PASS"`. Summaries with deterministic tasks must also
   report `replay.checks.deterministic_command_execution == "PASS"`.

Tests live in `tests/test_evidence_pack_writer.py`,
`tests/test_evidence_pack_verify.py`, `tests/test_factory_run_replay.py`,
`tests/test_factory_run_evidence_pack.py`,
`tests/test_check_evidence_pack_readiness.py`,
`tests/test_check_live_evidence_pack_replay.py`, and `tests/test_pr_ready.py`.
The fact-forcing gate applies; every caller and field above is documented here
so follow-up implementation PRs do not need to re-derive them.

## §11 — Compatibility & Versioning

- Wire format `ao-operator/evidence-pack/v1` is frozen at v0.7 release.
- Any breaking change (added required field, semantic change to existing
  field) bumps the namespace (`/v2`). v1 readers MUST refuse v2 packs
  rather than guess. v1 writers MUST NOT emit v2 fields.
- Additive non-breaking changes (new optional field, new event type
  emitted only when relevant) are allowed within v1.

## §12 — Cross-References

- Strategy v2 §1, §3, §9, §11 (in `ao-strategy/`).
- Financial-services profile SDD §5 (in `ao-strategy/`).
- `docs/compliance/what-we-are-not.md`.
- `docs/sdd/26-agent-os-runspec-execution-approval-gate.md`.
- `docs/sdd/30-agent-os-execution-approval-contract.md`.
- `docs/sdd/112-ai-agent-blast-radius-inventory.md`.
- `docs/sdd/116-` — MCP tool poisoning detection (poisoning evidence
  belongs in the pack).
