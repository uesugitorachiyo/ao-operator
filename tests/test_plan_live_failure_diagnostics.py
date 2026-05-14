from __future__ import annotations

import json
from pathlib import Path

import plan_live_failure_diagnostics


def write_classification(path: Path, classification: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "ao-operator/live-outcome-classification/v1",
                "verdict": "PASS" if classification != "DIAGNOSTIC_REQUIRED" else "FAIL",
                "classification": classification,
                "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
                "commit_success_evidence_allowed": classification == "ACCEPTED",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_plan_pending_live_run_does_not_allow_copy(tmp_path):
    classification = write_classification(tmp_path / "classification.json", "PENDING_LIVE_RUN")

    payload = plan_live_failure_diagnostics.plan(
        root=tmp_path,
        slug="live",
        ao_home="/tmp/ao-live",
        classification_path=classification,
    )

    assert payload["verdict"] == "PASS"
    assert payload["classification"] == "PENDING_LIVE_RUN"
    assert payload["diagnostics_required"] is False
    assert payload["copy_allowed"] is False
    assert payload["raw_snapshot_commit_allowed"] is False
    assert payload["commands"] == []


def test_plan_diagnostic_required_includes_bounded_commands(tmp_path):
    classification = write_classification(tmp_path / "classification.json", "DIAGNOSTIC_REQUIRED")

    payload = plan_live_failure_diagnostics.plan(
        root=tmp_path,
        slug="live",
        ao_home="/tmp/ao-live",
        classification_path=classification,
    )

    assert payload["verdict"] == "PASS"
    assert payload["diagnostics_required"] is True
    assert payload["copy_allowed"] is True
    assert payload["raw_snapshot_commit_allowed"] is False
    assert payload["live_providers_run"] is False
    assert payload["commands"][0] == "mkdir -p run-artifacts/live/failure-snapshots"
    assert payload["commands"][1].startswith("cp -a /tmp/ao-live run-artifacts/live/failure-snapshots/ao-home-")
    assert payload["commands"][2] == "python3 scripts/summarize_ao_failure.py /tmp/ao-live --json"


def test_plan_accepted_live_run_does_not_allow_failure_snapshot(tmp_path):
    classification = write_classification(tmp_path / "classification.json", "ACCEPTED")

    payload = plan_live_failure_diagnostics.plan(
        root=tmp_path,
        slug="live",
        ao_home="/tmp/ao-live",
        classification_path=classification,
    )

    assert payload["verdict"] == "PASS"
    assert payload["diagnostics_required"] is False
    assert payload["copy_allowed"] is False
    assert payload["success_evidence_commit_allowed"] is True
    assert payload["commands"] == []


def test_plan_fails_for_missing_classification(tmp_path):
    payload = plan_live_failure_diagnostics.plan(
        root=tmp_path,
        slug="live",
        ao_home="/tmp/ao-live",
        classification_path=tmp_path / "missing.json",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["copy_allowed"] is False
    assert payload["raw_snapshot_commit_allowed"] is False
    assert any("classification unavailable" in error for error in payload["errors"])


def test_plan_fails_for_unknown_classification(tmp_path):
    classification = write_classification(tmp_path / "classification.json", "UNKNOWN")

    payload = plan_live_failure_diagnostics.plan(
        root=tmp_path,
        slug="live",
        ao_home="/tmp/ao-live",
        classification_path=classification,
    )

    assert payload["verdict"] == "FAIL"
    assert any("classification must be one of" in error for error in payload["errors"])


def test_main_writes_plan(tmp_path, capsys):
    classification = write_classification(tmp_path / "classification.json", "PENDING_LIVE_RUN")
    plan_path = tmp_path / "plan.json"

    result = plan_live_failure_diagnostics.main(
        [
            "--root",
            str(tmp_path),
            "--slug",
            "live",
            "--ao-home",
            "/tmp/ao-live",
            "--classification",
            str(classification),
            "--write-plan",
            str(plan_path),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"] == str(plan_path)
    written = json.loads(plan_path.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-failure-diagnostics-plan/v1"
    assert written["classification"] == "PENDING_LIVE_RUN"
