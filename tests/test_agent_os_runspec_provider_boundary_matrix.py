from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_runspec_provider_boundary_matrix


def test_runspec_provider_boundary_matrix_covers_codex_claude_mixed_and_refusal(tmp_path):
    payload = check_agent_os_runspec_provider_boundary_matrix.build_matrix(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-runspec-provider-boundary-matrix/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 4
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    by_id = {case["id"]: case for case in payload["cases"]}
    assert by_id["codex_only"]["provider_set"] == ["codex"]
    assert by_id["claude_only"]["provider_set"] == ["claude"]
    assert by_id["mixed_profile"]["provider_set"] == ["claude", "codex"]
    assert by_id["mixed_profile"]["profile_path"] == "examples/provider-profiles/mixed-throughput.env"
    assert by_id["mixed_profile"]["yaml_verified"] is True
    assert by_id["mixed_profile"]["yaml_provider_set"] == ["claude", "codex"]
    assert by_id["provider_substitution_refusal"]["verdict"] == "FAIL"
    assert by_id["provider_substitution_refusal"]["substitution_refused"] is True
    assert by_id["provider_substitution_refusal"]["yaml_verified"] is True
    assert "provider mismatch for planner" in by_id["provider_substitution_refusal"]["errors"][0]
    assert payload["next_safe_command"] == "RunSpec provider boundary matrix passes; keep provider substitution explicit."


def test_runspec_provider_boundary_matrix_cli_writes_output(tmp_path):
    output = tmp_path / "status" / "agent-os-runspec-provider-boundary-matrix.json"

    code = check_agent_os_runspec_provider_boundary_matrix.main([
        "--root",
        str(tmp_path),
        "--write-output",
        str(output),
        "--json",
    ])

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert saved["case_count"] == 4
    assert saved["verdict"] == "PASS"
