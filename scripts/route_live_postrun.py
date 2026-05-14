#!/usr/bin/env python3
"""Route bounded-live post-run artifacts to the next operator slice."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_CLASSIFIER_SLICE = "18-classify-live-outcome"
DEFAULT_PLAN_SLICE = "19-plan-live-failure-diagnostics"
DEFAULT_PRESERVE_SLICE = "20-preserve-live-failure-diagnostics"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
VALID_CLASSIFICATIONS = {"ACCEPTED", "DIAGNOSTIC_REQUIRED", "PENDING_LIVE_RUN"}


def dispatch_dir(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch"


def default_classification_path(root: Path, slug: str) -> Path:
    return dispatch_dir(root, slug) / "live-outcome-classification.json"


def default_plan_path(root: Path, slug: str) -> Path:
    return dispatch_dir(root, slug) / "live-failure-diagnostics-plan.json"


def default_preservation_path(root: Path, slug: str) -> Path:
    return dispatch_dir(root, slug) / "live-failure-diagnostics-preservation.json"


def default_output_path(root: Path, slug: str) -> Path:
    return dispatch_dir(root, slug) / "live-postrun-routing.json"


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


def optional_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return load_json(path), None
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {}, str(exc)


def validate_plan(plan: dict[str, Any], classification: str) -> list[str]:
    errors: list[str] = []
    if plan.get("schema") != "ao-operator/live-failure-diagnostics-plan/v1":
        errors.append("diagnostics plan schema is invalid")
    if plan.get("classification") != classification:
        errors.append("diagnostics plan classification does not match outcome classification")
    if plan.get("raw_snapshot_commit_allowed") is not False:
        errors.append("diagnostics plan must keep raw_snapshot_commit_allowed=false")
    if plan.get("live_providers_run") is not False:
        errors.append("diagnostics plan must have live_providers_run=false")
    if classification == "DIAGNOSTIC_REQUIRED":
        if plan.get("diagnostics_required") is not True:
            errors.append("diagnostics plan must have diagnostics_required=true")
        if plan.get("copy_allowed") is not True:
            errors.append("diagnostics plan must have copy_allowed=true")
    return errors


def validate_preservation(preservation: dict[str, Any], classification: str) -> list[str]:
    errors: list[str] = []
    if not preservation:
        return errors
    if preservation.get("schema") != "ao-operator/live-failure-diagnostics-preservation/v1":
        errors.append("preservation report schema is invalid")
    if preservation.get("classification") != classification:
        errors.append("preservation report classification does not match outcome classification")
    if preservation.get("raw_snapshot_commit_allowed") is not False:
        errors.append("preservation report must keep raw_snapshot_commit_allowed=false")
    if preservation.get("live_providers_run") is not False:
        errors.append("preservation report must have live_providers_run=false")
    return errors


def route(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    classification_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    preservation_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_classification = (
        resolve_path(root, classification_path) if classification_path is not None else default_classification_path(root, slug)
    )
    resolved_plan = resolve_path(root, plan_path) if plan_path is not None else default_plan_path(root, slug)
    resolved_preservation = (
        resolve_path(root, preservation_path) if preservation_path is not None else default_preservation_path(root, slug)
    )
    errors: list[str] = []
    warnings: list[str] = []

    try:
        classification_payload = load_json(resolved_classification)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        classification_payload = {}
        classification = ""
        errors.append(f"outcome classification unavailable: {exc}")
    else:
        classification = str(classification_payload.get("classification") or "")
        if classification not in VALID_CLASSIFICATIONS:
            errors.append(f"classification must be one of {sorted(VALID_CLASSIFICATIONS)}")

    plan, plan_error = optional_json(resolved_plan)
    if plan_error and classification != "ACCEPTED":
        errors.append(f"diagnostics plan unavailable: {plan_error}")
    elif plan_error:
        warnings.append(f"diagnostics plan unavailable: {plan_error}")
    elif classification in VALID_CLASSIFICATIONS and classification != "ACCEPTED":
        errors.extend(validate_plan(plan, classification))

    preservation, preservation_error = optional_json(resolved_preservation)
    if preservation_error:
        warnings.append(f"preservation report unavailable: {preservation_error}")
    elif classification in VALID_CLASSIFICATIONS and classification != "ACCEPTED":
        errors.extend(validate_preservation(preservation, classification))

    acceptance = check_live_acceptance.check_slug(slug, root=root)
    if classification == "ACCEPTED" and acceptance.get("verdict") != "PASS":
        errors.append("accepted classification requires live acceptance PASS")
    if classification in {"PENDING_LIVE_RUN", "DIAGNOSTIC_REQUIRED"} and acceptance.get("verdict") == "PASS":
        errors.append("non-accepted classification conflicts with live acceptance PASS")

    summary_written = preservation.get("summary_written") is True if preservation else False
    raw_copied = preservation.get("raw_snapshot_copied") is True if preservation else False
    if classification == "PENDING_LIVE_RUN":
        route_name = "WAIT_FOR_LIVE_RUN"
        next_slice = DEFAULT_LIVE_SLICE
        next_command = (
            "python3 scripts/run_operator_slice.py examples/remote-transfer-v2-stress/operator-slices.json "
            f"--slice {DEFAULT_LIVE_SLICE} --execute --allow-live --json"
        )
    elif classification == "DIAGNOSTIC_REQUIRED" and summary_written:
        route_name = "DIAGNOSTICS_PRESERVED"
        next_slice = None
        next_command = "Review sanitized diagnostics before any rerun."
    elif classification == "DIAGNOSTIC_REQUIRED":
        route_name = "PRESERVE_DIAGNOSTICS"
        next_slice = DEFAULT_PRESERVE_SLICE
        next_command = (
            "python3 scripts/run_operator_slice.py examples/remote-transfer-v2-stress/operator-slices.json "
            f"--slice {DEFAULT_PRESERVE_SLICE} --execute --json"
        )
    elif classification == "ACCEPTED":
        route_name = "RUN_ACCEPTANCE"
        next_slice = DEFAULT_ACCEPTANCE_SLICE
        next_command = (
            "python3 scripts/run_operator_slice.py examples/remote-transfer-v2-stress/operator-slices.json "
            f"--slice {DEFAULT_ACCEPTANCE_SLICE} --execute --json"
        )
    else:
        route_name = "UNKNOWN"
        next_slice = DEFAULT_CLASSIFIER_SLICE
        next_command = "python3 scripts/classify_live_outcome.py --write-output --json"

    if raw_copied:
        warnings.append("raw AO snapshot was copied; keep it ignored and commit sanitized summaries only")

    return {
        "schema": "ao-operator/live-postrun-routing/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "slug": slug,
        "classification": classification,
        "route": route_name,
        "next_slice": next_slice,
        "next_command": next_command,
        "commit_success_evidence_allowed": classification == "ACCEPTED" and acceptance.get("verdict") == "PASS",
        "diagnostics_required": classification == "DIAGNOSTIC_REQUIRED",
        "summary_written": summary_written,
        "raw_snapshot_copied": raw_copied,
        "raw_snapshot_commit_allowed": False,
        "live_providers_run": False,
        "artifacts": {
            "classification": relpath(root, resolved_classification),
            "plan": relpath(root, resolved_plan),
            "preservation": relpath(root, resolved_preservation),
        },
        "acceptance": {
            "verdict": acceptance.get("verdict"),
            "checks": acceptance.get("checks", []),
        },
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"classification={payload['classification']}",
        f"route={payload['route']}",
        f"next_slice={payload['next_slice']}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    lines.extend(f"warning={warning}" for warning in payload.get("warnings", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route bounded-live post-run artifacts to the next operator slice")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--classification", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--preservation", default=None)
    parser.add_argument(
        "--write-output",
        nargs="?",
        const="",
        help="Write routing JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = route(
        root=args.root,
        slug=args.slug,
        classification_path=args.classification,
        plan_path=args.plan,
        preservation_path=args.preservation,
    )
    if args.write_output is not None:
        output_path = Path(args.write_output) if args.write_output else default_output_path(args.root, args.slug)
        if not output_path.is_absolute():
            output_path = args.root / output_path
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
