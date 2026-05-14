from __future__ import annotations

import os

import check_three_os_pre_public_gate as gate


def test_three_os_gate_fails_closed_when_target_env_missing(monkeypatch):
    for name in gate.REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    result = gate.run_gate(timeout=1)

    assert result["schema"] == gate.SCHEMA
    assert result["status"] == "FAIL"
    assert sorted(result["missing_env"]) == sorted(gate.REQUIRED_ENV)
    assert result["errors"]


def test_three_os_gate_builds_redacted_command_from_env(monkeypatch):
    values = {
        "AO_OPERATOR_UBUNTU_TARGET": "ubuntu-worker@example.invalid",
        "AO_OPERATOR_UBUNTU_IDENTITY": "/private/key-a",
        "AO_OPERATOR_UBUNTU_REPO": "/opt/ao-operator",
        "AO_OPERATOR_WINDOWS_TARGET": "windows-worker@example.invalid",
        "AO_OPERATOR_WINDOWS_IDENTITY": "/private/key-b",
        "AO_OPERATOR_WINDOWS_REPO": "$env:USERPROFILE\\Documents\\ao-operator",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    command, missing = gate.build_command(timeout=7)
    redacted = gate.redact_command(command)

    assert missing == []
    assert command[:3] == [gate.sys.executable, "scripts/run_three_os_setup_smoke.py", "--timeout"]
    assert "7" in command
    assert "--ubuntu-target" in command
    assert "--windows-repo" in command
    assert all(value not in redacted for value in values.values())
    assert redacted.count("<redacted>") == len(gate.REQUIRED_ENV)
