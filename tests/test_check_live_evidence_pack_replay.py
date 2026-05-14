from __future__ import annotations

import json
from pathlib import Path

import check_live_evidence_pack_replay as gate


def _summary(
    root: Path,
    slug: str,
    run_id: str,
    replay_verdict: str | None,
    *,
    deterministic_task_count: int = 0,
    deterministic_command_execution: str = "SKIPPED",
) -> Path:
    target = root / "run-artifacts" / slug / "evidence-packs" / f"evidence-pack-{run_id}-summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {
        "schema": "ao-operator/evidence-pack-live-run/v1",
        "run_id": run_id,
        "verify": {"verdict": "PASS"},
        "verdict": "PASS",
    }
    if replay_verdict is not None:
        body["replay"] = {
            "verdict": replay_verdict,
            "deterministic_task_count": deterministic_task_count,
            "checks": {"deterministic_command_execution": deterministic_command_execution},
        }
    target.write_text(json.dumps(body), encoding="utf-8")
    return target


def test_check_live_evidence_pack_replay_passes_when_no_summaries(tmp_path):
    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["schema"] == "ao-operator/live-evidence-pack-replay-gate/v1"
    assert report["verdict"] == "PASS"
    assert report["summary_count"] == 0
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False


def test_check_live_evidence_pack_replay_accepts_pass_replay_summary(tmp_path):
    _summary(tmp_path, "demo", "feedfacecafebeef", "PASS")

    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["verdict"] == "PASS"
    assert report["summary_count"] == 1
    assert report["summaries"][0]["replay_verdict"] == "PASS"


def test_check_live_evidence_pack_replay_accepts_executed_deterministic_summary(tmp_path):
    _summary(
        tmp_path,
        "demo",
        "feedfacecafebeef",
        "PASS",
        deterministic_task_count=1,
        deterministic_command_execution="PASS",
    )

    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["verdict"] == "PASS"
    assert report["summaries"][0]["deterministic_task_count"] == 1
    assert report["summaries"][0]["deterministic_command_execution"] == "PASS"


def test_check_live_evidence_pack_replay_rejects_missing_replay_verdict(tmp_path):
    path = _summary(tmp_path, "demo", "feedfacecafebeef", None)

    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["verdict"] == "FAIL"
    assert f"missing_replay_verdict:{path.relative_to(tmp_path).as_posix()}" in report["errors"]


def test_check_live_evidence_pack_replay_rejects_failed_replay_verdict(tmp_path):
    path = _summary(tmp_path, "demo", "feedfacecafebeef", "FAIL")

    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["verdict"] == "FAIL"
    assert f"replay_verdict_not_pass:{path.relative_to(tmp_path).as_posix()}:FAIL" in report["errors"]


def test_check_live_evidence_pack_replay_requires_deterministic_execution_for_deterministic_tasks(tmp_path):
    path = _summary(
        tmp_path,
        "demo",
        "feedfacecafebeef",
        "PASS",
        deterministic_task_count=1,
        deterministic_command_execution="SKIPPED",
    )

    report = gate.check_live_evidence_pack_replay(tmp_path)

    assert report["verdict"] == "FAIL"
    assert (
        f"deterministic_command_execution_not_pass:{path.relative_to(tmp_path).as_posix()}:SKIPPED"
        in report["errors"]
    )


def test_check_live_evidence_pack_replay_cli_writes_output(tmp_path, capsys):
    output = tmp_path / "run-artifacts/live-evidence-pack-replay-gate.json"

    code = gate.main(["--root", str(tmp_path), "--write-output", str(output), "--json"])

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/live-evidence-pack-replay-gate/v1"
    assert saved["verdict"] == "PASS"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
