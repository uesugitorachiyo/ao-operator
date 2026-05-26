#!/usr/bin/env python3
"""Produce the ao2.evidence-pack.v1 the nightly evaluator producer consumes.

Phase 2 exit-gate item #4 requires AO2 to own the closure verdict. The
existing evaluator-decision producer
(``scripts/ao2_release_ao2_native_evaluator_producer.py``) only emits a
real AO2 decision when an evidence pack is already on disk. This
producer fills that prerequisite by asking AO2 to export an
``ao2.evidence-pack.v1`` from a completed factory-compat queue entry.

Behaviour:

- If ``--ao2-target`` exists, the ``ao2`` binary resolves on PATH
  (``--ao2-binary`` override allowed), and the AO2 factory queue holds at
  least one completed entry with a valid evidence pack, the helper
  invokes ``ao2 factory pack-evidence`` (with ``--run-id`` when
  supplied), writes the canonical evidence-pack JSON to
  ``--evidence-pack-out``, and emits a wrapper summary with
  ``status=produced`` referencing the AO2-emitted path.
- Otherwise the helper writes a wrapper summary with
  ``status=missing_inputs`` enumerating what is missing.  The nightly
  evaluator-decision producer consumes the produced evidence pack via
  ``--evidence-pack`` and inherits the same ``missing_inputs``
  short-circuit shape so nightly never fabricates a closure verdict.
- When ``--signing-key`` is supplied, the path is forwarded to AO2 as
  ``ao2 factory pack-evidence --signing-key``. AO2 owns the key
  material and writes the ``.json.sig`` + ``.json.public.pem`` sidecars
  next to the canonical pack; the produced summary surfaces AO2's
  ``signature`` block under ``evidence_pack_signature``.
- The produced summary always surfaces AO2's ``deterministic_replay``
  block under ``evidence_pack_deterministic_replay`` so nightly readers
  can gate on byte-stable canonicalisation regardless of signing.
- ``--require-signed-evidence`` refuses to mark the summary produced
  unless AO2 reports ``signature_verified=true`` AND
  ``deterministic_replay.verified=true``, enforcing Phase 2 exit-gate
  item #4 (evaluator/closer evidence representable as AO2 obligations).

The wrapper schema is
``ao-operator/ao2-release-ao2-native-evidence-pack-producer/v1``.

This script is pure stdlib (argparse / json / pathlib / shutil /
subprocess). It never embeds bearer tokens, secrets, cookies or
credentials, and it does not mutate any AO2 artifact. Factory-v3 never
fabricates the evidence pack itself; it only invokes AO2 and records
the path AO2 wrote.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PRODUCER_SCHEMA = "ao-operator/ao2-release-ao2-native-evidence-pack-producer/v1"
AO2_PACK_EVIDENCE_SCHEMA = "ao2.ao-operator-compat-pack-evidence.v1"
AO2_EVIDENCE_PACK_SCHEMA = "ao2.evidence-pack.v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-workbench-queue"
EXPECTED_CONTROL_PLANE_ROLE = "read_only_observer_after_signed_evidence"


def _factory_queue_path(target: Path) -> Path:
    return target / ".ao2" / "factory-compat" / "queue.json"


def _input_summary(
    *,
    ao2_binary: str,
    ao2_binary_resolved: str | None,
    ao2_target: Path | None,
    run_id: str | None,
    evidence_pack_out: Path,
    queue_path_resolved: str | None,
    signing_key: Path | None,
    signer_id: str | None,
) -> dict[str, Any]:
    return {
        "ao2_binary": ao2_binary,
        "ao2_binary_resolved": ao2_binary_resolved,
        "ao2_target": str(ao2_target) if ao2_target is not None else None,
        "run_id": run_id,
        "evidence_pack_out": str(evidence_pack_out),
        "queue_path": queue_path_resolved,
        "signing_key": str(signing_key) if signing_key is not None else None,
        "signer_id": signer_id,
    }


def _build_missing_inputs_payload(
    *, inputs: dict[str, Any], missing: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCER_SCHEMA,
        "status": "missing_inputs",
        "missing": missing,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
        "evidence_pack_path": None,
        "evidence_pack_schema": AO2_EVIDENCE_PACK_SCHEMA,
        "evidence_pack_emitted": False,
        "evidence_pack_signature": None,
        "evidence_pack_deterministic_replay": None,
        "inputs": inputs,
        "next_action": (
            "supply --ao2-target pointing at a factory-compat repo whose AO2 "
            "queue has at least one completed entry with a populated "
            "evidence_pack reference; the helper will then ask AO2 to "
            "canonicalise that pack into --evidence-pack-out and the "
            "downstream evaluator-decision producer will run for real"
        ),
    }


def _build_produced_payload(
    *,
    inputs: dict[str, Any],
    ao2_result: dict[str, Any],
    evidence_pack_out: Path,
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCER_SCHEMA,
        "status": "produced",
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
        "evidence_pack_path": str(evidence_pack_out),
        "evidence_pack_schema": AO2_EVIDENCE_PACK_SCHEMA,
        "evidence_pack_emitted": True,
        "evidence_pack_summary": {
            "schema_version": ao2_result.get("schema_version"),
            "run_id": ao2_result.get("run_id"),
            "entry_status": ao2_result.get("entry_status"),
            "native_evaluator_verdict": ao2_result.get("native_evaluator_verdict"),
            "evidence_pack_source": ao2_result.get("evidence_pack_source"),
            "evidence_pack_source_sha256": ao2_result.get(
                "evidence_pack_source_sha256"
            ),
            "evidence_pack_sha256": ao2_result.get("evidence_pack_sha256"),
            "evidence_pack_execution_owner": ao2_result.get(
                "evidence_pack_execution_owner"
            ),
            "queue_path": ao2_result.get("queue_path"),
        },
        # AO2 owns the trust boundary: surface AO2's signature + deterministic
        # replay verdicts verbatim. Factory-v3 never re-signs or re-canonicalises
        # the pack here; we only observe and forward the AO2 verdict so
        # downstream nightly readers can gate on it.
        "evidence_pack_signature": ao2_result.get("signature"),
        "evidence_pack_deterministic_replay": ao2_result.get(
            "deterministic_replay"
        ),
        "inputs": inputs,
        "next_action": (
            "pass --evidence-pack pointing at evidence_pack_path to "
            "ao2_release_ao2_native_evaluator_producer.py so AO2 owns the "
            "subsequent evaluator-decision verdict"
        ),
    }


def _invoke_ao2_pack_evidence(
    *,
    ao2_binary: str,
    ao2_target: Path,
    run_id: str | None,
    evidence_pack_out: Path,
    signing_key: Path | None,
    signer_id: str | None,
) -> dict[str, Any]:
    command = [
        ao2_binary,
        "factory",
        "pack-evidence",
        "--target",
        str(ao2_target),
        "--out",
        str(evidence_pack_out),
        "--json",
    ]
    if run_id is not None:
        command.extend(["--run-id", run_id])
    if signing_key is not None:
        command.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        command.extend(["--signer-id", signer_id])

    evidence_pack_out.parent.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "ao2 factory pack-evidence failed "
            f"(exit {completed.returncode}): "
            f"{completed.stderr.strip() or '<no stderr>'}"
        )
    stdout = completed.stdout.strip()
    if not stdout:
        raise SystemExit("ao2 factory pack-evidence produced no stdout JSON")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ao2 factory pack-evidence returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit("ao2 factory pack-evidence JSON was not an object")
    schema = payload.get("schema_version")
    if schema != AO2_PACK_EVIDENCE_SCHEMA:
        raise SystemExit(
            "ao2 factory pack-evidence returned unexpected schema_version "
            f"{schema!r}; expected {AO2_PACK_EVIDENCE_SCHEMA!r}"
        )
    pack_schema = payload.get("evidence_pack_schema_version")
    if pack_schema != AO2_EVIDENCE_PACK_SCHEMA:
        raise SystemExit(
            "ao2 factory pack-evidence produced an evidence pack with "
            f"schema_version {pack_schema!r}; expected {AO2_EVIDENCE_PACK_SCHEMA!r}"
        )
    if not evidence_pack_out.is_file():
        raise SystemExit(
            "ao2 factory pack-evidence did not write the evidence pack file at "
            f"{evidence_pack_out}"
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ao2-binary",
        default="ao2",
        help="Name or path of the ao2 binary (default: ao2)",
    )
    parser.add_argument(
        "--ao2-target",
        type=Path,
        default=None,
        help=(
            "Path to the factory-compat repo whose AO2 queue holds the "
            "completed entry to pack-evidence from"
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Optional run_id to pack-evidence; defaults to AO2's latest "
            "completed entry with a populated evidence_pack"
        ),
    )
    parser.add_argument(
        "--evidence-pack-out",
        type=Path,
        required=True,
        help="Path the canonical ao2.evidence-pack.v1 JSON is written to",
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        default=None,
        help=(
            "Optional path to an AO2-owned RSA private key (PKCS8/PKCS1 PEM) "
            "passed through to `ao2 factory pack-evidence --signing-key`. "
            "Factory-v3 never generates or owns the key material; AO2 "
            "writes the .json.sig + .json.public.pem sidecars next to "
            "--evidence-pack-out and reports the verified signature back."
        ),
    )
    parser.add_argument(
        "--signer-id",
        default=None,
        help=(
            "Optional signer identifier forwarded to AO2 when --signing-key "
            "is supplied; AO2 records it in the signature block. Defaults "
            "to AO2's built-in ao2-factory-pack-evidence-signer when "
            "omitted."
        ),
    )
    parser.add_argument(
        "--require-signed-evidence",
        action="store_true",
        help=(
            "Refuse to mark the produced summary as accepted unless AO2 "
            "reports signature_verified=true AND deterministic_replay."
            "verified=true on the emitted pack."
        ),
    )
    parser.add_argument("--write-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.signer_id is not None and args.signing_key is None:
        raise SystemExit(
            "--signer-id requires --signing-key; AO2 only honours signer_id "
            "when key material is supplied"
        )

    resolved = shutil.which(args.ao2_binary)
    queue_path = (
        _factory_queue_path(args.ao2_target) if args.ao2_target is not None else None
    )
    inputs = _input_summary(
        ao2_binary=args.ao2_binary,
        ao2_binary_resolved=resolved,
        ao2_target=args.ao2_target,
        run_id=args.run_id,
        evidence_pack_out=args.evidence_pack_out,
        queue_path_resolved=str(queue_path) if queue_path is not None else None,
        signing_key=args.signing_key,
        signer_id=args.signer_id,
    )

    missing: list[str] = []
    if args.ao2_target is None:
        missing.append("ao2_target")
    elif not args.ao2_target.exists():
        missing.append(f"ao2_target_not_found:{args.ao2_target}")
    elif queue_path is None or not queue_path.is_file():
        missing.append(
            f"factory_queue_not_found:{queue_path}"
            if queue_path is not None
            else "factory_queue_not_found"
        )
    if resolved is None:
        missing.append(f"ao2_binary_not_on_path:{args.ao2_binary}")
    if args.signing_key is not None and not args.signing_key.is_file():
        missing.append(f"signing_key_not_found:{args.signing_key}")

    if missing:
        payload = _build_missing_inputs_payload(inputs=inputs, missing=missing)
    else:
        assert args.ao2_target is not None  # for type-checker
        ao2_result = _invoke_ao2_pack_evidence(
            ao2_binary=args.ao2_binary,
            ao2_target=args.ao2_target,
            run_id=args.run_id,
            evidence_pack_out=args.evidence_pack_out,
            signing_key=args.signing_key,
            signer_id=args.signer_id,
        )
        payload = _build_produced_payload(
            inputs=inputs,
            ao2_result=ao2_result,
            evidence_pack_out=args.evidence_pack_out,
        )
        if args.require_signed_evidence:
            signature_block = payload.get("evidence_pack_signature") or {}
            replay_block = payload.get("evidence_pack_deterministic_replay") or {}
            signed = signature_block.get("signature_verified") is True
            replayed = replay_block.get("verified") is True
            if not (signed and replayed):
                raise SystemExit(
                    "--require-signed-evidence: AO2 did not report a verified "
                    "signature and deterministic replay; signature_verified="
                    f"{signature_block.get('signature_verified')!r}, "
                    f"deterministic_replay.verified={replay_block.get('verified')!r}"
                )

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.write_json.parent.mkdir(parents=True, exist_ok=True)
    args.write_json.write_text(text, encoding="utf-8")
    if args.json:
        print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
