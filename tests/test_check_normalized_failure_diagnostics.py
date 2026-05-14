from __future__ import annotations

import json

import check_normalized_failure_diagnostics


def test_normalized_failure_diagnostics_checker_passes_provider_free_fixture(tmp_path):
    payload = check_normalized_failure_diagnostics.check(root=tmp_path)

    assert payload["schema"] == "ao-operator/normalized-failure-diagnostics/v1"
    assert payload["verdict"] == "PASS"
    assert payload["primary_normalized_reason"] == "provider-rate-limit"
    assert payload["normalized_reason_counts"] == {
        "provider-auth-missing": 1,
        "provider-rate-limit": 1,
    }
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert str(tmp_path) not in json.dumps(payload)


def test_normalized_failure_diagnostics_checker_writes_report(tmp_path, capsys):
    report = tmp_path / "report.json"

    code = check_normalized_failure_diagnostics.main(
        ["--root", str(tmp_path), "--write-output", str(report), "--json"]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == "report.json"
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["verdict"] == "PASS"
