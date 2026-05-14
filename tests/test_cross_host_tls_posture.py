from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cross_host_tls_posture_check_passes_json() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_cross_host_tls_posture.py", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "PASS"
    ids = {check["id"] for check in payload["checks"]}
    assert {
        "runbook.worker_runtime_guard",
        "tunnel.sh.reverse_forward_loopback",
        "tunnel.ps1.reverse_forward_loopback",
        "windows.generator.runtime_bind_loopback",
        "windows.artifact.runtime_bind_loopback",
        "windows.status.mdm_outbound_topology",
        "tls.posture.baseline",
        "live.validation.references_tls_posture",
    }.issubset(ids)


def test_cross_host_tls_posture_check_has_no_failed_checks() -> None:
    from scripts.check_cross_host_tls_posture import run_checks

    payload = run_checks()
    failed = [check for check in payload["checks"] if check["status"] != "PASS"]

    assert payload["verdict"] == "PASS"
    assert failed == []
