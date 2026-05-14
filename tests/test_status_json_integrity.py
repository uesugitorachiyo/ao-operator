from __future__ import annotations

from pathlib import Path

import check_status_json_integrity as integrity


def test_status_json_integrity_reports_invalid_json(tmp_path):
    bad = tmp_path / "run-artifacts" / "bad.json"
    bad.parent.mkdir(parents=True)
    bad.write_text('{"broken": ', encoding="utf-8")

    payload = integrity.summarize(tmp_path)

    assert payload["verdict"] == "FAIL"
    assert payload["invalid_count"] == 1
    assert payload["invalid_files"][0]["path"] == "run-artifacts/bad.json"


def test_status_json_integrity_passes_valid_status_and_evaluation_json(tmp_path):
    status = tmp_path / "run-artifacts" / "ok.json"
    evaluation = tmp_path / "docs" / "evaluations" / "ok.json"
    status.parent.mkdir(parents=True)
    evaluation.parent.mkdir(parents=True)
    status.write_text('{"ok": true}\n', encoding="utf-8")
    evaluation.write_text('{"ok": true}\n', encoding="utf-8")

    payload = integrity.summarize(tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["files_checked"] == 2
    assert payload["invalid_files"] == []
