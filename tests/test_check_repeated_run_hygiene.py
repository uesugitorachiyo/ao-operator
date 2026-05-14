from __future__ import annotations

import json

import check_repeated_run_hygiene


def test_check_repeated_run_hygiene_passes_all_scenarios(tmp_path):
    payload = check_repeated_run_hygiene.check(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["repo"] == "${FACTORY_V3_ROOT}"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert str(tmp_path) not in json.dumps(payload)
    assert {item["id"]: item["verdict"] for item in payload["scenarios"]} == {
        "same-slug-dry-run-after-live": "PASS",
        "live-after-failed-live": "PASS",
        "reroute-after-accepted-live": "PASS",
    }


def test_main_writes_json_report(tmp_path, capsys):
    report = tmp_path / "report.json"

    result = check_repeated_run_hygiene.main(["--root", str(tmp_path), "--write-output", str(report), "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == "report.json"
    assert str(tmp_path) not in json.dumps(payload)
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/repeated-run-hygiene/v1"
    assert written["verdict"] == "PASS"
