from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_bundle_content_type_allowlist as gate


def test_bundle_content_type_allowlist_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-bundle-content-type-allowlist/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_allowlisted_content_type_passes",
        "unknown_content_type_silently_coerced_rejected",
        "mismatched_extension_to_content_type_rejected",
        "unknown_content_encoding_silently_decoded_rejected",
        "content_type_charset_parameter_smuggled_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_allowlisted_content_type_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_allowlisted_content_type_passes"]["observed_errors"] == []
    for fail_case in (
        "unknown_content_type_silently_coerced_rejected",
        "mismatched_extension_to_content_type_rejected",
        "unknown_content_encoding_silently_decoded_rejected",
        "content_type_charset_parameter_smuggled_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_bundle_content_type_allowlist_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("silently_coerced_unknown_content_type:")
        for err in by_id["unknown_content_type_silently_coerced_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("dispatched_with_payload_magic_mismatch:")
        for err in by_id["mismatched_extension_to_content_type_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("silently_fell_back_to_identity_encoding:")
        for err in by_id["unknown_content_encoding_silently_decoded_rejected"]["observed_errors"]
    )
    charset_errors = by_id["content_type_charset_parameter_smuggled_rejected"]["observed_errors"]
    assert any(err.startswith("unsafe_charset_parameter:") for err in charset_errors)
    assert any(err.startswith("path_traversal_in_charset_parameter:") for err in charset_errors)


def test_bundle_content_type_allowlist_fails_when_mutation_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_unknown_content_type_silently_coerced_rejected

    def neutered_runner(work):
        result = real_runner(work)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(
        gate.CASE_RUNNERS,
        "unknown_content_type_silently_coerced_rejected",
        neutered_runner,
    )
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any(
        "unknown_content_type_silently_coerced_rejected" in err
        for err in payload["errors"]
    )


def test_bundle_content_type_allowlist_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-bundle-content-type-allowlist/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
