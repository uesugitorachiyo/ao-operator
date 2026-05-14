#!/usr/bin/env python3
"""Build a provider-free Agent OS approved execution happy-path fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_agent_os_accepted_execution_commit_guard
import route_agent_os_runspec_postrun
import validate_agent_os_runspec_evaluator_closure
import validate_agent_os_runspec_execution_approval


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-fixture.json"
FIXTURE_DIR = "run-artifacts/remote-transfer-v2-stress-live/approved-execution-fixture"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_fixture_runspec(root: Path) -> str:
    path = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kind: Run\nmetadata:\n  name: agent-os-phase-draft-fixture\n", encoding="utf-8")
    return sha256_file(path)


def approval_gate(root: Path, fixture_root: Path) -> Path:
    runspec_sha256 = ensure_fixture_runspec(root)
    return write_json(
        fixture_root / "approval-gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "approval_file": relpath(root, fixture_root / "approval.json"),
            "approval_file_present": True,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": runspec_sha256,
            "runspec_lock": {
                "algorithm": "sha256",
                "path": "ao/runspecs/agent-os-phase-draft.yaml",
                "sha256": runspec_sha256,
            },
            "task_count": 7,
            "execution_command": [
                "ao",
                "run",
                "ao/runspecs/agent-os-phase-draft.yaml",
                "--home",
                "/tmp/ao-operator-ao-agent-os-phase-draft-fixture",
            ],
            "provider_profile": ".env.example",
            "provider_profile_checked": True,
            "provider_profile_matches": True,
            "provider_mismatches": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def approval_file(fixture_root: Path) -> Path:
    gate = json.loads((fixture_root / "approval-gate.json").read_text(encoding="utf-8"))
    return write_json(
        fixture_root / "approval.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
            "approved": True,
            "operator": "fixture",
            "approved_at": "2026-05-07T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": gate.get("runspec_sha256", ""),
            "task_count": 7,
            "accepted_risk": "Provider-free fixture validates accepted execution control flow only.",
        },
    )


def execution_report(root: Path, fixture_root: Path, *, evaluator_accepted: bool) -> Path:
    return write_json(
        fixture_root / "execution-report.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-report/v1",
            "verdict": "PASS",
            "fixture_only": True,
            "ao_completed": True,
            "evaluator_accepted": evaluator_accepted,
            "role_outputs": [
                relpath(root, fixture_root / "role-outputs" / "planner.json"),
                relpath(root, fixture_root / "role-outputs" / "evaluator-closer.json"),
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
            "would_run_provider": False,
            "live_command_exit": 0,
        },
    )


def build_fixture(
    *,
    root: Path = ROOT,
    fixture_dir: str | Path = FIXTURE_DIR,
    evaluator_accepted: bool = True,
) -> dict[str, Any]:
    fixture_root = resolve_path(root, fixture_dir)
    gate = approval_gate(root, fixture_root)
    approval = approval_file(fixture_root)
    approval_validation = validate_agent_os_runspec_execution_approval.validate_approval(
        root=root,
        approval_gate=gate,
        approval_file=approval,
    )
    approval_validation_path = write_json(fixture_root / "approval-validation.json", approval_validation)
    execution = execution_report(root, fixture_root, evaluator_accepted=evaluator_accepted)
    route = route_agent_os_runspec_postrun.route(root=root, approval_gate=gate, execution_report=execution)
    route_path = write_json(fixture_root / "postrun-route.json", route)
    closure = validate_agent_os_runspec_evaluator_closure.validate_closure(root=root, execution_report=execution)
    closure_path = write_json(fixture_root / "evaluator-closure.json", closure)
    guard = check_agent_os_accepted_execution_commit_guard.check_guard(
        root=root,
        postrun_route=route_path,
        execution_report=execution,
        evaluator_closure=closure_path,
    )
    guard_path = write_json(fixture_root / "commit-guard.json", guard)

    component_results = {
        "approval_gate": "PASS",
        "approval_validation": str(approval_validation.get("approval_state") or "UNKNOWN"),
        "execution_report": "PASS",
        "postrun_route": str(route.get("route") or "UNKNOWN"),
        "evaluator_closure": str(closure.get("verdict") or "UNKNOWN"),
        "commit_guard": str(guard.get("verdict") or "UNKNOWN"),
    }
    errors: list[str] = []
    if approval_validation.get("approval_valid") is not True:
        errors.append("fixture approval validation must be valid")
    if route.get("route") != "ACCEPTED":
        errors.append("fixture expected ACCEPTED postrun route")
    if closure.get("accepted") is not True:
        errors.append("fixture expected evaluator closure acceptance")
    if guard.get("commit_success_evidence_allowed") is not False:
        errors.append("fixture commit guard must reject synthetic success evidence")
    if guard.get("verdict") != "FAIL":
        errors.append("fixture commit guard must fail synthetic accepted evidence")
    if guard.get("dispatch_authorized") is not False or guard.get("live_providers_run") is not False:
        errors.append("fixture commit guard must remain non-dispatching")

    return {
        "schema": "ao-operator/agent-os-approved-execution-fixture/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture_only": True,
        "component_results": component_results,
        "commit_guard_fixture_acceptance": guard.get("commit_success_evidence_allowed") is True,
        "commit_success_evidence_allowed": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "artifacts": {
            "approval_gate": relpath(root, gate),
            "approval": relpath(root, approval),
            "approval_validation": relpath(root, approval_validation_path),
            "execution_report": relpath(root, execution),
            "postrun_route": relpath(root, route_path),
            "evaluator_closure": relpath(root, closure_path),
            "commit_guard": relpath(root, guard_path),
        },
        "next_safe_command": (
            "Use this fixture as a provider-free baseline only; do not commit it as live success evidence."
            if not errors
            else "Fix approved execution fixture control-flow failures before architecture implementation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check provider-free Agent OS approved execution fixture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-dir", default=FIXTURE_DIR)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_fixture(root=args.root, fixture_dir=args.fixture_dir)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
