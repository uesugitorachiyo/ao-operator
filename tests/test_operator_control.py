from __future__ import annotations

import json
from pathlib import Path

import operator_control


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_ready_bundle(root: Path) -> None:
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
        "Verdict: ACCEPTED\nAO Run: r-live-50\nAO command exit=0\nAO completed=true\nBlockers:\n- none\n",
    )
    write_text(
        root / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-status.md",
        "Mode: run\nAO Run: r-live-50\n",
    )
    write_text(
        root / "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-v2-stress-live-ao-events.md",
        "AO command exit=0\nAO completed=true\n",
    )


def read_audit(root: Path) -> list[dict[str, object]]:
    audit = root / "run-artifacts/remote-transfer-v2-stress-live/operator-controls/operator-audit.jsonl"
    return [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]


def test_status_reports_next_safe_command_without_dispatch(tmp_path):
    write_ready_bundle(tmp_path)

    payload = operator_control.status(root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert payload["action"] == "status"
    assert payload["dispatch_authorized"] is False
    assert "next_safe_command" in payload
    assert "No live command is safe yet" in payload["next_safe_command"]


def test_submit_observe_and_cancel_write_audit_without_dispatch(tmp_path):
    write_ready_bundle(tmp_path)

    submit = operator_control.submit(root=tmp_path, source="chat", intent="operator smoke")
    observe = operator_control.observe(root=tmp_path)
    cancel = operator_control.cancel(root=tmp_path, target_run="r-test", reason="operator requested stop")

    assert submit["dispatch_authorized"] is False
    assert observe["dispatch_authorized"] is False
    assert cancel["dispatch_authorized"] is False
    assert [item["action"] for item in read_audit(tmp_path)] == ["submit", "observe", "cancel"]


def test_approval_refuses_large_live_without_override_env(tmp_path):
    write_ready_bundle(tmp_path)

    payload = operator_control.approval(
        root=tmp_path,
        approved_by="operator",
        approval_source="test",
        env={},
        write_approval_file=True,
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["dispatch_authorized"] is False
    assert payload["approval_file_written"] is False
    assert not (tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json").exists()


def test_approval_writes_file_with_explicit_override_and_keeps_audit(tmp_path):
    write_ready_bundle(tmp_path)

    payload = operator_control.approval(
        root=tmp_path,
        approved_by="operator",
        approval_source="test",
        env={"FACTORY_V3_ALLOW_LARGE_LIVE_RUN": "1"},
        write_approval_file=True,
    )

    approval_file = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json"
    written = json.loads(approval_file.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["approval_file_written"] is True
    assert payload["dispatch_authorized"] is True
    assert "--slice 31-run-50-slice-live" in payload["next_safe_command"]
    assert written["approved"] is True
    assert read_audit(tmp_path)[0]["action"] == "approval"
