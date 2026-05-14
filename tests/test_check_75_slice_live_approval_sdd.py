from __future__ import annotations

import json
from pathlib import Path

import check_75_slice_live_approval_sdd


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_prerequisites(root: Path) -> None:
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress/profile-prep/75-slice-dry-run-prep.json",
        {
            "verdict": "PASS",
            "mode": "dry-run-temp-worktree",
            "slices": 75,
            "tasks": 157,
            "accepted_live_evidence_preserved_in_main": True,
            "commands": [{"exit": 0}, {"exit": 0}, {"exit": 0}, {"exit": 0}],
        },
    )
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json",
        {
            "verdict": "PASS",
            "current_state": "ACCEPTED_50_SLICE_LIVE",
            "target_slices": 50,
            "target_tasks": 107,
            "dispatch_authorized": False,
        },
    )
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-approval-gate.json",
        {
            "verdict": "PASS",
            "ready_for_operator_approval": True,
            "operator_approval_required": True,
            "target_slices": 75,
            "target_tasks": 157,
            "dispatch_authorized": False,
        },
    )
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-provider-budget.json",
        {
            "verdict": "PASS",
            "target_slices": 75,
            "target_tasks": 157,
            "dispatch_authorized": False,
            "abort_conditions": ["Provider returns sustained 429."],
        },
    )
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-rehearsal.json",
        {
            "verdict": "PASS",
            "target_slices": 75,
            "target_tasks": 157,
            "live_slice_present": False,
            "dispatch_authorized": False,
        },
    )
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-summary.json",
        {
            "verdict": "PASS",
            "current_state": "READY_FOR_EXPLICIT_APPROVAL_NOT_DISPATCH",
            "target_slices": 75,
            "target_tasks": 157,
            "dispatch_authorized": False,
        },
    )
    write_json(
        root / "examples/remote-transfer-v2-stress/operator-slices.json",
        {
            "slices": [
                {"order": 34, "id": "34-prepare-75-slice-dry-run-profile", "live_provider": False},
                {"order": 35, "id": "35-check-75-slice-live-approval-gate", "live_provider": False},
                {"order": 36, "id": "36-record-75-slice-provider-budget", "live_provider": False},
                {"order": 37, "id": "37-rehearse-75-slice-live-sequence", "live_provider": False},
                {"order": 38, "id": "38-record-75-slice-live-approval-sdd", "live_provider": False},
            ]
        },
    )


def test_approval_sdd_passes_when_75_slice_lane_is_ready_but_not_approved(tmp_path):
    write_prerequisites(tmp_path)

    payload = check_75_slice_live_approval_sdd.build_report(
        root=tmp_path,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "PASS"
    assert payload["current_state"] == "READY_FOR_OPERATOR_APPROVAL_NOT_DISPATCH"
    assert payload["target_tasks"] == 157
    assert payload["approval_file_present"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["required_operator_actions"][0].startswith("Review 75-slice")


def test_approval_sdd_fails_if_live_slice_already_exists(tmp_path):
    write_prerequisites(tmp_path)
    manifest_path = tmp_path / "examples/remote-transfer-v2-stress/operator-slices.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["slices"].append(
        {"order": 39, "id": "39-run-75-slice-live", "live_provider": True, "task_count": 157}
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = check_75_slice_live_approval_sdd.build_report(
        root=tmp_path,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "FAIL"
    assert any("75-slice live slice already exists" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_approval_sdd_fails_without_large_live_override_env(tmp_path):
    write_prerequisites(tmp_path)

    payload = check_75_slice_live_approval_sdd.build_report(root=tmp_path, env={})

    assert payload["verdict"] == "FAIL"
    assert any("FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_cli_write_output_uses_default_report(tmp_path, monkeypatch, capsys):
    write_prerequisites(tmp_path)
    monkeypatch.setenv("FACTORY_V3_ALLOW_LARGE_LIVE_RUN", "1")

    code = check_75_slice_live_approval_sdd.main(["--root", str(tmp_path), "--write-output", "--json"])

    output = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-live-approval-sdd.json"
    assert code == 0
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
