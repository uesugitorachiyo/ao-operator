from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_kyc_demo_script_source_pack_mode(tmp_path) -> None:
    cmd = [
        sys.executable,
        "scripts/run_financial_services_kyc_demo.py",
        "--case-id",
        "synthetic-kyc-001",
        "--slug",
        "unit-kyc-demo",
        "--status-dir",
        str(tmp_path),
        "--no-factory-dry-run",
    ]

    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    report = json.loads(completed.stdout)

    assert report["schema"] == "ao-operator/financial-services-kyc-demo/v1"
    assert report["status"] == "PASS"
    assert report["profile"] == "financial-services:kyc-document-triage"
    assert report["source_manifest_schema"] == "ao-operator/kyc-synthetic-source-pack/v1"
    assert (tmp_path / "unit-kyc-demo/kyc-demo.md").is_file()
    assert (tmp_path / "unit-kyc-demo/source-pack/kyc/manifest.json").is_file()
    assert "scripts/factory_run.py" in " ".join(report["factory_command"])


def test_kyc_demo_script_is_documented_in_fixture_status() -> None:
    body = (ROOT / "run-artifacts/financial-services-kyc/kyc-demo-fixture.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/run_financial_services_kyc_demo.py" in body
    assert "Shape: greenfield" in body
