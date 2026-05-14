# Codex / Claude Code Prompt: Financial Citation Audit

Use this prompt from Codex CLI or Claude Code when you want the public AO
Operator trial to start from the financial-services profile SDD.

```text
Try AO Operator with the financial-services citation-audit SDD.

Goal:
- Clone https://github.com/uesugitorachiyo/ao-operator.git if it is not already present.
- Clone https://github.com/uesugitorachiyo/financial-services-profile.git next to it if it is not already present.
- Enter the repo.
- Read examples/ingestible-specs/financial-citation-audit-sdd.md.
- Materialize that SDD through the provider-free AO Operator ingestion path.
- Use the smoke-test profile.
- Then enter ../financial-services-profile and run:
  python3 -m financial_services_profile.cli public-proof --run-id public-sec-citation-proof
- Do not set OPENAI_API_KEY or ANTHROPIC_API_KEY.
- Stop and explain the blocker if Python 3 or git is missing.

Report back with:
- the workflow outcome requested by the SDD;
- the public wedge AO Operator is proving;
- the role graph AO Operator created;
- the generated RunSpec path;
- the status directory path;
- what a live Codex or Claude Code run would do next.
- the `public-proof.json` path;
- the `public-proof.md` path;
- the evidence-pack path;
- verify/replay verdicts from the public proof.
```

Expected report shape:

```text
requested outcome: financial citation audit workflow
public wedge: citation and compliance review with signed paper trail
profile loaded: smoke-test
role graph: intake -> test-engineer -> evaluator-closer
runspec: run-artifacts/ingest-financial-citation-audit-sdd/ingest-financial-citation-audit-sdd.runspec.yaml
status directory: run-artifacts/ingest-financial-citation-audit-sdd/
profile proof: ../financial-services-profile/runs/public-sec-citation-proof/public-proof.json
proof summary: ../financial-services-profile/runs/public-sec-citation-proof/public-proof.md
verify/replay: PASS / PASS
```

This trial is intentionally provider-free. It proves the natural-language SDD
can become a role graph, RunSpec, status directory, and evidence path before a
live Codex or Claude Code run spends subscription tokens. The profile
`public-proof` command then proves the full buyer outcome: staged SEC-data
citation-audit artifact, approval state, signed evidence pack, and
deterministic verify/replay reports.
