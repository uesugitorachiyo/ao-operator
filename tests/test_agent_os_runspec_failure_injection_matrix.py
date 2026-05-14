from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_runspec_failure_injection_matrix


def test_runspec_failure_injection_matrix_fails_closed_without_dispatch(tmp_path):
    payload = check_agent_os_runspec_failure_injection_matrix.build_matrix(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-runspec-failure-injection-matrix/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 7
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["baseline_validates"]["observed_verdict"] == "PASS"
    assert by_id["stale_approval_hash_refused"]["observed_verdict"] == "REFUSED"
    assert by_id["missing_prompt_refused"]["observed_verdict"] == "FAIL"
    assert by_id["dispatch_flag_mutation_refused"]["observed_verdict"] == "FAIL"
    assert by_id["bad_provider_profile_refused"]["observed_verdict"] == "FAIL"
    assert by_id["invalid_provider_refused"]["observed_verdict"] == "FAIL"
    assert by_id["missing_state_baseline_refused"]["observed_verdict"] == "FAIL"
    for case in payload["cases"]:
        assert case["dispatch_authorized"] is False
        assert case["live_providers_run"] is False


def test_runspec_failure_injection_matrix_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-runspec-failure-injection-matrix.json"

    code = check_agent_os_runspec_failure_injection_matrix.main(
        ["--root", str(tmp_path), "--write-output", str(output), "--json"]
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["schema"] == "ao-operator/agent-os-runspec-failure-injection-matrix/v1"
    assert saved["case_count"] == 7
