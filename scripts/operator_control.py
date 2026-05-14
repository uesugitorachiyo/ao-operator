#!/usr/bin/env python3
"""OpenClaw-style operator controls for AO Operator gated runs.

The controls intentionally do not launch providers. They create auditable
operator records and surface the next safe AO Operator command from committed
gate evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import summarize_50_slice_operator_state


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
APPROVAL_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
DEFAULT_APPROVAL_PATH = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-approval.json"
DEFAULT_TARGET_SLICES = 50
DEFAULT_TARGET_TASKS = 107


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def audit_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "operator-controls" / "operator-audit.jsonl"


def append_audit(root: Path, slug: str, record: dict[str, Any]) -> Path:
    path = audit_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(json.dumps(record, sort_keys=True) + "\n")
    return path


def read_audit(root: Path, slug: str, limit: int = 20) -> list[dict[str, Any]]:
    path = audit_path(root, slug)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            records.append(data)
    return records[-max(0, limit) :]


def current_summary(root: Path, slug: str) -> dict[str, Any]:
    return summarize_50_slice_operator_state.summarize(root=root, slug=slug)


def base_payload(root: Path, slug: str, action: str) -> dict[str, Any]:
    summary = current_summary(root, slug)
    dispatch_authorized = bool(summary.get("dispatch_authorized")) if action == "approval" else False
    return {
        "schema": "ao-operator/operator-control/v1",
        "generated_at": utc_now(),
        "action": action,
        "slug": slug,
        "verdict": "PASS",
        "dispatch_authorized": dispatch_authorized,
        "live_providers_run": False,
        "current_state": summary.get("current_state"),
        "approval_status": summary.get("approval_status"),
        "next_safe_command": summary.get("next_safe_command"),
        "blockers": summary.get("blockers", []),
        "evidence_paths": summary.get("evidence_paths", {}),
    }


def record_action(root: Path, slug: str, payload: dict[str, Any], *, audit: bool) -> dict[str, Any]:
    if audit:
        path = append_audit(root, slug, payload)
        payload["audit_path"] = relpath(root, path)
    return payload


def status(*, root: Path = ROOT, slug: str = DEFAULT_SLUG, audit: bool = False) -> dict[str, Any]:
    payload = base_payload(root, slug, "status")
    payload["dispatch_authorized"] = False
    return record_action(root, slug, payload, audit=audit)


def submit(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    source: str,
    intent: str,
    audit: bool = True,
) -> dict[str, Any]:
    payload = base_payload(root, slug, "submit")
    payload.update(
        {
            "source": source,
            "intent": intent,
            "queued_for_factory": True,
            "dispatch_authorized": False,
        }
    )
    return record_action(root, slug, payload, audit=audit)


def observe(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    audit: bool = True,
    audit_limit: int = 20,
) -> dict[str, Any]:
    payload = base_payload(root, slug, "observe")
    payload["dispatch_authorized"] = False
    payload["recent_audit"] = read_audit(root, slug, limit=audit_limit)
    return record_action(root, slug, payload, audit=audit)


def cancel(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    target_run: str,
    reason: str,
    audit: bool = True,
) -> dict[str, Any]:
    payload = base_payload(root, slug, "cancel")
    payload.update(
        {
            "target_run": target_run,
            "reason": reason,
            "cancel_requested": True,
            "dispatch_authorized": False,
            "provider_cancel_invoked": False,
        }
    )
    return record_action(root, slug, payload, audit=audit)


def approval_file_payload(
    *,
    approved_by: str,
    approval_source: str,
    target_slices: int,
    target_tasks: int,
) -> dict[str, Any]:
    return {
        "schema": "ao-operator/50-slice-live-approval/v1",
        "approved": True,
        "approved_at": utc_now(),
        "approved_by": approved_by,
        "approval_source": approval_source,
        "approval_env": APPROVAL_ENV,
        "target_slices": target_slices,
        "target_tasks": target_tasks,
    }


def approval(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    approved_by: str,
    approval_source: str,
    target_slices: int = DEFAULT_TARGET_SLICES,
    target_tasks: int = DEFAULT_TARGET_TASKS,
    env: dict[str, str] | None = None,
    write_approval_file: bool = False,
    approval_path: str | Path = DEFAULT_APPROVAL_PATH,
    overwrite: bool = False,
    audit: bool = True,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    output_path = resolve_path(root, approval_path)
    errors: list[str] = []
    if not approved_by.strip():
        errors.append("approved_by is required")
    if not approval_source.strip():
        errors.append("approval_source is required")
    if target_slices >= DEFAULT_TARGET_SLICES and env.get(APPROVAL_ENV) != "1":
        errors.append(f"{APPROVAL_ENV}=1 is required for {target_slices}-slice live approval")
    if write_approval_file and output_path.exists() and not overwrite:
        errors.append(f"approval file already exists: {relpath(root, output_path)}")

    if errors:
        payload = base_payload(root, slug, "approval")
        payload.update(
            {
                "verdict": "BLOCKED",
                "dispatch_authorized": False,
                "approval_file_written": False,
                "errors": errors,
                "target_slices": target_slices,
                "target_tasks": target_tasks,
            }
        )
        return record_action(root, slug, payload, audit=audit)

    if write_approval_file:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                approval_file_payload(
                    approved_by=approved_by,
                    approval_source=approval_source,
                    target_slices=target_slices,
                    target_tasks=target_tasks,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    payload = base_payload(root, slug, "approval")
    if write_approval_file:
        summary = current_summary(root, slug)
        payload.update(
            {
                "current_state": summary.get("current_state"),
                "approval_status": summary.get("approval_status"),
                "next_safe_command": summary.get("next_safe_command"),
                "blockers": summary.get("blockers", []),
                "evidence_paths": summary.get("evidence_paths", {}),
                "dispatch_authorized": bool(summary.get("dispatch_authorized")),
            }
        )
    payload.update(
        {
            "approval_file_written": write_approval_file,
            "approval_file": relpath(root, output_path),
            "approved_by": approved_by,
            "approval_source": approval_source,
            "target_slices": target_slices,
            "target_tasks": target_tasks,
        }
    )
    return record_action(root, slug, payload, audit=audit)


def print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"verdict={payload['verdict']}")
    print(f"action={payload['action']}")
    print(f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}")
    print(f"next_safe_command={payload.get('next_safe_command', '')}")
    for error in payload.get("errors", []):
        print(f"error={error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AO Operator operator controls")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="action", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--audit", action="store_true")

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--source", required=True)
    submit_parser.add_argument("--intent", required=True)
    submit_parser.add_argument("--no-audit", action="store_true")

    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument("--audit-limit", type=int, default=20)
    observe_parser.add_argument("--no-audit", action="store_true")

    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument("--target-run", required=True)
    cancel_parser.add_argument("--reason", required=True)
    cancel_parser.add_argument("--no-audit", action="store_true")

    approval_parser = subparsers.add_parser("approval")
    approval_parser.add_argument("--approved-by", required=True)
    approval_parser.add_argument("--approval-source", required=True)
    approval_parser.add_argument("--target-slices", type=int, default=DEFAULT_TARGET_SLICES)
    approval_parser.add_argument("--target-tasks", type=int, default=DEFAULT_TARGET_TASKS)
    approval_parser.add_argument("--write-approval-file", action="store_true")
    approval_parser.add_argument("--approval-path", default=DEFAULT_APPROVAL_PATH)
    approval_parser.add_argument("--overwrite", action="store_true")
    approval_parser.add_argument("--no-audit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action == "status":
        payload = status(root=args.root, slug=args.slug, audit=args.audit)
    elif args.action == "submit":
        payload = submit(root=args.root, slug=args.slug, source=args.source, intent=args.intent, audit=not args.no_audit)
    elif args.action == "observe":
        payload = observe(root=args.root, slug=args.slug, audit=not args.no_audit, audit_limit=args.audit_limit)
    elif args.action == "cancel":
        payload = cancel(
            root=args.root,
            slug=args.slug,
            target_run=args.target_run,
            reason=args.reason,
            audit=not args.no_audit,
        )
    elif args.action == "approval":
        payload = approval(
            root=args.root,
            slug=args.slug,
            approved_by=args.approved_by,
            approval_source=args.approval_source,
            target_slices=args.target_slices,
            target_tasks=args.target_tasks,
            write_approval_file=args.write_approval_file,
            approval_path=args.approval_path,
            overwrite=args.overwrite,
            audit=not args.no_audit,
        )
    else:
        parser.error(f"unknown action {args.action}")
    print_payload(payload, as_json=args.json)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
