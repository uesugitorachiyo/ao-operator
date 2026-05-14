"""Tests for the synthetic KYC public-demo source pack."""

from __future__ import annotations

import json

import kyc_synthetic_source_pack as kyc_pack


def test_builds_deterministic_synthetic_kyc_source_pack(tmp_path):
    output_dir = tmp_path / "source-pack"

    pack = kyc_pack.write_source_pack("synthetic-kyc-001", output_dir)

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == pack
    assert manifest["schema"] == "ao-operator/kyc-synthetic-source-pack/v1"
    assert manifest["case_id"] == "synthetic-kyc-001"
    assert manifest["synthetic_data_only"] is True
    assert manifest["real_customer_pii"] is False
    assert [artifact["name"] for artifact in manifest["artifacts"]] == [
        "customer-documents.md",
        "rules-grid.json",
        "redaction-map-placeholder.json",
    ]
    assert all(len(artifact["sha256"]) == 64 for artifact in manifest["artifacts"])


def test_rejects_unknown_kyc_case_without_live_fallback(tmp_path):
    try:
        kyc_pack.write_source_pack("real-client-123", tmp_path)
    except ValueError as exc:
        assert "unsupported synthetic KYC case" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("unknown KYC cases must fail closed")
