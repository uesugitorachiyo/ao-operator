#!/usr/bin/env python3
"""Preserve bounded-live failure diagnostics only when the plan permits it."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import summarize_ao_failure


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_AO_HOME = "/tmp/ao-operator-ao-remote-transfer-v2-stress-live"


def default_plan_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-failure-diagnostics-plan.json"


def default_report_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-failure-diagnostics-preservation.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    target = path.relative_to(root) if path.is_relative_to(root) else Path(path)
    return target.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


_REDACTED_AO_HOME = "/tmp/[REDACTED_AO_HOME]"
_BACKSLASH_TAIL_AFTER_AO_HOME = re.compile(
    r"(/tmp/\[REDACTED_AO_HOME\])((?:\\[A-Za-z0-9._\-]+)+)"
)


def redact_ao_home(value: object, ao_home: str) -> object:
    if isinstance(value, str):
        text = value
        # Replace both OS-native and POSIX/Windows-form ao_home so the
        # redacted output is byte-identical regardless of which form
        # callers stored.
        variants = {
            ao_home,
            ao_home.replace("\\", "/"),
            ao_home.replace("/", "\\"),
        }
        for variant in variants:
            if variant:
                text = text.replace(variant, _REDACTED_AO_HOME)
        # Normalize Windows-style path tails that follow the placeholder
        # (e.g. /tmp/[REDACTED_AO_HOME]\runs\r-test\events.jsonl) so JSON
        # consumers parse identically across OSes.
        text = _BACKSLASH_TAIL_AFTER_AO_HOME.sub(
            lambda m: m.group(1) + m.group(2).replace("\\", "/"),
            text,
        )
        return text
    if isinstance(value, list):
        return [redact_ao_home(item, ao_home) for item in value]
    if isinstance(value, dict):
        return {key: redact_ao_home(item, ao_home) for key, item in value.items()}
    return value


def snapshot_dir(root: Path, slug: str, timestamp: str) -> Path:
    return root / "run-artifacts" / slug / "failure-snapshots" / f"ao-home-{timestamp}"


def summary_path(root: Path, slug: str, timestamp: str) -> Path:
    return root / "run-artifacts" / slug / "failure-snapshots" / f"ao-home-{timestamp}-summary.json"


def validate_plan(plan: dict[str, Any], *, slug: str) -> list[str]:
    errors: list[str] = []
    if plan.get("schema") != "ao-operator/live-failure-diagnostics-plan/v1":
        errors.append("plan schema must be ao-operator/live-failure-diagnostics-plan/v1")
    if plan.get("slug") != slug:
        errors.append(f"plan slug must be {slug}")
    if plan.get("live_providers_run") is not False:
        errors.append("plan must have live_providers_run=false")
    if plan.get("raw_snapshot_commit_allowed") is not False:
        errors.append("plan must have raw_snapshot_commit_allowed=false")
    return errors


def preserve(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    ao_home: str = DEFAULT_AO_HOME,
    plan_path: str | Path | None = None,
    execute: bool = False,
    copy_raw: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    resolved_plan = resolve_path(root, plan_path) if plan_path is not None else default_plan_path(root, slug)
    errors: list[str] = []
    try:
        plan = load_json(resolved_plan)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        plan = {}
        errors.append(f"diagnostics plan unavailable: {exc}")
    else:
        errors.extend(validate_plan(plan, slug=slug))

    copy_allowed = plan.get("copy_allowed") is True and not errors
    diagnostics_required = plan.get("diagnostics_required") is True and not errors
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = timestamp or generated_at.strftime("%Y%m%d-%H%M%S")

    if errors:
        verdict = "FAIL"
        next_actions = ["Regenerate the diagnostics plan before preserving failure evidence."]
    elif not diagnostics_required:
        verdict = "PASS"
        next_actions = ["No failure diagnostics are required for the current classification."]
    elif not execute:
        verdict = "BLOCKED"
        next_actions = ["Rerun with --execute after confirming the failed live attempt should be preserved."]
    else:
        verdict = "PASS"
        next_actions = ["Review the sanitized summary before committing diagnostic evidence."]

    summary_written = False
    raw_snapshot_copied = False
    summary_output: str | None = None
    raw_snapshot_output: str | None = None
    summary: dict[str, Any] | None = None
    primary_normalized_reason = ""
    normalized_reason_counts: dict[str, object] = {}
    if verdict == "PASS" and diagnostics_required and execute:
        ao_path = Path(ao_home)
        try:
            events = summarize_ao_failure.latest_events_path(ao_path)
            summary = summarize_ao_failure.summarize_events(events, first_failed=3)
        except (FileNotFoundError, OSError) as exc:
            errors.append(f"AO failure events unavailable: {exc}")
            verdict = "FAIL"
        else:
            summary = redact_ao_home(summary, ao_home)
            primary_normalized_reason = str(summary.get("primary_normalized_reason") or "")
            reason_counts = summary.get("normalized_reason_counts")
            if isinstance(reason_counts, dict):
                normalized_reason_counts = reason_counts
            summary_file = summary_path(root, slug, stamp)
            summary_file.parent.mkdir(parents=True, exist_ok=True)
            summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            summary_written = True
            summary_output = relpath(root, summary_file)
            if copy_raw:
                raw_dir = snapshot_dir(root, slug, stamp)
                try:
                    shutil.copytree(ao_path, raw_dir)
                except OSError as exc:
                    errors.append(f"raw AO snapshot copy failed: {exc}")
                    verdict = "FAIL"
                else:
                    raw_snapshot_copied = True
                    raw_snapshot_output = relpath(root, raw_dir)

    return {
        "schema": "ao-operator/live-failure-diagnostics-preservation/v1",
        "generated_at": generated_at.isoformat(),
        "verdict": verdict,
        "errors": errors,
        "slug": slug,
        "classification": plan.get("classification", ""),
        "diagnostics_required": diagnostics_required,
        "copy_allowed": copy_allowed,
        "execute": execute,
        "copy_raw_requested": copy_raw,
        "summary_written": summary_written,
        "raw_snapshot_copied": raw_snapshot_copied,
        "raw_snapshot_commit_allowed": False,
        "live_providers_run": False,
        "ao_home": "/tmp/[REDACTED_AO_HOME]",
        "plan": relpath(root, resolved_plan),
        "summary": summary_output,
        "raw_snapshot": raw_snapshot_output,
        "primary_normalized_reason": primary_normalized_reason,
        "normalized_reason_counts": normalized_reason_counts,
        "summary_payload": summary,
        "next_actions": next_actions,
    }


def write_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"classification={payload['classification']}",
        f"diagnostics_required={str(payload['diagnostics_required']).lower()}",
        f"summary_written={str(payload['summary_written']).lower()}",
        f"raw_snapshot_copied={str(payload['raw_snapshot_copied']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard and preserve bounded-live failure diagnostics")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--ao-home", default=DEFAULT_AO_HOME)
    parser.add_argument("--plan", default=None, help="Path to diagnostics plan JSON")
    parser.add_argument("--execute", action="store_true", help="Write sanitized summary when diagnostics are required")
    parser.add_argument("--copy-raw", action="store_true", help="Also copy the ignored raw AO home after --execute")
    parser.add_argument("--timestamp", default=None, help="Override timestamp for deterministic tests")
    parser.add_argument(
        "--write-report",
        nargs="?",
        const="",
        help="Write preservation report JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = preserve(
        root=args.root,
        slug=args.slug,
        ao_home=args.ao_home,
        plan_path=args.plan,
        execute=args.execute,
        copy_raw=args.copy_raw,
        timestamp=args.timestamp,
    )
    if args.write_report is not None:
        report_path = Path(args.write_report) if args.write_report else default_report_path(args.root, args.slug)
        if not report_path.is_absolute():
            report_path = args.root / report_path
        write_report(report_path, payload)
        payload["report"] = str(report_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    if payload["verdict"] == "PASS":
        return 0
    if payload["verdict"] == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
