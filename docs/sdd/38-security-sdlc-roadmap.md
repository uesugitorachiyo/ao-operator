# 38 - Security SDLC Roadmap

Classification: COMPLEX
Shape: greenfield

## Scope

This slice records the security controls that must stay in the AO Operator SDLC
before public release or broader remote-worker exposure. It extends the active
AST/SAST and no-provider DAST lane with explicit roadmap gates for SEI CERT
secure coding standards, threat model/data-flow analysis, manual secure code
review, and penetration testing.

## Current Controls

- AST/SAST gate: `scripts/check_public_release_security.py` scans source,
  public docs, examples, and operator artifacts for high-risk text markers and
  Python AST patterns.
- Strict-public artifact hygiene:
  `scripts/redact_strict_public_artifacts.py --fail-on-changes` prevents
  committed status/evaluation evidence from reintroducing local paths, private
  lab network targets, or stale context markers.
- Evidence integrity: `scripts/check_status_json_integrity.py` verifies
  committed status/evaluation JSON still parses after redaction and report
  generation.
- DAST gate: `scripts/check_dast_readiness.py` runs local dynamic tests for
  remote transfer and operator execution surfaces without provider dispatch.
- No-provider default: DAST readiness keeps `dispatch_authorized=false` and
  `live_providers_run=false`.
- Remote DAST escalation: live Mac-to-Ubuntu dynamic testing remains gated and
  requires explicit operator approval.
- Host-key evidence: `scripts/check_host_key_evidence.py` records the required
  `known_hosts` and fingerprint evidence before remote DAST approval.
- Manual pentest report classification: `scripts/classify_pentest_report.py`
  checks the report template before manual test evidence can be accepted.
- Supply-chain gate: `scripts/check_supply_chain_gate.py` records dependency
  manifest, lockfile, advisory, license, and pinning posture.
- AI-agent blast-radius gates are now required roadmap work before public
  release, larger live-provider escalation, or broader remote-worker exposure.
  The planned sequence is blast-radius inventory, destructive-action approval,
  credential reachability, instruction/release packaging leak detection,
  MCP/tool poisoning detection, then DeepSec diff-review as an advisory SAST
  layer.

## AI Agent Incident-Driven Roadmap Update

Recent AI-agent incidents shift the security priority from only "find vulnerable
code" to "bound what a misdirected agent can reach." AO Operator and AO Runtime
must treat credential reachability, destructive tool access, release packaging,
and MCP/tool poisoning as first-class release risks.

Start these gates after the current clean no-provider remote-transfer integrity
lane lands. Do not interrupt a passing lane mid-cascade, but do not begin
larger live-provider escalation, public release preparation, or broad
remote-worker expansion until the blast-radius, destructive-action,
credential-reachability, and packaging-leak gates are present and passing.

## Planned Security Standards

SEI CERT secure coding standards are a roadmap input for code review and
tooling. AO Operator is primarily Python and shell, while the official SEI CERT
language standards focus on C, C++, Java, Perl, and Android. For this repo, the
SDLC uses CERT-aligned controls instead of claiming full language-standard
conformance:

- avoid shell command interpretation when structured process APIs are enough
- validate archive/file-system inputs before extraction or writes
- authenticate remote endpoints before transfer or execution
- prevent credentials, private paths, lab network targets, and stale context
  markers from shipping in public artifacts
- require manual review for any exception to the automated controls

## Penetration Testing Roadmap

Penetration testing is planned, not active-by-default. It must be run as a
separate gated lane after host identity pinning.

Minimum manual pen test scope:

- remote worker transfer staging, extraction, cleanup, and artifact return
- malformed bundle and traversal attempts
- host-key mismatch and unknown-host behavior
- provider credential boundary checks
- operator approval bypass attempts
- generated artifact leak review
- denial-of-service rehearsal for large prompt/status fanout

## Verification

```bash
python3 scripts/check_security_sdlc_roadmap.py --write-output --json
python3 scripts/check_public_release_security.py --json
python3 scripts/redact_strict_public_artifacts.py --fail-on-changes --json
python3 scripts/check_status_json_integrity.py --json
python3 scripts/check_host_key_evidence.py --write-output --json
python3 scripts/classify_pentest_report.py --write-output --json
python3 scripts/check_supply_chain_gate.py --write-output --json
python3 scripts/check_dast_readiness.py --write-output --json
```

## Acceptance Criteria

- AST/SAST, no-provider DAST, SEI CERT, penetration testing, threat model, and
  data-flow analysis are represented in the SDLC roadmap.
- Operator slice `64-security-sdlc-roadmap-cert-pentest` records the roadmap
  without live provider dispatch.
- Operator slices `67`, `68`, and `69` record host-key, pentest report, and
  supply-chain gates without live provider dispatch.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- The roadmap clearly distinguishes active automated gates from planned manual
  penetration testing.
