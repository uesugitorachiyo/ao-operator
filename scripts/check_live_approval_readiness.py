#!/usr/bin/env python3
"""Check whether bounded-live execution is ready for explicit operator approval."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"
DEFAULT_READINESS = "run-artifacts/remote-transfer-v2-stress-live/readiness/bounded-live-preflight-summary.json"
DEFAULT_PACKET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-packet.json"
DEFAULT_GATE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-gate.json"
DEFAULT_ROUTE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-postrun-routing.json"
DEFAULT_SUCCESS_GUARD = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-success-commit-guard.json"
DEFAULT_SEQUENCE = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-operator-sequence.json"


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


def read_artifact(errors: list[str], path: Path, label: str) -> dict[str, Any]:
    try:
        return load_json(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{label} unavailable: {exc}")
        return {}


def readiness_checks(readiness: dict[str, Any]) -> dict[str, Any]:
    checks = readiness.get("checks", [])
    if not isinstance(checks, list):
        return {}
    return {str(check.get("id")): check for check in checks if isinstance(check, dict)}


def check_approval_readiness(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    live_slice: str = DEFAULT_LIVE_SLICE,
    acceptance_slice: str = DEFAULT_ACCEPTANCE_SLICE,
    readiness_path: str | Path = DEFAULT_READINESS,
    packet_path: str | Path = DEFAULT_PACKET,
    gate_path: str | Path = DEFAULT_GATE,
    route_path: str | Path = DEFAULT_ROUTE,
    success_guard_path: str | Path = DEFAULT_SUCCESS_GUARD,
    sequence_path: str | Path = DEFAULT_SEQUENCE,
) -> dict[str, Any]:
    paths = {
        "readiness": resolve_path(root, readiness_path),
        "packet": resolve_path(root, packet_path),
        "gate": resolve_path(root, gate_path),
        "route": resolve_path(root, route_path),
        "success_guard": resolve_path(root, success_guard_path),
        "sequence": resolve_path(root, sequence_path),
    }
    errors: list[str] = []
    readiness = read_artifact(errors, paths["readiness"], "readiness summary")
    packet = read_artifact(errors, paths["packet"], "dispatch packet")
    gate = read_artifact(errors, paths["gate"], "dispatch gate")
    route = read_artifact(errors, paths["route"], "postrun route")
    success_guard = read_artifact(errors, paths["success_guard"], "success commit guard")
    sequence = read_artifact(errors, paths["sequence"], "operator sequence")

    checks = readiness_checks(readiness)
    live_block = checks.get("live_slice.blocked_without_allow_live", {})
    if readiness and readiness.get("verdict") != "PASS":
        errors.append("readiness summary must be PASS")
    if readiness and readiness.get("live_providers_run") is not False:
        errors.append("readiness summary must have live_providers_run=false")
    if live_block and live_block.get("status") != "PASS":
        errors.append("live slice must be blocked without --allow-live")
    if packet and packet.get("verdict") != "PASS":
        errors.append("dispatch packet must be PASS")
    if packet and packet.get("dispatch_authorized") is not False:
        errors.append("dispatch packet must have dispatch_authorized=false")
    if packet and packet.get("live_providers_run") is not False:
        errors.append("dispatch packet must have live_providers_run=false")
    live_packet = packet.get("live_slice", {}) if isinstance(packet.get("live_slice"), dict) else {}
    if live_packet and live_packet.get("id") != live_slice:
        errors.append(f"dispatch packet live slice must be {live_slice}")
    packet_acceptance = packet.get("post_run_acceptance", {}) if isinstance(packet.get("post_run_acceptance"), dict) else {}
    if packet_acceptance and packet_acceptance.get("slice_id") != acceptance_slice:
        errors.append(f"dispatch packet acceptance slice must be {acceptance_slice}")
    if gate and gate.get("verdict") != "PASS":
        errors.append("dispatch gate must be PASS")
    if gate and gate.get("ready_for_operator_approval") is not True:
        errors.append("dispatch gate must have ready_for_operator_approval=true")
    if gate and gate.get("dispatch_authorized") is not False:
        errors.append("dispatch gate must have dispatch_authorized=false")
    if gate and gate.get("live_providers_run") is not False:
        errors.append("dispatch gate must have live_providers_run=false")
    if gate and gate.get("live_slice") != live_slice:
        errors.append(f"dispatch gate live slice must be {live_slice}")
    if gate and gate.get("acceptance_slice") != acceptance_slice:
        errors.append(f"dispatch gate acceptance slice must be {acceptance_slice}")
    if route and route.get("verdict") != "PASS":
        errors.append("postrun route must be PASS")
    if route and route.get("route") != "WAIT_FOR_LIVE_RUN":
        errors.append("postrun route must be WAIT_FOR_LIVE_RUN before approval")
    if route and route.get("next_slice") != live_slice:
        errors.append(f"postrun route next_slice must be {live_slice}")
    if route and route.get("commit_success_evidence_allowed") is not False:
        errors.append("postrun route must not allow success evidence commits before live")
    if success_guard and success_guard.get("verdict") != "PASS":
        errors.append("success commit guard must be PASS")
    if success_guard and success_guard.get("commit_success_evidence_allowed") is not False:
        errors.append("success commit guard must not allow success commits before live")
    if success_guard and success_guard.get("live_providers_run") is not False:
        errors.append("success commit guard must have live_providers_run=false")
    if sequence and sequence.get("verdict") != "PASS":
        errors.append("operator sequence must be PASS")
    if sequence and sequence.get("live_slice") != live_slice:
        errors.append(f"operator sequence live slice must be {live_slice}")
    if sequence and sequence.get("acceptance_slice") != acceptance_slice:
        errors.append(f"operator sequence acceptance slice must be {acceptance_slice}")
    if sequence and sequence.get("live_providers_run") is not False:
        errors.append("operator sequence must have live_providers_run=false")

    ready = not errors
    return {
        "schema": "ao-operator/live-approval-readiness/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "errors": errors,
        "slug": slug,
        "approval_request_ready": ready,
        "operator_approval_required": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "live_slice": live_slice,
        "acceptance_slice": acceptance_slice,
        "operator_dispatch_command": (
            "python3 scripts/run_operator_slice.py examples/remote-transfer-v2-stress/operator-slices.json "
            f"--slice {live_slice} --execute --allow-live --json"
        ),
        "artifacts": {key: relpath(root, path) for key, path in paths.items()},
        "next_actions": [
            "Ask for explicit operator approval before running live providers.",
            "Do not run the live slice without --allow-live and human approval.",
            "After live exits, run the post-live classification and guard slices.",
        ],
    }


def default_output_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-approval-readiness.json"


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"approval_request_ready={str(payload['approval_request_ready']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"live_slice={payload['live_slice']}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check bounded-live readiness for explicit operator approval")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--live-slice", default=DEFAULT_LIVE_SLICE)
    parser.add_argument("--acceptance-slice", default=DEFAULT_ACCEPTANCE_SLICE)
    parser.add_argument("--readiness", default=DEFAULT_READINESS)
    parser.add_argument("--packet", default=DEFAULT_PACKET)
    parser.add_argument("--gate", default=DEFAULT_GATE)
    parser.add_argument("--route", default=DEFAULT_ROUTE)
    parser.add_argument("--success-guard", default=DEFAULT_SUCCESS_GUARD)
    parser.add_argument("--sequence", default=DEFAULT_SEQUENCE)
    parser.add_argument(
        "--write-output",
        nargs="?",
        const="",
        help="Write approval-readiness JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_approval_readiness(
        root=args.root,
        slug=args.slug,
        live_slice=args.live_slice,
        acceptance_slice=args.acceptance_slice,
        readiness_path=args.readiness,
        packet_path=args.packet,
        gate_path=args.gate,
        route_path=args.route,
        success_guard_path=args.success_guard,
        sequence_path=args.sequence,
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
