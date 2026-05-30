from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_queue_failure_recovery_ownership.py"

SUBMIT_SCHEMA = "ao2.ao-operator-compat-workbench-queue-submit.v1"
TRANSITION_SCHEMA = "ao2.ao-operator-compat-workbench-queue-transition.v1"
OUTPUT_SCHEMA = "ao-operator/ao2-queue-failure-recovery-ownership/v1"


def entry_fixture(
    *,
    run_id: str = "factory-compat-20260524",
    status: str = "queued",
    attempts: int = 0,
    transition_history: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "ao2.ao-operator-compat-workbench-queue-entry.v1",
        "run_id": run_id,
        "status": status,
        "attempts": attempts,
        "created_at": "2026-05-24T22:00:00Z",
        "updated_at": "2026-05-24T22:00:00Z",
        "plan_path": "/tmp/plan.json",
        "plan_sha256": "ab" * 32,
        "workflow_path": "/tmp/workflow.json",
        "classification": {"shape": "small", "size": "single_file"},
        "parity_checklist_progress": {
            "ao2_persists_queue_history_cancel_retry_state": True,
            "factory_v3_drives_workflow": False,
            "ao2_queue_owner": "ao2-workbench-queue",
        },
        "execution_contract": {
            "execution_owner": "ao2",
            "factory_v3_role": "parity_oracle_only",
            "control_plane_role": "read_only_observer_after_signed_evidence",
            "provider_auth": "local OAuth CLI only; API-key provider auth forbidden",
        },
        "transition_history": transition_history
        or [
            {
                "at": "2026-05-24T22:00:00Z",
                "status": "queued",
                "reason": "submitted ao-operator-compatible governed plan to AO2-native persisted queue",
            }
        ],
    }


def submit_fixture(*, run_id: str = "factory-compat-20260524") -> dict:
    return {
        "schema_version": SUBMIT_SCHEMA,
        "status": "queued",
        "run_id": run_id,
        "queue_path": "/tmp/.ao2/factory-queue.json",
        "entry": entry_fixture(run_id=run_id),
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
    }


def transition_fixture(
    *,
    run_id: str = "factory-compat-20260524",
    new_status: str = "cancelled",
    previous_status: str = "queued",
    attempts: int = 0,
    reason: str = "operator cancelled run via ao2 factory queue-cancel",
    at: str = "2026-05-24T22:05:00Z",
) -> dict:
    history = [
        {
            "at": "2026-05-24T22:00:00Z",
            "status": "queued",
            "reason": "submitted ao-operator-compatible governed plan to AO2-native persisted queue",
        },
        {
            "at": at,
            "from": previous_status,
            "status": new_status,
            "reason": reason,
        },
    ]
    entry = entry_fixture(
        run_id=run_id,
        status=new_status,
        attempts=attempts,
        transition_history=history,
    )
    return {
        "schema_version": TRANSITION_SCHEMA,
        "status": new_status,
        "run_id": run_id,
        "queue_path": "/tmp/.ao2/factory-queue.json",
        "entry": entry,
        "continuity_contract": {
            "ao2_persists_queue_history_cancel_retry_state": True,
        },
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
    }


