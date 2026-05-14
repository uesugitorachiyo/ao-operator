from __future__ import annotations

import json
from pathlib import Path

import route_live_postrun
from test_check_live_acceptance import write_live_artifacts


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_bundle(
    tmp_path: Path,
    *,
    classification: str,
    summary_written: bool = False,
    acceptance: bool = False,
) -> tuple[Path, Path, Path]:
    if acceptance:
        write_live_artifacts(tmp_path)
    classification_path = write_json(
        tmp_path / "classification.json",
        {
            "schema": "ao-operator/live-outcome-classification/v1",
            "classification": classification,
            "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
            "commit_success_evidence_allowed": classification == "ACCEPTED",
        },
    )
    plan_path = write_json(
        tmp_path / "plan.json",
        {
            "schema": "ao-operator/live-failure-diagnostics-plan/v1",
            "slug": "remote-transfer-v2-stress-live",
            "classification": classification,
            "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
            "copy_allowed": classification == "DIAGNOSTIC_REQUIRED",
            "raw_snapshot_commit_allowed": False,
            "live_providers_run": False,
        },
    )
    preservation_path = write_json(
        tmp_path / "preservation.json",
        {
            "schema": "ao-operator/live-failure-diagnostics-preservation/v1",
            "slug": "remote-transfer-v2-stress-live",
            "classification": classification,
            "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
            "summary_written": summary_written,
            "raw_snapshot_copied": False,
            "raw_snapshot_commit_allowed": False,
            "live_providers_run": False,
        },
    )
    return classification_path, plan_path, preservation_path


def run_route(tmp_path: Path, classification: str, *, summary_written: bool = False, acceptance: bool = False):
    classification_path, plan_path, preservation_path = write_bundle(
        tmp_path,
        classification=classification,
        summary_written=summary_written,
        acceptance=acceptance,
    )
    return route_live_postrun.route(
        root=tmp_path,
        classification_path=classification_path,
        plan_path=plan_path,
        preservation_path=preservation_path,
    )


def test_routes_pending_to_live_slice(tmp_path):
    payload = run_route(tmp_path, "PENDING_LIVE_RUN")

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "WAIT_FOR_LIVE_RUN"
    assert payload["next_slice"] == "17-run-bounded-live-10"
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["live_providers_run"] is False


def test_routes_diagnostic_required_to_preservation_slice(tmp_path):
    payload = run_route(tmp_path, "DIAGNOSTIC_REQUIRED")

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "PRESERVE_DIAGNOSTICS"
    assert payload["next_slice"] == "20-preserve-live-failure-diagnostics"
    assert payload["diagnostics_required"] is True


def test_routes_preserved_diagnostics_to_review(tmp_path):
    payload = run_route(tmp_path, "DIAGNOSTIC_REQUIRED", summary_written=True)

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "DIAGNOSTICS_PRESERVED"
    assert payload["next_slice"] is None
    assert payload["summary_written"] is True


def test_routes_accepted_to_acceptance_slice(tmp_path):
    payload = run_route(tmp_path, "ACCEPTED", acceptance=True)

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "RUN_ACCEPTANCE"
    assert payload["next_slice"] == "24-check-live-acceptance"
    assert payload["commit_success_evidence_allowed"] is True


def test_routes_accepted_with_stale_diagnostic_artifacts(tmp_path):
    classification_path, plan_path, preservation_path = write_bundle(
        tmp_path,
        classification="ACCEPTED",
        acceptance=True,
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["classification"] = "DIAGNOSTIC_REQUIRED"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    preservation = json.loads(preservation_path.read_text(encoding="utf-8"))
    preservation["classification"] = "DIAGNOSTIC_REQUIRED"
    preservation_path.write_text(json.dumps(preservation), encoding="utf-8")

    payload = route_live_postrun.route(
        root=tmp_path,
        classification_path=classification_path,
        plan_path=plan_path,
        preservation_path=preservation_path,
    )

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "RUN_ACCEPTANCE"


def test_fails_when_accepted_classification_lacks_acceptance(tmp_path):
    payload = run_route(tmp_path, "ACCEPTED")

    assert payload["verdict"] == "FAIL"
    assert any("accepted classification requires live acceptance PASS" in error for error in payload["errors"])


def test_fails_when_plan_classification_is_stale(tmp_path):
    classification_path, plan_path, preservation_path = write_bundle(tmp_path, classification="DIAGNOSTIC_REQUIRED")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["classification"] = "PENDING_LIVE_RUN"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    payload = route_live_postrun.route(
        root=tmp_path,
        classification_path=classification_path,
        plan_path=plan_path,
        preservation_path=preservation_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("diagnostics plan classification" in error for error in payload["errors"])


def test_main_writes_output(tmp_path, capsys):
    classification_path, plan_path, preservation_path = write_bundle(tmp_path, classification="PENDING_LIVE_RUN")
    output = tmp_path / "routing.json"

    result = route_live_postrun.main(
        [
            "--root",
            str(tmp_path),
            "--classification",
            str(classification_path),
            "--plan",
            str(plan_path),
            "--preservation",
            str(preservation_path),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-postrun-routing/v1"
    assert written["route"] == "WAIT_FOR_LIVE_RUN"
