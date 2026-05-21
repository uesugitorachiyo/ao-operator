# Financial-Services MVP SEC EDGAR Demo Fixture

Date: 2026-05-12
Profile: `financial-services:earnings-note`
Fixture: `NVDA / 2026Q1`
Shape: greenfield

## Status

`DONE` for the deterministic public-data source-pack fixture.

This is not a production EDGAR fetcher. It is the first demo shim for the
financial-services profile: stdlib-only, no network call, no paid connector, and
no investment recommendation. The production path should replace the fixture
body with a live EDGAR fetch while keeping the same manifest contract.

## Artifacts

| Artifact | Purpose |
|---|---|
| `scripts/sec_edgar_public_source_pack.py` | Deterministic public SEC EDGAR source-pack shim. |
| `scripts/run_financial_services_sec_edgar_demo.py` | Repeatable demo wiring: regenerates source pack, renders the `financial-services:earnings-note` dry-run artifacts, and writes demo status JSON/Markdown. |
| `docs/status/financial-services-mvp/source-pack/sec-edgar/manifest.json` | Source-pack manifest, schema `factory-v3/sec-edgar-source-pack/v1`. |
| `docs/status/financial-services-mvp/source-pack/sec-edgar/filing-summary.md` | Public EDGAR endpoint summary for the demo issuer. |
| `docs/status/financial-services-mvp/source-pack/sec-edgar/metric-spans.json` | Citation-audit source anchors and metric tag names. |
| `profiles/financial-services/earnings-note.json` | Fetch-filings role now points at the shim and manifest schema. |
| `tests/test_sec_edgar_public_source_pack.py` | Focused tests for issuer resolution, deterministic pack output, fail-closed unsupported tickers, and profile wiring. |

## Manifest Summary

```text
schema: factory-v3/sec-edgar-source-pack/v1
ticker: NVDA
quarter: 2026Q1
cik: 0001045810
public_data_only: true
paid_connectors: []
artifacts:
  - filing-summary.md sha256=602eb7ef8d3d95967f751c586f87b8cbee2288f917244f95a486230847fd9c7e
  - metric-spans.json sha256=6f6736d79f818031479ac0342f529030c142a6e04bd9d983544c9b53d106dfff
```

## Commands

Generated fixture:

```sh
python3 scripts/sec_edgar_public_source_pack.py \
  --ticker NVDA \
  --quarter 2026Q1 \
  --output-dir docs/status/financial-services-mvp/source-pack/sec-edgar

python3 scripts/run_financial_services_sec_edgar_demo.py \
  --ticker NVDA \
  --quarter 2026Q1 \
  --slug financial-services-mvp-demo
```

Verified tests:

```sh
pytest -q tests/test_sec_edgar_public_source_pack.py
pytest -q tests/test_financial_services_sec_edgar_demo.py
pytest -q tests/test_factory_run_financial_services_profile.py tests/test_factory_profiles.py tests/test_factory_run_profile_loader.py tests/test_sec_edgar_public_source_pack.py
```

## Boundaries

- No paid connector credentials are required or referenced.
- No live network fetch happens in this fixture.
- No financial accuracy, legal compliance, or investment recommendation claim is made.
- Only `NVDA / 2026Q1` is supported until the next fixture or live-fetch path is added.

## Next Step

Use `scripts/run_financial_services_sec_edgar_demo.py` as the repeatable dry-run
wiring for the first recorded financial-services DAG-A demo. The next live lane
should consume `manifest.json`, cite `metric-spans.json`, and produce an
evidence pack that can be verified and replayed.
