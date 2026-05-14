from __future__ import annotations

import json
from pathlib import Path

import check_bounded_live_readiness


def fake_runner(command: list[str], *, root: Path, env: dict[str, str]) -> dict[str, object]:
    text = " ".join(command)
    if "run_operator_slice.py" in text:
        return {
            "command": command,
            "exit": 1,
            "json_verdict": "BLOCKED",
            "stdout": json.dumps({"verdict": "BLOCKED"}),
            "stderr": "",
        }
    if "check_live_acceptance.py" in text:
        return {
            "command": command,
            "exit": 1,
            "json_verdict": "FAIL",
            "stdout": json.dumps({"verdict": "FAIL"}),
            "stderr": "",
        }
    return {
        "command": command,
        "exit": 0,
        "json_verdict": "PASS",
        "stdout": json.dumps({"verdict": "PASS"}),
        "stderr": "",
    }


def test_check_readiness_accepts_expected_pre_live_state(tmp_path):
    payload = check_bounded_live_readiness.check_readiness(
        root=tmp_path,
        ao_runtime_path="/tmp/ao-runtime",
        runner=fake_runner,
    )

    assert payload["verdict"] == "PASS"
    assert payload["live_providers_run"] is False
    assert [check["id"] for check in payload["checks"]] == [
        "doctor.pass",
        "intake.pass",
        "factory.pass",
        "live_slice.blocked_without_allow_live",
        "acceptance.fails_before_live",
    ]


def test_check_readiness_fails_when_live_slice_is_not_blocked(tmp_path):
    def runner(command: list[str], *, root: Path, env: dict[str, str]) -> dict[str, object]:
        report = fake_runner(command, root=root, env=env)
        if "run_operator_slice.py" in " ".join(command):
            report = {
                "command": command,
                "exit": 0,
                "json_verdict": "PLAN",
                "stdout": json.dumps({"verdict": "PLAN"}),
                "stderr": "",
            }
        return report

    payload = check_bounded_live_readiness.check_readiness(root=tmp_path, runner=runner)

    assert payload["verdict"] == "FAIL"
    statuses = {check["id"]: check["status"] for check in payload["checks"]}
    assert statuses["live_slice.blocked_without_allow_live"] == "FAIL"


def test_main_emits_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(check_bounded_live_readiness, "run_command", fake_runner)

    result = check_bounded_live_readiness.main(["--root", str(tmp_path), "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"


def test_summary_payload_omits_stdout_and_stderr(tmp_path):
    payload = check_bounded_live_readiness.check_readiness(root=tmp_path, runner=fake_runner)

    summary = check_bounded_live_readiness.summary_payload(payload)

    assert summary["schema"] == "ao-operator/bounded-live-readiness-summary/v1"
    assert summary["verdict"] == "PASS"
    assert "stdout" not in json.dumps(summary)
    assert "stderr" not in json.dumps(summary)
    assert summary["checks"][0]["actual_verdict"] == "PASS"


def test_main_writes_summary(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(check_bounded_live_readiness, "run_command", fake_runner)
    summary_path = tmp_path / "summary.json"

    result = check_bounded_live_readiness.main(
        ["--root", str(tmp_path), "--write-summary", str(summary_path), "--json"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == str(summary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["verdict"] == "PASS"
