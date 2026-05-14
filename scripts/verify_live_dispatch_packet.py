#!/usr/bin/env python3
"""Verify a bounded live dispatch packet before any provider execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_live_dispatch_packet
import validate_operator_slices


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-packet.json"
DEFAULT_MANIFEST = build_live_dispatch_packet.DEFAULT_MANIFEST
DEFAULT_READINESS_SUMMARY = build_live_dispatch_packet.DEFAULT_READINESS_SUMMARY
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def list_field(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def expected_dispatch_command(manifest: str, live_slice_id: str) -> str:
    return (
        "python3 scripts/run_operator_slice.py "
        f"{manifest} --slice {live_slice_id} --execute --allow-live --json"
    )


def compare_list(errors: list[str], field: str, actual: Any, expected: list[str]) -> None:
    if actual != expected:
        errors.append(f"{field} does not match manifest")


def verify_packet(
    *,
    root: Path = ROOT,
    packet_path: str = DEFAULT_PACKET,
    manifest: str = DEFAULT_MANIFEST,
    readiness_summary: str = DEFAULT_READINESS_SUMMARY,
    live_slice_id: str = DEFAULT_LIVE_SLICE,
    acceptance_slice_id: str = DEFAULT_ACCEPTANCE_SLICE,
) -> dict[str, Any]:
    errors: list[str] = []
    resolved_packet = resolve_path(root, packet_path)
    resolved_manifest = resolve_path(root, manifest)
    resolved_readiness = resolve_path(root, readiness_summary)

    try:
        packet = load_json(resolved_packet)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        packet = {}
        errors.append(f"packet unavailable: {exc}")

    validation = validate_operator_slices.validate_path(resolved_manifest)
    if validation.get("verdict") != "PASS":
        errors.extend(str(error) for error in validation.get("errors", []))
        manifest_data: dict[str, Any] = {}
    else:
        manifest_data = validate_operator_slices.load_manifest(resolved_manifest)

    live_slice = build_live_dispatch_packet.find_slice(manifest_data, live_slice_id) or {}
    acceptance_slice = build_live_dispatch_packet.find_slice(manifest_data, acceptance_slice_id) or {}
    if not live_slice:
        errors.append(f"live slice {live_slice_id} not found")
    if not acceptance_slice:
        errors.append(f"acceptance slice {acceptance_slice_id} not found")

    try:
        readiness = load_json(resolved_readiness)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        readiness = {}
        errors.append(f"readiness summary unavailable: {exc}")
    else:
        errors.extend(build_live_dispatch_packet.validate_readiness(readiness))

    if packet:
        if packet.get("schema") != "ao-operator/live-dispatch-packet/v1":
            errors.append("packet schema is not ao-operator/live-dispatch-packet/v1")
        if packet.get("verdict") != "PASS":
            errors.append("packet verdict must be PASS")
        if packet.get("errors") not in ([], None):
            errors.append("packet errors must be empty")
        if packet.get("dispatch_authorized") is not False:
            errors.append("packet dispatch_authorized must be false")
        if packet.get("live_providers_run") is not False:
            errors.append("packet live_providers_run must be false")
        if packet.get("requires_explicit_operator_approval") is not True:
            errors.append("packet must require explicit operator approval")

    live_packet = packet.get("live_slice", {}) if isinstance(packet.get("live_slice"), dict) else {}
    if live_packet.get("id") != live_slice_id:
        errors.append(f"packet live_slice.id must be {live_slice_id}")
    live_commands = build_live_dispatch_packet.command_list(live_slice)
    expected_live_command = live_commands[0] if len(live_commands) == 1 else ""
    if live_packet.get("command") != expected_live_command:
        errors.append("packet live command does not match manifest")
    if live_packet.get("task_count") != live_slice.get("task_count"):
        errors.append("packet live task_count does not match manifest")
    compare_list(errors, "packet live reads", live_packet.get("reads"), list_field(live_slice, "reads"))
    compare_list(errors, "packet live writes", live_packet.get("writes"), list_field(live_slice, "writes"))
    compare_list(errors, "packet live evidence", live_packet.get("evidence"), list_field(live_slice, "evidence"))
    compare_list(errors, "packet live stop_rules", live_packet.get("stop_rules"), list_field(live_slice, "stop_rules"))

    dispatch = packet.get("operator_slice_dispatch", {})
    if not isinstance(dispatch, dict):
        dispatch = {}
    if dispatch.get("command") != expected_dispatch_command(manifest, live_slice_id):
        errors.append("packet operator dispatch command does not match expected operator slice command")

    acceptance_packet = packet.get("post_run_acceptance", {})
    if not isinstance(acceptance_packet, dict):
        acceptance_packet = {}
    if acceptance_packet.get("slice_id") != acceptance_slice_id:
        errors.append(f"packet post_run_acceptance.slice_id must be {acceptance_slice_id}")
    compare_list(
        errors,
        "packet acceptance commands",
        acceptance_packet.get("commands"),
        build_live_dispatch_packet.command_list(acceptance_slice),
    )
    compare_list(
        errors,
        "packet acceptance evidence",
        acceptance_packet.get("evidence"),
        list_field(acceptance_slice, "evidence"),
    )
    compare_list(
        errors,
        "packet acceptance stop_rules",
        acceptance_packet.get("stop_rules"),
        list_field(acceptance_slice, "stop_rules"),
    )

    preflight = packet.get("preflight", {})
    if not isinstance(preflight, dict):
        preflight = {}
    expected_summary = str(
        resolved_readiness.relative_to(root) if resolved_readiness.is_relative_to(root) else resolved_readiness
    )
    if preflight.get("summary") != expected_summary:
        errors.append("packet preflight summary path does not match readiness summary")
    for key in ("generated_at", "verdict", "mode", "live_providers_run"):
        if preflight.get(key) != readiness.get(key):
            errors.append(f"packet preflight {key} does not match readiness summary")
    if preflight.get("checks") != build_live_dispatch_packet.readiness_checks(readiness):
        errors.append("packet preflight checks do not match readiness summary")

    return {
        "schema": "ao-operator/live-dispatch-packet-verification/v1",
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "packet": str(resolved_packet.relative_to(root) if resolved_packet.is_relative_to(root) else resolved_packet),
        "manifest": str(resolved_manifest.relative_to(root) if resolved_manifest.is_relative_to(root) else resolved_manifest),
        "readiness_summary": str(
            resolved_readiness.relative_to(root) if resolved_readiness.is_relative_to(root) else resolved_readiness
        ),
        "live_slice": live_slice_id,
        "acceptance_slice": acceptance_slice_id,
        "dispatch_authorized": packet.get("dispatch_authorized") if packet else None,
        "live_providers_run": packet.get("live_providers_run") if packet else None,
    }


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"packet={payload['packet']}",
        f"live_slice={payload['live_slice']}",
        f"acceptance_slice={payload['acceptance_slice']}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a bounded live dispatch packet")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--packet", default=DEFAULT_PACKET)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--readiness-summary", default=DEFAULT_READINESS_SUMMARY)
    parser.add_argument("--live-slice", default=DEFAULT_LIVE_SLICE)
    parser.add_argument("--acceptance-slice", default=DEFAULT_ACCEPTANCE_SLICE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = verify_packet(
        root=args.root,
        packet_path=args.packet,
        manifest=args.manifest,
        readiness_summary=args.readiness_summary,
        live_slice_id=args.live_slice,
        acceptance_slice_id=args.acceptance_slice,
    )
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
