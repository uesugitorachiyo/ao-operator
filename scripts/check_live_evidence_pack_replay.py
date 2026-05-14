#!/usr/bin/env python3
"""Gate live evidence-pack summaries on replay verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/live-evidence-pack-replay-gate/v1"
LIVE_SUMMARY_SCHEMA = "ao-operator/evidence-pack-live-run/v1"
ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/live-evidence-pack-replay-gate.json"


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc)}
    return value if isinstance(value, dict) else {"_parse_error": "top-level JSON is not an object"}


def _summary_paths(root: Path) -> list[Path]:
    return sorted(
        (root / "run-artifacts").glob("*/evidence-packs/evidence-pack-*-summary.json")
    )


def check_live_evidence_pack_replay(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in _summary_paths(root):
        relpath = _rel(root, path)
        body = _load_json(path)
        if body.get("_parse_error"):
            errors.append(f"summary_json_invalid:{relpath}:{body['_parse_error']}")
            summaries.append({"path": relpath, "verdict": "FAIL"})
            continue
        if body.get("schema") != LIVE_SUMMARY_SCHEMA:
            continue

        replay = body.get("replay")
        replay_verdict = replay.get("verdict") if isinstance(replay, dict) else None
        replay_checks = replay.get("checks") if isinstance(replay, dict) else None
        deterministic_task_count = (
            int(replay.get("deterministic_task_count") or 0)
            if isinstance(replay, dict)
            else 0
        )
        deterministic_command_execution = (
            replay_checks.get("deterministic_command_execution")
            if isinstance(replay_checks, dict)
            else None
        )
        summary = {
            "path": relpath,
            "run_id": body.get("run_id", ""),
            "verify_verdict": (
                body.get("verify", {}).get("verdict")
                if isinstance(body.get("verify"), dict)
                else None
            ),
            "replay_verdict": replay_verdict,
            "deterministic_task_count": deterministic_task_count,
            "deterministic_command_execution": deterministic_command_execution,
            "verdict": "PASS" if replay_verdict == "PASS" else "FAIL",
        }
        summaries.append(summary)
        if replay_verdict is None:
            errors.append(f"missing_replay_verdict:{relpath}")
        elif replay_verdict != "PASS":
            errors.append(f"replay_verdict_not_pass:{relpath}:{replay_verdict}")
        if deterministic_task_count > 0 and deterministic_command_execution != "PASS":
            errors.append(
                f"deterministic_command_execution_not_pass:{relpath}:{deterministic_command_execution}"
            )

    return {
        "schema": SCHEMA,
        "verdict": "PASS" if not errors else "FAIL",
        "summary_count": len(summaries),
        "summaries": summaries,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check live evidence-pack replay summaries")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = check_live_evidence_pack_replay(args.root)
    if args.write_output is not None:
        output = args.write_output if args.write_output.is_absolute() else args.root / args.write_output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["output"] = str(output)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report["verdict"])
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
