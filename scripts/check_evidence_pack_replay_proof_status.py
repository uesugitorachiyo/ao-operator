#!/usr/bin/env python3
"""Summarize whether evidence-pack replay proof is demo/release ready."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/evidence-pack-replay-proof-status/v1"
LIVE_SUMMARY_SCHEMA = "ao-operator/evidence-pack-live-run/v1"
ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/evidence-pack-replay-proof-status.json"


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
    return sorted((root / "run-artifacts").glob("*/evidence-packs/evidence-pack-*-summary.json"))


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int) else 0


def build_status(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in _summary_paths(root):
        relpath = _rel(root, path)
        body = _load_json(path)
        if body.get("_parse_error"):
            errors.append(f"summary_json_invalid:{relpath}:{body['_parse_error']}")
            summaries.append(
                {
                    "path": relpath,
                    "run_id": "",
                    "verify_verdict": None,
                    "replay_verdict": None,
                    "deterministic_task_count": 0,
                    "deterministic_command_execution": None,
                    "verdict": "FAIL",
                }
            )
            continue
        if body.get("schema") != LIVE_SUMMARY_SCHEMA:
            continue

        verify = body.get("verify") if isinstance(body.get("verify"), dict) else {}
        replay = body.get("replay") if isinstance(body.get("replay"), dict) else {}
        checks = replay.get("checks") if isinstance(replay.get("checks"), dict) else {}
        verify_verdict = verify.get("verdict")
        replay_verdict = replay.get("verdict")
        deterministic_task_count = _int(replay.get("deterministic_task_count"))
        deterministic_command_execution = checks.get("deterministic_command_execution")
        verdict = (
            "PASS"
            if verify_verdict == "PASS"
            and replay_verdict == "PASS"
            and (deterministic_task_count == 0 or deterministic_command_execution == "PASS")
            else "FAIL"
        )
        summaries.append(
            {
                "path": relpath,
                "run_id": body.get("run_id", ""),
                "verify_verdict": verify_verdict,
                "replay_verdict": replay_verdict,
                "deterministic_task_count": deterministic_task_count,
                "deterministic_command_execution": deterministic_command_execution,
                "verdict": verdict,
            }
        )
        if deterministic_task_count > 0 and deterministic_command_execution != "PASS":
            errors.append(f"deterministic_command_execution_not_pass:{relpath}:{deterministic_command_execution}")

    executed_deterministic = [
        summary
        for summary in summaries
        if summary["deterministic_task_count"] > 0
        and summary["verify_verdict"] == "PASS"
        and summary["replay_verdict"] == "PASS"
        and summary["deterministic_command_execution"] == "PASS"
    ]
    deterministic_summary_count = sum(1 for summary in summaries if summary["deterministic_task_count"] > 0)
    if not executed_deterministic:
        errors.append("no_executed_deterministic_live_evidence_pack_summary")

    proof_ready = not errors
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if proof_ready else "FAIL",
        "proof_ready": proof_ready,
        "summary_count": len(summaries),
        "deterministic_summary_count": deterministic_summary_count,
        "executed_deterministic_summary_count": len(executed_deterministic),
        "summaries": summaries,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Evidence pack replay proof is ready for v0.7 release-readiness review."
            if proof_ready
            else "Generate one live evidence pack with deterministic replay command execution PASS."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check evidence-pack replay proof status")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_status(args.root)
    if args.write_output is not None:
        output = args.write_output if args.write_output.is_absolute() else args.root / args.write_output
        write_output(output, report)
        report["output"] = str(output)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else report["verdict"])
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
