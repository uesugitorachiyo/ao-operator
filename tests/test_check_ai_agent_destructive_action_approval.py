from __future__ import annotations

import json
from pathlib import Path

import check_ai_agent_destructive_action_approval as gate


EXPECTED_CASE_VERDICTS = {
    "clean_destructive_action_with_fresh_scoped_approval_executes": "PASS",
    "stale_approval_reused_after_expiry_rejected": "FAIL",
    "approval_scope_widened_at_exec_silently_accepted_rejected": "FAIL",
    "approval_consumed_twice_for_distinct_destructive_ops_rejected": "FAIL",
    "destructive_op_runs_with_policy_only_without_token_rejected": "FAIL",
    "parent_process_approval_inherited_by_child_without_reconfirm_rejected": "FAIL",
}


def test_summarize_passes_when_all_destructive_action_invariants_hold(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/ai-agent-destructive-action-approval/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["mutation_case_count"] == 5
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
    assert by_id["clean_destructive_action_with_fresh_scoped_approval_executes"]["observed_errors"] == []


def test_each_mutation_case_records_at_least_one_observed_error(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)
    by_id = {case["id"]: case for case in payload["cases"]}
    for case_id, expected in EXPECTED_CASE_VERDICTS.items():
        if expected != "FAIL":
            continue
        observed_errors = by_id[case_id]["observed_errors"]
        assert observed_errors, f"{case_id} must record at least one observed error"


def test_cli_writes_status_json_with_pass_verdict(tmp_path, capsys):
    output = tmp_path / "run-artifacts/ai-agent-destructive-action-approval.json"

    code = gate.main([
        "--root", str(tmp_path),
        "--work-dir", str(tmp_path / "work"),
        "--write-output", str(output),
        "--json",
    ])

    assert code == 0
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/ai-agent-destructive-action-approval/v1"
    assert saved["verdict"] == "PASS"
    assert saved["dispatch_authorized"] is False
    assert saved["live_providers_run"] is False
    captured = json.loads(capsys.readouterr().out)
    assert captured["verdict"] == "PASS"
