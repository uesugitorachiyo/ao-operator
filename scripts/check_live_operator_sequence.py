#!/usr/bin/env python3
"""Verify the bounded-live operator sequence and artifact slice references."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import validate_operator_slices


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_PACKET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-packet.json"
DEFAULT_GATE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-gate.json"
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"
EXPECTED_SEQUENCE = [
    "14-verify-live-dispatch-packet",
    "15-check-live-dispatch-gate",
    "16-check-live-approval-readiness",
    "17-run-bounded-live-10",
    "18-classify-live-outcome",
    "19-plan-live-failure-diagnostics",
    "20-preserve-live-failure-diagnostics",
    "21-route-live-postrun",
    "22-guard-live-success-commit",
    "23-verify-live-operator-sequence",
    DEFAULT_ACCEPTANCE_SLICE,
    "25-prepare-25-slice-profile",
    "26-large-live-override-run",
]


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


def command_list(item: dict[str, Any]) -> list[str]:
    commands = item.get("commands", [])
    return [command for command in commands if isinstance(command, str)] if isinstance(commands, list) else []


def validate_sequence(data: dict[str, Any], *, live_slice: str, acceptance_slice: str) -> list[str]:
    errors: list[str] = []
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return ["manifest slices must be a list"]
    by_id = {item.get("id"): item for item in slices if isinstance(item, dict)}
    missing = [slice_id for slice_id in EXPECTED_SEQUENCE if slice_id not in by_id]
    if missing:
        errors.append("missing expected slices: " + ", ".join(missing))
        return errors

    orders = {slice_id: by_id[slice_id].get("order") for slice_id in EXPECTED_SEQUENCE}
    if any(not isinstance(value, int) for value in orders.values()):
        errors.append("all expected live sequence slices must have integer order")
        return errors
    ordered_ids = sorted(EXPECTED_SEQUENCE, key=lambda slice_id: int(orders[slice_id]))
    if ordered_ids != EXPECTED_SEQUENCE:
        errors.append("live operator sequence order is stale")

    live = by_id[live_slice]
    if live.get("live_provider") is not True:
        errors.append(f"{live_slice} must be live_provider=true")
    if not any("--run" in command.split() for command in command_list(live)):
        errors.append(f"{live_slice} must include --run")

    for slice_id in EXPECTED_SEQUENCE:
        item = by_id[slice_id]
        if slice_id in {live_slice, "26-large-live-override-run"}:
            continue
        if item.get("live_provider") is True:
            errors.append(f"{slice_id} must not be a live provider slice")
        if any("--run" in command.split() for command in command_list(item)):
            errors.append(f"{slice_id} must not include --run")

    if by_id[acceptance_slice].get("writes") not in ([], None):
        errors.append(f"{acceptance_slice} must not write artifacts")
    if by_id[acceptance_slice].get("order") <= by_id["23-verify-live-operator-sequence"].get("order"):
        errors.append("acceptance must run after the sequence verifier")
    if by_id["25-prepare-25-slice-profile"].get("order") <= by_id[acceptance_slice].get("order"):
        errors.append("25-slice profile preparation must run after acceptance")
    if by_id["26-large-live-override-run"].get("requires_override") is not True:
        errors.append("large live override run must require override")
    return errors


def check_artifacts(
    *,
    root: Path,
    packet_path: Path,
    gate_path: Path,
    acceptance_slice: str,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    try:
        packet = load_json(packet_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        packet = {}
        errors.append(f"dispatch packet unavailable: {exc}")
    try:
        gate = load_json(gate_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        gate = {}
        errors.append(f"dispatch gate unavailable: {exc}")

    post_acceptance = packet.get("post_run_acceptance", {}) if isinstance(packet.get("post_run_acceptance"), dict) else {}
    if packet and post_acceptance.get("slice_id") != acceptance_slice:
        errors.append(f"dispatch packet acceptance slice must be {acceptance_slice}")
    if packet and packet.get("live_providers_run") is not False:
        errors.append("dispatch packet must have live_providers_run=false")
    if packet and packet.get("dispatch_authorized") is not False:
        errors.append("dispatch packet must have dispatch_authorized=false")
    if gate and gate.get("acceptance_slice") != acceptance_slice:
        errors.append(f"dispatch gate acceptance slice must be {acceptance_slice}")
    if gate and gate.get("live_providers_run") is not False:
        errors.append("dispatch gate must have live_providers_run=false")
    if gate and gate.get("dispatch_authorized") is not False:
        errors.append("dispatch gate must have dispatch_authorized=false")
    return errors, packet, gate


def check_sequence(
    *,
    root: Path = ROOT,
    manifest: str | Path = DEFAULT_MANIFEST,
    packet: str | Path = DEFAULT_PACKET,
    gate: str | Path = DEFAULT_GATE,
    live_slice: str = DEFAULT_LIVE_SLICE,
    acceptance_slice: str = DEFAULT_ACCEPTANCE_SLICE,
) -> dict[str, Any]:
    manifest_path = resolve_path(root, manifest)
    packet_path = resolve_path(root, packet)
    gate_path = resolve_path(root, gate)
    errors: list[str] = []
    validation = validate_operator_slices.validate_path(manifest_path)
    if validation.get("verdict") != "PASS":
        errors.extend(str(error) for error in validation.get("errors", []))
        manifest_data: dict[str, Any] = {}
    else:
        manifest_data = validate_operator_slices.load_manifest(manifest_path)
        errors.extend(validate_sequence(manifest_data, live_slice=live_slice, acceptance_slice=acceptance_slice))

    artifact_errors, packet_payload, gate_payload = check_artifacts(
        root=root,
        packet_path=packet_path,
        gate_path=gate_path,
        acceptance_slice=acceptance_slice,
    )
    errors.extend(artifact_errors)

    return {
        "schema": "ao-operator/live-operator-sequence/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "manifest": relpath(root, manifest_path),
        "packet": relpath(root, packet_path),
        "gate": relpath(root, gate_path),
        "expected_sequence": EXPECTED_SEQUENCE,
        "live_slice": live_slice,
        "acceptance_slice": acceptance_slice,
        "slice_count": validation.get("slice_count"),
        "dispatch_authorized": packet_payload.get("dispatch_authorized"),
        "ready_for_operator_approval": gate_payload.get("ready_for_operator_approval"),
        "live_providers_run": False,
        "next_actions": [
            "Run live slice only after explicit operator approval.",
            "Run classifier, diagnostics, routing, and commit guard before acceptance.",
            "Run acceptance only after the route and guard allow it.",
        ],
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"live_slice={payload['live_slice']}",
        f"acceptance_slice={payload['acceptance_slice']}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def default_output_path(root: Path) -> Path:
    return root / "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-operator-sequence.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify bounded-live operator sequence")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--packet", default=DEFAULT_PACKET)
    parser.add_argument("--gate", default=DEFAULT_GATE)
    parser.add_argument("--live-slice", default=DEFAULT_LIVE_SLICE)
    parser.add_argument("--acceptance-slice", default=DEFAULT_ACCEPTANCE_SLICE)
    parser.add_argument(
        "--write-output",
        nargs="?",
        const="",
        help="Write sequence JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_sequence(
        root=args.root,
        manifest=args.manifest,
        packet=args.packet,
        gate=args.gate,
        live_slice=args.live_slice,
        acceptance_slice=args.acceptance_slice,
    )
    if args.write_output is not None:
        output_path = Path(args.write_output) if args.write_output else default_output_path(args.root)
        if not output_path.is_absolute():
            output_path = args.root / output_path
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
