from __future__ import annotations

import json
from pathlib import Path

import check_50_slice_provider_budget
import route_50_slice_live_postrun
import run_50_slice_live


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def prep_report(path: Path) -> Path:
    return write_json(
        path,
        {
            "verdict": "PASS",
            "mode": "dry-run-temp-worktree",
            "slices": 50,
            "tasks": 107,
            "accepted_live_evidence_preserved_in_main": True,
            "commands": [{"exit": 0}, {"exit": 0}, {"exit": 0}, {"exit": 0}],
        },
    )


def test_provider_budget_passes_with_override_env(tmp_path):
    report = prep_report(tmp_path / "prep.json")

    payload = check_50_slice_provider_budget.check_budget(
        root=tmp_path,
        prep_report=report,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "PASS"
    assert payload["target_tasks"] == 107
    assert payload["dispatch_authorized"] is False


def test_provider_budget_fails_without_override_env(tmp_path):
    report = prep_report(tmp_path / "prep.json")

    payload = check_50_slice_provider_budget.check_budget(root=tmp_path, prep_report=report, env={})

    assert payload["verdict"] == "FAIL"
    assert any("FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1" in error for error in payload["errors"])


def test_live_launcher_requires_explicit_approval_file(tmp_path):
    prep_report(tmp_path / "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json")
    evaluation = tmp_path / "docs/evaluations/remote-transfer-v2-stress-live-evaluation.md"
    evaluation.parent.mkdir(parents=True)
    evaluation.write_text("Verdict: ACCEPTED\nAO Run: r-live-25\nBlockers:\n- none\n", encoding="utf-8")
    status = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-status.md"
    status.parent.mkdir(parents=True)
    status.write_text("Mode: run\n", encoding="utf-8")
    events = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-ao-events.md"
    events.write_text("AO completed=true\n", encoding="utf-8")

    payload = run_50_slice_live.report(
        root=tmp_path,
        approval_file=tmp_path / "approval.json",
        execute=False,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["dispatch_authorized"] is False
    assert any("approval file unavailable" in error for error in payload["errors"])


def test_postrun_route_waits_when_current_contract_is_still_25_slice(tmp_path):
    contract = write_json(tmp_path / "contract.json", {"slices": [{} for _ in range(25)]})

    payload = route_50_slice_live_postrun.route(root=tmp_path, contract=contract)

    assert payload["verdict"] == "PASS"
    assert payload["current_live_contract_slices"] == 25
    assert payload["route"] == "WAIT_FOR_50_SLICE_LIVE_RUN"
    assert payload["next_slice"] == "31-run-50-slice-live"
    assert payload["commit_success_evidence_allowed"] is False
