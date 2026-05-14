# Security Policy

## Supported Security Posture

AO Operator (formal name: AO Runtime Operator; GitHub repo slug `ao-operator`;
legacy compatibility slug `ao-operator`) is currently safe for
controlled local and Mac-to-Ubuntu lab operation. The public source/docs surface and committed historical evidence are
covered by redaction and strict-public security gates before release.

## Required Gates

Before public release or wider remote-worker exposure, run:

```bash
python3 scripts/check_public_release_security.py --json
python3 scripts/redact_strict_public_artifacts.py --fail-on-changes --json
python3 scripts/check_status_json_integrity.py --json
python3 scripts/check_public_release_security.py --strict-public --summary-only --json
python3 scripts/check_dast_readiness.py --write-output --json
python3 scripts/check_security_sdlc_roadmap.py --write-output --json
python3 scripts/check_security_threat_model.py --write-output --json
python3 scripts/check_pentest_gate.py --write-output --json
python3 scripts/check_host_key_evidence.py --write-output --json
python3 scripts/classify_pentest_report.py --write-output --json
python3 scripts/check_supply_chain_gate.py --write-output --json
python3 scripts/pr_ready.py --json
```

The public-release gate uses text scanning and Python AST checks. Historical
status/evaluation artifacts are first checked for redactable local paths,
private network targets, and stale context markers, then parsed to ensure JSON
evidence remains intact. The DAST gate runs no-provider dynamic tests by
default. Remote DAST requires
`FACTORY_V3_DAST_REMOTE=1` and should be treated as a separate operator-approved
network action.

## AI Agent Blast-Radius Roadmap

Recent AI-agent incidents show that the highest-risk failure mode is often not
only vulnerable code. It is a misdirected agent that can read private data,
consume untrusted instructions, and call destructive or outbound tools in the
same task.

Before public release, larger live-provider escalation, or broader
remote-worker exposure, AO Runtime Operator must add roadmap gates for agent
blast-radius inventory, destructive-action approval, credential reachability,
instruction and release-packaging leak detection, MCP/tool poisoning detection,
and DeepSec diff-review as an advisory SAST layer.

## Secure Coding And Penetration Testing Roadmap

AO Operator uses CERT-aligned secure coding controls in the SDLC. It does not
claim formal SEI CERT conformance because the official SEI CERT language
standards focus on C, C++, Java, Perl, and Android rather than this repo's
Python/shell surface. The current automated controls cover command execution,
archive extraction, host identity, credential leakage, personal paths, private
network targets, and stale context markers.

Manual penetration testing is planned as a separate gated lane after host-key
pinning evidence and a classified report template. It must not run from default
readiness checks.

The threat model/data-flow lane and manual pen-test gate are documented in:

- `docs/sdd/39-security-threat-model-data-flow.md`
- `docs/sdd/40-manual-penetration-test-gate.md`
- `docs/sdd/41-host-key-evidence-gate.md`
- `docs/sdd/42-manual-pentest-report-classifier.md`
- `docs/sdd/43-supply-chain-audit-gate.md`

## Provider Credentials

Provider authentication must stay local OAuth CLI only. `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, provider auth files, provider session directories, and
raw provider transcripts must not be transferred, committed, or included in
role handoffs.

## Remote Transfer Threat Model

The high-risk surfaces are workspace bundles, manifests, role artifacts,
operator reports, AO event logs, SSH transport, and provider CLI execution.
The current controls include explicit approval gates, no-provider default DAST,
safe tar extraction for the Mac-to-Ubuntu smoke, pinned SSH host-key mode, and
operator output redaction.

## Substrate Posture, Not Certification

AO Operator is a substrate that produces evidence; it is not a compliance
certification. The boundaries of what the product is *not* — including SOC 2,
FINRA Rule 3110, HIPAA BAA, autonomous decisioning, and hosted operations —
are documented in `docs/compliance/what-we-are-not.md`. Marketing and
sales materials must derive boundary language from that single source.

## Supply Chain Evidence

- Python SBOM and regeneration policy: `docs/sbom/README.md`.
- Most recent gitleaks history scan: `docs/compliance/secrets-sweep-2026-05-11.md`
  (0 leaks across 799 commits, 273 MB scanned).

## Disclosure

Report security issues privately to the repository owner. Do not include live
provider tokens, OAuth files, raw auth paths, or full private machine logs in
the report.
