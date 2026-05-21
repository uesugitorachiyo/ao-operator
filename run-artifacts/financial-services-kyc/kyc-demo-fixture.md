# Financial-Services KYC Demo Fixture

Date: 2026-05-12
Profile: `financial-services:kyc-document-triage`
Fixture: `synthetic-kyc-001`
Shape: greenfield

## Status

`DONE` for the deterministic synthetic KYC source-pack fixture.

This is not a production KYC connector and contains no real customer PII. It is
the first demo shim for the financial-services KYC profile: stdlib-only, no
network call, no paid connector, no account approval, and no regulatory
certification claim.

## Artifacts

| Artifact | Purpose |
|---|---|
| `scripts/kyc_synthetic_source_pack.py` | Deterministic synthetic KYC source-pack shim. |
| `scripts/run_financial_services_kyc_demo.py` | Repeatable demo wiring: regenerates source pack, renders the `financial-services:kyc-document-triage` dry-run artifacts, and writes demo status JSON/Markdown. |
| `profiles/financial-services/kyc-document-triage.json` | KYC profile DAG with PII-tagged host roles and supervisory review gate. |
| `tests/test_kyc_synthetic_source_pack.py` | Focused source-pack tests. |
| `tests/test_financial_services_kyc_demo.py` | Repeatable runner tests. |

## Commands

```sh
python3 scripts/kyc_synthetic_source_pack.py \
  --case-id synthetic-kyc-001 \
  --output-dir docs/status/financial-services-kyc/source-pack/kyc

python3 scripts/run_financial_services_kyc_demo.py \
  --case-id synthetic-kyc-001 \
  --slug financial-services-kyc-demo
```

## Boundaries

- Synthetic fixture only; no real customer PII.
- No paid connector credentials are required or referenced.
- No account approval, credit decision, or compliance certification claim is made.
- Only `synthetic-kyc-001` is supported until the next fixture or live connector path is added.
