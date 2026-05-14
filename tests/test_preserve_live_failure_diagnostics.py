from __future__ import annotations

import json
from pathlib import Path

import preserve_live_failure_diagnostics


def write_plan(path: Path, *, classification: str = "PENDING_LIVE_RUN", copy_allowed: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "ao-operator/live-failure-diagnostics-plan/v1",
                "slug": "live",
                "classification": classification,
                "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
                "copy_allowed": copy_allowed,
                "live_providers_run": False,
                "raw_snapshot_commit_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def write_ao_home(path: Path) -> Path:
    events = path / "runs" / "r-test" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        "\n".join(
            [
                json.dumps({"kind": "task.started", "taskId": "a"}),
                json.dumps(
                    {
                        "kind": "task.failed",
                        "taskId": "a",
                        "payload": {"error": "provider limit", "stderr": "rate limited"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_pending_plan_passes_without_preservation(tmp_path):
    plan = write_plan(tmp_path / "plan.json")

    payload = preserve_live_failure_diagnostics.preserve(
        root=tmp_path,
        slug="live",
        ao_home=str(tmp_path / "ao"),
        plan_path=plan,
    )

    assert payload["verdict"] == "PASS"
    assert payload["diagnostics_required"] is False
    assert payload["summary_written"] is False
    assert payload["raw_snapshot_copied"] is False
    assert payload["raw_snapshot_commit_allowed"] is False


def test_diagnostic_plan_blocks_without_execute(tmp_path):
    plan = write_plan(tmp_path / "plan.json", classification="DIAGNOSTIC_REQUIRED", copy_allowed=True)

    payload = preserve_live_failure_diagnostics.preserve(
        root=tmp_path,
        slug="live",
        ao_home=str(tmp_path / "ao"),
        plan_path=plan,
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["diagnostics_required"] is True
    assert payload["summary_written"] is False
    assert any("--execute" in action for action in payload["next_actions"])


def test_execute_writes_sanitized_summary_without_raw_copy(tmp_path):
    plan = write_plan(tmp_path / "plan.json", classification="DIAGNOSTIC_REQUIRED", copy_allowed=True)
    ao_home = write_ao_home(tmp_path / "ao")

    payload = preserve_live_failure_diagnostics.preserve(
        root=tmp_path,
        slug="live",
        ao_home=str(ao_home),
        plan_path=plan,
        execute=True,
        timestamp="20260506-010203",
    )

    assert payload["verdict"] == "PASS"
    assert payload["summary_written"] is True
    assert payload["raw_snapshot_copied"] is False
    assert payload["summary"] == "run-artifacts/live/failure-snapshots/ao-home-20260506-010203-summary.json"
    assert payload["primary_normalized_reason"] == "provider-rate-limit"
    assert payload["normalized_reason_counts"] == {"provider-rate-limit": 1}
    written = json.loads((tmp_path / payload["summary"]).read_text(encoding="utf-8"))
    assert "/tmp/[REDACTED_AO_HOME]/runs/r-test/events.jsonl" == written["events"]
    assert written["counts"]["task.failed"] == 1


def test_execute_can_copy_raw_snapshot_when_requested(tmp_path):
    plan = write_plan(tmp_path / "plan.json", classification="DIAGNOSTIC_REQUIRED", copy_allowed=True)
    ao_home = write_ao_home(tmp_path / "ao")

    payload = preserve_live_failure_diagnostics.preserve(
        root=tmp_path,
        slug="live",
        ao_home=str(ao_home),
        plan_path=plan,
        execute=True,
        copy_raw=True,
        timestamp="20260506-010203",
    )

    assert payload["verdict"] == "PASS"
    assert payload["raw_snapshot_copied"] is True
    assert payload["raw_snapshot"] == "run-artifacts/live/failure-snapshots/ao-home-20260506-010203"
    assert (tmp_path / payload["raw_snapshot"] / "runs" / "r-test" / "events.jsonl").is_file()
    assert payload["raw_snapshot_commit_allowed"] is False


def test_missing_plan_fails(tmp_path):
    payload = preserve_live_failure_diagnostics.preserve(
        root=tmp_path,
        slug="live",
        ao_home=str(tmp_path / "ao"),
        plan_path=tmp_path / "missing.json",
    )

    assert payload["verdict"] == "FAIL"
    assert any("diagnostics plan unavailable" in error for error in payload["errors"])


def test_main_writes_report_for_pending_plan(tmp_path, capsys):
    plan = write_plan(tmp_path / "plan.json")
    report = tmp_path / "report.json"

    result = preserve_live_failure_diagnostics.main(
        [
            "--root",
            str(tmp_path),
            "--slug",
            "live",
            "--plan",
            str(plan),
            "--write-report",
            str(report),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"] == str(report)
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-failure-diagnostics-preservation/v1"
    assert written["verdict"] == "PASS"
