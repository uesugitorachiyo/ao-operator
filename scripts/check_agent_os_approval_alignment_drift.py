#!/usr/bin/env python3
"""Check Agent OS approval artifacts carry provider alignment fields."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = [
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json",
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json",
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json",
    "run-artifacts/remote-transfer-v2-stress-live/approved-execution-fixture/approval-validation.json",
]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-alignment-drift.json"


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


def artifact_errors(root: Path, rel: str, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not data:
        return [f"{rel} is missing or invalid JSON"]
    if not str(data.get("provider_profile") or "").strip():
        errors.append(f"{rel} missing provider_profile")
    if data.get("provider_profile_checked") is not True:
        errors.append(f"{rel} provider_profile_checked must be true")
    if data.get("provider_profile_matches") is not True:
        errors.append(f"{rel} provider_profile_matches must be true")
    if data.get("provider_mismatches") not in ([], None):
        errors.append(f"{rel} provider_mismatches must be empty")
    if data.get("dispatch_authorized") is not False:
        errors.append(f"{rel} dispatch_authorized must be false")
    if data.get("live_providers_run") is not False:
        errors.append(f"{rel} live_providers_run must be false")
    return errors


def check_drift(
    *,
    root: Path = ROOT,
    artifact_paths: list[str] | None = None,
) -> dict[str, Any]:
    artifacts = artifact_paths or DEFAULT_ARTIFACTS
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    for artifact in artifacts:
        path = resolve_path(root, artifact)
        rel = relpath(root, path)
        data = load_json(path)
        item_errors = artifact_errors(root, rel, data)
        errors.extend(item_errors)
        results.append(
            {
                "path": rel,
                "schema": data.get("schema", ""),
                "provider_profile": data.get("provider_profile", ""),
                "provider_profile_checked": data.get("provider_profile_checked") is True,
                "provider_profile_matches": data.get("provider_profile_matches") is True,
                "provider_mismatch_count": len(data.get("provider_mismatches") or []),
                "verdict": "PASS" if not item_errors else "FAIL",
                "errors": item_errors,
            }
        )
    return {
        "schema": "ao-operator/agent-os-approval-alignment-drift/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "artifact_count": len(artifacts),
        "artifacts": results,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Approval alignment drift check passes; keep execution blocked without explicit approval."
            if not errors
            else "Restore provider alignment fields before Agent OS execution approval work."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS approval provider-alignment drift")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_drift(root=args.root, artifact_paths=args.artifact or None)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
