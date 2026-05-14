from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_agent_os_postrun_route_matrix


def test_postrun_route_matrix_covers_terminal_and_blocked_states(tmp_path):
    payload = check_agent_os_postrun_route_matrix.build_matrix(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["pending_without_execution"]["route"] == "PENDING_RUN"
    assert by_id["accepted_completed_execution"]["route"] == "ACCEPTED"
    assert by_id["accepted_completed_execution"]["commit_success_evidence_allowed"] is True
    assert by_id["failed_execution"]["route"] == "DIAGNOSTIC_REQUIRED"
    assert by_id["blocked_execution"]["route"] == "BLOCKED"
    assert by_id["invalid_approval_gate"]["verdict"] == "FAIL"
    assert by_id["missing_evaluator_acceptance"]["route"] == "DIAGNOSTIC_REQUIRED"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_postrun_route_matrix_cli_writes_report(tmp_path, capsys):
    output = tmp_path / "run-artifacts/matrix.json"

    code = check_agent_os_postrun_route_matrix.main(
        ["--root", str(tmp_path), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-postrun-route-matrix/v1"
    assert saved["verdict"] == "PASS"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
