#!/usr/bin/env python3
"""Check AO Operator live AO acceptance artifacts for a slug."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BAD_RUN_IDS = {"", "none", "not-dispatched", "null"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def has_real_run_id(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in BAD_RUN_IDS)


def combined_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.is_file():
            chunks.append(read_text(path))
    return "\n".join(chunks)


def blocker_free(text: str) -> bool:
    if re.search(r"^\s*(Verdict|Factory Verdict):\s*REJECTED\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
        return False
    blocked = first_match(r"^\s*-\s*Blocked:\s*(true|false)\s*$", text)
    if blocked and blocked.lower() == "true":
        return False
    if re.search(r"^\s*Blockers:\s*(none|false)\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
        return True
    section = re.search(r"(?ims)^Blockers:\s*\n(?P<body>.*?)(?:\n^##\s+|\Z)", text)
    if section:
        bullets = re.findall(r"(?im)^\s*-\s*(.+?)\s*$", section.group("body"))
        if bullets:
            return all(item.lower() in {"none", "false"} for item in bullets)
    return blocked == "false"


def check_slug(slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    eval_path = root / "docs" / "evaluations" / f"{slug}-evaluation.md"
    status_dir = root / "run-artifacts" / slug
    status_path = status_dir / f"{slug}-status.md"
    event_paths = sorted(status_dir.glob("*ao-events.md"))
    all_paths = [eval_path, status_path, *event_paths]
    text = combined_text(all_paths)
    blocker_text = combined_text([eval_path, status_path])

    verdict = first_match(r"^\s*Verdict:\s*(\S+)\s*$", read_text(eval_path)) if eval_path.is_file() else None
    mode = first_match(r"^\s*Mode:\s*(\S+)\s*$", read_text(status_path)) if status_path.is_file() else None
    run_id = first_match(r"^\s*AO Run:\s*(\S+)\s*$", read_text(status_path)) if status_path.is_file() else None
    if not run_id and eval_path.is_file():
        run_id = first_match(r"^\s*AO Run:\s*(\S+)\s*$", read_text(eval_path))
    command_exit = first_match(r"\bAO command exit\s*=\s*(-?\d+)\b", text)
    completed = first_match(r"\bAO completed\s*=\s*(true|false)\b", text)

    checks = [
        {
            "id": "evaluation.exists",
            "status": "PASS" if eval_path.is_file() else "FAIL",
            "message": str(eval_path),
        },
        {
            "id": "status.exists",
            "status": "PASS" if status_path.is_file() else "FAIL",
            "message": str(status_path),
        },
        {
            "id": "events.exists",
            "status": "PASS" if event_paths else "FAIL",
            "message": ",".join(str(path) for path in event_paths) if event_paths else "missing",
        },
        {
            "id": "verdict.accepted",
            "status": "PASS" if verdict == "ACCEPTED" else "FAIL",
            "message": verdict or "missing",
        },
        {
            "id": "mode.run",
            "status": "PASS" if mode == "run" else "FAIL",
            "message": mode or "missing",
        },
        {
            "id": "ao_run.real",
            "status": "PASS" if has_real_run_id(run_id) else "FAIL",
            "message": run_id or "missing",
        },
        {
            "id": "ao_command_exit.zero",
            "status": "PASS" if command_exit == "0" else "FAIL",
            "message": command_exit or "missing",
        },
        {
            "id": "ao_completed.true",
            "status": "PASS" if completed == "true" else "FAIL",
            "message": completed or "missing",
        },
        {
            "id": "blockers.none",
            "status": "PASS" if blocker_free(blocker_text) else "FAIL",
            "message": "no blockers" if blocker_free(blocker_text) else "blocker evidence missing or rejected",
        },
    ]
    verdict_out = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    return {
        "verdict": verdict_out,
        "slug": slug,
        "evaluation": str(eval_path),
        "status": str(status_path),
        "events": [str(path) for path in event_paths],
        "checks": checks,
    }


def text_report(payload: dict[str, Any]) -> str:
    lines = [f"verdict={payload['verdict']}", f"slug={payload['slug']}"]
    for check in payload["checks"]:
        lines.append(f"{check['status']} {check['id']}: {check['message']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check live AO acceptance artifacts for a AO Operator slug")
    parser.add_argument("--slug", default="remote-transfer-v2-stress-live", help="Factory slug to check")
    parser.add_argument("--root", type=Path, default=ROOT, help="Factory repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    payload = check_slug(args.slug, root=args.root)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
