#!/usr/bin/env python3
"""Prove approval audit archive and restore without mutating the source log."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_agent_os_approval_audit_retention


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_AUDIT_LOG = f"{STATUS_ROOT}/agent-os-approval-audit.jsonl"
DEFAULT_FIXTURE_ROOT = Path("/tmp/ao-operator-agent-os-approval-audit-archive-restore")
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-audit-archive-restore.json"
SCHEMA = "ao-operator/agent-os-approval-audit-archive-restore/v1"
MARKER = ".ao-operator-agent-os-approval-audit-archive-restore"


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


def reset_fixture(path: Path) -> None:
    if path.exists():
        marker = path / MARKER
        if not marker.is_file():
            raise RuntimeError(f"fixture root exists without marker: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER).write_text("AO Operator approval audit archive restore fixture\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_archive_restore(
    *,
    root: Path = ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    audit_log: str | Path = DEFAULT_AUDIT_LOG,
) -> dict[str, Any]:
    root = root.resolve()
    fixture_root = fixture_root.resolve()
    audit_path = resolve_path(root, audit_log)
    errors: list[str] = []
    events, read_errors = check_agent_os_approval_audit_retention.read_events(audit_path)
    errors.extend(read_errors)
    errors.extend(check_agent_os_approval_audit_retention.validate_events(events))
    archive_path = fixture_root / "archive" / audit_path.name
    restored_path = fixture_root / "restore" / audit_path.name
    source_sha = ""
    restored_sha = ""
    archive_created = False
    restore_verified = False
    if not errors:
        try:
            reset_fixture(fixture_root)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            restored_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audit_path, archive_path)
            archive_created = archive_path.is_file()
            source_sha = sha256_file(audit_path)
            archive_sha = sha256_file(archive_path)
            shutil.copy2(archive_path, restored_path)
            restored_sha = sha256_file(restored_path)
            restore_verified = source_sha == archive_sha == restored_sha
            if not restore_verified:
                errors.append("archive restore sha256 verification failed")
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc))

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture": "isolated-temp",
        "audit_log": relpath(root, audit_path),
        "event_count": len(events),
        "archive_created": archive_created,
        "restore_verified": restore_verified,
        "source_sha256": source_sha,
        "restored_sha256": restored_sha,
        "source_mutated": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval audit archive and restore proof passes; archive-before-truncate can be operated manually."
            if not errors
            else "Fix approval audit archive and restore proof before rotating audit logs."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove Agent OS approval audit archive and restore")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--audit-log", default=DEFAULT_AUDIT_LOG)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_archive_restore(root=args.root, fixture_root=args.fixture_root, audit_log=args.audit_log)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
