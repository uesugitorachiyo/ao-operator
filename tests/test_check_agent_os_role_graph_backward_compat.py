from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_role_graph_backward_compat as gate


def test_role_graph_backward_compat_passes_for_legacy_fixtures(tmp_path):
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-role-graph-backward-compat/v1"
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == [
        "legacy_v1_state_minimal_loadable",
        "legacy_v1_state_extra_unknown_fields_tolerated",
        "legacy_v1_state_no_role_graph_schema_injects_default",
        "legacy_v2_state_round_trip_preserves_previous_schema",
        "legacy_v1_role_graph_artifact_remains_loadable",
        "unknown_state_schema_refused",
    ]
    by_id = {case["id"]: case for case in payload["cases"]}
    for pass_case in (
        "legacy_v1_state_minimal_loadable",
        "legacy_v1_state_extra_unknown_fields_tolerated",
        "legacy_v1_state_no_role_graph_schema_injects_default",
        "legacy_v2_state_round_trip_preserves_previous_schema",
        "legacy_v1_role_graph_artifact_remains_loadable",
    ):
        assert by_id[pass_case]["observed_verdict"] == "PASS"
    assert by_id["unknown_state_schema_refused"]["observed_verdict"] == "FAIL"


def test_role_graph_backward_compat_fails_when_loader_breaks(tmp_path, monkeypatch):
    def broken_load(*, root: Path, state):
        return {
            "schema": "",
            "verdict": "FAIL",
            "previous_schema": "",
            "role_graph_schema": "",
            "errors": ["forced break"],
        }

    monkeypatch.setattr(gate.agent_os_state_v2, "load_or_migrate_state", broken_load)
    payload = gate.summarize(work_dir=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("legacy_v1_state_minimal_loadable" in err for err in payload["errors"])


def test_role_graph_backward_compat_cli_writes_report(tmp_path, capsys):
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
    assert written["schema"] == "ao-operator/agent-os-role-graph-backward-compat/v1"
    assert written["verdict"] == "PASS"
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(output)
