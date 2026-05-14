#!/usr/bin/env python3
"""Plan or apply Agent OS approval revocation without dispatch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_FILE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval.json"
DEFAULT_REVOCATION_LOG = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-revocations.jsonl"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-revocation.json"
SCHEMA = "ao-operator/agent-os-approval-revocation/v1"
EVENT_SCHEMA = "ao-operator/agent-os-approval-revocation-event/v1"


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


def read_jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def build_event(root: Path, approval_path: Path, approval: dict[str, Any], operator: str, reason: str) -> dict[str, Any]:
    return {
        "schema": EVENT_SCHEMA,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "event": "APPROVAL_REVOKED",
        "approval_file": relpath(root, approval_path),
        "operator": operator.strip(),
        "reason": reason.strip(),
        "runspec_path": approval.get("runspec_path", ""),
        "runspec_sha256": approval.get("runspec_sha256", ""),
        "task_count": approval.get("task_count", 0),
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def revoke_approval(
    *,
    root: Path = ROOT,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    revocation_log: str | Path = DEFAULT_REVOCATION_LOG,
    operator: str = "",
    reason: str = "",
    apply: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    approval_path = resolve_path(root, approval_file)
    log_path = resolve_path(root, revocation_log)
    approval_present_before = approval_path.is_file()
    approval = load_json(approval_path) if approval_present_before else {}
    errors: list[str] = []
    if apply:
        if not operator.strip():
            errors.append("revocation operator is required when applying")
        if not reason.strip():
            errors.append("revocation reason is required when applying")
        if not force:
            errors.append("force is required when applying revocation")
        if not approval_present_before:
            errors.append("approval file must exist when applying revocation")
    if approval_present_before and approval.get("schema") != "ao-operator/agent-os-runspec-execution-approval/v1":
        errors.append("approval file schema must be ao-operator/agent-os-runspec-execution-approval/v1")

    applied = False
    if apply and not errors:
        append_event(log_path, build_event(root, approval_path, approval, operator, reason))
        approval_path.unlink()
        applied = True

    approval_present_after = approval_path.is_file()
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_file": relpath(root, approval_path),
        "revocation_log": relpath(root, log_path),
        "approval_file_present_before": approval_present_before,
        "approval_file_present_after": approval_present_after,
        "revocation_applied": applied,
        "revocation_count": read_jsonl_count(log_path),
        "operator_recorded": bool(operator.strip()) if apply else False,
        "reason_recorded": bool(reason.strip()) if apply else False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval revocation applied; keep execution blocked until a fresh approval is materialized."
            if applied
            else (
                "Fix approval revocation blockers before applying."
                if errors
                else "Approval revocation plan passes; pass --apply --force only when intentionally revoking."
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply Agent OS approval revocation")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--revocation-log", default=DEFAULT_REVOCATION_LOG)
    parser.add_argument("--operator", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = revoke_approval(
        root=args.root,
        approval_file=args.approval_file,
        revocation_log=args.revocation_log,
        operator=args.operator,
        reason=args.reason,
        apply=args.apply,
        force=args.force,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
