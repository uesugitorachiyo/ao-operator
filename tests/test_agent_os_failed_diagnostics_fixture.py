from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_failed_diagnostics_fixture


def test_failed_diagnostics_fixture_preserves_sanitized_no_provider_summary(tmp_path):
    payload = check_agent_os_failed_diagnostics_fixture.build_fixture(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-failed-diagnostics-fixture/v1"
    assert payload["verdict"] == "PASS"
    assert payload["fixture_only"] is True
    assert payload["preservation_verdict"] == "PASS"
    assert payload["route"] == "DIAGNOSTIC_REQUIRED"
    assert payload["primary_normalized_reason"] == "provider-rate-limit"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["raw_snapshot_commit_allowed"] is False

    summary = json.loads((tmp_path / payload["summary"]).read_text(encoding="utf-8"))
    assert summary["primary_normalized_reason"] == "provider-rate-limit"
    assert "/tmp/[REDACTED_AO_HOME]" in json.dumps(summary)
    assert str(tmp_path) not in json.dumps(summary)


def test_failed_diagnostics_fixture_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-failed-diagnostics-fixture.json"

    code = check_agent_os_failed_diagnostics_fixture.main([
        "--root",
        str(tmp_path),
        "--write-output",
        str(output),
        "--json",
    ])

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["verdict"] == "PASS"
    assert saved["fixture_only"] is True
