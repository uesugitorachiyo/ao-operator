#!/usr/bin/env python3
"""Validate the Mac-to-Ubuntu remote approval operations runbook."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNBOOK = "docs/runbooks/mac-ubuntu-remote-approval-operations.md"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-remote-approval-runbook.json"
SCHEMA = "ao-operator/mac-ubuntu-remote-approval-runbook/v1"

REQUIRED_ITEMS = [
    "FACTORY_V3_REMOTE_HOST",
    "pr_ready.py --ci --json",
    "check_mac_ubuntu_approval_artifact_parity.py",
    "check_mac_ubuntu_signed_approval_bundle_transfer.py",
    "check_mac_ubuntu_remote_approval_materialization_dry_run.py",
    "check_mac_ubuntu_remote_approval_revocation_rollback.py",
    "check_operator_guardrail_summary.py",
    "check_status_json_integrity.py",
    "redact_strict_public_artifacts.py --fail-on-changes --json",
    "remote_git_synced=true",
    "remote_cleanup_absent=true",
    "Do not run AO",
    "Do not dispatch provider CLIs",
    "Do not write a real repo approval file",
    "Do not copy private signing keys or provider credentials",
    "Do not preserve remote staging",
    "Commit only PASS evidence",
]

REQUIRED_TEXT_FOR_TESTS = """# Mac Ubuntu Remote Approval Operations Runbook

FACTORY_V3_REMOTE_HOST="${FACTORY_V3_REMOTE_HOST}"
python3 scripts/pr_ready.py --ci --json
python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_operator_guardrail_summary.py --write-output --json
python3 scripts/check_status_json_integrity.py --json
python3 scripts/redact_strict_public_artifacts.py --fail-on-changes --json

Expected evidence includes remote_git_synced=true and remote_cleanup_absent=true.

Do not run AO from this runbook.
Do not dispatch provider CLIs from this runbook.
Do not write a real repo approval file from this runbook.
Do not copy private signing keys or provider credentials.
Do not preserve remote staging.
Commit only PASS evidence.
"""


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


def check_runbook(*, root: Path = ROOT, runbook: str | Path = DEFAULT_RUNBOOK) -> dict[str, Any]:
    root = root.resolve()
    runbook_path = resolve_path(root, runbook)
    errors: list[str] = []
    text = ""
    if not runbook_path.is_file():
        errors.append("remote approval runbook is missing")
    else:
        text = runbook_path.read_text(encoding="utf-8")
    for item in REQUIRED_ITEMS:
        if item not in text:
            errors.append(f"remote approval runbook must mention {item}")
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "runbook": relpath(root, runbook_path),
        "required_item_count": len(REQUIRED_ITEMS),
        "missing_count": len(errors),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Remote approval runbook passes; execute only the documented no-provider evidence sequence."
            if not errors
            else "Fix the remote approval runbook before operating Mac-to-Ubuntu approval flows."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Mac-to-Ubuntu remote approval operations runbook")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runbook", default=DEFAULT_RUNBOOK)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_runbook(root=args.root, runbook=args.runbook)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
