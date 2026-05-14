#!/usr/bin/env python3
"""Build a local Agent OS operator cockpit snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEARNING_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json"
DEFAULT_READINESS_REPORT = "run-artifacts/remote-transfer-v2-stress-live/release-readiness-gate.json"
DEFAULT_STATE_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json"
DEFAULT_RUNSPEC_RENDERER_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
DEFAULT_EXECUTION_APPROVAL_GATE = (
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
)
DEFAULT_EXECUTION_APPROVAL_VALIDATION = (
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json"
)
DEFAULT_EXECUTION_RUNNER_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json"
DEFAULT_EVIDENCE_PACK_REPLAY_PROOF = (
    "run-artifacts/remote-transfer-v2-stress-live/evidence-pack-replay-proof-status.json"
)
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-operator-cockpit.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    target = path.relative_to(root) if path.is_relative_to(root) else Path(path)
    return target.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def validate_non_dispatching_report(label: str, report: dict[str, Any], errors: list[str]) -> None:
    if report.get("dispatch_authorized") is not False:
        errors.append(f"{label} dispatch_authorized must remain false")
    if report.get("live_providers_run") is not False:
        errors.append(f"{label} live_providers_run must remain false")


def validate_sources(
    learning: dict[str, Any],
    readiness: dict[str, Any],
    state: dict[str, Any],
    renderer: dict[str, Any],
    approval_gate: dict[str, Any],
    approval_validation: dict[str, Any],
    execution_runner: dict[str, Any],
    evidence_pack_replay_proof: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if learning.get("schema") != "ao-operator/agent-os-learning-extract/v1":
        errors.append("learning report schema must be ao-operator/agent-os-learning-extract/v1")
    if learning.get("verdict") != "PASS":
        errors.append("learning report verdict must be PASS")
    validate_non_dispatching_report("learning", learning, errors)
    if learning.get("closure_authorized") is not False:
        errors.append("learning closure_authorized must remain false")
    if readiness.get("schema") != "ao-operator/release-readiness-gate/v1":
        errors.append("readiness report schema must be ao-operator/release-readiness-gate/v1")
    validate_non_dispatching_report("readiness", readiness, errors)
    if state.get("schema") != "ao-operator/agent-os-state/v2":
        errors.append("state report schema must be ao-operator/agent-os-state/v2")
    if state.get("verdict") != "PASS":
        errors.append("state report verdict must be PASS")
    validate_non_dispatching_report("state", state, errors)
    if renderer.get("schema") != "ao-operator/agent-os-runspec-renderer/v1":
        errors.append("RunSpec renderer schema must be ao-operator/agent-os-runspec-renderer/v1")
    if renderer.get("verdict") != "PASS":
        errors.append("RunSpec renderer verdict must be PASS")
    if renderer.get("state_schema_version") != "ao-operator/agent-os-state/v2":
        errors.append("RunSpec renderer must be based on Agent OS state v2")
    if renderer.get("state_baseline_checked") is not True:
        errors.append("RunSpec renderer must check state baseline")
    validate_non_dispatching_report("RunSpec renderer", renderer, errors)
    if approval_gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("execution approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if approval_gate.get("verdict") != "PASS":
        errors.append("execution approval gate verdict must be PASS")
    validate_non_dispatching_report("execution approval gate", approval_gate, errors)
    lock = approval_gate.get("runspec_lock")
    lock_ok = (
        isinstance(lock, dict)
        and lock.get("algorithm") == "sha256"
        and isinstance(lock.get("sha256"), str)
        and bool(lock.get("sha256"))
        and lock.get("sha256") == approval_gate.get("runspec_sha256")
    )
    if not lock_ok:
        errors.append("execution approval gate must include sha256 RunSpec lock")
    if approval_validation.get("schema") != "ao-operator/agent-os-runspec-execution-approval-validation/v1":
        errors.append(
            "execution approval validation schema must be ao-operator/agent-os-runspec-execution-approval-validation/v1"
        )
    if approval_validation.get("verdict") != "PASS":
        errors.append("execution approval validation verdict must be PASS")
    validate_non_dispatching_report("execution approval validation", approval_validation, errors)
    if approval_validation.get("runspec_sha256") != approval_gate.get("runspec_sha256"):
        errors.append("execution approval validation must carry approval gate RunSpec sha256")
    if execution_runner.get("schema") != "ao-operator/agent-os-runspec-execution-report/v1":
        errors.append("execution runner schema must be ao-operator/agent-os-runspec-execution-report/v1")
    if execution_runner.get("verdict") not in {"BLOCKED", "PASS"}:
        errors.append("execution runner verdict must be BLOCKED or PASS")
    validate_non_dispatching_report("execution runner", execution_runner, errors)
    if execution_runner.get("would_run_provider") is not False:
        errors.append("execution runner would_run_provider must remain false")
    if execution_runner.get("runspec_sha256") != approval_gate.get("runspec_sha256"):
        errors.append("execution runner must carry approval gate RunSpec sha256")
    if evidence_pack_replay_proof.get("schema") != "ao-operator/evidence-pack-replay-proof-status/v1":
        errors.append("evidence pack replay proof schema must be ao-operator/evidence-pack-replay-proof-status/v1")
    if evidence_pack_replay_proof.get("verdict") != "PASS" or evidence_pack_replay_proof.get("proof_ready") is not True:
        errors.append("evidence pack replay proof must be ready")
    validate_non_dispatching_report("evidence pack replay proof", evidence_pack_replay_proof, errors)
    return errors


def build_cockpit(
    *,
    root: Path = ROOT,
    learning_report: str | Path = DEFAULT_LEARNING_REPORT,
    readiness_report: str | Path = DEFAULT_READINESS_REPORT,
    state_report: str | Path = DEFAULT_STATE_REPORT,
    runspec_renderer_report: str | Path = DEFAULT_RUNSPEC_RENDERER_REPORT,
    execution_approval_gate: str | Path = DEFAULT_EXECUTION_APPROVAL_GATE,
    execution_approval_validation: str | Path = DEFAULT_EXECUTION_APPROVAL_VALIDATION,
    execution_runner_report: str | Path = DEFAULT_EXECUTION_RUNNER_REPORT,
    evidence_pack_replay_proof: str | Path = DEFAULT_EVIDENCE_PACK_REPLAY_PROOF,
) -> dict[str, Any]:
    learning_path = resolve_path(root, learning_report)
    readiness_path = resolve_path(root, readiness_report)
    state_path = resolve_path(root, state_report)
    renderer_path = resolve_path(root, runspec_renderer_report)
    approval_gate_path = resolve_path(root, execution_approval_gate)
    approval_validation_path = resolve_path(root, execution_approval_validation)
    execution_runner_path = resolve_path(root, execution_runner_report)
    evidence_pack_replay_proof_path = resolve_path(root, evidence_pack_replay_proof)
    learning = load_json(learning_path)
    readiness = load_json(readiness_path)
    state = load_json(state_path)
    renderer = load_json(renderer_path)
    approval_gate = load_json(approval_gate_path)
    approval_validation = load_json(approval_validation_path)
    execution_runner = load_json(execution_runner_path)
    evidence_pack_replay_proof_report = load_json(evidence_pack_replay_proof_path)
    errors = validate_sources(
        learning,
        readiness,
        state,
        renderer,
        approval_gate,
        approval_validation,
        execution_runner,
        evidence_pack_replay_proof_report,
    )
    blockers = string_list(learning.get("open_blockers"))
    lock = approval_gate.get("runspec_lock") if isinstance(approval_gate.get("runspec_lock"), dict) else {}
    approval_valid = approval_validation.get("approval_valid") is True
    runner_verdict = execution_runner.get("verdict", "")
    lock_sha = approval_gate.get("runspec_sha256", "")
    current_runspec_sha = str(execution_runner.get("current_runspec_sha256") or "")
    runspec_path_value = str(approval_gate.get("runspec_path") or "")
    if not current_runspec_sha and runspec_path_value:
        resolved_runspec = resolve_path(root, runspec_path_value)
        if resolved_runspec.is_file():
            current_runspec_sha = sha256_file(resolved_runspec)
    locked = (
        lock.get("algorithm") == "sha256"
        and bool(lock_sha)
        and lock.get("sha256") == lock_sha
        and approval_validation.get("runspec_sha256") == lock_sha
        and execution_runner.get("runspec_sha256") == lock_sha
        and (not current_runspec_sha or current_runspec_sha == lock_sha)
    )
    next_safe_command = "Fix cockpit source errors before operator handoff."
    if not errors:
        if locked and not approval_valid and runner_verdict == "BLOCKED":
            next_safe_command = "Execution is hash-locked and blocked until explicit approval is valid."
        else:
            next_safe_command = "Record human UAT responses or start the next gated SDD lane."
    return {
        "schema": "ao-operator/agent-os-operator-cockpit/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "active_milestone": "AO Operator Agent OS",
        "blockers": blockers,
        "state_v2": {
            "verdict": state.get("verdict"),
            "architecture_ready": state.get("architecture_ready") is True,
            "schema": state.get("schema", ""),
            "role_graph_schema": state.get("role_graph_schema", ""),
        },
        "runspec": {
            "verdict": renderer.get("verdict"),
            "path": renderer.get("runspec_path", ""),
            "task_count": int(renderer.get("task_count") or 0),
            "state_schema_version": renderer.get("state_schema_version", ""),
            "state_baseline_checked": renderer.get("state_baseline_checked") is True,
        },
        "execution_lock": {
            "locked": locked,
            "algorithm": lock.get("algorithm", ""),
            "runspec_path": approval_gate.get("runspec_path", ""),
            "runspec_sha256": lock_sha,
            "approval_state": approval_validation.get("approval_state", approval_gate.get("approval_state", "")),
            "approval_valid": approval_valid,
            "runner_verdict": runner_verdict,
            "would_run_provider": execution_runner.get("would_run_provider") is True,
            "current_runspec_sha256": current_runspec_sha,
        },
        "uat": {
            "pending_count": int(learning.get("pending_uat_count") or 0),
            "closure_authorized": False,
        },
        "readiness": {
            "verdict": readiness.get("verdict"),
            "ship_ready": readiness.get("ship_ready") is True,
            "next_safe_command": readiness.get("next_safe_command", ""),
        },
        "evidence_pack_replay_proof": {
            "verdict": evidence_pack_replay_proof_report.get("verdict"),
            "proof_ready": evidence_pack_replay_proof_report.get("proof_ready") is True,
            "summary_count": int(evidence_pack_replay_proof_report.get("summary_count") or 0),
            "deterministic_summary_count": int(
                evidence_pack_replay_proof_report.get("deterministic_summary_count") or 0
            ),
            "executed_deterministic_summary_count": int(
                evidence_pack_replay_proof_report.get("executed_deterministic_summary_count") or 0
            ),
        },
        "evidence_paths": {
            "learning_report": relpath(root, learning_path),
            "release_readiness": relpath(root, readiness_path),
            "state_v2": relpath(root, state_path),
            "runspec_renderer": relpath(root, renderer_path),
            "execution_approval_gate": relpath(root, approval_gate_path),
            "execution_approval_validation": relpath(root, approval_validation_path),
            "execution_runner": relpath(root, execution_runner_path),
            "evidence_pack_replay_proof": relpath(root, evidence_pack_replay_proof_path),
        },
        "ship_ready": readiness.get("ship_ready") is True,
        "closure_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": next_safe_command,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AO Operator Agent OS operator cockpit")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--learning-report", default=DEFAULT_LEARNING_REPORT)
    parser.add_argument("--readiness-report", default=DEFAULT_READINESS_REPORT)
    parser.add_argument("--state-report", default=DEFAULT_STATE_REPORT)
    parser.add_argument("--runspec-renderer-report", default=DEFAULT_RUNSPEC_RENDERER_REPORT)
    parser.add_argument("--execution-approval-gate", default=DEFAULT_EXECUTION_APPROVAL_GATE)
    parser.add_argument("--execution-approval-validation", default=DEFAULT_EXECUTION_APPROVAL_VALIDATION)
    parser.add_argument("--execution-runner-report", default=DEFAULT_EXECUTION_RUNNER_REPORT)
    parser.add_argument("--evidence-pack-replay-proof", default=DEFAULT_EVIDENCE_PACK_REPLAY_PROOF)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_cockpit(
        root=args.root,
        learning_report=args.learning_report,
        readiness_report=args.readiness_report,
        state_report=args.state_report,
        runspec_renderer_report=args.runspec_renderer_report,
        execution_approval_gate=args.execution_approval_gate,
        execution_approval_validation=args.execution_approval_validation,
        execution_runner_report=args.execution_runner_report,
        evidence_pack_replay_proof=args.evidence_pack_replay_proof,
    )
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
