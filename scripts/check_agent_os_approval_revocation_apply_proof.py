#!/usr/bin/env python3
"""Prove approval revocation apply behavior in an isolated fixture."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import check_agent_os_approval_revocation


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_APPROVAL_GATE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-gate.json"
DEFAULT_APPROVAL_BUNDLE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-bundle.json"
DEFAULT_FIXTURE_ROOT = Path("/tmp/ao-operator-agent-os-approval-revocation-apply-proof")
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-revocation-apply-proof.json"
SCHEMA = "ao-operator/agent-os-approval-revocation-apply-proof/v1"
MARKER = ".ao-operator-agent-os-approval-revocation-apply-proof"


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def reset_fixture(path: Path) -> None:
    if path.exists():
        marker = path / MARKER
        if not marker.is_file():
            raise RuntimeError(f"fixture root exists without marker: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER).write_text("AO Operator approval revocation apply proof fixture\n", encoding="utf-8")


def copy_required(source_root: Path, fixture_root: Path, rel: str | Path) -> None:
    source = resolve_path(source_root, rel)
    target = resolve_path(fixture_root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def approval_target(bundle: dict[str, Any]) -> str:
    return str(bundle.get("approval_file_target") or f"{STATUS_ROOT}/agent-os-runspec-execution-approval.json")


def materialize_fixture_approval(root: Path, gate_rel: str | Path, bundle_rel: str | Path) -> dict[str, Any]:
    gate = load_json(resolve_path(root, gate_rel))
    bundle = load_json(resolve_path(root, bundle_rel))
    target = resolve_path(root, approval_target(bundle))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    approval = {
        "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
        "approved": True,
        "operator": "ao-operator-revocation-apply-proof",
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "accepted_risk": "Isolated fixture approval used only to prove revocation apply behavior.",
        "runspec_path": gate.get("runspec_path", ""),
        "runspec_sha256": gate.get("runspec_sha256", ""),
        "task_count": gate.get("task_count", 0),
    }
    write_json(target, approval)
    return {
        "verdict": "PASS",
        "approval_file": relpath(root, target),
        "approval_file_written": True,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def revocation_log_sanitized(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return "accepted_risk" not in text and '"approval"' not in text


def check_apply_proof(
    *,
    root: Path = ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    approval_gate: str | Path = DEFAULT_APPROVAL_GATE,
    approval_bundle: str | Path = DEFAULT_APPROVAL_BUNDLE,
) -> dict[str, Any]:
    source_root = root.resolve()
    fixture_root = fixture_root.resolve()
    errors: list[str] = []
    try:
        reset_fixture(fixture_root)
        copy_required(source_root, fixture_root, approval_gate)
        copy_required(source_root, fixture_root, approval_bundle)
    except (OSError, RuntimeError) as exc:
        errors.append(str(exc))

    materialization: dict[str, Any] = {}
    revocation: dict[str, Any] = {}
    sanitized = False
    if not errors:
        materialization = materialize_fixture_approval(fixture_root, approval_gate, approval_bundle)
        bundle = load_json(resolve_path(fixture_root, approval_bundle))
        revocation_log = "run-artifacts/live/revocations.jsonl"
        revocation = check_agent_os_approval_revocation.revoke_approval(
            root=fixture_root,
            approval_file=approval_target(bundle),
            revocation_log=revocation_log,
            operator="ao-operator-revocation-apply-proof",
            reason="Isolated fixture revocation apply proof.",
            apply=True,
            force=True,
        )
        sanitized = revocation_log_sanitized(resolve_path(fixture_root, revocation_log))
        if revocation.get("verdict") != "PASS":
            errors.append("fixture revocation apply did not pass")
        if revocation.get("revocation_applied") is not True:
            errors.append("fixture revocation was not applied")
        if revocation.get("approval_file_present_after") is not False:
            errors.append("fixture approval file must be absent after revocation")
        if not sanitized:
            errors.append("fixture revocation log must omit approval payload and accepted_risk")

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture": "isolated-temp",
        "approval_gate": relpath(source_root, resolve_path(source_root, approval_gate)),
        "approval_bundle": relpath(source_root, resolve_path(source_root, approval_bundle)),
        "materialization": materialization,
        "revocation": {
            "verdict": revocation.get("verdict", ""),
            "revocation_applied": revocation.get("revocation_applied", False),
            "approval_file_present_after": revocation.get("approval_file_present_after", True),
            "revocation_count": revocation.get("revocation_count", 0),
            "dispatch_authorized": revocation.get("dispatch_authorized", False),
            "live_providers_run": revocation.get("live_providers_run", False),
        },
        "revocation_log_sanitized": sanitized,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Revocation apply proof passes in an isolated fixture; keep real approvals explicit."
            if not errors
            else "Fix revocation apply proof before relying on revocation rollback."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove Agent OS approval revocation apply behavior")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--approval-gate", default=DEFAULT_APPROVAL_GATE)
    parser.add_argument("--approval-bundle", default=DEFAULT_APPROVAL_BUNDLE)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_apply_proof(
        root=args.root,
        fixture_root=args.fixture_root,
        approval_gate=args.approval_gate,
        approval_bundle=args.approval_bundle,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
