---
name: citation-audit
description: "Audit financial-services draft claims against source artifacts so numeric and quoted claims hash-match cited spans before publication staging."
---

# Citation Audit

Use this skill for the financial-services DAG-A `citation-audit` role.

## Workflow

1. Read the draft note and all source artifacts supplied through AO handoff.
2. Extract every numeric claim, quoted phrase, material estimate delta, and source-dependent assertion.
3. Match each claim to a cited source span.
4. Mark a claim `PASS` only when the source span supports the claim and the span hash or artifact digest is present.
5. Mark a claim `FAIL` when support is missing, ambiguous, stale, uncited, or materially different.

## Output

Return a STATUS block and include:

- `claim_table`: claim, citation, source artifact, span hash, verdict, rationale.
- `summary_verdict`: `PASS`, `NEEDS_REVIEW`, or `FAIL`.
- `blocker`: set when source artifacts or citation anchors are not inspectable.

Do not rewrite the note. Downstream compliance roles consume the findings.
