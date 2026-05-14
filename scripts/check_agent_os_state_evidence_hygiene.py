#!/usr/bin/env python3
"""Check Agent OS state evidence hygiene before architecture runs."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/agent-os-state-evidence-hygiene/v1"
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"
ROLE_GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-evidence-hygiene.json"
DEFAULT_STATE_FILES = [
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json",
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json",
]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


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


def git_status_lines(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return completed.stdout.splitlines()


def dirty_state_artifacts_from(lines: list[str]) -> list[str]:
    dirty: list[str] = []
    for line in lines:
        if not line.startswith("?? "):
            continue
        path = line[3:].strip()
        name = Path(path).name
        if path.startswith("run-artifacts/") and name.startswith("agent-os") and "state" in name and name.endswith(".json"):
            dirty.append(path)
    return dirty


def check_state_file(root: Path, rel: str) -> tuple[str, list[str]]:
    path = resolve_path(root, rel)
    display = relpath(root, path)
    payload = load_json(path)
    blockers: list[str] = []
    if not path.is_file():
        blockers.append(f"{display} is missing")
        return display, blockers
    if payload.get("schema") != STATE_SCHEMA_V2:
        blockers.append(f"{display} schema must be {STATE_SCHEMA_V2}")
    if payload.get("dispatch_authorized") is not False:
        blockers.append(f"{display} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        blockers.append(f"{display} live_providers_run must remain false")
    if payload.get("role_graph_schema") != ROLE_GRAPH_SCHEMA:
        blockers.append(f"{display} role_graph_schema must be {ROLE_GRAPH_SCHEMA}")
    blockers_value = payload.get("blockers")
    if isinstance(blockers_value, list) and blockers_value:
        blockers.append(f"{display} blockers must be empty")
    return display, blockers


def check_hygiene(
    *,
    root: Path = ROOT,
    state_files: list[str] | None = None,
    git_status_lines: list[str] | None = None,
) -> dict[str, Any]:
    selected = state_files or DEFAULT_STATE_FILES
    blockers: list[str] = []
    file_checks: dict[str, str] = {}
    for state_file in selected:
        display, file_blockers = check_state_file(root, state_file)
        blockers.extend(file_blockers)
        file_checks[display] = "PASS" if not file_blockers else "FAIL"
    dirty = dirty_state_artifacts_from(git_status_lines if git_status_lines is not None else globals()["git_status_lines"](root))
    if dirty:
        blockers.append("untracked Agent OS state artifacts must be cleaned or intentionally staged")
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not blockers else "FAIL",
        "state_file_count": len(selected),
        "file_checks": file_checks,
        "dirty_state_artifacts": dirty,
        "blockers": blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "State evidence hygiene passes; continue the next gated Agent OS architecture slice."
            if not blockers
            else "Clean or stage Agent OS state evidence before continuing architecture work."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS state evidence hygiene")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state-file", action="append", default=[])
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_hygiene(root=args.root, state_files=args.state_file or None)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
