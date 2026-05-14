from __future__ import annotations

import json
from pathlib import Path

import check_evidence_pack_replay_proof_status


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def live_summary(
    *,
    run_id: str = "run-demo",
    deterministic_task_count: int = 1,
    deterministic_command_execution: str | None = "PASS",
    replay_verdict: str = "PASS",
) -> dict[str, object]:
    checks: dict[str, object] = {}
    if deterministic_command_execution is not None:
        checks["deterministic_command_execution"] = deterministic_command_execution
    return {
        "schema": "ao-operator/evidence-pack-live-run/v1",
        "run_id": run_id,
        "verify": {"verdict": "PASS"},
        "replay": {
            "verdict": replay_verdict,
            "deterministic_task_count": deterministic_task_count,
            "checks": checks,
        },
    }


def test_replay_proof_status_passes_with_executed_deterministic_live_summary(tmp_path):
    summary = tmp_path / "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json"
    write_json(summary, live_summary())

    report = check_evidence_pack_replay_proof_status.build_status(root=tmp_path)

    assert report["schema"] == "ao-operator/evidence-pack-replay-proof-status/v1"
    assert report["verdict"] == "PASS"
    assert report["proof_ready"] is True
    assert report["summary_count"] == 1
    assert report["deterministic_summary_count"] == 1
    assert report["executed_deterministic_summary_count"] == 1
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False
    assert report["summaries"] == [
        {
            "path": "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json",
            "run_id": "run-demo",
            "verify_verdict": "PASS",
            "replay_verdict": "PASS",
            "deterministic_task_count": 1,
            "deterministic_command_execution": "PASS",
            "verdict": "PASS",
        }
    ]


def test_replay_proof_status_fails_without_executed_deterministic_summary(tmp_path):
    summary = tmp_path / "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json"
    write_json(summary, live_summary(deterministic_task_count=0, deterministic_command_execution=None))

    report = check_evidence_pack_replay_proof_status.build_status(root=tmp_path)

    assert report["verdict"] == "FAIL"
    assert report["proof_ready"] is False
    assert report["deterministic_summary_count"] == 0
    assert "no_executed_deterministic_live_evidence_pack_summary" in report["errors"]


def test_replay_proof_status_fails_when_deterministic_command_execution_is_not_pass(tmp_path):
    summary = tmp_path / "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json"
    write_json(summary, live_summary(deterministic_command_execution="FAIL"))

    report = check_evidence_pack_replay_proof_status.build_status(root=tmp_path)

    assert report["verdict"] == "FAIL"
    assert report["proof_ready"] is False
    assert report["executed_deterministic_summary_count"] == 0
    assert report["errors"] == [
        "deterministic_command_execution_not_pass:"
        "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json:FAIL",
        "no_executed_deterministic_live_evidence_pack_summary",
    ]


def test_cli_writes_replay_proof_status(tmp_path, capsys):
    summary = tmp_path / "run-artifacts/demo/evidence-packs/evidence-pack-run-demo-summary.json"
    output = tmp_path / "run-artifacts/demo/evidence-pack-replay-proof-status.json"
    write_json(summary, live_summary())

    code = check_evidence_pack_replay_proof_status.main(
        ["--root", str(tmp_path), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/evidence-pack-replay-proof-status/v1"
    assert saved["verdict"] == "PASS"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
