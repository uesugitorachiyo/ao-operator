from __future__ import annotations

import json
import hashlib
from pathlib import Path

import agent_os_operator_cockpit


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def learning_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-learning-extract/v1",
        "verdict": "PASS",
        "closure_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "pending_uat_count": 2,
        "open_blockers": ["human UAT acceptance is pending"],
        "next_safe_command": "Add operator cockpit visibility for UAT, dispatch, readiness, and blockers.",
    }


def readiness_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/release-readiness-gate/v1",
        "verdict": "PASS",
        "ship_ready": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": "Repository is release-ready; start the next gated SDD lane.",
    }


def state_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-state/v2",
        "verdict": "PASS",
        "architecture_ready": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
        "next_safe_command": "Compile the next Agent OS implementation phase behind state v2 compatibility baselines.",
    }


def runspec_renderer_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "state_schema_version": "ao-operator/agent-os-state/v2",
        "state_baseline_checked": True,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "task_count": 7,
    }


def approval_gate_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "approval_state": "NOT_APPROVED",
        "approval_request_ready": True,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec_sha256": "abc123",
        "runspec_lock": {
            "algorithm": "sha256",
            "path": "ao/runspecs/agent-os-phase-draft.yaml",
            "sha256": "abc123",
        },
    }


def approval_validation_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-execution-approval-validation/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "approval_state": "NOT_APPROVED",
        "approval_valid": False,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec_sha256": "abc123",
        "approval_runspec_sha256": "",
    }


def execution_runner_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-execution-report/v1",
        "verdict": "BLOCKED",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "execute_requested": False,
        "would_run_provider": False,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec_sha256": "abc123",
        "current_runspec_sha256": "",
        "errors": ["explicit approval is not valid"],
    }


def evidence_pack_replay_proof_report() -> dict[str, object]:
    return {
        "schema": "ao-operator/evidence-pack-replay-proof-status/v1",
        "verdict": "PASS",
        "proof_ready": True,
        "summary_count": 1,
        "deterministic_summary_count": 1,
        "executed_deterministic_summary_count": 1,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": "Evidence pack replay proof is ready for v0.7 release-readiness review.",
        "errors": [],
    }