def run_coordinator(
    tmp_path: Path,
    submit: dict,
    *,
    transitions: list[dict] | None = None,
    local_retry: dict | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    submit_path = tmp_path / "submit.json"
    submit_path.write_text(json.dumps(submit), encoding="utf-8")
    args = [
        sys.executable,
        str(SCRIPT),
        "--submit",
        str(submit_path),
        "--write-json",
        str(tmp_path / "ownership.json"),
        "--write-md",
        str(tmp_path / "ownership.md"),
        "--json",
    ]
    for i, transition in enumerate(transitions or []):
        t_path = tmp_path / f"transition-{i}.json"
        t_path.write_text(json.dumps(transition), encoding="utf-8")
        args.extend(["--transition", str(t_path)])
    if local_retry is not None:
        lr_path = tmp_path / "local-retry.json"
        lr_path.write_text(json.dumps(local_retry), encoding="utf-8")
        args.extend(["--local-retry-decision", str(lr_path)])
    result = subprocess.run(
        args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    payload = json.loads(result.stdout)
    return payload, result


def test_accepts_submit_alone(tmp_path: Path) -> None:
    payload, _ = run_coordinator(tmp_path, submit_fixture())
    assert payload is not None
    assert payload["schema"] == OUTPUT_SCHEMA
    assert payload["status"] == "accepted"
    assert payload["decision"] == "accept_ao2_owns_retry_cancel_lifecycle"
    assert payload["run_id"] == "factory-compat-20260524"
    assert payload["current_status"] == "queued"
    assert payload["attempts"] == 0
    assert payload["blockers"] == []
    assert len(payload["transition_chain"]) == 1
    assert payload["transition_chain"][0]["status"] == "queued"
    assert payload["ao2_ownership"]["execution_owner"] == "ao2"
    assert payload["ao2_ownership"]["queue_owner"] == "ao2-workbench-queue"
    assert payload["ao2_ownership"]["retry_cancel_owner"] == "ao2-workbench-queue"
    assert payload["ao2_ownership"]["factory_v3_role"] == "parity_oracle_only"
    assert payload["trust_boundary"]["failure_lifecycle_owner"] == "ao2_factory_queue"
    assert payload["trust_boundary"]["factory_v3_role"] == "defers_to_ao2_queue"
    assert payload["trust_boundary"]["control_plane_role"] == "read_only_observer"
    assert payload["trust_boundary"]["control_plane_approves_release"] is False
    assert payload["trust_boundary"]["mutates_ao_artifacts"] is False


def test_accepts_submit_plus_cancel_transition(tmp_path: Path) -> None:
    payload, _ = run_coordinator(
        tmp_path,
        submit_fixture(),
        transitions=[transition_fixture(new_status="cancelled")],
    )
    assert payload is not None
    assert payload["status"] == "accepted"
    assert payload["current_status"] == "cancelled"
    assert len(payload["transition_chain"]) == 2
    assert payload["transition_chain"][-1]["status"] == "cancelled"
    assert "operator cancelled" in payload["transition_chain"][-1]["reason"]


def test_accepts_submit_plus_retry_transition_increments_attempts(tmp_path: Path) -> None:
    payload, _ = run_coordinator(
        tmp_path,
        submit_fixture(),
        transitions=[
            transition_fixture(
                new_status="queued",
                previous_status="failed",
                attempts=1,
                reason="operator retried run via ao2 factory queue-retry",
                at="2026-05-24T22:10:00Z",
            )
        ],
    )
    assert payload is not None
    assert payload["status"] == "accepted"
    assert payload["current_status"] == "queued"
    assert payload["attempts"] == 1
    assert "retried" in payload["transition_chain"][-1]["reason"]


def test_rejects_when_local_retry_decision_supplied(tmp_path: Path) -> None:
    # Load-bearing safeguard: any local-side retry/cancel decision forfeits
    # AO2's ownership claim because ao-operator is then the lifecycle owner.
    _, result = run_coordinator(
        tmp_path,
        submit_fixture(),
        local_retry={"why": "ao-operator retried locally without consulting AO2 queue"},
        expect_returncode=2,
    )
    assert "retry/cancel ownership cannot be local" in result.stderr
    assert "AO2 owns the failure lifecycle" in result.stderr


def test_rejects_submit_with_wrong_schema(tmp_path: Path) -> None:
    bad = submit_fixture()
    bad["schema_version"] = "ao2.wrong/v0"
    _, result = run_coordinator(tmp_path, bad, expect_returncode=2)
    assert "submit schema must be" in result.stderr
    assert SUBMIT_SCHEMA in result.stderr


def test_rejects_transition_with_wrong_schema(tmp_path: Path) -> None:
    bad_transition = transition_fixture()
    bad_transition["schema_version"] = "ao2.wrong-transition/v0"
    _, result = run_coordinator(
        tmp_path,
        submit_fixture(),
        transitions=[bad_transition],
        expect_returncode=2,
    )
    assert "transition schema must be" in result.stderr
    assert TRANSITION_SCHEMA in result.stderr


def test_rejects_run_id_mismatch(tmp_path: Path) -> None:
    _, result = run_coordinator(
        tmp_path,
        submit_fixture(run_id="factory-compat-A"),
        transitions=[transition_fixture(run_id="factory-compat-B")],
        expect_returncode=2,
    )
    assert "run_id mismatch" in result.stderr
    assert "factory-compat-A" in result.stderr
    assert "factory-compat-B" in result.stderr


def test_rejects_when_execution_owner_is_not_ao2(tmp_path: Path) -> None:
    # Defense in depth: if the submit entry says execution_owner is not
    # ao2, ao-operator must not certify AO2 ownership of the lifecycle.
    bad = submit_fixture()
    bad["entry"]["execution_contract"]["execution_owner"] = "ao-operator"
    _, result = run_coordinator(tmp_path, bad, expect_returncode=2)
    assert "execution_owner" in result.stderr
    assert "ao2" in result.stderr


def test_rejects_when_parity_checklist_says_ao2_does_not_persist_queue(tmp_path: Path) -> None:
    bad = submit_fixture()
    bad["entry"]["parity_checklist_progress"][
        "ao2_persists_queue_history_cancel_retry_state"
    ] = False
    _, result = run_coordinator(tmp_path, bad, expect_returncode=2)
    assert "ao2_persists_queue_history_cancel_retry_state" in result.stderr
