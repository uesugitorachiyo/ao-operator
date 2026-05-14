#!/usr/bin/env python3
"""Route 50-slice live postrun state without confusing it with 25-slice evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_CONTRACT = "examples/remote-transfer-v2-stress/spec-forge.live.contract.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/50-slice-live-postrun-route.json"
EXPECTED_SLICES = 50
EXPECTED_TASKS = 107


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def live_contract_slice_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    slices = data.get("slices", []) if isinstance(data, dict) else []
    return len(slices) if isinstance(slices, list) else 0


def route(*, root: Path = ROOT, slug: str = DEFAULT_SLUG, contract: str | Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract_path = resolve_path(root, contract)
    slice_count = live_contract_slice_count(contract_path)
    acceptance = check_live_acceptance.check_slug(slug, root=root)
    errors: list[str] = []
    if slice_count == EXPECTED_SLICES and acceptance.get("verdict") == "PASS":
        route_name = "RUN_50_SLICE_ACCEPTANCE"
        next_slice = "24-check-live-acceptance"
        commit_success_evidence_allowed = True
    elif slice_count == EXPECTED_SLICES:
        route_name = "CLASSIFY_50_SLICE_DIAGNOSTICS"
        next_slice = "18-classify-live-outcome"
        commit_success_evidence_allowed = False
    else:
        route_name = "WAIT_FOR_50_SLICE_LIVE_RUN"
        next_slice = "31-run-50-slice-live"
        commit_success_evidence_allowed = False
    return {
        "schema": "ao-operator/50-slice-live-postrun-route/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "slug": slug,
        "expected_slices": EXPECTED_SLICES,
        "expected_tasks": EXPECTED_TASKS,
        "current_live_contract_slices": slice_count,
        "route": route_name,
        "next_slice": next_slice,
        "commit_success_evidence_allowed": commit_success_evidence_allowed,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "acceptance_verdict": acceptance.get("verdict"),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route 50-slice live postrun state")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = route(root=args.root, slug=args.slug, contract=args.contract)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"route={payload['route']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
