from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_per_tenant_quota_isolation as gate


EXPECTED_CASE_VERDICTS = {
    "clean_per_tenant_within_quota_passes": "PASS",
    "tenant_a_overflows_tenant_b_quota_slot_rejected": "FAIL",
    "aggregated_quota_across_tenants_merged_rejected": "FAIL",
    "tenant_identity_stripped_silently_coerced_to_default_rejected": "FAIL",
    "quota_refund_on_abort_double_credited_rejected": "FAIL",
}


def test_summarize_passes_when_all_per_tenant_quota_invariants_hold(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/remote-transfer-per-tenant-quota-isolation/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
    assert payload["mutation_case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    by_id = {case["id"]: case for case in payload["cases"]}
    for case_id, expected in EXPECTED_CASE_VERDICTS.items():
        assert by_id[case_id]["observed_verdict"] == expected, (
            f"{case_id} expected {expected}, observed {by_id[case_id]['observed_verdict']}"
        )
    assert payload["errors"] == []


def test_clean_case_records_no_observed_errors(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_per_tenant_within_quota_passes"]["observed_errors"] == []


def test_each_mutation_case_records_at_least_one_observed_error(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)
    by_id = {case["id"]: case for case in payload["cases"]}
    for case_id, expected in EXPECTED_CASE_VERDICTS.items():
        if expected != "FAIL":
            continue
        observed_errors = by_id[case_id]["observed_errors"]
        assert observed_errors, f"{case_id} must record at least one observed error"


def test_cli_writes_status_json_with_pass_verdict(tmp_path, capsys):
    output = tmp_path / "run-artifacts/per-tenant-quota.json"

    code = gate.main([
        "--root", str(tmp_path),
        "--work-dir", str(tmp_path / "work"),
        "--write-output", str(output),
        "--json",
    ])

    assert code == 0
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/remote-transfer-per-tenant-quota-isolation/v1"
    assert saved["verdict"] == "PASS"
    assert saved["dispatch_authorized"] is False
    assert saved["live_providers_run"] is False
    captured = json.loads(capsys.readouterr().out)
    assert captured["verdict"] == "PASS"
