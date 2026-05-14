from __future__ import annotations

import json
from pathlib import Path

import classify_live_outcome
from test_check_live_acceptance import write_live_artifacts


def test_classifies_pending_before_live_run(tmp_path):
    slug = "remote-transfer-v2-stress-live"
    status_dir = tmp_path / "run-artifacts" / slug
    status_dir.mkdir(parents=True)
    (status_dir / f"{slug}-status.md").write_text("Mode: dry-run\nAO Run: none\nBlockers: none\n", encoding="utf-8")

    payload = classify_live_outcome.classify(slug, root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["classification"] == "PENDING_LIVE_RUN"
    assert payload["live_success"] is False
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["diagnostics_required"] is False


def test_classifies_accepted_live_run(tmp_path):
    write_live_artifacts(tmp_path)

    payload = classify_live_outcome.classify("remote-transfer-v2-stress-live", root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["classification"] == "ACCEPTED"
    assert payload["commit_success_evidence_allowed"] is True


def test_classifies_failed_live_run_as_diagnostic_required(tmp_path):
    write_live_artifacts(tmp_path, accepted=False, run_id="r-live-failed")
    events = tmp_path / "run-artifacts" / "remote-transfer-v2-stress-live" / "remote-transfer-v2-stress-live-ao-events.md"
    events.write_text("AO command exit=1\nAO completed=false\n", encoding="utf-8")

    payload = classify_live_outcome.classify("remote-transfer-v2-stress-live", root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert payload["classification"] == "DIAGNOSTIC_REQUIRED"
    assert payload["diagnostics_required"] is True
    assert payload["commit_success_evidence_allowed"] is False


def test_main_writes_output_and_exits_zero_for_pending(tmp_path, capsys):
    output = tmp_path / "outcome.json"

    result = classify_live_outcome.main(
        ["--root", str(tmp_path), "--slug", "remote-transfer-v2-stress-live", "--write-output", str(output), "--json"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-outcome-classification/v1"
    assert written["classification"] == "PENDING_LIVE_RUN"