def seed_reports(root: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    learning = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json"
    readiness = root / "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json"
    state = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json"
    renderer = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
    approval_gate = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
    approval_validation = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json"
    execution_runner = root / "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json"
    evidence_pack_replay_proof = root / "run-artifacts/remote-transfer-v2-stress-live/evidence-pack-replay-proof-status.json"
    write(learning, json.dumps(learning_report()))
    write(readiness, json.dumps(readiness_report()))
    write(state, json.dumps(state_report()))
    write(renderer, json.dumps(runspec_renderer_report()))
    write(approval_gate, json.dumps(approval_gate_report()))
    write(approval_validation, json.dumps(approval_validation_report()))
    write(execution_runner, json.dumps(execution_runner_report()))
    write(evidence_pack_replay_proof, json.dumps(evidence_pack_replay_proof_report()))
    return learning, readiness, state, renderer, approval_gate, approval_validation, execution_runner


def test_operator_cockpit_summarizes_blockers_and_readiness_without_dispatch(tmp_path):
    learning, readiness, *_ = seed_reports(tmp_path)

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["ship_ready"] is True
    assert payload["active_milestone"] == "AO Operator Agent OS"
    assert payload["blockers"] == ["human UAT acceptance is pending"]
    assert payload["next_safe_command"] == "Execution is hash-locked and blocked until explicit approval is valid."


def test_operator_cockpit_records_evidence_paths_and_uat_state(tmp_path):
    learning, readiness, state, renderer, approval_gate, approval_validation, execution_runner = seed_reports(tmp_path)

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["uat"]["pending_count"] == 2
    assert payload["uat"]["closure_authorized"] is False
    assert payload["evidence_paths"]["learning_report"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json"
    assert payload["evidence_paths"]["release_readiness"] == "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json"
    assert payload["evidence_paths"]["state_v2"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json"
    assert payload["evidence_paths"]["runspec_renderer"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
    assert payload["evidence_paths"]["execution_approval_gate"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
    assert payload["evidence_paths"]["execution_approval_validation"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json"
    assert payload["evidence_paths"]["execution_runner"] == "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json"
    assert payload["evidence_paths"]["evidence_pack_replay_proof"] == "run-artifacts/remote-transfer-v2-stress-live/evidence-pack-replay-proof-status.json"


def test_operator_cockpit_includes_evidence_pack_replay_proof_status(tmp_path):
    learning, readiness, *_ = seed_reports(tmp_path)

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["evidence_pack_replay_proof"] == {
        "verdict": "PASS",
        "proof_ready": True,
        "summary_count": 1,
        "deterministic_summary_count": 1,
        "executed_deterministic_summary_count": 1,
    }


def test_operator_cockpit_fails_when_evidence_pack_replay_proof_is_not_ready(tmp_path):
    learning, readiness, *_ = seed_reports(tmp_path)
    proof = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/evidence-pack-replay-proof-status.json"
    data = evidence_pack_replay_proof_report()
    data["verdict"] = "FAIL"
    data["proof_ready"] = False
    write(proof, json.dumps(data))

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["verdict"] == "FAIL"
    assert any("evidence pack replay proof must be ready" in error for error in payload["errors"])


def test_operator_cockpit_fails_when_learning_authorizes_dispatch(tmp_path):
    learning, readiness, *_ = seed_reports(tmp_path)
    data = learning_report()
    data["dispatch_authorized"] = True
    write(learning, json.dumps(data))

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert any("learning dispatch_authorized must remain false" in error for error in payload["errors"])


def test_operator_cockpit_summarizes_state_v2_and_runspec_lock(tmp_path):
    learning, readiness, *_ = seed_reports(tmp_path)

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["state_v2"] == {
        "verdict": "PASS",
        "architecture_ready": True,
        "schema": "ao-operator/agent-os-state/v2",
        "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
    }
    assert payload["runspec"] == {
        "verdict": "PASS",
        "path": "ao/runspecs/agent-os-phase-draft.yaml",
        "task_count": 7,
        "state_schema_version": "ao-operator/agent-os-state/v2",
        "state_baseline_checked": True,
    }
    assert payload["execution_lock"] == {
        "locked": True,
        "algorithm": "sha256",
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec_sha256": "abc123",
        "approval_state": "NOT_APPROVED",
        "approval_valid": False,
        "runner_verdict": "BLOCKED",
        "would_run_provider": False,
        "current_runspec_sha256": "",
    }
    assert payload["next_safe_command"] == "Execution is hash-locked and blocked until explicit approval is valid."


def test_operator_cockpit_computes_current_runspec_hash_when_runner_is_blocked(tmp_path):
    learning, readiness, _state, _renderer, approval_gate, approval_validation, execution_runner = seed_reports(tmp_path)
    runspec = tmp_path / "ao/runspecs/agent-os-phase-draft.yaml"
    write(runspec, "apiVersion: ao.dev/v1\nkind: Run\n")
    digest = hashlib.sha256(runspec.read_bytes()).hexdigest()
    gate = approval_gate_report()
    gate["runspec_sha256"] = digest
    gate["runspec_lock"] = {
        "algorithm": "sha256",
        "path": "ao/runspecs/agent-os-phase-draft.yaml",
        "sha256": digest,
    }
    validation = approval_validation_report()
    validation["runspec_sha256"] = digest
    runner = execution_runner_report()
    runner["runspec_sha256"] = digest
    runner["current_runspec_sha256"] = ""
    write(approval_gate, json.dumps(gate))
    write(approval_validation, json.dumps(validation))
    write(execution_runner, json.dumps(runner))

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["execution_lock"]["locked"] is True
    assert payload["execution_lock"]["runspec_sha256"] == digest
    assert payload["execution_lock"]["current_runspec_sha256"] == digest


def test_operator_cockpit_marks_lock_unlocked_when_current_runspec_hash_drifts(tmp_path):
    learning, readiness, _state, _renderer, approval_gate, approval_validation, execution_runner = seed_reports(tmp_path)
    runspec = tmp_path / "ao/runspecs/agent-os-phase-draft.yaml"
    write(runspec, "apiVersion: ao.dev/v1\nkind: Run\nmetadata:\n  name: drifted\n")

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["execution_lock"]["locked"] is False
    assert payload["execution_lock"]["runspec_sha256"] == "abc123"
    assert payload["execution_lock"]["current_runspec_sha256"] != "abc123"
    assert payload["next_safe_command"] == "Record human UAT responses or start the next gated SDD lane."


def test_operator_cockpit_fails_when_state_report_is_not_v2(tmp_path):
    learning, readiness, state, *_ = seed_reports(tmp_path)
    data = state_report()
    data["schema"] = "ao-operator/agent-os-state/v1"
    write(state, json.dumps(data))

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["verdict"] == "FAIL"
    assert any("state report schema must be ao-operator/agent-os-state/v2" in error for error in payload["errors"])


def test_operator_cockpit_fails_when_runspec_hash_lock_is_missing(tmp_path):
    learning, readiness, _state, _renderer, approval_gate, *_ = seed_reports(tmp_path)
    data = approval_gate_report()
    data["runspec_sha256"] = ""
    data["runspec_lock"] = {}
    write(approval_gate, json.dumps(data))

    payload = agent_os_operator_cockpit.build_cockpit(root=tmp_path, learning_report=learning, readiness_report=readiness)

    assert payload["verdict"] == "FAIL"
    assert any("execution approval gate must include sha256 RunSpec lock" in error for error in payload["errors"])


def test_cli_writes_operator_cockpit(tmp_path, capsys):
    learning, readiness, *_ = seed_reports(tmp_path)
    output = tmp_path / "run-artifacts/cockpit.json"

    code = agent_os_operator_cockpit.main(
        [
            "--root",
            str(tmp_path),
            "--learning-report",
            str(learning),
            "--readiness-report",
            str(readiness),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-operator-cockpit/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
