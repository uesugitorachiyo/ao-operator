from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_approval_expiry_rotation as gate


def test_approval_expiry_rotation_passes_for_synthesized_cases(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-approval-expiry-rotation/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "clean_approval_passes",
        "expired_approval_rejected",
        "approval_used_after_rotation_cutover_rejected",
        "signing_key_rotated_midflight_without_grace_rejected",
        "approval_reused_beyond_ttl_rejected",
    ]

    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_approval_passes"]["observed_verdict"] == "PASS"
    assert by_id["clean_approval_passes"]["observed_errors"] == []
    for fail_case in (
        "expired_approval_rejected",
        "approval_used_after_rotation_cutover_rejected",
        "signing_key_rotated_midflight_without_grace_rejected",
        "approval_reused_beyond_ttl_rejected",
    ):
        assert by_id[fail_case]["observed_verdict"] == "FAIL"
        assert by_id[fail_case]["observed_errors"], (
            f"{fail_case} must surface at least one observed error"
        )
        assert by_id[fail_case]["dispatch_authorized"] is False
        assert by_id[fail_case]["live_providers_run"] is False


def test_approval_expiry_rotation_validator_detects_specific_mutations():
    payload = gate.summarize()
    by_id = {case["id"]: case for case in payload["cases"]}

    assert any(
        err.startswith("approval_expired:")
        for err in by_id["expired_approval_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("kid_inactive_at_use_time:")
        for err in by_id["approval_used_after_rotation_cutover_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("kid_inactive_at_use_time:")
        for err in by_id["signing_key_rotated_midflight_without_grace_rejected"]["observed_errors"]
    )
    assert any(
        err.startswith("approval_reused_beyond_ttl:")
        for err in by_id["approval_reused_beyond_ttl_rejected"]["observed_errors"]
    )


def test_approval_expiry_rotation_fails_when_expiry_undetected(tmp_path, monkeypatch):
    real_runner = gate.run_expired_approval_rejected

    def neutered_runner(work, *, use_counts):
        result = real_runner(work, use_counts=use_counts)
        result["observed_verdict"] = "PASS"
        result["observed_errors"] = []
        return result

    monkeypatch.setitem(gate.CASE_RUNNERS, "expired_approval_rejected", neutered_runner)
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("expired_approval_rejected" in err for err in payload["errors"])


def test_approval_expiry_rotation_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/remote-transfer-approval-expiry-rotation/v1"
    assert written["verdict"] == "PASS"
    assert written["case_count"] == 5
    assert written["mutation_case_count"] == 4
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
