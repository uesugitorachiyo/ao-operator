#!/usr/bin/env python3
"""Prove simulated approved postrun routing ends with approval cleanup."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_agent_os_approval_audit_history
import check_agent_os_approval_lifecycle
import cleanup_agent_os_approval
import materialize_agent_os_approval
import route_agent_os_runspec_postrun


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_FIXTURE_ROOT = Path("/tmp/ao-operator-agent-os-post-approval-cleanup-route")
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-post-approval-cleanup-route.json"
APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"
APPROVAL_BUNDLE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-bundle.json"
APPROVAL_FILE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval.json"
MATERIALIZATION_REPORT = f"{STATUS_ROOT}/agent-os-approval-materialization.json"
CLEANUP_REPORT = f"{STATUS_ROOT}/agent-os-approval-cleanup.json"
AUDIT_LOG = f"{STATUS_ROOT}/agent-os-approval-audit.jsonl"
EXECUTION_REPORT = f"{STATUS_ROOT}/agent-os-runspec-execution-report.json"
POSTRUN_ROUTE = f"{STATUS_ROOT}/agent-os-runspec-postrun-route.json"
RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"
MARKER = ".ao-operator-post-approval-cleanup-route"


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


def reset_fixture_root(path: Path) -> None:
    if not path.exists():
        return
    marker = path / MARKER
    if path.is_dir() and marker.is_file():
        shutil.rmtree(path)
        return
    raise RuntimeError(f"fixture root exists without marker: {path}")


def copy_required_file(source_root: Path, fixture_root: Path, rel: str) -> None:
    source = resolve_path(source_root, rel)
    target = resolve_path(fixture_root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prepare_fixture(source_root: Path, fixture_root: Path) -> None:
    reset_fixture_root(fixture_root)
    fixture_root.mkdir(parents=True, exist_ok=True)
    (fixture_root / MARKER).write_text("AO Operator post-approval cleanup route fixture\n", encoding="utf-8")
    for rel in (RUNSPEC, APPROVAL_GATE, APPROVAL_BUNDLE):
        copy_required_file(source_root, fixture_root, rel)


def compact(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys if key in payload}


def seed_accepted_execution(root: Path) -> Path:
    return write_json(
        resolve_path(root, EXECUTION_REPORT),
        {
            "schema": "ao-operator/agent-os-runspec-execution-report/v1",
            "verdict": "PASS",
            "ao_completed": True,
            "evaluator_accepted": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "simulated": True,
        },
    )


def check_route(
    *,
    root: Path = ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    source_root = root.resolve()
    fixture_root = fixture_root.resolve()
    try:
        prepare_fixture(source_root, fixture_root)
    except (OSError, RuntimeError) as exc:
        return {
            "schema": "ao-operator/agent-os-post-approval-cleanup-route/v1",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "verdict": "FAIL",
            "fixture": "unavailable",
            "materialization": {},
            "postrun_route": {},
            "cleanup": {},
            "lifecycle_after_cleanup": {},
            "audit_history": {},
            "dispatch_authorized": False,
            "live_providers_run": False,
            "errors": [str(exc)],
            "next_safe_command": "Fix post-approval cleanup route fixture setup.",
        }

    errors: list[str] = []
    materialized = materialize_agent_os_approval.materialize(
        root=fixture_root,
        approval_bundle=APPROVAL_BUNDLE,
        approval_gate=APPROVAL_GATE,
        approved=True,
        operator="ao-operator-post-approval-cleanup-route",
        accepted_risk="Approve one isolated post-approval cleanup route fixture only.",
        write_approval_file=True,
        overwrite=True,
        now=now,
    )
    materialization_path = write_json(resolve_path(fixture_root, MATERIALIZATION_REPORT), materialized)
    materialization_event = check_agent_os_approval_audit_history.build_event(
        root=fixture_root,
        source_report=materialization_path,
    )
    check_agent_os_approval_audit_history.append_event(resolve_path(fixture_root, AUDIT_LOG), materialization_event)
    if materialized.get("approval_file_written") is not True:
        errors.append("approval materialization did not write fixture approval")

    seed_accepted_execution(fixture_root)
    postrun = route_agent_os_runspec_postrun.route(
        root=fixture_root,
        approval_gate=APPROVAL_GATE,
        execution_report=EXECUTION_REPORT,
    )
    write_json(resolve_path(fixture_root, POSTRUN_ROUTE), postrun)
    if postrun.get("route") != "ACCEPTED":
        errors.append("simulated accepted execution did not route ACCEPTED")

    cleanup = cleanup_agent_os_approval.plan_cleanup(
        root=fixture_root,
        approval_file=APPROVAL_FILE,
        apply=True,
        force=True,
        now=now,
    )
    cleanup_path = write_json(resolve_path(fixture_root, CLEANUP_REPORT), cleanup)
    cleanup_event = check_agent_os_approval_audit_history.build_event(root=fixture_root, source_report=cleanup_path)
    check_agent_os_approval_audit_history.append_event(resolve_path(fixture_root, AUDIT_LOG), cleanup_event)
    if cleanup.get("removed") is not True:
        errors.append("approval cleanup did not remove fixture approval")

    lifecycle = check_agent_os_approval_lifecycle.check_lifecycle(
        root=fixture_root,
        approval_gate=APPROVAL_GATE,
        approval_file=APPROVAL_FILE,
        now=now,
    )
    if lifecycle.get("approval_state") != "ABSENT":
        errors.append("approval lifecycle after cleanup must be ABSENT")

    audit = check_agent_os_approval_audit_history.summarize(root=fixture_root, audit_log=AUDIT_LOG)
    if audit.get("verdict") != "PASS":
        errors.append("approval audit history did not pass")

    return {
        "schema": "ao-operator/agent-os-post-approval-cleanup-route/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture": "isolated-temp",
        "source_runspec": RUNSPEC,
        "materialization": compact(materialized, ("verdict", "approval_file_written", "approval_valid", "dispatch_authorized", "live_providers_run")),
        "postrun_route": compact(postrun, ("verdict", "route", "diagnostics_required", "commit_success_evidence_allowed", "dispatch_authorized", "live_providers_run")),
        "cleanup": compact(cleanup, ("verdict", "approval_state", "removed", "force", "dispatch_authorized", "live_providers_run")),
        "lifecycle_after_cleanup": compact(lifecycle, ("verdict", "approval_state", "approval_usable", "approval_file_present", "dispatch_authorized", "live_providers_run")),
        "audit_history": compact(audit, ("verdict", "event_count", "latest_event", "dispatch_authorized", "live_providers_run")),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Post-approval cleanup route proof passes; keep real execution blocked until explicit approval."
            if not errors
            else "Fix post-approval cleanup route proof before relying on cleanup."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove simulated approved postrun cleanup route")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--now", default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_route(root=args.root, fixture_root=args.fixture_root, now=args.now)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
