#!/usr/bin/env python3
"""Build a local dispatch packet for the bounded live Remote Transfer run."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import validate_operator_slices


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"
DEFAULT_LIVE_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_AO_RUNTIME_PATH = "../ao-runtime"
DEFAULT_READINESS_SUMMARY = (
    "run-artifacts/remote-transfer-v2-stress-live/readiness/bounded-live-preflight-summary.json"
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def find_slice(data: dict[str, Any], slice_id: str) -> dict[str, Any] | None:
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return None
    for item in slices:
        if isinstance(item, dict) and item.get("id") == slice_id:
            return item
    return None


def command_list(item: dict[str, Any]) -> list[str]:
    commands = item.get("commands", [])
    return [command for command in commands if isinstance(command, str)] if isinstance(commands, list) else []


def field_list(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def readiness_checks(summary: dict[str, Any]) -> list[dict[str, Any]]:
    checks = summary.get("checks", [])
    if not isinstance(checks, list):
        return []
    compact: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        compact.append(
            {
                "id": check.get("id"),
                "status": check.get("status"),
                "expected_exit": check.get("expected_exit"),
                "actual_exit": check.get("actual_exit"),
                "expected_verdict": check.get("expected_verdict"),
                "actual_verdict": check.get("actual_verdict"),
            }
        )
    return compact


def validate_readiness(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("schema") != "ao-operator/bounded-live-readiness-summary/v1":
        errors.append("readiness summary schema is not ao-operator/bounded-live-readiness-summary/v1")
    if summary.get("verdict") != "PASS":
        errors.append("readiness summary verdict must be PASS")
    if summary.get("mode") != "pre-live-readiness":
        errors.append("readiness summary mode must be pre-live-readiness")
    if summary.get("live_providers_run") is not False:
        errors.append("readiness summary must have live_providers_run=false")
    for check in readiness_checks(summary):
        if check.get("status") != "PASS":
            errors.append(f"readiness check {check.get('id')} must be PASS")
    return errors


def build_packet(
    *,
    root: Path = ROOT,
    manifest: str = DEFAULT_MANIFEST,
    live_slice_id: str = DEFAULT_LIVE_SLICE,
    acceptance_slice_id: str = DEFAULT_ACCEPTANCE_SLICE,
    readiness_summary: str = DEFAULT_READINESS_SUMMARY,
    live_slug: str = DEFAULT_LIVE_SLUG,
    ao_runtime_path: str = DEFAULT_AO_RUNTIME_PATH,
) -> dict[str, Any]:
    manifest_path = resolve_path(root, manifest)
    readiness_path = resolve_path(root, readiness_summary)
    errors: list[str] = []

    validation = validate_operator_slices.validate_path(manifest_path)
    if validation.get("verdict") != "PASS":
        errors.extend(str(error) for error in validation.get("errors", []))
        manifest_data: dict[str, Any] = {}
    else:
        manifest_data = validate_operator_slices.load_manifest(manifest_path)

    live_slice = find_slice(manifest_data, live_slice_id)
    acceptance_slice = find_slice(manifest_data, acceptance_slice_id)
    if live_slice is None:
        errors.append(f"live slice {live_slice_id} not found")
        live_slice = {}
    if acceptance_slice is None:
        errors.append(f"acceptance slice {acceptance_slice_id} not found")
        acceptance_slice = {}

    if live_slice and live_slice.get("live_provider") is not True:
        errors.append(f"live slice {live_slice_id} must be live_provider=true")
    if live_slice and live_slice.get("requires_override") is True:
        errors.append(f"live slice {live_slice_id} must not require override for the bounded dispatch packet")
    live_commands = command_list(live_slice)
    if len(live_commands) != 1:
        errors.append(f"live slice {live_slice_id} must declare exactly one command")
    elif "--run" not in live_commands[0].split():
        errors.append(f"live slice {live_slice_id} command must include --run")

    try:
        readiness = load_json(readiness_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        readiness = {}
        errors.append(f"readiness summary unavailable: {exc}")
    else:
        errors.extend(validate_readiness(readiness))

    acceptance_commands = command_list(acceptance_slice)
    if not acceptance_commands:
        errors.append(f"acceptance slice {acceptance_slice_id} must declare acceptance commands")

    packet = {
        "schema": "ao-operator/live-dispatch-packet/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "live_providers_run": False,
        "dispatch_authorized": False,
        "requires_explicit_operator_approval": True,
        "slug": live_slug,
        "manifest": str(manifest_path.relative_to(root) if manifest_path.is_relative_to(root) else manifest_path),
        "live_slice": {
            "id": live_slice.get("id"),
            "order": live_slice.get("order"),
            "task_count": live_slice.get("task_count"),
            "command": live_commands[0] if live_commands else "",
            "reads": field_list(live_slice, "reads"),
            "writes": field_list(live_slice, "writes"),
            "evidence": field_list(live_slice, "evidence"),
            "stop_rules": field_list(live_slice, "stop_rules"),
        },
        "operator_slice_dispatch": {
            "command": (
                "python3 scripts/run_operator_slice.py "
                f"{manifest} --slice {live_slice_id} --execute --allow-live --json"
            ),
            "note": "Requires explicit operator approval before use.",
        },
        "environment": {
            "exports": [
                f"export FACTORY_V3_AO_RUNTIME_PATH={ao_runtime_path}",
                'export PATH="$FACTORY_V3_AO_RUNTIME_PATH/target/release:$PATH"',
            ],
            "forbidden": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        },
        "preflight": {
            "summary": str(readiness_path.relative_to(root) if readiness_path.is_relative_to(root) else readiness_path),
            "generated_at": readiness.get("generated_at"),
            "verdict": readiness.get("verdict"),
            "mode": readiness.get("mode"),
            "live_providers_run": readiness.get("live_providers_run"),
            "checks": readiness_checks(readiness),
        },
        "post_run_acceptance": {
            "slice_id": acceptance_slice.get("id"),
            "commands": acceptance_commands,
            "evidence": field_list(acceptance_slice, "evidence"),
            "stop_rules": field_list(acceptance_slice, "stop_rules"),
        },
        "failure_preservation": {
            "commands": [
                "mkdir -p run-artifacts/remote-transfer-v2-stress-live/failure-snapshots",
                (
                    "cp -a /tmp/ao-operator-ao-remote-transfer-v2-stress-live "
                    "run-artifacts/remote-transfer-v2-stress-live/failure-snapshots/"
                    "ao-home-$(date +%Y%m%d-%H%M%S)"
                ),
                (
                    "python3 scripts/summarize_ao_failure.py "
                    "/tmp/ao-operator-ao-remote-transfer-v2-stress-live --json"
                ),
            ],
            "notes": [
                "Stop before rerun.",
                "Commit sanitized summaries only.",
                "Do not treat failed live artifacts as successful evidence.",
            ],
        },
        "negative_constraints": manifest_data.get("negative_constraints", []),
        "sensitive_fields": manifest_data.get("sensitive_fields", []),
    }
    return packet


def default_packet_path(root: Path, live_slug: str) -> Path:
    return root / "run-artifacts" / live_slug / "dispatch" / "live-dispatch-packet.json"


def write_packet(path: Path, packet: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(packet: dict[str, Any]) -> str:
    live = packet["live_slice"]
    return "\n".join(
        [
            f"verdict={packet['verdict']}",
            f"slug={packet['slug']}",
            f"dispatch_authorized={str(packet['dispatch_authorized']).lower()}",
            f"live_providers_run={str(packet['live_providers_run']).lower()}",
            f"live_slice={live['id']}",
            f"command={live['command']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a bounded live dispatch packet without running providers")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--live-slice", default=DEFAULT_LIVE_SLICE)
    parser.add_argument("--acceptance-slice", default=DEFAULT_ACCEPTANCE_SLICE)
    parser.add_argument("--readiness-summary", default=DEFAULT_READINESS_SUMMARY)
    parser.add_argument("--live-slug", default=DEFAULT_LIVE_SLUG)
    parser.add_argument("--ao-runtime-path", default=os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", DEFAULT_AO_RUNTIME_PATH))
    parser.add_argument(
        "--write-packet",
        nargs="?",
        const="",
        help="Write packet JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    packet = build_packet(
        root=args.root,
        manifest=args.manifest,
        live_slice_id=args.live_slice,
        acceptance_slice_id=args.acceptance_slice,
        readiness_summary=args.readiness_summary,
        live_slug=args.live_slug,
        ao_runtime_path=args.ao_runtime_path,
    )
    if args.write_packet is not None:
        packet_path = Path(args.write_packet) if args.write_packet else default_packet_path(args.root, args.live_slug)
        if not packet_path.is_absolute():
            packet_path = args.root / packet_path
        write_packet(packet_path, packet)
        packet["packet"] = str(packet_path)
    print(json.dumps(packet, indent=2, sort_keys=True) if args.json else text_report(packet))
    return 0 if packet["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
