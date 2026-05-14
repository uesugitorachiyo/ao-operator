"""Tests for the public SEC EDGAR financial-services demo shim."""

from __future__ import annotations

import json

import sec_edgar_public_source_pack as sec_edgar


def test_resolves_supported_demo_ticker_to_cik_and_edgar_urls():
    issuer = sec_edgar.resolve_issuer("nvda")

    assert issuer.ticker == "NVDA"
    assert issuer.cik == "0001045810"
    assert issuer.submissions_url.endswith("CIK0001045810.json")
    assert issuer.companyfacts_url.endswith("CIK0001045810.json")


def test_builds_deterministic_nvda_2026q1_source_pack(tmp_path):
    output_dir = tmp_path / "source-pack"

    pack = sec_edgar.write_source_pack("NVDA", "2026Q1", output_dir)

    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest == pack
    assert manifest["schema"] == "ao-operator/sec-edgar-source-pack/v1"
    assert manifest["ticker"] == "NVDA"
    assert manifest["quarter"] == "2026Q1"
    assert manifest["public_data_only"] is True
    assert manifest["paid_connectors"] == []
    assert [artifact["name"] for artifact in manifest["artifacts"]] == [
        "filing-summary.md",
        "metric-spans.json",
    ]
    assert all(len(artifact["sha256"]) == 64 for artifact in manifest["artifacts"])


def test_rejects_unsupported_ticker_without_live_network_fallback(tmp_path):
    try:
        sec_edgar.write_source_pack("MSFT", "2026Q1", tmp_path)
    except ValueError as exc:
        assert "unsupported demo ticker" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("unsupported ticker should fail closed")


def test_financial_services_profile_points_fetch_filings_at_sec_edgar_shim():
    import factory_run

    profile = factory_run._load_profile("financial-services:earnings-note")
    fetch_filings = profile["roles_by_id"]["fetch-filings"]

    joined = "\n".join(fetch_filings["instructions"])
    assert "scripts/sec_edgar_public_source_pack.py" in joined
    assert "ao-operator/sec-edgar-source-pack/v1" in joined
