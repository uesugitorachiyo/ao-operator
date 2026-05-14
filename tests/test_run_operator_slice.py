from __future__ import annotations

import json
import sys
from pathlib import Path

import run_operator_slice


def manifest(command: str | None = None) -> dict[str, object]:
    return {
        "schema": "ao-operator/operator-slices/v1",
        "slug": "test-operator",
        "title": "Test operator slices",
        "classification": "COMPLEX",
        "shape": "refactor",
        "max_live_tasks_default": 50,
        "objective": "Test operator execution.",
        "negative_constraints": ["MUST NOT run live by default"],
        "sensitive_fields": ["provider OAuth credentials"],
        "slices": [
            {
                "order": 0,
                "id": "00-local",
                "mode": "diagnostic",
                "live_provider": False,
                "task_count": 0,
                "objective": "Run local command.",
                "reads": [],
                "writes": [],
                "commands": [command or f"{sys.executable} -c \"print('ok')\""],
                "evidence": ["exit 0"],
                "stop_rules": ["Stop on failure."],
            },
            {
                "order": 1,
                "id": "01-validation",
                "mode": "validation",
                "live_provider": False,
                "task_count": 0,
                "objective": "Validate locally.",
                "reads": [],
                "writes": [],
                "commands": [f"{sys.executable} -c \"print('valid')\""],
                "evidence": ["exit 0"],
                "stop_rules": ["Stop on failure."],
            },
            {
                "order": 2,
                "id": "01-blocked",
                "mode": "preflight-block",
                "live_provider": False,
                "expected_blocked": True,
                "expected_exit": 1,
                "task_count": 10,
                "objective": "Accept expected block.",
                "reads": [],
                "writes": [],
                "commands": [f"{sys.executable} -c \"raise SystemExit(1)\""],
                "evidence": ["exit 1"],
                "stop_rules": ["Stop if exit is not 1."],
            },
            {
                "order": 3,
                "id": "02-live",
                "mode": "live-run",
                "live_provider": True,
                "task_count": 10,
                "objective": "Live slice.",
                "reads": [],
                "writes": [],
                "commands": [f"{sys.executable} -c \"print('live')\" --run"],
                "evidence": ["live evidence"],
                "stop_rules": ["Stop on blockers."],
            },
        ],
    }


def write_manifest(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "operator-slices.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_select_slices_through_local_only_excludes_live():
    selected = run_operator_slice.select_slices(manifest(), through="3", local_only=True)

    assert [item["id"] for item in selected] == ["00-local", "01-validation", "01-blocked"]


def test_select_slices_from_through_range():
    selected = run_operator_slice.select_slices(manifest(), from_slice="01-validation", through="01-blocked")

    assert [item["id"] for item in selected] == ["01-validation", "01-blocked"]


def test_plan_does_not_execute(tmp_path, capsys):
    path = write_manifest(tmp_path, manifest(f"{sys.executable} -c \"raise SystemExit(9)\""))

    result = run_operator_slice.main([str(path), "--slice", "00-local", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PLAN"


def test_runner_applies_slice_env(tmp_path, monkeypatch, capsys):
    data = manifest(
        f"{sys.executable} -c \"import os; raise SystemExit(0 if os.environ.get('AO_HOME') == '/tmp/test-ao' else 3)\""
    )
    slices = data["slices"]
    assert isinstance(slices, list)
    local = slices[0]
    assert isinstance(local, dict)
    local["env"] = {"AO_HOME": "/tmp/test-ao"}
    path = write_manifest(tmp_path, data)
    monkeypatch.setattr(run_operator_slice, "ROOT", tmp_path)

    result = run_operator_slice.main([str(path), "--slice", "00-local", "--execute", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"


def test_runner_applies_leading_env_assignment_without_shell(tmp_path, monkeypatch, capsys):
    command = (
        "OPERATOR_TEST_VALUE=ok "
        f"{sys.executable} -c \"import os; raise SystemExit(0 if os.environ.get('OPERATOR_TEST_VALUE') == 'ok' else 4)\""
    )
    path = write_manifest(tmp_path, manifest(command))
    monkeypatch.setattr(run_operator_slice, "ROOT", tmp_path)

    result = run_operator_slice.main([str(path), "--slice", "00-local", "--execute", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"


def test_runner_refuses_live_slice_by_default(tmp_path, capsys):
    path = write_manifest(tmp_path, manifest())

    result = run_operator_slice.main([str(path), "--slice", "02-live", "--execute", "--json"])

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "BLOCKED"
    assert "requires --allow-live" in payload["errors"][0]


def test_runner_accepts_expected_block_exit(tmp_path, monkeypatch, capsys):
    path = write_manifest(tmp_path, manifest())
    monkeypatch.setattr(run_operator_slice, "ROOT", tmp_path)

    result = run_operator_slice.main([str(path), "--slice", "01-blocked", "--execute", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"
    assert payload["slices"][0]["expected_exit"] == 1


def test_runner_writes_report_for_executed_slice(tmp_path, monkeypatch, capsys):
    path = write_manifest(tmp_path, manifest())
    monkeypatch.setattr(run_operator_slice, "ROOT", tmp_path)

    result = run_operator_slice.main([str(path), "--slice", "00-local", "--execute", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    report = Path(payload["report"])
    assert report.is_file()
    assert report.read_text(encoding="utf-8")


def test_runner_redacts_sensitive_report_output(tmp_path, monkeypatch, capsys):
    command = (
        f"{sys.executable} -c \""
        "print('/home/tester/.codex/auth.json'); "
        "print('/tmp/ao-operator-ao-remote-transfer-v2-stress/runs/r-1/events.jsonl'); "
        "print('OPENAI_API_KEY=sk-test'); "
        "print('Authorization: Bearer live-token')"
        "\""
    )
    path = write_manifest(tmp_path, manifest(command))
    monkeypatch.setattr(run_operator_slice, "ROOT", tmp_path)

    result = run_operator_slice.main([str(path), "--slice", "00-local", "--execute", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    report_text = Path(payload["report"]).read_text(encoding="utf-8")
    assert "/home/tester/.codex/auth.json" not in report_text
    assert "/tmp/ao-operator-ao-remote-transfer-v2-stress" not in report_text
    assert "sk-test" not in report_text
    assert "live-token" not in report_text
    assert "[REDACTED_PROVIDER_AUTH_PATH]" in report_text
    assert "[REDACTED_AO_HOME]" in report_text
