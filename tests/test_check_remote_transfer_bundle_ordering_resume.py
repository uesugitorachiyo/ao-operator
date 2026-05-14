from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_bundle_ordering_resume as gate


def test_bundle_ordering_resume_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-bundle-ordering-resume/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_ordered_delivery_passes",
        "out_of_order_chunk_rejected",
        "partial_resume_drops_middle_chunk_rejected",
        "resume_cursor_lies_about_high_water_rejected",
        "duplicate_chunk_delivery_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_ordered_delivery_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_ordered_delivery_passes"]["observed_errors"] == []
    for fail_case in (
        "out_of_order_chunk_rejected",
        "partial_resume_drops_middle_chunk_rejected",
        "resume_cursor_lies_about_high_water_rejected",
        "duplicate_chunk_delivery_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_bundle_ordering_resume_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("out_of_order_chunk:")
        for err in by_id["out_of_order_chunk_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("missing_chunk_at_finalize:")
        or err.startswith("finalize_before_all_chunks_delivered:")
        or err.startswith("out_of_order_chunk:")
        for err in by_id["partial_resume_drops_middle_chunk_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("resume_cursor_exceeds_confirmed_high_water:")
        for err in by_id["resume_cursor_lies_about_high_water_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("out_of_order_chunk:")
        for err in by_id["duplicate_chunk_delivery_rejected"]["observed_errors"]
    )


def test_bundle_ordering_resume_fails_when_out_of_order_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_out_of_order_chunk_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(gate.CASE_RUNNERS, "out_of_order_chunk_rejected", neutered_runner)
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("out_of_order_chunk_rejected" in err for err in payload["errors"])


def test_bundle_ordering_resume_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-bundle-ordering-resume/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
