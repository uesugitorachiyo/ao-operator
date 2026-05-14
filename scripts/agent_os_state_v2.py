#!/usr/bin/env python3
"""Load, migrate, and write Agent OS state v2 snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_SCHEMA_V1 = "ao-operator/agent-os-state/v1"
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"
ROLE_GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
DEFAULT_STATE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-mission-router-state.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json"


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


def normalize_state(snapshot: dict[str, Any], *, source: str) -> dict[str, Any]:
    schema = str(snapshot.get("schema") or "")
    errors: list[str] = []
    if schema not in {STATE_SCHEMA_V1, STATE_SCHEMA_V2}:
        errors.append(f"unsupported state schema: {schema or 'missing'}")

    return {
        "schema": STATE_SCHEMA_V2,
        "previous_schema": schema,
        "role_graph_schema": str(snapshot.get("role_graph_schema") or ROLE_GRAPH_SCHEMA),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "source": source,
        "lane": snapshot.get("lane", ""),
        "route": snapshot.get("route", {}),
        "blockers": snapshot.get("blockers", []),
        "evidence_paths": snapshot.get("evidence_paths", []),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "migration_notes": [
            "v2 state explicitly links the Agent OS role graph schema.",
            "dispatch_authorized and live_providers_run are always reset during load/migration.",
        ],
        "next_safe_command": (
            "Use this state v2 snapshot as the router architecture compatibility baseline."
            if not errors
            else "Fix Agent OS state schema before router architecture changes."
        ),
    }


def load_or_migrate_state(*, root: Path = ROOT, state: str | Path = DEFAULT_STATE) -> dict[str, Any]:
    path = resolve_path(root, state)
    return normalize_state(load_json(path), source=relpath(root, path))


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load or migrate Agent OS state v2")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = load_or_migrate_state(root=args.root, state=args.state)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
