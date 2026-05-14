from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import agent_os_state_v2


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_load_or_migrate_state_v1_forces_dispatch_flags_false(tmp_path):
    source = write_json(
        tmp_path / "state-v1.json",
        {
            "schema": "ao-operator/agent-os-state/v1",
            "lane": "agent-os-mission-router-state",
            "route": {"routes": ["live-provider"], "dispatch_authorized": True},
            "blockers": ["needs approval"],
            "live_providers_run": True,
        },
    )

    payload = agent_os_state_v2.load_or_migrate_state(root=tmp_path, state=source)

    assert payload["verdict"] == "PASS"
    assert payload["schema"] == "ao-operator/agent-os-state/v2"
    assert payload["previous_schema"] == "ao-operator/agent-os-state/v1"
    assert payload["role_graph_schema"] == "ao-operator/agent-os-role-graph/v1"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["route"]["dispatch_authorized"] is True


def test_load_or_migrate_state_v2_preserves_known_fields_without_authorizing(tmp_path):
    source = write_json(
        tmp_path / "state-v2.json",
        {
            "schema": "ao-operator/agent-os-state/v2",
            "lane": "agent-os-architecture",
            "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
            "route": {"routes": ["phase"]},
            "blockers": [],
            "evidence_paths": ["run-artifacts/example.json"],
            "dispatch_authorized": True,
            "live_providers_run": True,
        },
    )

    payload = agent_os_state_v2.load_or_migrate_state(root=tmp_path, state=source)

    assert payload["verdict"] == "PASS"
    assert payload["previous_schema"] == "ao-operator/agent-os-state/v2"
    assert payload["lane"] == "agent-os-architecture"
    assert payload["evidence_paths"] == ["run-artifacts/example.json"]
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_load_or_migrate_state_reports_invalid_schema(tmp_path):
    source = write_json(tmp_path / "bad.json", {"schema": "ao-operator/unknown"})

    payload = agent_os_state_v2.load_or_migrate_state(root=tmp_path, state=source)

    assert payload["verdict"] == "FAIL"
    assert "unsupported state schema: ao-operator/unknown" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_cli_writes_state_v2_snapshot(tmp_path, capsys):
    source = write_json(tmp_path / "state-v1.json", {"schema": "ao-operator/agent-os-state/v1", "lane": "legacy"})
    output = tmp_path / "run-artifacts/state-v2.json"

    code = agent_os_state_v2.main(
        ["--root", str(tmp_path), "--state", str(source), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-state/v2"
    assert saved["lane"] == "legacy"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
