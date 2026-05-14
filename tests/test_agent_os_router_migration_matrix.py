from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_router_migration_matrix


def test_router_migration_matrix_covers_v1_v2_and_fail_closed_cases(tmp_path):
    payload = check_agent_os_router_migration_matrix.build_matrix(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-router-migration-matrix/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["router_v1_to_state_v2"]["verdict"] == "PASS"
    assert by_id["router_v1_to_state_v2"]["previous_schema"] == "ao-operator/agent-os-state/v1"
    assert by_id["router_v2_reload"]["previous_schema"] == "ao-operator/agent-os-state/v2"
    assert by_id["stale_v2_flags_reset"]["dispatch_authorized"] is False
    assert by_id["live_provider_blocker_preserved"]["blocker_count"] == 1
    assert by_id["invalid_schema_fails"]["verdict"] == "FAIL"
    assert by_id["missing_architecture_readiness_fails_closed"]["verdict"] == "FAIL"
    assert payload["next_safe_command"] == "Router migration matrix passes; continue Agent OS architecture changes behind state v2."


def test_router_migration_matrix_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-router-migration-matrix.json"

    code = check_agent_os_router_migration_matrix.main([
        "--root",
        str(tmp_path),
        "--write-output",
        str(output),
        "--json",
    ])

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["verdict"] == "PASS"
    assert saved["case_count"] == 6
