#!/usr/bin/env python3
"""Classify bounded live AO artifacts into an operator decision."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
BAD_RUN_IDS = {"", "none", "not-dispatched", "null"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def real_run_id(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in BAD_RUN_IDS)


def combined(paths: list[Path]) -> str:
    return "\n".join(read_text(path) for path in paths if path.is_file())


def artifact_state(slug: str, *, root: Path) -> dict[str, Any]:
    evaluation = root / "docs" / "evaluations" / f"{slug}-evaluation.md"
    status_dir = root / "run-artifacts" / slug
    status = status_dir / f"{slug}-status.md"
    events = sorted(status_dir.glob("*ao-events.md"))
    text = combined([evaluation, status, *events])
    status_text = read_text(status) if status.is_file() else ""
    eval_text = read_text(evaluation) if evaluation.is_file() else ""
    mode = first_match(r"^\s*Mode:\s*(\S+)\s*$", status_text)
    run_id = first_match(r"^\s*AO Run:\s*(\S+)\s*$", status_text) or first_match(
        r"^\s*AO Run:\s*(\S+)\s*$", eval_text
    )
    command_exit = first_match(r"\bAO command exit\s*=\s*(-?\d+)\b", text)
    completed = first_match(r"\bAO completed\s*=\s*(true|false)\b", text)
    rejected = bool(re.search(r"\bREJECTED\b", text, flags=re.IGNORECASE))
    blockers = not check_live_acceptance.blocker_free(text) if text else False
    return {
        "evaluation_exists": evaluation.is_file(),
        "status_exists": status.is_file(),
        "events_exist": bool(events),
        "evaluation": str(evaluation),
        "status": str(status),
        "events": [str(path) for path in events],
        "mode": mode or "",
        "ao_run": run_id or "",
        "ao_run_real": real_run_id(run_id),
        "ao_command_exit": command_exit or "",
        "ao_completed": completed or "",
        "rejected": rejected,
        "blockers_detected": blockers,
    }


def classify(slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    acceptance = check_live_acceptance.check_slug(slug, root=root)
    state = artifact_state(slug, root=root)
    if acceptance.get("verdict") == "PASS":
        classification = "ACCEPTED"
        exit_code = 0
        next_actions = [
            "Run validation commands one final time.",
            "Commit accepted bounded-live evidence only.",
        ]
    else:
        live_attempt_seen = (
            state["events_exist"]
            or state["ao_run_real"]
            or state["mode"] == "run"
            or bool(state["ao_command_exit"])
            or state["ao_completed"] in {"true", "false"}
        )
        failed_signal = (
            state["rejected"]
            or state["blockers_detected"]
            or (bool(state["ao_command_exit"]) and state["ao_command_exit"] != "0")
            or state["ao_completed"] == "false"
        )
        if live_attempt_seen or failed_signal:
            classification = "DIAGNOSTIC_REQUIRED"
            exit_code = 2
            next_actions = [
                "Stop before rerun.",
                "Preserve AO home diagnostics.",
                "Write or commit sanitized summaries only.",
                "Do not commit failed live artifacts as successful evidence.",
            ]
        else:
            classification = "PENDING_LIVE_RUN"
            exit_code = 0
            next_actions = [
                "Do not claim live success.",
                "Run the bounded live slice only after explicit operator approval.",
                "After live command exits, rerun this classifier before acceptance.",
            ]
    return {
        "schema": "ao-operator/live-outcome-classification/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if classification in {"ACCEPTED", "PENDING_LIVE_RUN"} else "FAIL",
        "classification": classification,
        "exit_code": exit_code,
        "slug": slug,
        "live_success": classification == "ACCEPTED",
        "commit_success_evidence_allowed": classification == "ACCEPTED",
        "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
        "acceptance": acceptance,
        "artifact_state": state,
        "next_actions": next_actions,
    }


def default_output_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-outcome-classification.json"


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"classification={payload['classification']}",
        f"live_success={str(payload['live_success']).lower()}",
        f"diagnostics_required={str(payload['diagnostics_required']).lower()}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify bounded live outcome artifacts")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument(
        "--write-output",
        nargs="?",
        const="",
        help="Write classification JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = classify(args.slug, root=args.root)
    if args.write_output is not None:
        output_path = Path(args.write_output) if args.write_output else default_output_path(args.root, args.slug)
        if not output_path.is_absolute():
            output_path = args.root / output_path
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
