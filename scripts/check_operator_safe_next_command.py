#!/usr/bin/env python3
"""Build the operator-facing safe next command report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/operator-safe-next-command.json"

SOURCES = {
    "accepted_50_summary": {
        "path": f"{STATUS_ROOT}/dispatch/50-slice-operator-summary.json",
        "schema": "ao-operator/50-slice-operator-summary/v1",
    },
    "operator_guardrail_summary": {
        "path": f"{STATUS_ROOT}/operator-guardrail-summary.json",
        "schema": "ao-operator/operator-guardrail-summary/v1",
    },
    "release_readiness": {
        "path": f"{STATUS_ROOT}/release-readiness-gate.json",
        "schema": "ao-operator/release-readiness-gate/v1",
    },
    "release_artifact_index": {
        "path": f"{STATUS_ROOT}/release-artifact-index.json",
        "schema": "ao-operator/release-artifact-index/v1",
    },
}

SAFE_RECOMMENDED_COMMANDS = [
    "python3 scripts/operator_control.py status --json",
    "python3 scripts/check_operator_safe_next_command.py --json",
]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def source_errors(source_id: str, payload: dict[str, Any], expected_schema: str) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != expected_schema:
        errors.append(f"{source_id} schema must be {expected_schema}")
    if payload.get("verdict") != "PASS":
        errors.append(f"{source_id} verdict must be PASS")
    if payload.get("dispatch_authorized") is not False:
        errors.append(f"{source_id} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        errors.append(f"{source_id} live_providers_run must remain false")
    if source_id in {"operator_guardrail_summary", "release_readiness"} and payload.get("ship_ready") is not True:
        errors.append(f"{source_id} ship_ready must be true")
    if source_id == "operator_guardrail_summary":
        if payload.get("approval_usable") is True:
            errors.append("operator_guardrail_summary approval_usable must remain false")
        if payload.get("positive_approval_path") != "PLAN_WITHOUT_DISPATCH":
            errors.append("operator_guardrail_summary positive_approval_path must be PLAN_WITHOUT_DISPATCH")
    if source_id == "release_artifact_index":
        if int(payload.get("artifact_count") or 0) < 64:
            errors.append("release_artifact_index artifact_count must cover committed guardrails")
        if int(payload.get("sdd_count") or 0) < 65:
            errors.append("release_artifact_index sdd_count must cover committed SDDs")
    return errors


def summarize(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    blockers: list[str] = []
    errors: list[str] = []
    sources: dict[str, Any] = {}
    evidence_paths: dict[str, str] = {}
    source_payloads: dict[str, dict[str, Any]] = {}

    for source_id, config in SOURCES.items():
        path = resolve_path(root, config["path"])
        payload = load_json(path)
        source_payloads[source_id] = payload
        evidence_paths[source_id] = relpath(root, path)
        current_errors = source_errors(source_id, payload, config["schema"])
        if current_errors:
            blockers.append(source_id)
            errors.extend(current_errors)
        sources[source_id] = {
            "path": relpath(root, path),
            "schema": payload.get("schema", ""),
            "verdict": payload.get("verdict", "MISSING"),
            "dispatch_authorized": payload.get("dispatch_authorized"),
            "live_providers_run": payload.get("live_providers_run"),
            "next_safe_command": payload.get("next_safe_command", ""),
        }
        for key in ("ship_ready", "approval_state", "approval_usable", "positive_approval_path", "current_state"):
            if key in payload:
                sources[source_id][key] = payload[key]

    accepted = source_payloads.get("accepted_50_summary", {})
    guardrail = source_payloads.get("operator_guardrail_summary", {})
    release = source_payloads.get("release_readiness", {})

    current_state = str(accepted.get("current_state") or "UNKNOWN")
    approval_state = str(guardrail.get("approval_state") or "UNKNOWN")
    ship_ready = guardrail.get("ship_ready") is True and release.get("ship_ready") is True

    if errors:
        safe_action = "BLOCKED"
        next_safe_command = "Fix safe-next-command blockers before running operator actions."
        recommended_commands: list[str] = []
    else:
        safe_action = "START_NEXT_GATED_SDD_LANE"
        next_safe_command = "Start the next gated SDD lane; keep Agent OS execution blocked until explicit approval."
        recommended_commands = SAFE_RECOMMENDED_COMMANDS

    return {
        "schema": "ao-operator/operator-safe-next-command/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "safe_action": safe_action,
        "current_state": current_state,
        "approval_state": approval_state,
        "ship_ready": ship_ready,
        "sources": sources,
        "evidence_paths": evidence_paths,
        "recommended_commands": recommended_commands,
        "blockers": sorted(set(blockers)),
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": next_safe_command,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"safe_action={payload['safe_action']}",
        f"current_state={payload['current_state']}",
        f"approval_state={payload['approval_state']}",
        f"ship_ready={str(payload['ship_ready']).lower()}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"live_providers_run={str(payload['live_providers_run']).lower()}",
        f"next_safe_command={payload['next_safe_command']}",
    ]
    lines.extend(f"recommended_command={command}" for command in payload["recommended_commands"])
    lines.extend(f"blocker={blocker}" for blocker in payload["blockers"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build operator safe next command report")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
