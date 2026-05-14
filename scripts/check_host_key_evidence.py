#!/usr/bin/env python3
"""Validate host-key evidence requirements before remote DAST approval."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/host-key-evidence/v1"
DEFAULT_DOC = "docs/sdd/41-host-key-evidence-gate.md"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/host-key-evidence.json"

CHECKS = {
    "known_hosts": ["known_hosts", "ssh-keygen -F"],
    "fingerprint": ["fingerprint", "ssh-keyscan"],
    "strict_ssh": ["StrictHostKeyChecking=yes", "UserKnownHostsFile"],
    "no_opportunistic_trust": ["accept-new", "Do not use"],
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def summarize(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    body = read_text(root / DEFAULT_DOC)
    blockers: list[str] = []
    checks: dict[str, dict[str, Any]] = {}
    for check_id, terms in CHECKS.items():
        missing = [term for term in terms if term.lower() not in body.lower()]
        documented = not missing
        if not documented:
            blockers.append(f"{check_id}: missing " + ", ".join(missing))
        checks[check_id] = {
            "documented": documented,
            "required_terms": terms,
            "missing_terms": missing,
        }

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "document": DEFAULT_DOC,
        "verdict": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "checks": checks,
        "host_key_evidence_required": True,
        "remote_dast_authorized": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Collect reviewed known_hosts fingerprint evidence before remote DAST approval."
            if not blockers
            else "Fix host-key evidence documentation before remote DAST approval."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate host-key evidence gate")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(args.root)
    if args.write_output is not None:
        output = Path(args.write_output)
        if not output.is_absolute():
            output = args.root / output
        write_output(output, payload)
        payload["output"] = output.relative_to(args.root).as_posix() if output.is_relative_to(args.root) else str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
