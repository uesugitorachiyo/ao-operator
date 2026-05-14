#!/usr/bin/env python3
"""Plan bounded-live failure diagnostics without copying raw AO homes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_AO_HOME = "/tmp/ao-operator-ao-remote-transfer-v2-stress-live"
VALID_CLASSIFICATIONS = {"ACCEPTED", "DIAGNOSTIC_REQUIRED", "PENDING_LIVE_RUN"}


def default_classification_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-outcome-classification.json"


def default_plan_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-failure-diagnostics-plan.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def diagnostics_commands(*, slug: str, ao_home: str) -> list[str]:
    snapshots = f"run-artifacts/{slug}/failure-snapshots"
    return [
        f"mkdir -p {snapshots}",
        f"cp -a {ao_home} {snapshots}/ao-home-$(date +%Y%m%d-%H%M%S)",
        f"python3 scripts/summarize_ao_failure.py {ao_home} --json",
    ]


def plan(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    ao_home: str = DEFAULT_AO_HOME,
    classification_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_classification = (
        resolve_path(root, classification_path)
        if classification_path is not None
        else default_classification_path(root, slug)
    )
    errors: list[str] = []
    try:
        classification_payload = load_json(resolved_classification)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        classification_payload = {}
        classification = ""
        errors.append(f"classification unavailable: {exc}")
    else:
        classification = str(classification_payload.get("classification") or "")
        if classification not in VALID_CLASSIFICATIONS:
            errors.append(f"classification must be one of {sorted(VALID_CLASSIFICATIONS)}")

    diagnostics_required = classification == "DIAGNOSTIC_REQUIRED"
    accepted = classification == "ACCEPTED"
    pending = classification == "PENDING_LIVE_RUN"
    copy_allowed = diagnostics_required and not errors

    if diagnostics_required:
        next_actions = [
            "Stop before rerun.",
            "Preserve the local AO home if it exists.",
            "Generate a sanitized failure summary before deciding what to commit.",
            "Do not commit failed live artifacts as successful evidence.",
        ]
    elif pending:
        next_actions = [
            "Do not preserve failure diagnostics before a live attempt.",
            "Run the bounded live slice only after explicit operator approval.",
            "Rerun the classifier after the live command exits.",
        ]
    elif accepted:
        next_actions = [
            "Do not preserve failure diagnostics for an accepted live run.",
            "Run the acceptance slice and commit accepted live evidence only if it passes.",
        ]
    else:
        next_actions = ["Fix or regenerate live-outcome classification before planning diagnostics."]

    return {
        "schema": "ao-operator/live-failure-diagnostics-plan/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "slug": slug,
        "classification": classification,
        "classification_artifact": relpath(root, resolved_classification),
        "diagnostics_required": diagnostics_required,
        "copy_allowed": copy_allowed,
        "live_providers_run": False,
        "raw_snapshot_commit_allowed": False,
        "success_evidence_commit_allowed": accepted,
        "ao_home": ao_home,
        "raw_snapshot_policy": [
            "AO homes are local diagnostics only.",
            "Raw ao-home-* snapshots must remain ignored and must not be committed.",
            "Commit sanitized summaries only when diagnostics are needed.",
        ],
        "commands": diagnostics_commands(slug=slug, ao_home=ao_home) if copy_allowed else [],
        "summary_command": f"python3 scripts/summarize_ao_failure.py {ao_home} --json",
        "recommended_summary_path": f"run-artifacts/{slug}/failure-snapshots/<timestamp>-summary.json",
        "next_actions": next_actions,
        "source": {
            "classification_verdict": classification_payload.get("verdict"),
            "diagnostics_required": classification_payload.get("diagnostics_required"),
            "commit_success_evidence_allowed": classification_payload.get("commit_success_evidence_allowed"),
        },
    }


def write_plan(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"classification={payload['classification']}",
        f"diagnostics_required={str(payload['diagnostics_required']).lower()}",
        f"copy_allowed={str(payload['copy_allowed']).lower()}",
        f"raw_snapshot_commit_allowed={str(payload['raw_snapshot_commit_allowed']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan bounded-live diagnostic preservation without copying AO homes")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--ao-home", default=DEFAULT_AO_HOME)
    parser.add_argument("--classification", default=None, help="Path to live-outcome classification JSON")
    parser.add_argument(
        "--write-plan",
        nargs="?",
        const="",
        help="Write plan JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = plan(
        root=args.root,
        slug=args.slug,
        ao_home=args.ao_home,
        classification_path=args.classification,
    )
    if args.write_plan is not None:
        plan_path = Path(args.write_plan) if args.write_plan else default_plan_path(args.root, args.slug)
        if not plan_path.is_absolute():
            plan_path = args.root / plan_path
        write_plan(plan_path, payload)
        payload["plan"] = str(plan_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
