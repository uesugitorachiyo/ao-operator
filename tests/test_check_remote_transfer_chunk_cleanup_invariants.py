from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_chunk_cleanup_invariants as gate


def test_chunk_cleanup_invariants_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-chunk-cleanup-invariants/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["mutation_case_count"] == 5
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_upload_commit_passes",
        "orphaned_chunk_after_abort_detected",
        "missing_finalize_detected",
        "stale_partial_stage_dir_detected",
        "double_commit_rejected",
        "retry_index_drift_detected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_upload_commit_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_upload_commit_passes"]["observed_errors"] == []
    for fail_case in (
        "orphaned_chunk_after_abort_detected",
        "missing_finalize_detected",
        "stale_partial_stage_dir_detected",
        "double_commit_rejected",
        "retry_index_drift_detected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_chunk_cleanup_invariants_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("orphaned_chunks_after_abort:")
        for err in by_id["orphaned_chunk_after_abort_detected"]["observed_errors"]
    )
    assert "missing_finalize_after_successful_chunks" in by_id["missing_finalize_detected"]["observed_errors"]
    assert any(
        err.startswith("stale_partial_stage_dir:")
        for err in by_id["stale_partial_stage_dir_detected"]["observed_errors"]
    )
    assert any(
        err.startswith("double_commit:")
        for err in by_id["double_commit_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("retry_index_drift:")
        for err in by_id["retry_index_drift_detected"]["observed_errors"]
    )


def test_chunk_cleanup_invariants_fails_when_orphan_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_orphaned_chunk_after_abort_detected

    def neutered_runner(work):
        result = real_runner(work)
        case_id = "orphaned_chunk_after_abort_detected"
        stage = work / case_id
        for child in list(stage.iterdir()):
            child.unlink()
        session = {
            "upload_id": "upload-002",
            "aborted": True,
            "finalize_count": 0,
            "chunks_uploaded": [0, 1, 2],
            "last_failed_chunk_index": None,
            "expected_failed_chunk_index": None,
        }
        verdict, errors = gate._validate(session, stage)
        result["observed_verdict"] = verdict
        result["observed_errors"] = errors
        return result

    monkeypatch.setitem(gate.CASE_RUNNERS, "orphaned_chunk_after_abort_detected", neutered_runner)
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "orphaned_chunk_after_abort_detected" in err for err in payload["errors"]
    )


def test_chunk_cleanup_invariants_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-chunk-cleanup-invariants/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 6
    assert written["mutation_case_count"] == 5
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
