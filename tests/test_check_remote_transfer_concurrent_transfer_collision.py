from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_concurrent_transfer_collision as gate


def test_concurrent_transfer_collision_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-concurrent-transfer-collision/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_serialized_concurrent_transfers_passes",
        "parallel_transfers_no_lock_corrupts_state_rejected",
        "simultaneous_finalize_double_completes_bundle_rejected",
        "lost_writer_overwrites_winner_bundle_rejected",
        "stale_lock_holder_resumes_after_handoff_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_serialized_concurrent_transfers_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_serialized_concurrent_transfers_passes"]["observed_errors"] == []
    for fail_case in (
        "parallel_transfers_no_lock_corrupts_state_rejected",
        "simultaneous_finalize_double_completes_bundle_rejected",
        "lost_writer_overwrites_winner_bundle_rejected",
        "stale_lock_holder_resumes_after_handoff_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_concurrent_transfer_collision_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("write_without_lock:") or err.startswith("finalize_without_lock:")
        for err in by_id["parallel_transfers_no_lock_corrupts_state_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("finalize_without_lock:") or err.startswith("double_finalize:")
        for err in by_id["simultaneous_finalize_double_completes_bundle_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("write_without_lock:") or err.startswith("chunk_overwrite_by_other_writer:")
        for err in by_id["lost_writer_overwrites_winner_bundle_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("stale_lock_holder_write:")
        for err in by_id["stale_lock_holder_resumes_after_handoff_rejected"]["observed_errors"]
    )


def test_concurrent_transfer_collision_fails_when_mutation_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_parallel_transfers_no_lock_corrupts_state_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "parallel_transfers_no_lock_corrupts_state_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "parallel_transfers_no_lock_corrupts_state_rejected" in err
        for err in payload["errors"]
    )


def test_concurrent_transfer_collision_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-concurrent-transfer-collision/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
