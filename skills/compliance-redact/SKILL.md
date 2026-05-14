---
name: compliance-redact
description: "Scrub financial-services draft notes for Reg FD, MNPI, PII, and unsupported compliance-language risks before supervisory review."
---

# Compliance Redact

Use this skill for the financial-services DAG-A `compliance-redact` role.

## Workflow

1. Read the draft note and citation-audit artifact.
2. Stop with `BLOCKED` when citation-audit has unresolved `FAIL` findings.
3. Flag and redact private client identifiers, account data, credentials, MNPI indicators, selective-disclosure language, and unsupported compliance claims.
4. Preserve citation anchors when redacting text.
5. Emit a finding table with severity, location, action, and residual risk.

## Boundaries

- This skill does not certify legal or regulatory compliance.
- This skill does not make investment, trading, onboarding, or supervisory decisions.
- A human supervisory approval gate remains required after this role.
