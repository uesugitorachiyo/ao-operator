#!/usr/bin/env python3
"""Prepare Agent OS RunSpec execution approval without dispatching providers."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATION = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-validation.json"
DEFAULT_APPROVAL_FILE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_AO_HOME = "/tmp/ao-operator-ao-agent-os-phase-draft"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validation_errors(validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if validation.get("schema") != "ao-operator/agent-os-runspec-validation/v1":
        errors.append("RunSpec validation schema must be ao-operator/agent-os-runspec-validation/v1")
    if validation.get("verdict") != "PASS" or validation.get("runspec_valid") is not True:
        errors.append("RunSpec validation must pass before execution approval")
    if validation.get("dispatch_authorized") is not False:
        errors.append("RunSpec validation dispatch_authorized must remain false")
    if validation.get("live_providers_run") is not False:
        errors.append("RunSpec validation live_providers_run must remain false")
    if not validation.get("runspec_path"):
        errors.append("RunSpec validation missing runspec_path")
    if not isinstance(validation.get("task_count"), int) or validation.get("task_count") <= 0:
        errors.append("RunSpec validation task_count must be positive")
    if validation.get("provider_profile_checked") is not True or validation.get("provider_profile_matches") is not True:
        errors.append("RunSpec provider profile must be checked and match before execution approval")
    if validation.get("provider_mismatches"):
        errors.append("RunSpec validation must not contain provider mismatches before execution approval")
    return errors


def build_gate(
    *,
    root: Path = ROOT,
    validation_report: str | Path = DEFAULT_VALIDATION,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    ao_home: str = DEFAULT_AO_HOME,
) -> dict[str, Any]:
    validation_path = resolve_path(root, validation_report)
    approval_path = resolve_path(root, approval_file)
    validation = load_json(validation_path)
    errors = validation_errors(validation)
    runspec_path = str(validation.get("runspec_path") or "ao/runspecs/agent-os-phase-draft.yaml")
    resolved_runspec = resolve_path(root, runspec_path)
    runspec_sha256 = ""
    if resolved_runspec.is_file():
        runspec_sha256 = sha256_file(resolved_runspec)
    else:
        errors.append("RunSpec file must exist before execution approval lock")
    execution_command = ["ao", "run", runspec_path, "--home", ao_home]
    approval_file_present = approval_path.is_file()
    ready = not errors
    return {
        "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "approval_request_ready": ready,
        "approval_file": relpath(root, approval_path),
        "approval_file_present": approval_file_present,
        "approval_state": "NOT_APPROVED" if not approval_file_present else "APPROVAL_FILE_PRESENT_REVIEW_BEFORE_DISPATCH",
        "approval_schema": "ao-operator/agent-os-runspec-execution-approval/v1",
        "validation_report": relpath(root, validation_path),
        "runspec_path": runspec_path,
        "runspec_sha256": runspec_sha256,
        "runspec_lock": {
            "algorithm": "sha256",
            "path": runspec_path,
            "sha256": runspec_sha256,
        },
        "task_count": validation.get("task_count", 0),
        "provider_profile": validation.get("provider_profile", ""),
        "provider_profile_checked": validation.get("provider_profile_checked") is True,
        "provider_profile_matches": validation.get("provider_profile_matches") is True,
        "provider_mismatches": validation.get("provider_mismatches", []),
        "execution_command": execution_command,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "stop_rules": [
            "Do not run AO from this approval gate.",
            "Do not dispatch unless a later execution slice validates an explicit approval file.",
            "Stop if RunSpec validation is not PASS.",
            "Stop if RunSpec provider profile alignment is not PASS.",
            "Stop if dispatch_authorized is not false.",
        ],
        "next_safe_command": (
            "Run the Agent OS no-provider execution rehearsal."
            if ready
            else "Fix Agent OS RunSpec validation before preparing execution approval."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec execution approval posture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--validation-report", default=DEFAULT_VALIDATION)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--ao-home", default=DEFAULT_AO_HOME)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_gate(root=args.root, validation_report=args.validation_report, approval_file=args.approval_file, ao_home=args.ao_home)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
