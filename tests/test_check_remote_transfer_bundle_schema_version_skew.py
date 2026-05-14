from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_bundle_schema_version_skew as gate


def test_bundle_schema_version_skew_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-bundle-schema-version-skew/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_matched_schema_version_passes",
        "receiver_below_min_version_rejected",
        "receiver_above_max_silently_downgrades_rejected",
        "bundle_advertises_unknown_extension_field_rejected",
        "schema_version_field_missing_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_matched_schema_version_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_matched_schema_version_passes"]["observed_errors"] == []
    for fail_case in (
        "receiver_below_min_version_rejected",
        "receiver_above_max_silently_downgrades_rejected",
        "bundle_advertises_unknown_extension_field_rejected",
        "schema_version_field_missing_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_bundle_schema_version_skew_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("force_accepted_below_min:")
        for err in by_id["receiver_below_min_version_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("silent_downgrade:")
        for err in by_id["receiver_above_max_silently_downgrades_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("force_accepted_unknown_extension:")
        for err in by_id["bundle_advertises_unknown_extension_field_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("force_accepted_missing_version:")
        for err in by_id["schema_version_field_missing_rejected"]["observed_errors"]
    )


def test_bundle_schema_version_skew_fails_when_mutation_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_receiver_below_min_version_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "receiver_below_min_version_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "receiver_below_min_version_rejected" in err
        for err in payload["errors"]
    )


def test_bundle_schema_version_skew_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-bundle-schema-version-skew/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
