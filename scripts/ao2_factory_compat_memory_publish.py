#!/usr/bin/env python3
"""Produce a factory-compat cp-ingest receipt by chaining ``ao2 memory``.

Phase 2 exit-gate item #3 of ``AO2-FACTORY-MIGRATION-ROADMAP.md`` asks
the Hermes context payload to pin AO2-owned identifiers for every
AO2 surface that observes the run: mapping digest, evidence pack,
memory record, and ``ao2-control-plane`` ingest receipt. The bridge
already pins the first three; the prior receipt-pinning slice taught
the Hermes auto-discovery to read a receipt at
``<out-dir>/factory-compat-cp-ingest-receipt.json`` when one exists.

This producer closes the missing half: it writes the receipt file
itself by running

  1. ``ao2 memory export --target <T> --out <export.json>
     --signing-key <K> --signer-id <I> --json`` to produce a signed
     ``ao2.memory-export.v1`` artifact (with sibling ``.sig`` +
     ``memory-export-signing-public.pem`` written by AO2);
  2. ``ao2 memory publish --export <export.json> --control-plane-url
     <URL> --api-token <token-from-env> --json`` to post the export to
     the configured ``ao2-control-plane`` and capture the returned
     ``ao2.cp-ingest-receipt.v1`` envelope.

When ``--control-plane-url`` is omitted or the configured
``--api-token-env`` variable is unset, the producer emits a
``status="skipped"`` summary with a redacted ``reason`` and does not
write the receipt file. Hermes auto-discovery then sees no receipt and
the downstream payload omits the ``control_plane_*`` fields, which is
already supported by the consumer.

The summary schema is
``ao-operator/ao2-factory-compat-memory-publish/v1``.

Trust boundary
==============

- ao-operator only invokes the AO2 CLI and reads its JSON output;
- AO2 owns the export canonicalization, signature, control-plane POST,
  and the cp-ingest-receipt schema;
- the operator's bearer token never appears in this script's stdout,
  status JSON, logs, error messages, or the receipt file. It is read
  from the environment variable named by ``--api-token-env`` and
  forwarded to ``ao2 memory publish`` via ``--api-token`` on a single
  subprocess argv. The captured publish response is reduced to its
  ``receipt`` envelope before being written to disk so the wrapped
  HTTP transcript (which never contains the token regardless) stays
  out of the committed artifact tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ORCHESTRATOR_SCHEMA = "ao-operator/ao2-factory-compat-memory-publish/v1"
AO2_MEMORY_EXPORT_SCHEMA = "ao2.memory-export.v1"
AO2_CP_INGEST_RECEIPT_SCHEMA = "ao2.cp-ingest-receipt.v1"

EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-cli-memory-publish"
EXPECTED_CONTROL_PLANE_ROLE = "read_only_observer_after_signed_evidence"

DEFAULT_API_TOKEN_ENV = "AO2_CP_API_TOKEN"
DEFAULT_QUERY = "ao-operator-compat-nightly-run"
DEFAULT_LIMIT = 50
DEFAULT_SIGNER_ID = "ao2-memory"

SECRET_OUTPUT_PATTERNS = (
    (re.compile(r"(?i)\bAO2_CP_API_TOKEN=[^\s]+"), "AO2_CP_API_TOKEN:<redacted>"),
    (re.compile(r"(?i)\b(api_token=)[^\s&]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(api-token\s+)\S+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(token=)[^\s&]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(Authorization:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
)


def _redact(text: str) -> str:
    redacted = text
    for pattern, replacement in SECRET_OUTPUT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _trust_boundary() -> dict[str, str]:
    return {
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
    }


def _command_summary(command: list[str]) -> list[str]:
    """Return a copy of ``command`` with any token positional arg replaced."""
    sanitized: list[str] = []
    skip_next = False
    for arg in command:
        if skip_next:
            sanitized.append("<redacted>")
            skip_next = False
            continue
        if arg == "--api-token":
            sanitized.append(arg)
            skip_next = True
            continue
        sanitized.append(_redact(arg))
    return sanitized


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialized, encoding="utf-8")
    tmp.replace(path)


def _emit_summary(out_path: Path | None, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if out_path is None:
        sys.stdout.write(serialized)
        sys.stdout.flush()
        return
    _write_atomic(out_path, payload)


def _build_skipped(
    *,
    reason: str,
    inputs: dict[str, Any],
    stage: str = "preflight",
) -> dict[str, Any]:
    return {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "skipped",
        "stage": stage,
        "reason": _redact(reason),
        "inputs": inputs,
        "trust_boundary": _trust_boundary(),
        "export_path": None,
        "receipt_path": None,
        "receipt": None,
        "control_plane_url": inputs.get("control_plane_url"),
    }


def _build_failed(
    *,
    reason: str,
    stage: str,
    inputs: dict[str, Any],
    completed: list[str] | None = None,
    export_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "failed",
        "stage": stage,
        "reason": _redact(reason),
        "inputs": inputs,
        "completed": completed or [],
        "trust_boundary": _trust_boundary(),
        "export_path": str(export_path) if export_path is not None else None,
        "receipt_path": None,
        "receipt": None,
        "control_plane_url": inputs.get("control_plane_url"),
    }


def _run_ao2(
    *,
    ao2_binary: str,
    subcommand: list[str],
    stage: str,
    env_token: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run an ``ao2 <subcommand>`` invocation and return the parsed JSON.

    ``env_token``, when provided, is not echoed anywhere — it is the
    raw bearer that ``--api-token`` carries inside ``subcommand``. The
    sanitized command (used for error messages + tracing) has the
    token positional replaced with ``<redacted>``.
    """
    command = [ao2_binary, *subcommand]
    sanitized = _command_summary(command)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise _AO2Failure(
            stage=stage,
            reason=f"ao2 binary not found: {exc.filename}",
            sanitized_command=sanitized,
        ) from exc
    if completed.returncode != 0:
        stderr = _redact((completed.stderr or "").strip())
        stdout = _redact((completed.stdout or "").strip())
        raise _AO2Failure(
            stage=stage,
            reason=(
                f"ao2 {' '.join(subcommand[:2])} exited {completed.returncode}: "
                f"{stderr or stdout or '<no output>'}"
            ),
            sanitized_command=sanitized,
        )
    raw_stdout = completed.stdout or ""
    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError as exc:
        raise _AO2Failure(
            stage=stage,
            reason=(
                f"ao2 {' '.join(subcommand[:2])} returned invalid JSON: {exc}"
            ),
            sanitized_command=sanitized,
        ) from exc
    if not isinstance(payload, dict):
        raise _AO2Failure(
            stage=stage,
            reason=(
                f"ao2 {' '.join(subcommand[:2])} did not return a JSON object"
            ),
            sanitized_command=sanitized,
        )
    return payload, sanitized


