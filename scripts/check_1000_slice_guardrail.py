#!/usr/bin/env python3
"""Check the 1000-slice dry-run and live-dispatch guardrail."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import factory_run


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress"
DEFAULT_TOPOLOGY = "examples/remote-transfer-v2-stress/ao-stress-topology.yaml"
DEFAULT_CONTRACT = "examples/remote-transfer-v2-stress/spec-forge.contract.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress/1000-slice-guardrail.json"
EXPECTED_SLICES = 1000
EXPECTED_TASKS = 2007


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_contract(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def runspec_task_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s{4}- id:\s*", line)
    )


def dry_run_evidence_checks(
    *,
    root: Path,
    slug: str,
    expected_tasks: int = EXPECTED_TASKS,
) -> tuple[list[dict[str, Any]], list[str]]:
    status = root / "run-artifacts" / slug / f"{slug}-status.md"
    evaluation = root / "docs" / "evaluations" / f"{slug}-evaluation.md"
    runspec = root / "run-artifacts" / slug / f"{slug}.runspec.yaml"
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    status_text = status.read_text(encoding="utf-8") if status.is_file() else ""
    evaluation_text = evaluation.read_text(encoding="utf-8") if evaluation.is_file() else ""
    facts = {
        "status.exists": status.is_file(),
        "status.mode_dry_run": "Mode: dry-run" in status_text,
        "status.ao_run_none": "AO Run: none" in status_text,
        "evaluation.exists": evaluation.is_file(),
        "evaluation.accepted": "Verdict: ACCEPTED" in evaluation_text,
        "evaluation.dry_run_only": "does not claim a live AO provider run" in evaluation_text,
        "evaluation.ao_run_none": "AO Run: none" in evaluation_text,
        "runspec.exists": runspec.is_file(),
        "runspec.task_count": runspec_task_count(runspec) == expected_tasks,
    }
    for check_id, ok in facts.items():
        checks.append({"id": check_id, "status": "PASS" if ok else "FAIL"})
        if not ok:
            errors.append(f"{check_id} failed")
    return checks, errors


def guarded_live_blockers(tasks: list[dict[str, object]]) -> list[str]:
    previous = os.environ.pop(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, None)
    try:
        return factory_run.live_run_blockers(tasks, run=True)
    finally:
        if previous is not None:
            os.environ[factory_run.ALLOW_LARGE_LIVE_RUN_ENV] = previous


def summarize(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    topology: str | Path = DEFAULT_TOPOLOGY,
    contract: str | Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    topology_path = resolve_path(root, topology)
    contract_path = resolve_path(root, contract)
    contract_payload = load_contract(contract_path)
    tasks = factory_run.parse_topology(topology_path, slug, contract_payload)
    slices = contract_payload.get("slices", [])
    slice_count = len(slices) if isinstance(slices, list) else 0

    checks, errors = dry_run_evidence_checks(root=root, slug=slug)
    task_count_ok = len(tasks) == EXPECTED_TASKS
    slice_count_ok = slice_count == EXPECTED_SLICES
    checks.extend(
        [
            {
                "id": "topology.task_count",
                "status": "PASS" if task_count_ok else "FAIL",
                "message": f"{len(tasks)} task(s), expected {EXPECTED_TASKS}",
            },
            {
                "id": "contract.slice_count",
                "status": "PASS" if slice_count_ok else "FAIL",
                "message": f"{slice_count} slice(s), expected {EXPECTED_SLICES}",
            },
        ]
    )
    if not task_count_ok:
        errors.append("topology.task_count failed")
    if not slice_count_ok:
        errors.append("contract.slice_count failed")

    blockers = guarded_live_blockers(tasks)
    guard_ok = (
        len(blockers) == 1
        and str(EXPECTED_TASKS) in blockers[0]
        and factory_run.MAX_LIVE_TASKS_ENV in blockers[0]
        and factory_run.ALLOW_LARGE_LIVE_RUN_ENV in blockers[0]
    )
    checks.append(
        {
            "id": "live_guardrail.blocks_1000_slice_run",
            "status": "PASS" if guard_ok else "FAIL",
            "message": blockers[0] if blockers else "no blocker",
        }
    )
    if not guard_ok:
        errors.append("live_guardrail.blocks_1000_slice_run failed")

    return {
        "schema": "ao-operator/1000-slice-guardrail/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "slug": slug,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
        "target_slices": EXPECTED_SLICES,
        "target_tasks": EXPECTED_TASKS,
        "topology": relpath(root, topology_path),
        "contract": relpath(root, contract_path),
        "dry_run_only": True,
        "live_guardrail_blocked": guard_ok,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "live_blocker": blockers[0] if blockers else "",
        "next_safe_command": (
            "Keep 1000-slice live blocked; start a separate provider-limit SDD before any live attempt."
            if not errors
            else "Fix 1000-slice guardrail evidence before escalation."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"dry_run_only={str(payload['dry_run_only']).lower()}",
        f"live_guardrail_blocked={str(payload['live_guardrail_blocked']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload["errors"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check 1000-slice dry-run guardrail")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(
        root=args.root,
        slug=args.slug,
        topology=args.topology,
        contract=args.contract,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
