from __future__ import annotations

from pathlib import Path

import check_supply_chain_gate as supply


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_supply_chain_gate_passes_when_no_dependency_manifests_exist(tmp_path):
    payload = supply.summarize(tmp_path)

    assert payload["schema"] == "ao-operator/supply-chain-gate/v1"
    assert payload["verdict"] == "PASS"
    assert payload["dependency_manifests"] == []
    assert payload["dispatch_authorized"] is False


def test_supply_chain_gate_fails_python_dependencies_without_lock_or_audit_plan(tmp_path):
    write(tmp_path / "pyproject.toml", "[project]\ndependencies = ['requests']\n")

    payload = supply.summarize(tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("lockfile" in blocker for blocker in payload["blockers"])


def test_supply_chain_gate_passes_python_dependencies_with_lock_and_audit_plan(tmp_path):
    write(tmp_path / "pyproject.toml", "[project]\ndependencies = ['requests']\n")
    write(tmp_path / "requirements.lock", "requests==2.32.0\n")
    write(tmp_path / "docs" / "sdd" / "43-supply-chain-audit-gate.md", "pip-audit dependency review vulnerability advisory license pinning\n")

    payload = supply.summarize(tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["lockfiles"] == ["requirements.lock"]
