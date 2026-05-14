from __future__ import annotations

import json
from pathlib import Path

import summarize_50_slice_operator_state


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_summary_bundle(root: Path) -> None:
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json",
        {"verdict": "PASS"},
    )
    for rel in [
        "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-provider-budget.json",
        "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval-gate.json",
        "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-rehearsal.json",
    ]:
        write_json(root / rel, {"verdict": "PASS"})
    write_json(
        root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-postrun-route.json",
        {"verdict": "PASS", "route": "WAIT_FOR_50_SLICE_LIVE_RUN", "next_slice": "31-run-50-slice-live"},
    )
    write_text(
        root / "docs/evaluations/remote-transfer-v2-stress-live-evaluation.md",
        "Verdict: ACCEPTED\nAO Run: r-live-25\nAO command exit=0\nAO completed=true\nBlockers:\n- none\n",
    )
    write_text(
        root / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-status.md",
        "Mode: run\nAO Run: r-live-25\n",
    )
    write_text(
        root / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-ao-events.md",
        "AO command exit=0\nAO completed=true\n",
    )


def test_summary_ready_for_approval_but_not_dispatch(tmp_path):
    write_summary_bundle(tmp_path)

    payload = summarize_50_slice_operator_state.summarize(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["current_state"] == "READY_FOR_APPROVAL_NOT_DISPATCH"
    assert payload["approval_status"] == "NEEDS_EXPLICIT_APPROVAL"
    assert payload["dispatch_authorized"] is False
    assert "No live command is safe yet" in payload["next_safe_command"]


def test_summary_allows_dispatch_only_with_valid_approval_file(tmp_path):
    write_summary_bundle(tmp_path)
    write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json",
        {
            "approved": True,
            "target_slices": 50,
            "target_tasks": 107,
            "approval_env": "FACTORY_V3_ALLOW_LARGE_LIVE_RUN",
            "approved_by": "operator",
        },
    )

    payload = summarize_50_slice_operator_state.summarize(root=tmp_path)

    assert payload["current_state"] == "READY_FOR_50_SLICE_LIVE"
    assert payload["approval_status"] == "APPROVED"
    assert payload["dispatch_authorized"] is True
    assert "--slice 31-run-50-slice-live" in payload["next_safe_command"]


def test_summary_recognizes_accepted_50_slice_postrun_route(tmp_path):
    write_summary_bundle(tmp_path)
    write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json",
        {
            "approved": True,
            "target_slices": 50,
            "target_tasks": 107,
            "approval_env": "FACTORY_V3_ALLOW_LARGE_LIVE_RUN",
            "approved_by": "operator",
        },
    )
    write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-postrun-route.json",
        {
            "verdict": "PASS",
            "route": "RUN_50_SLICE_ACCEPTANCE",
            "next_slice": "24-check-live-acceptance",
            "commit_success_evidence_allowed": True,
            "acceptance_verdict": "PASS",
        },
    )

    payload = summarize_50_slice_operator_state.summarize(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["current_state"] == "ACCEPTED_50_SLICE_LIVE"
    assert payload["dispatch_authorized"] is False
    assert "new gated escalation lane" in payload["next_safe_command"]
