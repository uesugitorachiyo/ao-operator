from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_signed_bundle_tamper as gate


def test_signed_bundle_tamper_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-signed-bundle-tamper/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["mutation_case_count"] == 5
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_signed_bundle_passes",
        "truncated_bundle_rejected",
        "swapped_chunk_rejected",
        "wrong_signing_key_rejected",
        "replayed_bundle_rejected",
        "manifest_digest_mismatch_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_signed_bundle_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_signed_bundle_passes"]["observed_errors"] == []
    for fail_case in (
        "truncated_bundle_rejected",
        "swapped_chunk_rejected",
        "wrong_signing_key_rejected",
        "replayed_bundle_rejected",
        "manifest_digest_mismatch_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_signed_bundle_tamper_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("truncated_or_oversize_chunk:")
        for err in by_id["truncated_bundle_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("chunk_digest_mismatch:")
        for err in by_id["swapped_chunk_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("unregistered_signing_key:")
        for err in by_id["wrong_signing_key_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("nonce_replayed:")
        for err in by_id["replayed_bundle_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("chunk_digest_mismatch:")
        for err in by_id["manifest_digest_mismatch_rejected"]["observed_errors"]
    )


def test_signed_bundle_tamper_fails_when_swap_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_swapped_chunk_rejected

    def neutered_runner(work, *, seen_nonces):
        result = real_runner(work, seen_nonces=seen_nonces)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(gate.CASE_RUNNERS, "swapped_chunk_rejected", neutered_runner)
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("swapped_chunk_rejected" in err for err in payload["errors"])


def test_signed_bundle_tamper_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-signed-bundle-tamper/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 6
    assert written["mutation_case_count"] == 5
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
