#!/usr/bin/env python3
"""Check the final local gate before bounded live provider dispatch."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_bounded_live_readiness
import verify_live_dispatch_packet


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_CONTRACT = "examples/remote-transfer-v2-stress/spec-forge.live.contract.json"
DEFAULT_TOPOLOGY = "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml"
DEFAULT_PACKET = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-dispatch-packet.json"
DEFAULT_READINESS_SUMMARY = (
    "run-artifacts/remote-transfer-v2-stress-live/readiness/bounded-live-preflight-summary.json"
)
DEFAULT_AO_RUNTIME_PATH = "../ao-runtime"
DEFAULT_LIVE_SLICE = "17-run-bounded-live-10"
DEFAULT_ACCEPTANCE_SLICE = "24-check-live-acceptance"


def readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        report = check.get("report", {})
        if not isinstance(report, dict):
            report = {}
        checks.append(
            {
                "id": check.get("id"),
                "status": check.get("status"),
                "expected_exit": check.get("expected_exit"),
                "actual_exit": report.get("exit"),
                "expected_verdict": check.get("expected_verdict"),
                "actual_verdict": report.get("json_verdict"),
            }
        )
    return {
        "verdict": payload.get("verdict"),
        "slug": payload.get("slug"),
        "mode": payload.get("mode"),
        "live_providers_run": payload.get("live_providers_run"),
        "checks": checks,
    }


def check_gate(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    manifest: str = DEFAULT_MANIFEST,
    contract: str = DEFAULT_CONTRACT,
    topology: str = DEFAULT_TOPOLOGY,
    packet: str = DEFAULT_PACKET,
    readiness_summary_path: str = DEFAULT_READINESS_SUMMARY,
    live_slice_id: str = DEFAULT_LIVE_SLICE,
    acceptance_slice_id: str = DEFAULT_ACCEPTANCE_SLICE,
    ao_runtime_path: str | None = None,
    runner=None,
) -> dict[str, Any]:
    readiness = check_bounded_live_readiness.check_readiness(
        root=root,
        slug=slug,
        manifest=manifest,
        contract=contract,
        topology=topology,
        ao_runtime_path=ao_runtime_path,
        runner=runner,
    )
    packet_verification = verify_live_dispatch_packet.verify_packet(
        root=root,
        packet_path=packet,
        manifest=manifest,
        readiness_summary=readiness_summary_path,
        live_slice_id=live_slice_id,
        acceptance_slice_id=acceptance_slice_id,
    )
    errors: list[str] = []
    if readiness.get("verdict") != "PASS":
        errors.append("bounded live readiness must be PASS")
    if readiness.get("live_providers_run") is not False:
        errors.append("bounded live readiness must have live_providers_run=false")
    if packet_verification.get("verdict") != "PASS":
        errors.append("dispatch packet verification must be PASS")
    if packet_verification.get("dispatch_authorized") is not False:
        errors.append("dispatch packet must have dispatch_authorized=false")
    if packet_verification.get("live_providers_run") is not False:
        errors.append("dispatch packet must have live_providers_run=false")
    errors.extend(str(error) for error in packet_verification.get("errors", []))

    verdict = "PASS" if not errors else "FAIL"
    return {
        "schema": "ao-operator/live-dispatch-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "errors": errors,
        "slug": slug,
        "live_execution_performed": False,
        "live_providers_run": False,
        "dispatch_authorized": False,
        "operator_approval_required": True,
        "ready_for_operator_approval": verdict == "PASS",
        "live_slice": live_slice_id,
        "acceptance_slice": acceptance_slice_id,
        "readiness": readiness_summary(readiness),
        "packet_verification": packet_verification,
        "required_next_steps": [
            "Operator must explicitly approve live provider execution before the live slice.",
            f"Run {live_slice_id} only with --allow-live after approval.",
            "Run the live outcome classifier immediately after the live command exits.",
            f"Run {acceptance_slice_id} only when the classifier reports ACCEPTED.",
            "If the classifier reports DIAGNOSTIC_REQUIRED, run diagnostics plan and preservation slices before any rerun.",
        ],
    }


def default_gate_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-dispatch-gate.json"


def write_gate(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"slug={payload['slug']}",
        f"ready_for_operator_approval={str(payload['ready_for_operator_approval']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"live_providers_run={str(payload['live_providers_run']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check final bounded live dispatch gate without running providers")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--packet", default=DEFAULT_PACKET)
    parser.add_argument("--readiness-summary", default=DEFAULT_READINESS_SUMMARY)
    parser.add_argument("--live-slice", default=DEFAULT_LIVE_SLICE)
    parser.add_argument("--acceptance-slice", default=DEFAULT_ACCEPTANCE_SLICE)
    parser.add_argument("--ao-runtime-path", default=os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", DEFAULT_AO_RUNTIME_PATH))
    parser.add_argument(
        "--write-gate",
        nargs="?",
        const="",
        help="Write gate JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_gate(
        root=args.root,
        slug=args.slug,
        manifest=args.manifest,
        contract=args.contract,
        topology=args.topology,
        packet=args.packet,
        readiness_summary_path=args.readiness_summary,
        live_slice_id=args.live_slice,
        acceptance_slice_id=args.acceptance_slice,
        ao_runtime_path=args.ao_runtime_path or None,
    )
    if args.write_gate is not None:
        gate_path = Path(args.write_gate) if args.write_gate else default_gate_path(args.root, args.slug)
        if not gate_path.is_absolute():
            gate_path = args.root / gate_path
        write_gate(gate_path, payload)
        payload["gate"] = str(gate_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
