from __future__ import annotations

import shutil

import pytest

import check_evidence_pack_readiness


def _requires_zstd() -> None:
    if shutil.which("zstd") is None:
        pytest.skip("zstd CLI is not available")


def test_check_evidence_pack_readiness_passes_with_synthetic_pack(tmp_path):
    _requires_zstd()
    report = check_evidence_pack_readiness.check_readiness(tmp_path)

    assert report["schema"] == "ao-operator/evidence-pack-readiness/v1"
    assert report["verdict"] == "PASS"
    assert report["verify"]["verdict"] == "PASS"
    assert report["replay"]["schema"] == "ao-operator/evidence-pack-replay/v1"
    assert report["replay"]["verdict"] == "PASS"
    assert report["replay"]["checks"]["deterministic_non_llm_replay"] == "PASS"
    assert report["replay"]["deterministic_task_count"] == 1


def test_cli_json_returns_pass(capsys, tmp_path):
    _requires_zstd()
    rc = check_evidence_pack_readiness.main(["--work-dir", str(tmp_path), "--json"])

    assert rc == 0
    assert '"verdict": "PASS"' in capsys.readouterr().out
