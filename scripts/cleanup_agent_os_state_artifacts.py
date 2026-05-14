#!/usr/bin/env python3
"""Plan or remove stale untracked Agent OS state diagnostic artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/agent-os-state-stale-cleanup/v1"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-stale-cleanup.json"


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


def cleanup_candidates_from(lines: list[str], *, excluded: set[str] | None = None) -> list[str]:
    excluded = excluded or set()
    candidates: list[str] = []
    for line in lines:
        if not line.startswith("?? "):
            continue
        path = line[3:].strip()
        if path in excluded:
            continue
        name = Path(path).name
        if path.startswith("run-artifacts/") and name.startswith("agent-os") and "state" in name and name.endswith(".json"):
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def safe_candidate_path(root: Path, rel: str) -> tuple[Path | None, str | None]:
    path = resolve_path(root, rel)
    try:
        path.relative_to(root)
    except ValueError:
        return None, f"candidate escapes repository root: {rel}"
    if not rel.startswith("run-artifacts/"):
        return None, f"candidate outside run-artifacts: {rel}"
    return path, None


def plan_cleanup(
    *,
    root: Path = ROOT,
    git_status_lines: list[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    lines = git_status_lines if git_status_lines is not None else globals()["git_status_lines"](root)
    candidates = cleanup_candidates_from(lines, excluded={DEFAULT_OUTPUT})
    blockers: list[str] = []
    removed: list[str] = []

    for rel in candidates:
        path, error = safe_candidate_path(root, rel)
        if error:
            blockers.append(error)
            continue
        assert path is not None
        if apply:
            if not path.is_file():
                blockers.append(f"candidate missing before cleanup: {rel}")
                continue
            path.unlink()
            removed.append(relpath(root, path))

    verdict = "PASS" if not blockers else "FAIL"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "mode": "apply" if apply else "dry-run",
        "candidate_count": len(candidates),
        "removed_count": len(removed),
        "candidates": candidates,
        "removed": removed,
        "blockers": blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Run state evidence hygiene after cleanup."
            if apply and verdict == "PASS"
            else "Review candidates, then rerun with --apply if they are stale untracked diagnostics."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or remove stale untracked Agent OS state artifacts")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true", help="Remove selected untracked diagnostic artifacts")
    parser.add_argument("--git-status-line", action="append", default=[], help="Test hook: provide git status porcelain lines")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = plan_cleanup(
        root=args.root,
        git_status_lines=args.git_status_line or None,
        apply=args.apply,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
