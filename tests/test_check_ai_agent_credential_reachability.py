from __future__ import annotations

import json
from pathlib import Path

import check_ai_agent_credential_reachability as gate


EXPECTED_CASE_VERDICTS = {
    "clean_no_untrusted_to_credential_reachable_path": "PASS",
    "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected": "FAIL",
    "agent_tool_output_piped_to_shell_with_ssh_dir_rejected": "FAIL",
    "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected": "FAIL",
    "web_fetch_reflected_into_shell_resolving_env_rejected": "FAIL",
    "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected": "FAIL",
}


def test_summarize_passes_when_all_credential_reachability_invariants_hold(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/ai-agent-credential-reachability/v1"
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
    assert "untrusted_user_prompt" in payload["untrusted_sources"]
    assert "subprocess_argv" in payload["sinks"]


def test_clean_case_records_no_observed_errors(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["clean_no_untrusted_to_credential_reachable_path"]["observed_errors"] == []


def test_each_mutation_case_records_at_least_one_observed_error(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)
    by_id = {case["id"]: case for case in payload["cases"]}
    for case_id, expected in EXPECTED_CASE_VERDICTS.items():
        if expected != "FAIL":
            continue
        observed_errors = by_id[case_id]["observed_errors"]
        assert observed_errors, f"{case_id} must record at least one observed error"


def test_cli_writes_status_json_with_pass_verdict(tmp_path, capsys):
    output = tmp_path / "run-artifacts/ai-agent-credential-reachability.json"

    code = gate.main([
        "--root", str(tmp_path),
        "--work-dir", str(tmp_path / "work"),
        "--write-output", str(output),
        "--json",
    ])

    assert code == 0
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/ai-agent-credential-reachability/v1"
    assert saved["verdict"] == "PASS"
    assert saved["dispatch_authorized"] is False
    assert saved["live_providers_run"] is False
    captured = json.loads(capsys.readouterr().out)
    assert captured["verdict"] == "PASS"
