from __future__ import annotations

import json
from pathlib import Path

import check_resource_performance_gate


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_reports(root: Path) -> tuple[Path, Path, Path]:
    prep = root / "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json"
    budget = root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json"
    summary = root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json"
    write_json(
        prep,
        {
            "schema": "ao-operator/live-profile-dry-run-prep/v1",
            "verdict": "PASS",
            "slices": 50,
            "tasks": 107,
            "commands": [
                {"exit": 0, "duration_seconds": 0.1},
                {"exit": 0, "duration_seconds": 0.2},
                {"exit": 0, "duration_seconds": 0.3},
                {"exit": 0, "duration_seconds": 0.4},
            ],
        },
    )
    write_json(
        budget,
        {
            "schema": "ao-operator/50-slice-provider-budget/v1",
            "verdict": "PASS",
            "target_slices": 50,
            "target_tasks": 107,
            "recommended_timeout_seconds": 3600,
            "abort_conditions": [
                "Provider returns sustained 429 or authentication failures.",
                "AO events stop advancing for 10 minutes.",
                "Role artifact generation omits load-bearing factory or reviewer outputs.",
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        summary,
        {
            "schema": "ao-operator/50-slice-operator-summary/v1",
            "verdict": "PASS",
            "current_state": "ACCEPTED_50_SLICE_LIVE",
            "target_slices": 50,
            "target_tasks": 107,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    return prep, budget, summary


def test_resource_performance_gate_passes_with_budget_and_cleanup_posture(tmp_path):
    seed_reports(tmp_path)
    worktree = tmp_path / "tmp/worktrees"
    ao_home = tmp_path / "tmp/ao-home"

    payload = check_resource_performance_gate.summarize(
        root=tmp_path,
        worktree_path=worktree,
        ao_home_path=ao_home,
    )

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["checks"]["dry_run_wallclock"]["verdict"] == "PASS"
    assert payload["checks"]["provider_budget"]["verdict"] == "PASS"
    assert payload["checks"]["temp_footprint"]["verdict"] == "PASS"
    assert payload["next_safe_command"] == "Resource and performance guardrails pass for the accepted 50-slice baseline."


def test_resource_performance_gate_blocks_slow_dry_run(tmp_path):
    prep, _budget, _summary = seed_reports(tmp_path)
    data = json.loads(prep.read_text(encoding="utf-8"))
    data["commands"][0]["duration_seconds"] = 999
    write_json(prep, data)

    payload = check_resource_performance_gate.summarize(root=tmp_path, max_dry_run_seconds=30)

    assert payload["verdict"] == "FAIL"
    assert "dry_run_wallclock" in payload["blockers"]


def test_resource_performance_gate_measures_existing_temp_footprint(tmp_path):
    seed_reports(tmp_path)
    worktree = tmp_path / "tmp/worktrees"
    ao_home = tmp_path / "tmp/ao-home"
    worktree.mkdir(parents=True)
    ao_home.mkdir(parents=True)
    (worktree / "data.bin").write_bytes(b"x" * 1024)
    (ao_home / "data.bin").write_bytes(b"x" * 1024)

    payload = check_resource_performance_gate.summarize(
        root=tmp_path,
        worktree_path=worktree,
        ao_home_path=ao_home,
        max_worktree_bytes=2048,
        max_ao_home_bytes=2048,
    )

    assert payload["verdict"] == "PASS"
    assert payload["checks"]["temp_footprint"]["worktree_bytes"] >= 1024
    assert payload["checks"]["temp_footprint"]["ao_home_bytes"] >= 1024


def test_cli_writes_resource_performance_report(tmp_path, capsys):
    seed_reports(tmp_path)
    output = tmp_path / "run-artifacts/resource.json"
    worktree = tmp_path / "tmp/worktrees"
    ao_home = tmp_path / "tmp/ao-home"

    code = check_resource_performance_gate.main(
        [
            "--root",
            str(tmp_path),
            "--worktree-path",
            str(worktree),
            "--ao-home-path",
            str(ao_home),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/resource-performance-gate/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
