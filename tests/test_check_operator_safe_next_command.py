from __future__ import annotations

import json
from pathlib import Path

import check_operator_safe_next_command


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def seed_safe_reports(root: Path) -> Path:
    base = root / "run-artifacts/remote-transfer-v2-stress-live"
    write_json(
        base / "dispatch/50-slice-operator-summary.json",
        {
            "schema": "ao-operator/50-slice-operator-summary/v1",
            "verdict": "PASS",
            "current_state": "ACCEPTED_50_SLICE_LIVE",
            "approval_status": "APPROVED",
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "50-slice live is accepted; start a new gated escalation lane before any larger live run.",
            "evidence_paths": {
                "postrun_route": "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-postrun-route.json"
            },
            "blockers": [],
        },
    )
    write_json(
        base / "operator-guardrail-summary.json",
        {
            "schema": "ao-operator/operator-guardrail-summary/v1",
            "verdict": "PASS",
            "ship_ready": True,
            "approval_state": "ABSENT",
            "approval_usable": False,
            "positive_approval_path": "PLAN_WITHOUT_DISPATCH",
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "All operator guardrails pass; keep Agent OS execution blocked without explicit approval.",
            "guardrails": {
                "release_readiness": {
                    "path": "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json",
                    "verdict": "PASS",
                    "ship_ready": True,
                }
            },
            "blockers": [],
        },
    )
    write_json(
        base / "release-readiness-gate.json",
        {
            "schema": "ao-operator/release-readiness-gate/v1",
            "verdict": "PASS",
            "ship_ready": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "Repository is release-ready; start the next gated SDD lane.",
            "blockers": [],
        },
    )
    write_json(
        base / "release-artifact-index.json",
        {
            "schema": "ao-operator/release-artifact-index/v1",
            "verdict": "PASS",
            "artifact_count": 64,
            "sdd_count": 65,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "Release artifact index is complete; continue with the next gated SDD lane.",
            "blockers": [],
        },
    )
    return base


def test_safe_next_command_reports_current_state_and_evidence_without_dispatch(tmp_path):
    seed_safe_reports(tmp_path)

    payload = check_operator_safe_next_command.summarize(root=tmp_path)

    assert payload["schema"] == "ao-operator/operator-safe-next-command/v1"
    assert payload["verdict"] == "PASS"
    assert payload["safe_action"] == "START_NEXT_GATED_SDD_LANE"
    assert payload["current_state"] == "ACCEPTED_50_SLICE_LIVE"
    assert payload["approval_state"] == "ABSENT"
    assert payload["ship_ready"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["next_safe_command"] == "Start the next gated SDD lane; keep Agent OS execution blocked until explicit approval."
    assert payload["recommended_commands"] == [
        "python3 scripts/operator_control.py status --json",
        "python3 scripts/check_operator_safe_next_command.py --json",
    ]
    assert "operator_guardrail_summary" in payload["evidence_paths"]


def test_safe_next_command_blocks_dispatching_or_live_source(tmp_path):
    base = seed_safe_reports(tmp_path)
    report = base / "operator-guardrail-summary.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    data["live_providers_run"] = True
    write_json(report, data)

    payload = check_operator_safe_next_command.summarize(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert payload["safe_action"] == "BLOCKED"
    assert "operator_guardrail_summary live_providers_run must remain false" in payload["errors"]
    assert payload["recommended_commands"] == []


def test_safe_next_command_cli_writes_report(tmp_path, capsys):
    seed_safe_reports(tmp_path)
    output = tmp_path / "run-artifacts/safe-next.json"

    code = check_operator_safe_next_command.main(["--root", str(tmp_path), "--write-output", str(output), "--json"])

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/operator-safe-next-command/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
