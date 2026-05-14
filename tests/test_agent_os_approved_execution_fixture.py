from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approved_execution_fixture


def test_approved_execution_fixture_exercises_happy_path_without_provider_dispatch(tmp_path):
    payload = check_agent_os_approved_execution_fixture.build_fixture(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-approved-execution-fixture/v1"
    assert payload["verdict"] == "PASS"
    assert payload["fixture_only"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["component_results"] == {
        "approval_gate": "PASS",
        "approval_validation": "APPROVED",
        "execution_report": "PASS",
        "postrun_route": "ACCEPTED",
        "evaluator_closure": "PASS",
        "commit_guard": "FAIL",
    }
    approval_validation = json.loads(
        (tmp_path / payload["artifacts"]["approval_validation"]).read_text(encoding="utf-8")
    )
    assert approval_validation["provider_profile_checked"] is True
    assert approval_validation["provider_profile_matches"] is True
    assert payload["commit_guard_fixture_acceptance"] is False
    assert payload["artifacts"]["execution_report"].endswith("approved-execution-fixture/execution-report.json")
    assert payload["next_safe_command"] == "Use this fixture as a provider-free baseline only; do not commit it as live success evidence."


def test_approved_execution_fixture_fails_when_commit_guard_would_not_accept(tmp_path):
    payload = check_agent_os_approved_execution_fixture.build_fixture(root=tmp_path, evaluator_accepted=False)

    assert payload["verdict"] == "FAIL"
    assert payload["component_results"]["postrun_route"] == "DIAGNOSTIC_REQUIRED"
    assert payload["component_results"]["evaluator_closure"] == "FAIL"
    assert payload["component_results"]["commit_guard"] == "PASS"
    assert payload["commit_guard_fixture_acceptance"] is False
    assert payload["commit_success_evidence_allowed"] is False
    assert any("fixture expected ACCEPTED postrun route" in error for error in payload["errors"])


def test_approved_execution_fixture_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-approved-execution-fixture.json"

    code = check_agent_os_approved_execution_fixture.main([
        "--root",
        str(tmp_path),
        "--write-output",
        str(output),
        "--json",
    ])

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["verdict"] == "PASS"
    assert saved["fixture_only"] is True
