from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_router_transition_matrix


def test_router_transition_matrix_covers_expected_route_edges(tmp_path):
    payload = check_agent_os_router_transition_matrix.build_matrix(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-router-transition-matrix/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 9
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["trivial_to_fast"]["classification"] == "TRIVIAL"
    assert by_id["trivial_to_fast"]["routes"] == ["fast"]
    assert by_id["moderate_remote_worker_to_quick"]["routes"] == ["quick", "remote-worker"]
    assert by_id["complex_phase_to_phase"]["routes"] == ["phase"]
    assert by_id["frontend_label_promotes_to_moderate"]["classification"] == "MODERATE"
    assert by_id["live_provider_blocks_dispatch"]["route_dispatch_authorized"] is False
    assert by_id["live_provider_blocks_dispatch"]["blocker_count"] == 1
    assert by_id["unknown_label_ignored"]["routes"] == ["fast"]
    assert by_id["bug_fix_without_reproducer_fails_shape_gate"]["blocker_count"] >= 1
    assert by_id["refactor_with_release_state_v2"]["state_schema"] == "ao-operator/agent-os-state/v2"
    assert by_id["refactor_with_release_state_v2"]["state_verdict"] == "PASS"


def test_router_transition_matrix_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-router-transition-matrix.json"

    code = check_agent_os_router_transition_matrix.main(
        ["--root", str(tmp_path), "--write-output", str(output), "--json"]
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["schema"] == "ao-operator/agent-os-router-transition-matrix/v1"
    assert saved["case_count"] == 9
