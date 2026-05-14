#!/usr/bin/env python3
"""Build a deterministic public SEC EDGAR source pack for financial demos.

The first supported demo fixture is intentionally narrow: NVDA / 2026Q1.
It does not call paid connectors and it does not perform live network fetches.
Instead it records the public EDGAR endpoints, source policy, and fixture spans
needed for the financial-services profile to produce inspectable demo evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/sec-edgar-source-pack/v1"


@dataclass(frozen=True)
class Issuer:
    ticker: str
    name: str
    cik: str
    submissions_url: str
    companyfacts_url: str


SUPPORTED_ISSUERS = {
    "NVDA": Issuer(
        ticker="NVDA",
        name="NVIDIA Corporation",
        cik="0001045810",
        submissions_url="https://data.sec.gov/submissions/CIK0001045810.json",
        companyfacts_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json",
    )
}

SUPPORTED_FIXTURES: dict[tuple[str, str], dict[str, Any]] = {
    (
        "NVDA",
        "2026Q1",
    ): {
        "fiscal_period": "FY2026 Q1",
        "source_policy": "public SEC EDGAR only; paid connectors forbidden",
        "expected_forms": ["10-Q", "8-K"],
        "metric_tags": [
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:GrossProfit",
            "us-gaap:OperatingIncomeLoss",
            "us-gaap:NetIncomeLoss",
        ],
        "demo_spans": [
            {
                "id": "edgar-endpoints",
                "citation": "SEC EDGAR submissions and companyfacts endpoints",
                "text": "Use EDGAR submissions for filing metadata and companyfacts XBRL for source-tagged metrics.",
            },
            {
                "id": "paid-connector-boundary",
                "citation": "Factory financial-services demo policy",
                "text": "The demo source pack uses public SEC EDGAR endpoints only and does not require FactSet, Daloopa, PitchBook, or Aiera credentials.",
            },
        ],
    }
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, body: object) -> str:
    encoded = json.dumps(body, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(encoded)
    return _sha256_bytes(encoded)


def _write_text(path: Path, body: str) -> str:
    encoded = body.encode("utf-8")
    path.write_bytes(encoded)
    return _sha256_bytes(encoded)


def resolve_issuer(ticker: str) -> Issuer:
    """Return a supported public-demo issuer or fail closed."""
    normalized = ticker.strip().upper()
    try:
        return SUPPORTED_ISSUERS[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(SUPPORTED_ISSUERS))
        raise ValueError(
            f"unsupported demo ticker {ticker!r}; supported demo tickers: {supported}"
        ) from exc


def _fixture_for(ticker: str, quarter: str) -> dict[str, Any]:
    key = (ticker.strip().upper(), quarter.strip().upper())
    try:
        return SUPPORTED_FIXTURES[key]
    except KeyError as exc:
        raise ValueError(
            f"unsupported demo fixture {ticker!r} / {quarter!r}; "
            "only deterministic public-data fixtures are allowed"
        ) from exc


def build_source_pack(ticker: str, quarter: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Build manifest and artifact bodies for a deterministic EDGAR source pack."""
    issuer = resolve_issuer(ticker)
    normalized_quarter = quarter.strip().upper()
    fixture = _fixture_for(issuer.ticker, normalized_quarter)

    filing_summary = "\n".join(
        [
            f"# SEC EDGAR Source Summary - {issuer.ticker} {normalized_quarter}",
            "",
            f"Issuer: {issuer.name}",
            f"CIK: {issuer.cik}",
            f"Fiscal period: {fixture['fiscal_period']}",
            f"Source policy: {fixture['source_policy']}",
            "",
            "Public endpoints:",
            f"- Submissions: {issuer.submissions_url}",
            f"- Company facts: {issuer.companyfacts_url}",
            "",
            "Expected forms:",
            *[f"- {form}" for form in fixture["expected_forms"]],
            "",
            "Boundary:",
            "- This fixture records public EDGAR source anchors for demo use.",
            "- It does not certify financial accuracy and does not make investment recommendations.",
            "- Replace this fixture with a live EDGAR fetch before production customer use.",
            "",
        ]
    )
    metric_spans = {
        "schema": "ao-operator/sec-edgar-metric-spans/v1",
        "ticker": issuer.ticker,
        "quarter": normalized_quarter,
        "source_urls": [issuer.submissions_url, issuer.companyfacts_url],
        "metric_tags": fixture["metric_tags"],
        "demo_spans": fixture["demo_spans"],
    }
    artifacts = {
        "filing-summary.md": filing_summary,
        "metric-spans.json": json.dumps(metric_spans, indent=2, sort_keys=True) + "\n",
    }
    manifest = {
        "schema": SCHEMA,
        "ticker": issuer.ticker,
        "issuer": asdict(issuer),
        "quarter": normalized_quarter,
        "public_data_only": True,
        "paid_connectors": [],
        "artifacts": [],
    }
    for name, body in artifacts.items():
        manifest["artifacts"].append(
            {
                "name": name,
                "sha256": _sha256_bytes(body.encode("utf-8")),
                "bytes": len(body.encode("utf-8")),
            }
        )
    return manifest, artifacts


def write_source_pack(ticker: str, quarter: str, output_dir: Path) -> dict[str, Any]:
    """Write a source pack directory and return the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, artifacts = build_source_pack(ticker, quarter)
    for name, body in artifacts.items():
        artifact_path = output_dir / name
        if name.endswith(".json"):
            parsed = json.loads(body)
            digest = _write_json(artifact_path, parsed)
        else:
            digest = _write_text(artifact_path, body)
        expected = next(item["sha256"] for item in manifest["artifacts"] if item["name"] == name)
        if digest != expected:  # pragma: no cover - defensive invariant
            raise RuntimeError(f"digest mismatch while writing {name}")
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    manifest = write_source_pack(args.ticker, args.quarter, args.output_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
