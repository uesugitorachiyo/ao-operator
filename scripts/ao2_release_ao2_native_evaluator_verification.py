#!/usr/bin/env python3
"""Produce the AO2 native-evaluator-decision verification artifact for the nightly pipeline.

Phase 2 exit-gate item #4 requires that AO2 owns the closure verdict
for ao-operator release-line decisions. The closer
(``scripts/ao2_release_evaluator_closure_with_ao2_verification.py``)
consumes a verification artifact with schema_version
``ao2.ao-operator-compat-native-evaluator-verification.v1`` produced by
``ao2 factory verify-evaluator-decision --decision <native> --json``.

This helper is a thin shim the nightly pipeline can call regardless of
whether AO2 evidence has been wired through to release-line nightly yet:

- If ``--ao2-native-decision`` is supplied and the ``ao2`` binary is on
  PATH (``--ao2-binary`` override allowed), the helper invokes the
  binary and captures the JSON it emits to ``--write-json``.
- Otherwise the helper writes a ``status=missing_inputs`` artifact that
  still carries the verifier's ``schema_version`` and the
  ``factory_v3_role=parity_oracle_only`` discipline marker. The closer
  recognises this short-circuit and emits a
  ``decision=blocked_awaiting_ao2_verification`` closure rather than
  accepting on ao-operator's local verdict alone.

The script is pure stdlib (argparse / json / pathlib / shutil /
subprocess). It never embeds bearer tokens, secrets, cookies or
credentials, and it does not mutate any AO2 artifact.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

AO2_VERIFICATION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-verification.v1"
PRODUCER_SCHEMA = "ao-operator/ao2-release-ao2-native-evaluator-producer/v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-native-evaluator-decision-verifier"
EXPECTED_CONTROL_PLANE_ROLE = "read_only_observer"


def _build_missing_inputs_payload(
    *,
    ao2_binary: str,
    ao2_binary_resolved: str | None,
    ao2_native_decision: Path | None,
    missing: list[str],
    producer_summary_path: Path | None = None,
    producer_status: str | None = None,
    producer_missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": AO2_VERIFICATION_SCHEMA,
        "status": "missing_inputs",
        "missing": missing,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
        "trust_boundary_ok": False,
        "signature_status": "missing",
        "signature_verified": False,
        "signature_requirement_satisfied": False,
        "signature_digest_match": False,
        "public_key_digest_match": False,
        "signed_payload_digest_match": False,
        "decision_payload_matches_signed_payload": False,
        "verdict": {
            "status": "missing_inputs",
            "factory_v3_required_to_decide": False,
            "owner": EXPECTED_AO2_DECISION_OWNER,
        },
        "inputs": {
            "ao2_binary": ao2_binary,
            "ao2_binary_resolved": ao2_binary_resolved,
            "ao2_native_decision": (
                str(ao2_native_decision) if ao2_native_decision is not None else None
            ),
            "ao2_producer_summary": (
                str(producer_summary_path)
                if producer_summary_path is not None
                else None
            ),
        },
        "producer": (
            {
                "status": producer_status,
                "missing": producer_missing or [],
            }
            if producer_status is not None
            else None
        ),
        "next_action": (
            "produce an AO2 native evaluator decision and re-run this helper "
            "with --ao2-native-decision pointing at it; AO2 owns the closure verdict"
        ),
    }


def _load_producer_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"failed to read --ao2-producer-summary {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SystemExit(
            f"--ao2-producer-summary {path} did not contain a JSON object"
        )
    schema = data.get("schema_version")
    if schema != PRODUCER_SCHEMA:
        raise SystemExit(
            "--ao2-producer-summary has unexpected schema_version "
            f"{schema!r}; expected {PRODUCER_SCHEMA!r}"
        )
    return data


def _run_ao2_verifier(
    *,
    ao2_binary: str,
    ao2_native_decision: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ao2_binary,
            "factory",
            "verify-evaluator-decision",
            "--decision",
            str(ao2_native_decision),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "ao2 factory verify-evaluator-decision failed "
            f"(exit {completed.returncode}): {completed.stderr.strip() or '<no stderr>'}"
        )
    stdout = completed.stdout.strip()
    if not stdout:
        raise SystemExit(
            "ao2 factory verify-evaluator-decision produced no stdout JSON"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ao2 factory verify-evaluator-decision returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(
            "ao2 factory verify-evaluator-decision JSON was not an object"
        )
    schema = payload.get("schema_version")
    if schema != AO2_VERIFICATION_SCHEMA:
        raise SystemExit(
            "ao2 verifier returned unexpected schema_version "
            f"{schema!r}; expected {AO2_VERIFICATION_SCHEMA!r}"
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
        "--ao2-native-decision",
        type=Path,
        default=None,
        help="Path to the AO2 native evaluator decision JSON to verify",
    )
    parser.add_argument(
        "--ao2-producer-summary",
        type=Path,
        default=None,
        help=(
            "Optional path to the producer wrapper summary written by "
            "ao2_release_ao2_native_evaluator_producer.py. When supplied and "
            "--ao2-native-decision is not given, the verifier reads the "
            "producer summary to determine whether AO2 emitted a decision "
            "(status=produced) or surfaced its own missing_inputs and "
            "short-circuits accordingly so nightly never fabricates a verdict."
        ),
    )
    parser.add_argument("--write-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    resolved = shutil.which(args.ao2_binary)

    producer_summary: dict[str, Any] | None = None
    producer_status: str | None = None
    producer_missing: list[str] | None = None
    ao2_native_decision = args.ao2_native_decision

    if args.ao2_producer_summary is not None:
        if not args.ao2_producer_summary.is_file():
            raise SystemExit(
                "--ao2-producer-summary path does not exist: "
                f"{args.ao2_producer_summary}"
            )
        producer_summary = _load_producer_summary(args.ao2_producer_summary)
        producer_status = producer_summary.get("status")
        raw_missing = producer_summary.get("missing")
        producer_missing = (
            [str(item) for item in raw_missing] if isinstance(raw_missing, list) else []
        )
        if ao2_native_decision is None and producer_status == "produced":
            decision_path_str = producer_summary.get("ao2_native_decision_path")
            if isinstance(decision_path_str, str) and decision_path_str:
                ao2_native_decision = Path(decision_path_str)

    missing: list[str] = []
    if producer_status == "missing_inputs":
        missing.append("ao2_producer_status_missing_inputs")
    elif ao2_native_decision is None:
        missing.append("ao2_native_decision")
    elif not ao2_native_decision.is_file():
        missing.append(
            f"ao2_native_decision_file_not_found:{ao2_native_decision}"
        )
    if resolved is None:
        missing.append(f"ao2_binary_not_on_path:{args.ao2_binary}")

    if missing:
        payload = _build_missing_inputs_payload(
            ao2_binary=args.ao2_binary,
            ao2_binary_resolved=resolved,
            ao2_native_decision=ao2_native_decision,
            missing=missing,
            producer_summary_path=args.ao2_producer_summary,
            producer_status=producer_status,
            producer_missing=producer_missing,
        )
    else:
        assert ao2_native_decision is not None  # for type-checker
        payload = _run_ao2_verifier(
            ao2_binary=args.ao2_binary,
            ao2_native_decision=ao2_native_decision,
        )
        if args.ao2_producer_summary is not None:
            payload.setdefault("inputs", {})
            if isinstance(payload["inputs"], dict):
                payload["inputs"]["ao2_producer_summary"] = str(
                    args.ao2_producer_summary
                )
            payload["producer"] = {
                "status": producer_status,
                "missing": producer_missing or [],
            }

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.write_json.parent.mkdir(parents=True, exist_ok=True)
    args.write_json.write_text(text, encoding="utf-8")
    if args.json:
        print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
