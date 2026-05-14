#!/usr/bin/env python3
"""Materialize an Agent OS RunSpec execution approval only with explicit operator input."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_BUNDLE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json"
DEFAULT_APPROVAL_GATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-materialization.json"


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight_errors(bundle: dict[str, Any], gate: dict[str, Any], current_runspec_sha256: str) -> list[str]:
    errors: list[str] = []
    if bundle.get("schema") != "ao-operator/agent-os-execution-approval-bundle/v1":
        errors.append("approval bundle schema must be ao-operator/agent-os-execution-approval-bundle/v1")
    if bundle.get("verdict") != "PASS":
        errors.append("approval bundle verdict must be PASS")
    if bundle.get("dispatch_authorized") is not False:
        errors.append("approval bundle dispatch_authorized must remain false")
    if bundle.get("live_providers_run") is not False:
        errors.append("approval bundle live_providers_run must remain false")
    if gate.get("schema") != "ao-operator/agent-os-runspec-execution-approval-gate/v1":
        errors.append("approval gate schema must be ao-operator/agent-os-runspec-execution-approval-gate/v1")
    if gate.get("verdict") != "PASS" or gate.get("approval_request_ready") is not True:
        errors.append("approval gate must be ready")
    if gate.get("dispatch_authorized") is not False:
        errors.append("approval gate dispatch_authorized must remain false")
    if gate.get("live_providers_run") is not False:
        errors.append("approval gate live_providers_run must remain false")
    if gate.get("provider_profile_checked") is not True or gate.get("provider_profile_matches") is not True:
        errors.append("approval gate provider profile must be checked and match")
    if gate.get("provider_mismatches"):
        errors.append("approval gate must not contain provider mismatches")
    gate_sha = str(gate.get("runspec_sha256") or "")
    bundle_template = bundle.get("approval_template") if isinstance(bundle.get("approval_template"), dict) else {}
    if not gate_sha:
        errors.append("approval gate missing runspec_sha256")
    if bundle_template.get("runspec_sha256") != gate_sha:
        errors.append("approval bundle template sha256 must match approval gate sha256")
    if current_runspec_sha256 != gate_sha:
        errors.append("current RunSpec sha256 must match approval gate sha256")
    return errors


def materialize(
    *,
    root: Path = ROOT,
    approval_bundle: str | Path = DEFAULT_APPROVAL_BUNDLE,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    approved: bool = False,
    operator: str = "",
    accepted_risk: str = "",
    write_approval_file: bool = False,
    overwrite: bool = False,
    now: str | datetime | None = None,
    expires_in_hours: int = 4,
) -> dict[str, Any]:
    root = root.resolve()
    bundle_path = resolve_path(root, approval_bundle)
    gate_path = resolve_path(root, approval_gate)
    bundle = load_json(bundle_path)
    gate = load_json(gate_path)
    template = bundle.get("approval_template") if isinstance(bundle.get("approval_template"), dict) else {}
    target_path = resolve_path(root, str(bundle.get("approval_file_target") or ""))
    runspec_path = resolve_path(root, str(gate.get("runspec_path") or template.get("runspec_path") or ""))
    current_sha = sha256_file(runspec_path) if runspec_path.is_file() else ""
    errors = preflight_errors(bundle, gate, current_sha)
    approved_at = parse_utc(now).replace(microsecond=0)
    expires_at = approved_at + timedelta(hours=expires_in_hours)
    approval = {
        "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
        "approved": bool(approved),
        "operator": operator.strip(),
        "approved_at": approved_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "runspec_path": gate.get("runspec_path", template.get("runspec_path", "")),
        "runspec_sha256": gate.get("runspec_sha256", template.get("runspec_sha256", "")),
        "task_count": gate.get("task_count", template.get("task_count", 0)),
        "accepted_risk": accepted_risk.strip(),
    }

    if write_approval_file:
        if approved is not True:
            errors.append("approved must be true when writing approval file")
        if not approval["operator"]:
            errors.append("operator is required when writing approval file")
        if not approval["accepted_risk"]:
            errors.append("accepted_risk is required when writing approval file")
        if target_path.exists() and not overwrite:
            errors.append("approval file already exists; pass --overwrite to replace it")

    wrote = False
    if write_approval_file and not errors:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(approval, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        wrote = True

    return {
        "schema": "ao-operator/agent-os-approval-materialization/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_bundle": relpath(root, bundle_path),
        "approval_gate": relpath(root, gate_path),
        "approval_file": relpath(root, target_path),
        "approval_file_written": wrote,
        "approval_valid": wrote and bool(approved),
        "approval": approval,
        "current_runspec_sha256": current_sha,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Validate the materialized approval file before any execution launcher."
            if wrote
            else "Keep Agent OS execution blocked until approval materialization is explicitly requested."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize an Agent OS RunSpec execution approval")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-bundle", default=DEFAULT_APPROVAL_BUNDLE)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--operator", default="")
    parser.add_argument("--accepted-risk", default="")
    parser.add_argument("--write-approval-file", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--now", default=None)
    parser.add_argument("--expires-in-hours", type=int, default=4)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = materialize(
        root=args.root,
        approval_bundle=args.approval_bundle,
        approval_gate=args.approval_gate,
        approved=args.approved,
        operator=args.operator,
        accepted_risk=args.accepted_risk,
        write_approval_file=args.write_approval_file,
        overwrite=args.overwrite,
        now=args.now,
        expires_in_hours=args.expires_in_hours,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
