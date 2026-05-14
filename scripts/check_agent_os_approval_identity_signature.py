#!/usr/bin/env python3
"""Prove identity-bound approval bundle signing in an isolated fixture."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_APPROVAL_BUNDLE = f"{STATUS_ROOT}/agent-os-runspec-execution-approval-bundle.json"
DEFAULT_FIXTURE_ROOT = Path("/tmp/ao-operator-agent-os-approval-identity-signature")
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-approval-identity-signature.json"
SCHEMA = "ao-operator/agent-os-approval-identity-signature/v1"
MARKER = ".ao-operator-agent-os-approval-identity-signature"
NAMESPACE = "ao-operator-approval"
PRINCIPAL = "ao-operator-operator"


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
    (path / MARKER).write_text("AO Operator approval identity signature fixture\n", encoding="utf-8")


def run(command: list[str], *, cwd: Path, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


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
    return errors


def check_identity_signature(
    *,
    root: Path = ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    approval_bundle: str | Path = DEFAULT_APPROVAL_BUNDLE,
    tamper_after_sign: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    fixture_root = fixture_root.resolve()
    source_bundle = resolve_path(root, approval_bundle)
    errors: list[str] = []
    bundle = load_json(source_bundle)
    errors.extend(bundle_errors(bundle))
    if shutil.which("ssh-keygen") is None:
        errors.append("ssh-keygen is required for identity signature proof")
    try:
        reset_fixture(fixture_root)
    except RuntimeError as exc:
        errors.append(str(exc))
    fixture_bundle = fixture_root / "approval-bundle.json"
    key = fixture_root / "operator_ed25519"
    allowed_signers = fixture_root / "allowed_signers"
    signature = fixture_bundle.with_suffix(fixture_bundle.suffix + ".sig")

    signature_verified = False
    fingerprint = ""
    if not errors:
        shutil.copy2(source_bundle, fixture_bundle)
        generated = run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", PRINCIPAL, "-f", str(key)], cwd=fixture_root)
        if generated.returncode != 0:
            errors.append("ssh-keygen key generation failed")
        public_key = key.with_suffix(".pub")
        if not errors:
            public_text = public_key.read_text(encoding="utf-8").strip()
            allowed_signers.write_text(f'{PRINCIPAL} namespaces="{NAMESPACE}" {public_text}\n', encoding="utf-8")
            fp = run(["ssh-keygen", "-lf", str(public_key)], cwd=fixture_root)
            if fp.returncode == 0:
                fingerprint = fp.stdout.decode("utf-8", errors="replace").strip()
            signed = run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(fixture_bundle)], cwd=fixture_root)
            if signed.returncode != 0:
                errors.append("identity signature creation failed")
        if not errors and tamper_after_sign:
            data = load_json(fixture_bundle)
            data["tampered"] = True
            write_json(fixture_bundle, data)
        if not errors:
            verified = run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_signers),
                    "-I",
                    PRINCIPAL,
                    "-n",
                    NAMESPACE,
                    "-s",
                    str(signature),
                ],
                cwd=fixture_root,
                input_bytes=fixture_bundle.read_bytes(),
            )
            signature_verified = verified.returncode == 0
            if not signature_verified:
                errors.append("identity signature verification failed")

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "fixture": "isolated-temp",
        "approval_bundle": relpath(root, source_bundle),
        "signature_namespace": NAMESPACE,
        "principal": PRINCIPAL,
        "public_key_fingerprint": fingerprint,
        "identity_signature": bool(not errors or signature_verified) and signature_verified,
        "signature_verified": signature_verified,
        "tamper_after_sign": tamper_after_sign,
        "private_key_committed": False,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Identity-bound approval signature proof passes; keep real approval materialization explicit."
            if not errors
            else "Fix identity-bound approval signature proof before trusting signed approval bundles."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove identity-bound approval bundle signing")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--approval-bundle", default=DEFAULT_APPROVAL_BUNDLE)
    parser.add_argument("--tamper-after-sign", action="store_true")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_identity_signature(
        root=args.root,
        fixture_root=args.fixture_root,
        approval_bundle=args.approval_bundle,
        tamper_after_sign=args.tamper_after_sign,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
