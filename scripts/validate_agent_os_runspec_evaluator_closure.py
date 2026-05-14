#!/usr/bin/env python3
"""Validate Agent OS RunSpec evaluator closure evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXECUTION_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-evaluator-closure.json"


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_closure(*, root: Path = ROOT, execution_report: str | Path = DEFAULT_EXECUTION_REPORT) -> dict[str, Any]:
    report_path = resolve_path(root, execution_report)
    report = load_json(report_path)
    errors: list[str] = []
    if report.get("schema") != "ao-operator/agent-os-runspec-execution-report/v1":
        errors.append("execution report schema must be ao-operator/agent-os-runspec-execution-report/v1")
    if report.get("verdict") != "PASS":
        errors.append("execution report verdict must be PASS")
    if report.get("ao_completed") is not True:
        errors.append("AO execution must be completed")
    if report.get("evaluator_accepted") is not True:
        errors.append("evaluator acceptance must be true")
    accepted = not errors
    return {
        "schema": "ao-operator/agent-os-runspec-evaluator-closure/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if accepted else "FAIL",
        "execution_report": relpath(root, report_path),
        "accepted": accepted,
        "closure_authorized": accepted,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": "Commit accepted Agent OS execution evidence." if accepted else "Keep Agent OS execution unclosed.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS evaluator closure")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--execution-report", default=DEFAULT_EXECUTION_REPORT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = validate_closure(root=args.root, execution_report=args.execution_report)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"accepted={str(payload['accepted']).lower()}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
