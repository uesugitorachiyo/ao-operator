#!/usr/bin/env python3
"""Plan or remove Agent OS execution approval files after use or expiry."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_APPROVAL_FILE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval.json"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-cleanup.json"
SCHEMA = "ao-operator/agent-os-approval-cleanup/v1"


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


def parse_utc(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if text:
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def approval_state(approval: dict[str, Any], now: datetime) -> tuple[str, list[str]]:
    errors: list[str] = []
    if approval.get("schema") != "ao-operator/agent-os-runspec-execution-approval/v1":
        errors.append("approval file schema must be ao-operator/agent-os-runspec-execution-approval/v1")
    try:
        approved_at = parse_utc(approval.get("approved_at"))
        expires_at = parse_utc(approval.get("expires_at"))
    except (TypeError, ValueError):
        return "INVALID", ["approval file approved_at and expires_at must be valid datetimes", *errors]
    if approved_at > now:
        return "FUTURE", errors
    if expires_at <= now:
        return "EXPIRED", errors
    return "ACTIVE", errors


def safe_approval_path(root: Path, approval_path: Path) -> str | None:
    try:
        rel = approval_path.relative_to(root).as_posix()
    except ValueError:
        return "approval file must live under run-artifacts/"
    if not rel.startswith("run-artifacts/"):
        return "approval file must live under run-artifacts/"
    if approval_path.name != "agent-os-runspec-execution-approval.json":
        return "approval file name must be agent-os-runspec-execution-approval.json"
    return None


def plan_cleanup(
    *,
    root: Path = ROOT,
    approval_file: str | Path = DEFAULT_APPROVAL_FILE,
    apply: bool = False,
    force: bool = False,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    approval_path = resolve_path(root, approval_file)
    errors: list[str] = []
    removed = False
    checked_at = parse_utc(now).replace(microsecond=0)

    path_error = safe_approval_path(root, approval_path)
    if path_error:
        errors.append(path_error)

    if not approval_path.is_file():
        state = "ABSENT"
        candidate = False
    else:
        state, state_errors = approval_state(load_json(approval_path), checked_at)
        errors.extend(state_errors)
        candidate = state in {"EXPIRED", "INVALID"} or force
        if state == "ACTIVE" and apply and not force:
            errors.append("active approval requires --force")
        if state == "FUTURE" and apply and not force:
            errors.append("future approval requires --force")

    if errors and any(error.startswith("approval file must live") for error in errors):
        verdict = "FAIL"
    elif errors and apply:
        verdict = "BLOCKED"
    else:
        verdict = "PASS"

    if apply and verdict == "PASS" and candidate and approval_path.is_file():
        approval_path.unlink()
        removed = True

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checked_at": checked_at.isoformat(),
        "verdict": verdict,
        "mode": "apply" if apply else "dry-run",
        "approval_file": relpath(root, approval_path),
        "approval_file_present": approval_path.is_file() if not removed else False,
        "approval_state": state,
        "candidate": candidate,
        "removed": removed,
        "force": force,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval cleanup completed; rerun approval lifecycle before any launcher use."
            if removed
            else "No approval file removed; keep execution blocked unless a fresh approval is intentionally materialized."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or remove Agent OS approval files")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_FILE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--now", default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = plan_cleanup(
        root=args.root,
        approval_file=args.approval_file,
        apply=args.apply,
        force=args.force,
        now=args.now,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
