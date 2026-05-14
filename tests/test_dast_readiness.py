from __future__ import annotations

import check_dast_readiness as dast


def test_dast_command_plan_defaults_to_no_remote_provider_dispatch():
    commands = dast.command_plan(include_remote=False)

    flat = [" ".join(command) for command in commands]
    assert any("tests/test_mac_ubuntu_remote_smoke.py" in item for item in flat)
    assert any("scripts/check_public_release_security.py" in item for item in flat)
    assert all(not item.startswith("python3 scripts/run_mac_ubuntu_remote_smoke.py") for item in flat)
    assert all(" scripts/run_mac_ubuntu_remote_smoke.py --json" not in item for item in flat)


def test_dast_summary_blocks_remote_without_explicit_env():
    payload = dast.summarize(run_commands=False, include_remote=False)

    assert payload["schema"] == "ao-operator/dast-readiness/v1"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["remote_dast_enabled"] is False
    assert payload["verdict"] == "PASS"


def test_dast_summary_classifies_command_failure():
    def fake_runner(command, timeout):
        return {
            "command": command,
            "duration_seconds": 0.01,
            "returncode": 7,
            "stdout_tail": "",
            "stderr_tail": "boom",
            "verdict": "FAIL",
        }

    payload = dast.summarize(run_command_fn=fake_runner, include_remote=False)

    assert payload["verdict"] == "FAIL"
    assert payload["blockers"]
    assert payload["results"][0]["returncode"] == 7
