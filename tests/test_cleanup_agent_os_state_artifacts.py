from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cleanup_agent_os_state_artifacts


def write_json(path: Path, payload: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {"schema": "debug"}, indent=2) + "\n", encoding="utf-8")


def test_plan_cleanup_only_selects_untracked_agent_os_state_diagnostics(tmp_path):
    candidate = tmp_path / "run-artifacts/live/agent-os-router-v2-state-debug.json"
    ignored_prompt = tmp_path / "run-artifacts/live/agent-os-prompt-debug.json"
    ignored_tracked = tmp_path / "run-artifacts/live/agent-os-state-v2.json"
    write_json(candidate)
    write_json(ignored_prompt)
    write_json(ignored_tracked)

    payload = cleanup_agent_os_state_artifacts.plan_cleanup(
        root=tmp_path,
        git_status_lines=[
            "?? run-artifacts/live/agent-os-router-v2-state-debug.json",
            "?? run-artifacts/live/agent-os-prompt-debug.json",
            " M run-artifacts/live/agent-os-state-v2.json",
        ],
        apply=False,
    )

    assert payload["verdict"] == "PASS"
    assert payload["mode"] == "dry-run"
    assert payload["candidate_count"] == 1
    assert payload["removed_count"] == 0
    assert payload["candidates"] == ["run-artifacts/live/agent-os-router-v2-state-debug.json"]
    assert candidate.exists()


def test_apply_cleanup_removes_only_selected_untracked_state_diagnostics(tmp_path):
    candidate = tmp_path / "run-artifacts/live/agent-os-router-v2-state-debug.json"
    ignored = tmp_path / "run-artifacts/live/agent-os-prompt-debug.json"
    write_json(candidate)
    write_json(ignored)

    payload = cleanup_agent_os_state_artifacts.plan_cleanup(
        root=tmp_path,
        git_status_lines=[
            "?? run-artifacts/live/agent-os-router-v2-state-debug.json",
            "?? run-artifacts/live/agent-os-prompt-debug.json",
        ],
        apply=True,
    )

    assert payload["verdict"] == "PASS"
    assert payload["mode"] == "apply"
    assert payload["candidate_count"] == 1
    assert payload["removed_count"] == 1
    assert not candidate.exists()
    assert ignored.exists()


def test_apply_cleanup_fails_closed_when_candidate_is_missing(tmp_path):
    payload = cleanup_agent_os_state_artifacts.plan_cleanup(
        root=tmp_path,
        git_status_lines=["?? run-artifacts/live/agent-os-router-v2-state-debug.json"],
        apply=True,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["removed_count"] == 0
    assert "candidate missing before cleanup: run-artifacts/live/agent-os-router-v2-state-debug.json" in payload["blockers"]


def test_plan_cleanup_excludes_default_cleanup_report(tmp_path):
    report = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json"
    write_json(report)

    payload = cleanup_agent_os_state_artifacts.plan_cleanup(
        root=tmp_path,
        git_status_lines=["?? run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json"],
        apply=False,
    )

    assert payload["verdict"] == "PASS"
    assert payload["candidate_count"] == 0
    assert payload["candidates"] == []


def test_cli_writes_cleanup_report(tmp_path):
    candidate = tmp_path / "run-artifacts/live/agent-os-router-v2-state-debug.json"
    output = tmp_path / "cleanup.json"
    write_json(candidate)

    code = cleanup_agent_os_state_artifacts.main(
        [
            "--root",
            str(tmp_path),
            "--git-status-line",
            "?? run-artifacts/live/agent-os-router-v2-state-debug.json",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert output.is_file()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-state-stale-cleanup/v1"
    assert saved["candidate_count"] == 1
    assert saved["removed_count"] == 0
