#!/usr/bin/env python3
"""Validate the Agent OS approval materialization runbook."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNBOOK = "docs/runbooks/agent-os-approval-materialization.md"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-runbook.json"
SCHEMA = "ao-operator/agent-os-approval-runbook/v1"

REQUIRED_ITEMS = [
    "materialize_agent_os_approval.py",
    "--write-approval-file",
    "validate_agent_os_runspec_execution_approval.py",
    "check_agent_os_approval_lifecycle.py",
    "run_agent_os_runspec_execution.py",
    "cleanup_agent_os_approval.py",
    "Do not run AO",
    "Do not dispatch provider CLIs",
    "Do not commit approval files",
]

REQUIRED_TEXT_FOR_TESTS = """# Agent OS Approval Materialization Runbook

python3 scripts/materialize_agent_os_approval.py --write-approval-file --approved --operator OPERATOR --accepted-risk RISK
python3 scripts/validate_agent_os_runspec_execution_approval.py --json
python3 scripts/check_agent_os_approval_lifecycle.py --json
python3 scripts/run_agent_os_runspec_execution.py --json
python3 scripts/cleanup_agent_os_approval.py --apply --force --json

Do not run AO from this runbook.
Do not dispatch provider CLIs from this runbook.
Do not commit approval files.
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
        errors.append("approval runbook is missing")
    else:
        text = runbook_path.read_text(encoding="utf-8")
    for item in REQUIRED_ITEMS:
        if item not in text:
            errors.append(f"approval runbook must mention {item}")
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
            "Approval runbook passes; materialization still requires explicit operator action."
            if not errors
            else "Fix the approval materialization runbook before approving execution."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS approval materialization runbook")
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
