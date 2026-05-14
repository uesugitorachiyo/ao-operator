#!/usr/bin/env python3
"""Create and verify tamper-evident signatures for approval bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_BUNDLE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json"
DEFAULT_SIGNATURE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-bundle-signature.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-bundle-signature-report.json"
SCHEMA = "ao-operator/agent-os-approval-bundle-signature/v1"
SIGNATURE_SCHEMA = "ao-operator/agent-os-approval-bundle-signature-sidecar/v1"


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


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bundle_errors(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bundle.get("schema") != "ao-operator/agent-os-execution-approval-bundle/v1":
        errors.append("approval bundle schema must be ao-operator/agent-os-execution-approval-bundle/v1")
    if bundle.get("verdict") != "PASS":
        errors.append("approval bundle verdict must be PASS")
    if bundle.get("dispatch_authorized") is not False:
        errors.append("approval bundle dispatch_authorized must remain false")
    if bundle.get("live_providers_run") is not False:
        errors.append("approval bundle live_providers_run must remain false")
    template = bundle.get("approval_template")
    if not isinstance(template, dict):
        errors.append("approval bundle must include approval_template")
    elif template.get("approved") is not False:
        errors.append("approval bundle template must remain unapproved")
    return errors


def build_sidecar(root: Path, bundle_path: Path, subject_sha: str) -> dict[str, Any]:
    return {
        "schema": SIGNATURE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "subject": relpath(root, bundle_path),
        "subject_sha256": subject_sha,
        "signature_algorithm": "sha256-canonical-json",
        "signing_profile": "ao-operator-local-tamper-evidence",
        "identity_signature": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def check_signature(
    *,
    root: Path = ROOT,
    approval_bundle: str | Path = DEFAULT_APPROVAL_BUNDLE,
    signature_file: str | Path = DEFAULT_SIGNATURE,
    write_signature: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    bundle_path = resolve_path(root, approval_bundle)
    signature_path = resolve_path(root, signature_file)
    bundle = load_json(bundle_path)
    errors = bundle_errors(bundle)
    subject_sha = canonical_sha256(bundle) if bundle else ""
    signature_present = signature_path.is_file()
    if write_signature and not errors:
        write_json(signature_path, build_sidecar(root, bundle_path, subject_sha))
        signature_present = True
    sidecar = load_json(signature_path) if signature_present else {}
    if not signature_present:
        errors.append("approval bundle signature sidecar is missing")
    else:
        if sidecar.get("schema") != SIGNATURE_SCHEMA:
            errors.append(f"approval bundle signature schema must be {SIGNATURE_SCHEMA}")
        if sidecar.get("subject") != relpath(root, bundle_path):
            errors.append("approval bundle signature subject mismatch")
        if sidecar.get("subject_sha256") != subject_sha:
            errors.append("approval bundle signature mismatch")
        if sidecar.get("dispatch_authorized") is not False:
            errors.append("approval bundle signature dispatch_authorized must remain false")
        if sidecar.get("live_providers_run") is not False:
            errors.append("approval bundle signature live_providers_run must remain false")
    signature_matches = signature_present and sidecar.get("subject_sha256") == subject_sha
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "approval_bundle": relpath(root, bundle_path),
        "signature_file": relpath(root, signature_path),
        "signature_present": signature_present,
        "signature_matches": signature_matches,
        "subject_sha256": subject_sha,
        "signature_algorithm": "sha256-canonical-json",
        "identity_signature": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Approval bundle signature passes; materialization remains blocked until explicit approval."
            if not errors
            else "Regenerate and review approval bundle signature before materialization."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS approval bundle tamper-evident signature")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--approval-bundle", default=DEFAULT_APPROVAL_BUNDLE)
    parser.add_argument("--signature-file", default=DEFAULT_SIGNATURE)
    parser.add_argument("--write-signature", action="store_true")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_signature(
        root=args.root,
        approval_bundle=args.approval_bundle,
        signature_file=args.signature_file,
        write_signature=args.write_signature,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
