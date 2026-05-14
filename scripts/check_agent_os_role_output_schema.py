#!/usr/bin/env python3
"""Validate Agent OS role output status schema."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-output-schema-validation.json"
STATUS_FIELDS = ["Result", "Artifact", "Evidence", "Concerns", "Blocker"]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


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


def validate_role_outputs(*, root: Path = ROOT, role_outputs: list[str | Path] | None = None) -> dict[str, Any]:
    paths = [resolve_path(root, item) for item in (role_outputs or [])]
    errors: list[str] = []
    for path in paths:
        data = load_json(path)
        role = str(data.get("role") or path.name)
        if data.get("schema") != "ao-operator/agent-os-role-output/v1":
            errors.append(f"{role} schema must be ao-operator/agent-os-role-output/v1")
        for field in STATUS_FIELDS:
            if field not in data:
                errors.append(f"{role} missing {field}")
        if str(data.get("full_transcript") or "").strip():
            errors.append(f"{role} contains full transcript")
    return {
        "schema": "ao-operator/agent-os-role-output-schema-validation/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "role_outputs_checked": len(paths),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS role output schema")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--role-output", action="append", default=[])
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = validate_role_outputs(root=args.root, role_outputs=args.role_output)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
