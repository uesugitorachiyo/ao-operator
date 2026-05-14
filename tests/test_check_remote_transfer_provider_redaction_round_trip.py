from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_provider_redaction_round_trip as gate


def test_provider_redaction_round_trip_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-provider-redaction-round-trip/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_round_trip_passes",
        "redaction_marker_stripped_before_transmit_rejected",
        "sensitive_field_leaks_past_redaction_filter_rejected",
        "double_redaction_corrupts_payload_rejected",
        "provider_response_leaks_redacted_value_back_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_round_trip_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_round_trip_passes"]["observed_errors"] == []
    for fail_case in (
        "redaction_marker_stripped_before_transmit_rejected",
        "sensitive_field_leaks_past_redaction_filter_rejected",
        "double_redaction_corrupts_payload_rejected",
        "provider_response_leaks_redacted_value_back_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_provider_redaction_round_trip_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("plaintext_sensitive_value_in_transmit:")
        or err.startswith("redaction_marker_missing_or_malformed:")
        for err in by_id["redaction_marker_stripped_before_transmit_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("plaintext_sensitive_value_in_transmit:")
        or err.startswith("redaction_marker_missing_or_malformed:")
        for err in by_id["sensitive_field_leaks_past_redaction_filter_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("double_redaction_not_idempotent:")
        for err in by_id["double_redaction_corrupts_payload_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("plaintext_sensitive_value_in_response:")
        for err in by_id["provider_response_leaks_redacted_value_back_rejected"]["observed_errors"]
    )


def test_provider_redaction_round_trip_fails_when_redaction_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_redaction_marker_stripped_before_transmit_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "redaction_marker_stripped_before_transmit_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "redaction_marker_stripped_before_transmit_rejected" in err
        for err in payload["errors"]
    )


def test_provider_redaction_round_trip_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-provider-redaction-round-trip/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
