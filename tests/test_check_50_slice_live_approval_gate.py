from __future__ import annotations

import json
from pathlib import Path

import check_50_slice_live_approval_gate


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_bundle(tmp_path: Path) -> dict[str, Path]:
    prep = write_json(
        tmp_path / "prep.json",
        {
            "schema": "ao-operator/live-profile-dry-run-prep/v1",
            "verdict": "PASS",
            "mode": "dry-run-temp-worktree",
            "slices": 50,
            "tasks": 107,
            "accepted_live_evidence_preserved_in_main": True,
            "commands": [
                {"command": "generate", "exit": 0},
                {"command": "dry-run", "exit": 0},
                {"command": "intake", "exit": 0},
                {"command": "factory", "exit": 0},
            ],
        },
    )
    evaluation = tmp_path / "evaluation.md"
    evaluation.write_text(
        "\n".join(["Verdict: ACCEPTED", "AO Run: r-live-25", "Blockers:", "- none"]),
        encoding="utf-8",
    )
    status = tmp_path / "status.md"
    status.write_text("Mode: run\n", encoding="utf-8")
    events = tmp_path / "events.md"
    events.write_text("AO completed=true\n", encoding="utf-8")
    return {"prep": prep, "evaluation": evaluation, "status": status, "events": events}


def call_gate(tmp_path: Path, paths: dict[str, Path], *, env: dict[str, str] | None = None):
    return check_50_slice_live_approval_gate.check_gate(
        root=tmp_path,
        prep_report=paths["prep"],
        acceptance_evaluation=paths["evaluation"],
        acceptance_status=paths["status"],
        acceptance_events=paths["events"],
        success_guard=paths.get("success_guard", tmp_path / "missing-success-guard.json"),
        env=env if env is not None else {"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )


def test_gate_passes_with_env_and_provider_limit_evidence(tmp_path):
    payload = call_gate(tmp_path, write_bundle(tmp_path))

    assert payload["verdict"] == "PASS"
    assert payload["ready_for_operator_approval"] is True
    assert payload["operator_approval_required"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["target_tasks"] == 107


def test_gate_refuses_without_override_env(tmp_path):
    payload = call_gate(tmp_path, write_bundle(tmp_path), env={})

    assert payload["verdict"] == "FAIL"
    assert payload["ready_for_operator_approval"] is False
    assert any("FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1" in error for error in payload["errors"])


def test_gate_refuses_failed_prep_report(tmp_path):
    paths = write_bundle(tmp_path)
    prep = json.loads(paths["prep"].read_text(encoding="utf-8"))
    prep["verdict"] = "FAIL"
    paths["prep"].write_text(json.dumps(prep), encoding="utf-8")

    payload = call_gate(tmp_path, paths)

    assert payload["verdict"] == "FAIL"
    assert any("prep.verdict" in error for error in payload["errors"])


def test_gate_accepts_preserved_success_guard_after_current_diagnostic(tmp_path):
    paths = write_bundle(tmp_path)
    paths["evaluation"].write_text("Verdict: REJECTED\nAO Run: r-live-50\nBlockers:\n- reviewer rejected\n", encoding="utf-8")
    paths["success_guard"] = write_json(
        tmp_path / "success-guard.json",
        {
            "verdict": "PASS",
            "acceptance_verdict": "PASS",
            "classification": "ACCEPTED",
            "commit_success_evidence_allowed": True,
        },
    )

    payload = call_gate(tmp_path, paths)

    assert payload["verdict"] == "PASS"
    assert payload["ready_for_operator_approval"] is True
    assert payload["prior_accepted_live_evidence"]["success_guard"] == "success-guard.json"


def test_main_writes_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("FACTORY_V3_ALLOW_LARGE_LIVE_RUN", "1")
    paths = write_bundle(tmp_path)
    output = tmp_path / "gate.json"

    result = check_50_slice_live_approval_gate.main(
        [
            "--root",
            str(tmp_path),
            "--prep-report",
            str(paths["prep"]),
            "--acceptance-evaluation",
            str(paths["evaluation"]),
            "--acceptance-status",
            str(paths["status"]),
            "--acceptance-events",
            str(paths["events"]),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/50-slice-live-approval-gate/v1"
