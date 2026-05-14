from __future__ import annotations

import json
from pathlib import Path

import run_three_os_setup_smoke as smoke


def test_redact_target_hides_user_and_host() -> None:
    assert smoke.redact_target("alice@192.0.2.96") == "<redacted-user>@<redacted-host>"
    assert smoke.redact_target("192.0.2.96") == "<redacted-host>"
    assert smoke.redact_target(None) == "<not-configured>"


def test_forbidden_keys_detects_only_present_values() -> None:
    assert smoke.forbidden_keys_from_env({"OPENAI_API_KEY": "x"}) == ["OPENAI_API_KEY"]
    assert smoke.forbidden_keys_from_env({"ANTHROPIC_API_KEY": ""}) == []


def test_ps_location_expands_userprofile_without_exposing_shell_injection() -> None:
    assert (
        smoke.ps_location(r"$env:USERPROFILE\Documents\ao-operator")
        == r"(Join-Path $env:USERPROFILE 'Documents\ao-operator')"
    )
    assert smoke.ps_location(r"C:\work\ao-operator") == r"'C:\work\ao-operator'"


def test_write_outputs_creates_promised_evidence_files(tmp_path: Path) -> None:
    results = [
        smoke.ProbeResult(
            host="mac",
            status="PASS",
            label="macOS local worker",
            target="local",
            command="local",
            payload={"host": "mac", "provider_api_keys_present": []},
        ),
        smoke.ProbeResult(
            host="ubuntu",
            status="PASS",
            label="Ubuntu coordinator / Linux lane",
            target="ubuntu@<redacted-host>",
            command="ssh ubuntu@<redacted-host> ...",
            payload={"host": "ubuntu", "provider_api_keys_present": []},
        ),
        smoke.ProbeResult(
            host="windows",
            status="PASS",
            label="native Windows worker",
            target="windows@<redacted-host>",
            command="ssh windows@<redacted-host> powershell ...",
            payload={"host": "windows", "provider_api_keys_present": [], "non_wsl": True},
        ),
    ]

    report = smoke.write_outputs(tmp_path, results)

    assert report["status"] == "PASS"
    for name in (
        "mac-evidence.md",
        "ubuntu-evidence.md",
        "windows-evidence.md",
        "three-os-setup-report.md",
        "three-os-setup-report.json",
    ):
        assert (tmp_path / name).is_file()
    payload = json.loads((tmp_path / "three-os-setup-report.json").read_text(encoding="utf-8"))
    assert payload["provider_dispatch"] is False
    assert "OPENAI_API_KEY" in payload["forbidden_provider_api_keys"]
    assert "192.0.2.96" not in (tmp_path / "windows-evidence.md").read_text(encoding="utf-8")
