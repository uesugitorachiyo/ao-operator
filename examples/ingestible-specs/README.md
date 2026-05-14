# Ingestible Specs

These are copy-pasteable specs and SDD-style briefs for trying AO Operator.

They are intentionally small. The point is to show how a structured document
becomes a local agent-team workflow:

```text
spec -> profile -> role graph -> RunSpec -> status artifacts
```

## Run One

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/bug-fix-sdd.md bug-fix
```

Try the others by changing the path and profile:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/financial-citation-audit-sdd.md smoke-test
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/greenfield-feature-sdd.md greenfield
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/secure-agent-change-sdd.md bug-fix
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/service-booking-recovery-sdd.md greenfield
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/three-os-setup-sdd.md smoke-test
```

## Files

- `financial-citation-audit-sdd.md`: a read-only citation-audit workflow.
- `bug-fix-sdd.md`: a narrow CLI validation bug.
- `greenfield-feature-sdd.md`: a small feature with acceptance criteria.
- `secure-agent-change-sdd.md`: a bounded secure-coding task.
- `service-booking-recovery-sdd.md`: a high-level app sample with business
  outcome, seed data, review, and cross-platform verification expectations.
- `three-os-setup-sdd.md`: a one-step native Ubuntu, macOS, and Windows setup brief.
