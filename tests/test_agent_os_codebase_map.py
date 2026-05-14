from __future__ import annotations

import json
from pathlib import Path

import agent_os_codebase_map


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_repo(root: Path) -> None:
    write(root / "scripts/factory_run.py", "print('runtime')\n")
    write(root / "scripts/factory_doctor.py", "print('doctor')\n")
    write(root / "tests/test_factory_run.py", "def test_runtime(): pass\n")
    write(root / "docs/sdd/13-agent-os.md", "# Agent OS\n")
    write(root / "agents/planner.toml", "name = 'planner'\n")
    write(root / "skills/factory-intake/SKILL.md", "# Intake\n")


def test_map_codebase_groups_factory_surfaces(tmp_path):
    seed_repo(tmp_path)

    payload = agent_os_codebase_map.map_codebase(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["surfaces"]["runtime_scripts"]["count"] == 2
    assert payload["surfaces"]["tests"]["count"] == 1
    assert payload["surfaces"]["sdd_docs"]["count"] == 1
    assert "engineering-manager" in payload["recommended_specialists"]


def test_map_codebase_records_missing_core_surface(tmp_path):
    write(tmp_path / "scripts/factory_run.py", "print('runtime')\n")

    payload = agent_os_codebase_map.map_codebase(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("tests" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_cli_writes_report(tmp_path, capsys):
    seed_repo(tmp_path)
    output = tmp_path / "run-artifacts/map.json"

    code = agent_os_codebase_map.main(["--root", str(tmp_path), "--write-output", str(output), "--json"])

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-codebase-map/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