class _AO2Failure(Exception):
    def __init__(
        self,
        *,
        stage: str,
        reason: str,
        sanitized_command: list[str] | None = None,
    ) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.sanitized_command = sanitized_command or []


def _validate_export_payload(payload: dict[str, Any], path: Path) -> None:
    actual = payload.get("schema_version")
    if actual != AO2_MEMORY_EXPORT_SCHEMA:
        raise _AO2Failure(
            stage="memory-export",
            reason=(
                f"ao2 memory export wrote {path}; expected "
                f"schema_version={AO2_MEMORY_EXPORT_SCHEMA!r} but found "
                f"{actual!r}"
            ),
        )


def _validate_receipt(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise _AO2Failure(
            stage="memory-publish",
            reason=(
                "ao2 memory publish response did not include a 'receipt' "
                "object"
            ),
        )
    if receipt.get("schema_version") != AO2_CP_INGEST_RECEIPT_SCHEMA:
        raise _AO2Failure(
            stage="memory-publish",
            reason=(
                "ao2 memory publish receipt has unexpected schema_version "
                f"{receipt.get('schema_version')!r}; "
                f"expected {AO2_CP_INGEST_RECEIPT_SCHEMA!r}"
            ),
        )
    if not receipt.get("sha256"):
        raise _AO2Failure(
            stage="memory-publish",
            reason="ao2 memory publish receipt is missing 'sha256'",
        )
    if not receipt.get("stored_at"):
        raise _AO2Failure(
            stage="memory-publish",
            reason="ao2 memory publish receipt is missing 'stored_at'",
        )
    return receipt


def _input_summary(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ao2_binary": args.ao2_binary,
        "target": str(args.target) if args.target is not None else None,
        "export_out": (
            str(args.export_out) if args.export_out is not None else None
        ),
        "receipt_out": (
            str(args.receipt_out) if args.receipt_out is not None else None
        ),
        "signing_key": (
            str(args.signing_key) if args.signing_key is not None else None
        ),
        "signer_id": args.signer_id,
        "query": args.query,
        "limit": args.limit,
        "control_plane_url": args.control_plane_url,
        "api_token_env": args.api_token_env,
        "allow_unsigned_memory_export": args.allow_unsigned_memory_export,
    }


def _build_export_command(args: argparse.Namespace) -> list[str]:
    command = [
        "memory",
        "export",
        "--target",
        str(args.target),
        "--out",
        str(args.export_out),
        "--query",
        args.query,
        "--limit",
        str(args.limit),
        "--signer-id",
        args.signer_id,
        "--json",
    ]
    if args.signing_key is not None:
        command.extend(["--signing-key", str(args.signing_key)])
    return command


def _build_publish_command(
    args: argparse.Namespace,
    *,
    token: str,
) -> list[str]:
    command = [
        "memory",
        "publish",
        "--export",
        str(args.export_out),
        "--control-plane-url",
        args.control_plane_url,
        "--api-token",
        token,
        "--json",
    ]
    if args.allow_unsigned_memory_export:
        command.append("--allow-unsigned-memory-export")
    return command


def run(args: argparse.Namespace) -> dict[str, Any]:
    inputs = _input_summary(args)

    if args.control_plane_url is None or not args.control_plane_url.strip():
        return _build_skipped(
            reason=(
                "control-plane URL not configured; pass "
                "--control-plane-url to enable memory publish"
            ),
            inputs=inputs,
        )

    token = os.environ.get(args.api_token_env)
    if not token:
        return _build_skipped(
            reason=(
                f"{args.api_token_env} is required to publish factory-compat "
                "memory exports to ao2-control-plane"
            ),
            inputs=inputs,
        )

    if args.target is None:
        return _build_failed(
            reason="--target is required when publish is enabled",
            stage="preflight",
            inputs=inputs,
        )
    if args.export_out is None:
        return _build_failed(
            reason="--export-out is required when publish is enabled",
            stage="preflight",
            inputs=inputs,
        )
    if args.receipt_out is None:
        return _build_failed(
            reason="--receipt-out is required when publish is enabled",
            stage="preflight",
            inputs=inputs,
        )
    if args.signing_key is None and not args.allow_unsigned_memory_export:
        return _build_failed(
            reason=(
                "--signing-key is required when publish is enabled "
                "(slice-19 default-on signed publish); pass "
                "--allow-unsigned-memory-export to opt out explicitly"
            ),
            stage="preflight",
            inputs=inputs,
        )
    target = args.target
    if not target.exists() or not target.is_dir():
        return _build_failed(
            reason=f"factory-compat target directory does not exist: {target}",
            stage="preflight",
            inputs=inputs,
        )

    args.export_out.parent.mkdir(parents=True, exist_ok=True)
    completed: list[str] = []
    try:
        export_payload, export_cmd = _run_ao2(
            ao2_binary=args.ao2_binary,
            subcommand=_build_export_command(args),
            stage="memory-export",
        )
        _validate_export_payload(export_payload, args.export_out)
        completed.append("memory-export")

        publish_payload, publish_cmd = _run_ao2(
            ao2_binary=args.ao2_binary,
            subcommand=_build_publish_command(args, token=token),
            stage="memory-publish",
            env_token=token,
        )
        receipt = _validate_receipt(publish_payload.get("receipt"))
        completed.append("memory-publish")
    except _AO2Failure as failure:
        return _build_failed(
            reason=failure.reason,
            stage=failure.stage,
            inputs=inputs,
            completed=completed,
            export_path=args.export_out if "memory-export" in completed else None,
        )

    _write_atomic(args.receipt_out, receipt)
    return {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "produced",
        "stage": "complete",
        "inputs": inputs,
        "completed": completed,
        "trust_boundary": _trust_boundary(),
        "export_path": str(args.export_out),
        "export_schema_version": export_payload.get("schema_version"),
        "export_signer_id": export_payload.get("signer_id"),
        "export_signature_present": bool(export_payload.get("signature")),
        "receipt_path": str(args.receipt_out),
        "receipt": receipt,
        "control_plane_url": args.control_plane_url,
        "command_summary": {
            "memory_export": export_cmd,
            "memory_publish": publish_cmd,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run ao2 memory export then ao2 memory publish to land a "
            "factory-compat cp-ingest-receipt for the nightly Hermes "
            "AO2-refs payload."
        ),
    )
    parser.add_argument(
        "--ao2-binary",
        default="ao2",
        help="Path to the ao2 CLI binary (default: ao2 from $PATH)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        help=(
            "Factory-compat target directory whose .ao2/memory store is the "
            "export source"
        ),
    )
    parser.add_argument(
        "--export-out",
        type=Path,
        help="Path where ao2 memory export will write ao2.memory-export.v1",
    )
    parser.add_argument(
        "--receipt-out",
        type=Path,
        help=(
            "Path where the bare ao2.cp-ingest-receipt.v1 envelope returned "
            "by ao2 memory publish will be written for Hermes auto-discovery"
        ),
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        help=(
            "Path to the ed25519 signing key forwarded to ao2 memory export "
            "(slice-19 default-on signed publish)"
        ),
    )
    parser.add_argument(
        "--signer-id",
        default=DEFAULT_SIGNER_ID,
        help=f"signer-id forwarded to ao2 memory export (default: {DEFAULT_SIGNER_ID})",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help=(
            "ao2 memory export --query filter (default: "
            f"{DEFAULT_QUERY})"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"ao2 memory export --limit (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--control-plane-url",
        help=(
            "ao2-control-plane base URL; producer skips with status=skipped "
            "when omitted or blank"
        ),
    )
    parser.add_argument(
        "--api-token-env",
        default=DEFAULT_API_TOKEN_ENV,
        help=(
            "Environment variable that holds the ao2-control-plane bearer "
            f"token (default: {DEFAULT_API_TOKEN_ENV}); producer skips with "
            "status=skipped when unset"
        ),
    )
    parser.add_argument(
        "--allow-unsigned-memory-export",
        action="store_true",
        help=(
            "Forward --allow-unsigned-memory-export to ao2 memory publish "
            "(opts out of slice-19 default-on signed publish; hidden upstream)"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=(
            "Path to write the orchestrator status JSON; defaults to stdout "
            "when omitted"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = run(args)
    _emit_summary(args.out, payload)
    return 0 if payload.get("status") in {"produced", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
