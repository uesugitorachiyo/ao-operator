from __future__ import annotations

import json
from pathlib import Path

import check_next_escalation_profile


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_prep(root: Path, slices: int = 75) -> Path:
    return write_json(
        root / f"run-artifacts/remote-transfer-v2-stress/profile-prep/{slices}-slice-dry-run-prep.json",
        {
            "verdict": "PASS",
            "mode": "dry-run-temp-worktree",
            "slices": slices,
            "tasks": (slices * 2) + 7,
            "accepted_live_evidence_preserved_in_main": True,
            "commands": [{"exit": 0}, {"exit": 0}, {"exit": 0}, {"exit": 0}],
        },
    )


def write_accepted_50_summary(root: Path) -> Path:
    return write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-operator-summary.json",
        {
            "verdict": "PASS",
            "current_state": "ACCEPTED_50_SLICE_LIVE",
            "target_slices": 50,
            "target_tasks": 107,
            "dispatch_authorized": False,
        },
    )


def test_approval_gate_requires_accepted_50_summary_and_override(tmp_path):
    prep = write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)

    payload = check_next_escalation_profile.approval_gate(
        root=tmp_path,
        target_slices=75,
        prep_report=prep,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "PASS"
    assert payload["target_tasks"] == 157
    assert payload["ready_for_operator_approval"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["prior_accepted_profile"]["target_slices"] == 50


def test_approval_gate_fails_without_override_env(tmp_path):
    prep = write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)

    payload = check_next_escalation_profile.approval_gate(
        root=tmp_path,
        target_slices=75,
        prep_report=prep,
        env={},
    )

    assert payload["verdict"] == "FAIL"
    assert any("FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_provider_budget_records_abort_rules_without_authorizing_dispatch(tmp_path):
    prep = write_prep(tmp_path)

    payload = check_next_escalation_profile.provider_budget(
        root=tmp_path,
        target_slices=75,
        prep_report=prep,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "PASS"
    assert payload["target_slices"] == 75
    assert payload["target_tasks"] == 157
    assert payload["dispatch_authorized"] is False
    assert payload["abort_conditions"]


def test_rehearsal_requires_no_live_slice_for_target(tmp_path):
    prep = write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)
    manifest = write_json(
        tmp_path / "operator-slices.json",
        {
            "slices": [
                {"id": "34-prepare-75-slice-dry-run-profile", "live_provider": False},
                {"id": "35-check-75-slice-live-approval-gate", "live_provider": False},
                {"id": "36-record-75-slice-provider-budget", "live_provider": False},
                {"id": "37-rehearse-75-slice-live-sequence", "live_provider": False},
            ]
        },
    )

    payload = check_next_escalation_profile.rehearsal(
        root=tmp_path,
        manifest=manifest,
        target_slices=75,
        prep_report=prep,
    )

    assert payload["verdict"] == "PASS"
    assert payload["live_slice_present"] is False
    assert payload["dispatch_authorized"] is False


def test_summary_reports_ready_without_dispatch(tmp_path):
    prep = write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)

    payload = check_next_escalation_profile.summary(
        root=tmp_path,
        target_slices=75,
        prep_report=prep,
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
    )

    assert payload["verdict"] == "PASS"
    assert payload["current_state"] == "READY_FOR_EXPLICIT_APPROVAL_NOT_DISPATCH"
    assert payload["dispatch_authorized"] is False
    assert "separate live slice" in payload["next_safe_command"]


def test_summary_uses_committed_gate_reports_without_override_env(tmp_path):
    write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)
    write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-approval-gate.json",
        {
            "schema": "ao-operator/next-escalation-approval-gate/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-provider-budget.json",
        {
            "schema": "ao-operator/next-escalation-provider-budget/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )

    payload = check_next_escalation_profile.summary(
        root=tmp_path,
        target_slices=75,
        prep_report=tmp_path / "run-artifacts/remote-transfer-v2-stress/profile-prep/75-slice-dry-run-prep.json",
        env=None,
    )

    assert payload["verdict"] == "PASS"
    assert payload["current_state"] == "READY_FOR_EXPLICIT_APPROVAL_NOT_DISPATCH"
    assert payload["dispatch_authorized"] is False


def test_cli_write_output_without_path_uses_default_report(tmp_path, monkeypatch, capsys):
    write_prep(tmp_path)
    write_accepted_50_summary(tmp_path)
    monkeypatch.setenv("FACTORY_V3_ALLOW_LARGE_LIVE_RUN", "1")

    code = check_next_escalation_profile.main(
        [
            "--root",
            str(tmp_path),
            "--target-slices",
            "75",
            "--check",
            "approval-gate",
            "--write-output",
            "--json",
        ]
    )

    output = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/75-slice-next-escalation-approval-gate.json"
    assert code == 0
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
