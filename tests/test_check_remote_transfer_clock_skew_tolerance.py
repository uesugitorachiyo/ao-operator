from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_clock_skew_tolerance as gate


def test_clock_skew_tolerance_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-clock-skew-tolerance/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_within_skew_tolerance_passes",
        "sender_clock_ahead_of_receiver_rejected",
        "sender_clock_behind_receiver_rejected",
        "future_dated_bundle_accepted_as_currently_valid_rejected",
        "ttl_window_straddling_skew_silently_extended_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_within_skew_tolerance_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_within_skew_tolerance_passes"]["observed_errors"] == []
    for fail_case in (
        "sender_clock_ahead_of_receiver_rejected",
        "sender_clock_behind_receiver_rejected",
        "future_dated_bundle_accepted_as_currently_valid_rejected",
        "ttl_window_straddling_skew_silently_extended_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_clock_skew_tolerance_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("force_accepted_not_before_beyond_skew:")
        for err in by_id["sender_clock_ahead_of_receiver_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("force_accepted_not_after_beyond_skew:")
        for err in by_id["sender_clock_behind_receiver_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("silently_clamped_future_not_before:")
        for err in by_id["future_dated_bundle_accepted_as_currently_valid_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("silently_extended_ttl_by_skew:")
        for err in by_id["ttl_window_straddling_skew_silently_extended_rejected"]["observed_errors"]
    )


def test_clock_skew_tolerance_fails_when_mutation_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_sender_clock_ahead_of_receiver_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "sender_clock_ahead_of_receiver_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "sender_clock_ahead_of_receiver_rejected" in err
        for err in payload["errors"]
    )


def test_clock_skew_tolerance_cli_writes_report(tmp_path, capsys):
    output = tmp_path / "report.json"

    code = gate.main(
        [
            "--root",
            str(Path(__file__).resolve().parents[1]),
            "--work-dir",
            str(tmp_path / "work"),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/remote-transfer-clock-skew-tolerance/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
