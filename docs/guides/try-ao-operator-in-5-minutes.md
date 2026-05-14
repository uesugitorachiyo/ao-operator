# Try AO Operator In 5 Minutes

Start in Codex CLI or Claude Code. The first trial should feel like asking for
an outcome, not assembling a toolchain by hand.

Paste this prompt into Codex CLI or Claude Code from a parent directory where a
new checkout can be created:

```text
Try AO Operator with the financial-services citation-audit SDD.

Goal:
- Clone https://github.com/uesugitorachiyo/ao-operator.git if it is not already present.
- Enter the repo.
- Read examples/ingestible-specs/financial-citation-audit-sdd.md.
- Materialize the SDD through the provider-free AO Operator ingestion path.
- Use the smoke-test profile.
- Do not set OPENAI_API_KEY or ANTHROPIC_API_KEY.

Report back with:
- what workflow outcome the SDD requests;
- what public wedge AO Operator is proving;
- the generated RunSpec path;
- the status directory path;
- the role graph AO Operator used;
- what evidence a live Codex or Claude Code run would produce next.
```

Expected useful result:

```text
workflow outcome: financial citation audit workflow
public wedge: citation and compliance review with signed paper trail
role graph: intake -> test-engineer -> evaluator-closer
runspec: run-artifacts/ingest-financial-citation-audit-sdd/ingest-financial-citation-audit-sdd.runspec.yaml
status directory: run-artifacts/ingest-financial-citation-audit-sdd/
```

For the full copy-paste prompt, use
[`codex-claude-financial-services-profile-prompt.md`](./codex-claude-financial-services-profile-prompt.md).
That sample is intentionally written like a high-level regulated-workflow
request: verify material claims, match citations, flag unsupported statements,
and stage evidence without claiming investment advice or compliance
certification.

## What The Trial Proves

- A high-level SDD can become a concrete agent-team workflow.
- The workflow produces role packets, a RunSpec, and status evidence, so the
  result is not just prose.
- AO Operator turns the same SDD into role packets, a RunSpec, and status
  evidence before live provider tokens are spent.
- Live Codex or Claude Code execution can continue from the same generated
  artifacts when local provider auth is available.

## Manual Verification Path

Use this only when you want to inspect the files yourself:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/financial-citation-audit-sdd.md smoke-test
python3 scripts/factory_run.py tasks ingest-financial-citation-audit-sdd --profile smoke-test --json
```

To run the full financial-services profile fixture after this operator trial:

```bash
cd ../financial-services-profile
fsp run earnings-note --engine ao --provider-mode fixture --demo-approval
```

## Next Step After The Trial

Use [`from-sdd-to-agent-team.md`](./from-sdd-to-agent-team.md) when you want to
adapt your own SDD into an AO Operator role chain.
