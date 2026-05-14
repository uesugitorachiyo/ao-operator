#!/usr/bin/env python3
"""Guard Agent OS accepted execution evidence commits."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSTRUN_ROUTE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-postrun-route.json"
DEFAULT_EXECUTION_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
DEFAULT_EVALUATOR_CLOSURE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-evaluator-closure.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-accepted-execution-commit-guard.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def check_guard(
    *,
    root: Path = ROOT,
    postrun_route: str | Path = DEFAULT_POSTRUN_ROUTE,
    execution_report: str | Path = DEFAULT_EXECUTION_REPORT,
    evaluator_closure: str | Path = DEFAULT_EVALUATOR_CLOSURE,
) -> dict[str, Any]:
    route_path = resolve_path(root, postrun_route)
    report_path = resolve_path(root, execution_report)
    closure_path = resolve_path(root, evaluator_closure)
    route = load_json(route_path)
    report = load_json(report_path)
    closure = load_json(closure_path)
    errors: list[str] = []
    warnings: list[str] = []

    route_name = str(route.get("route") or "MISSING")
    route_commit = route.get("commit_success_evidence_allowed") is True
    closure_authorized = closure.get("closure_authorized") is True
    execution_completed = (
        report.get("schema") == "ao-operator/agent-os-runspec-execution-report/v1"
        and report.get("verdict") == "PASS"
        and report.get("ao_completed") is True
        and report.get("evaluator_accepted") is True
    )
    live_provider_execution = report.get("live_providers_run") is True and report.get("fixture_only") is not True

    if route.get("schema") != "ao-operator/agent-os-runspec-postrun-route/v1":
        errors.append("postrun route schema must be ao-operator/agent-os-runspec-postrun-route/v1")
    if route.get("verdict") != "PASS":
        errors.append("postrun route verdict must be PASS")
    if route.get("dispatch_authorized") is not False:
        errors.append("postrun route dispatch_authorized must be false")
    if route.get("live_providers_run") is not False:
        errors.append("postrun route live_providers_run must be false")
    if closure and closure.get("schema") != "ao-operator/agent-os-runspec-evaluator-closure/v1":
        errors.append("evaluator closure schema must be ao-operator/agent-os-runspec-evaluator-closure/v1")
    if closure.get("dispatch_authorized") is not False:
        errors.append("evaluator closure dispatch_authorized must be false")
    if closure.get("live_providers_run") is not False:
        errors.append("evaluator closure live_providers_run must be false")

    accepted_route = route_name == "ACCEPTED" or route_commit
    if accepted_route and not execution_completed:
        errors.append("accepted execution commit requires completed AO execution and evaluator acceptance")
    if accepted_route and not live_provider_execution:
        errors.append("accepted execution commit requires live provider execution, not fixture-only evidence")
    if accepted_route and not closure_authorized:
        errors.append("evaluator closure must authorize success commit")
    if route_name == "ACCEPTED" and not route_commit:
        errors.append("ACCEPTED postrun route must set commit_success_evidence_allowed=true")
    if route_commit and route_name != "ACCEPTED":
        errors.append("commit_success_evidence_allowed=true is only valid for ACCEPTED route")

    commit_allowed = bool(
        not errors
        and route_name == "ACCEPTED"
        and route_commit
        and execution_completed
        and live_provider_execution
        and closure_authorized
    )
    if not commit_allowed:
        warnings.append("Agent OS success evidence commit is not allowed in the current state")

    return {
        "schema": "ao-operator/agent-os-accepted-execution-commit-guard/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "postrun_route": relpath(root, route_path),
        "execution_report": relpath(root, report_path),
        "evaluator_closure": relpath(root, closure_path),
        "route": route_name,
        "execution_completed": execution_completed,
        "live_provider_execution": live_provider_execution,
        "closure_authorized": closure_authorized,
        "commit_success_evidence_allowed": commit_allowed,
        "raw_snapshot_commit_allowed": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "warnings": warnings,
        "next_safe_command": (
            "Commit accepted Agent OS execution evidence only."
            if commit_allowed
            else "Keep Agent OS execution evidence uncommitted as success until postrun route, execution report, and evaluator closure all accept."
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard Agent OS accepted execution evidence commits")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--postrun-route", default=DEFAULT_POSTRUN_ROUTE)
    parser.add_argument("--execution-report", default=DEFAULT_EXECUTION_REPORT)
    parser.add_argument("--evaluator-closure", default=DEFAULT_EVALUATOR_CLOSURE)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_guard(
        root=args.root,
        postrun_route=args.postrun_route,
        execution_report=args.execution_report,
        evaluator_closure=args.evaluator_closure,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
