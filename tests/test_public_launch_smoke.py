from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_launch_smoke_runs_in_clean_temp_copy_without_report_write() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/public_launch_smoke.py",
            "--json",
            "--no-write-report",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "ao-operator/public-launch-smoke/v1"
    assert payload["status"] == "PASS"
    assert payload["provider_dispatch"] is False
    assert payload["forbidden_provider_api_keys_present"] == []
    assert payload["scaffold"]["returncode"] == 0
    assert {demo["id"] for demo in payload["demos"]} == {
        "first-run-agent-team",
        "ingest-financial-citation-audit-sdd",
        "ingest-service-booking-sdd",
        "ingest-bug-fix-sdd",
        "ingest-three-os-setup-sdd",
    }
    for demo in payload["demos"]:
        assert demo["status"] == "PASS"
        assert demo["specify"]["returncode"] == 0
        assert demo["tasks"]["returncode"] == 0
        assert all(item["present"] for item in demo["artifacts"])


def test_readme_exposes_public_launch_smoke_command() -> None:
    body = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "python3 scripts/public_launch_smoke.py" in body
    assert "provider-free public-launch smoke" in body
