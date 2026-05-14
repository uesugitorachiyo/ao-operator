from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_network_retry_idempotency as gate


def test_network_retry_idempotency_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-network-retry-idempotency/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_retry_round_trip_passes",
        "retry_without_nonce_dedup_rejected",
        "partial_flush_on_network_drop_rejected",
        "ack_lost_causes_double_commit_rejected",
        "timeout_shorter_than_response_causes_orphan_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_retry_round_trip_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_retry_round_trip_passes"]["observed_errors"] == []
    for fail_case in (
        "retry_without_nonce_dedup_rejected",
        "partial_flush_on_network_drop_rejected",
        "ack_lost_causes_double_commit_rejected",
        "timeout_shorter_than_response_causes_orphan_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_network_retry_idempotency_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("retry_minted_new_nonce:")
        for err in by_id["retry_without_nonce_dedup_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("finalize_with_in_flight_nonces:")
        or err.startswith("finalize_without_commit:")
        for err in by_id["partial_flush_on_network_drop_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("double_commit_for_nonce:")
        for err in by_id["ack_lost_causes_double_commit_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("orphan_commit_after_timeout:")
        for err in by_id["timeout_shorter_than_response_causes_orphan_rejected"]["observed_errors"]
    )


def test_network_retry_idempotency_fails_when_mutation_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_retry_without_nonce_dedup_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "retry_without_nonce_dedup_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "retry_without_nonce_dedup_rejected" in err
        for err in payload["errors"]
    )


def test_network_retry_idempotency_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-network-retry-idempotency/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
