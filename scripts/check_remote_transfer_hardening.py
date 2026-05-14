#!/usr/bin/env python3
"""Verify remote-transfer signing and chunk-cleanup hardening evidence."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redact_strict_public_artifacts import redact_text


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AO_RUNTIME = ROOT.parent / "ao-runtime"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-hardening.json"


CONTROL_SPECS = {
    "manifest_signing": {
        "paths": [
            "progress/slice-reports/remote_transfer_v2_phase3_signed_manifest_verification.md",
            "docs/remote-worker-workspace-transfer-spec.md",
        ],
        "terms": [
            "Ed25519",
            "canonical signing payload",
            "required_signature_rejects_unsigned_manifest",
            "required_signature_rejects_tampered_manifest_metadata",
            "AO_WORKSPACE_SIGNING_KEY",
            "AO_WORKSPACE_VERIFY_KEY",
        ],
    },
    "chunk_cleanup": {
        "paths": [
            "progress/slice-reports/remote_transfer_v2_phase2b_grpc_chunked_upload.md",
            "docs/remote-worker-workspace-transfer-spec.md",
            "run-artifacts/remote-transfer-v2-stress-live/chunked-upload-validation-20260506T233808Z.md",
        ],
        "terms": [
            "BeginWorkspaceUpload",
            "UploadWorkspaceChunk",
            "CommitWorkspaceUpload",
            "failed chunk index",
            "Delete partial chunks",
            "cleans partial staging",
            "Total hash mismatch cleans staging",
        ],
    },
    "large_transfer_smoke": {
        "paths": [
            "run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-remote-smoke-large-64m-20260506T233645Z.json",
        ],
        "terms": [
            "\"verdict\": \"PASS\"",
            "\"provider_dispatch\": false",
            "\"remote_cleanup_absent\": true",
            "\"extra_bytes\": 67108864",
        ],
    },
    "worker_runtime_signed_smoke": {
        "paths": [
            "run-artifacts/remote-transfer-v2-stress-live/remote-codex-worker-runtime-smoke-20260507T004907Z.md",
        ],
        "terms": [
            "Verdict: PASS",
            "Mac-signed bundle",
            "Ubuntu verified the signed bundle",
            "task.completed",
        ],
    },
}


def resolve_path(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def rel_or_abs(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def check_terms(*, root: Path, ao_runtime: Path, paths: list[str], terms: list[str]) -> dict[str, Any]:
    resolved: list[Path] = []
    combined = ""
    missing_paths: list[str] = []
    for rel in paths:
        base = ao_runtime if rel.startswith(("progress/", "docs/remote-worker")) else root
        path = resolve_path(base, rel)
        resolved.append(path)
        text = read_text(path)
        if not text:
            missing_paths.append(rel_or_abs(root, path))
        combined += "\n" + text
    missing_terms = [term for term in terms if term not in combined]
    return {
        "verdict": "PASS" if not missing_paths and not missing_terms else "FAIL",
        "paths": [rel_or_abs(root, path) for path in resolved],
        "missing_paths": missing_paths,
        "missing_terms": missing_terms,
        "required_terms": terms,
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def summarize(
    *,
    root: Path = ROOT,
    ao_runtime: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    ao_runtime = (ao_runtime or Path(os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", DEFAULT_AO_RUNTIME))).resolve()
    controls = {
        control_id: check_terms(
            root=root,
            ao_runtime=ao_runtime,
            paths=list(spec["paths"]),
            terms=list(spec["terms"]),
        )
        for control_id, spec in CONTROL_SPECS.items()
    }
    blockers = [control_id for control_id, control in controls.items() if control.get("verdict") != "PASS"]
    payload = {
        "schema": "ao-operator/remote-transfer-hardening/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": str(root),
        "ao_runtime": str(ao_runtime),
        "verdict": "PASS" if not blockers else "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "blockers": blockers,
        "controls": controls,
        "next_safe_command": (
            "Remote transfer signing and chunk cleanup hardening evidence passes."
            if not blockers
            else "Fix remote transfer hardening evidence before larger network transfer tests."
        ),
    }
    return sanitize(payload)


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check remote-transfer hardening evidence")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ao-runtime", type=Path, default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(root=args.root, ao_runtime=args.ao_runtime)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
