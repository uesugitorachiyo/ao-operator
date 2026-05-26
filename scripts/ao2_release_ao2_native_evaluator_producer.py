#!/usr/bin/env python3
"""Produce the AO2 native evaluator decision the nightly verifier consumes.

Phase 2 exit-gate item #4 requires AO2 to own the closure verdict for
ao-operator release-line decisions. The verifier helper
(``scripts/ao2_release_ao2_native_evaluator_verification.py``) consumes
a decision file with schema_version
``ao2.ao-operator-compat-native-evaluator-result.v1`` that AO2 emits via
``ao2 factory evaluate --evidence-pack <pack> --out <decision> --json``.

Until this producer existed, the nightly pipeline had no way to wire a
real AO2 native decision into the verifier and the verifier
short-circuited to ``status=missing_inputs`` every run. This helper
closes that gap:

- If ``--evidence-pack`` exists and the ``ao2`` binary resolves on PATH
  (``--ao2-binary`` override allowed), the helper invokes
  ``ao2 factory evaluate`` against the supplied inputs, writes the AO2
  native decision to ``--ao2-decision-out``, and emits a wrapper
  summary with status=``produced`` referencing the decision path and
  schema.
- Otherwise the helper writes a wrapper summary with
  status=``missing_inputs`` enumerating the missing inputs. The nightly
  verifier consumes the wrapper summary via ``--ao2-producer-summary``
  and inherits the missing_inputs short-circuit so nightly never
  fabricates a closure verdict.

The wrapper schema is ``ao-operator/ao2-release-ao2-native-evaluator-producer/v1``.

This script is pure stdlib (argparse / json / pathlib / shutil /
subprocess). It never embeds bearer tokens, secrets, cookies or
credentials, and it does not mutate any AO2 artifact. The ao-operator
side never produces the AO2 decision itself; the producer only
*invokes* AO2, captures the path AO2 wrote, and records that fact.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PRODUCER_SCHEMA = "ao-operator/ao2-release-ao2-native-evaluator-producer/v1"
AO2_DECISION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-result.v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-native-evaluator-closer"
EXPECTED_CONTROL_PLANE_ROLE = "read_only_observer"


def _input_summary(
    *,
    ao2_binary: str,
    ao2_binary_resolved: str | None,
    evidence_pack: Path | None,
    report: Path | None,
    factory_decision: Path | None,
    signing_key: Path | None,
    signer_id: str,
    ao2_decision_out: Path,
) -> dict[str, Any]:
    return {
        "ao2_binary": ao2_binary,
        "ao2_binary_resolved": ao2_binary_resolved,
        "evidence_pack": str(evidence_pack) if evidence_pack is not None else None,
        "report": str(report) if report is not None else None,
        "factory_decision": (
            str(factory_decision) if factory_decision is not None else None
        ),
        "signing_key": str(signing_key) if signing_key is not None else None,
        "signer_id": signer_id,
        "ao2_decision_out": str(ao2_decision_out),
    }


def _build_missing_inputs_payload(
    *,
    inputs: dict[str, Any],
    missing: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCER_SCHEMA,
        "status": "missing_inputs",
        "missing": missing,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
        "ao2_native_decision_path": inputs["ao2_decision_out"],
        "ao2_native_decision_schema": AO2_DECISION_SCHEMA,
        "ao2_native_decision_emitted": False,
        "inputs": inputs,
        "next_action": (
            "supply --evidence-pack pointing at an ao2.evidence-pack.v1 file "
            "and ensure the ao2 binary resolves on PATH (or pass --ao2-binary "
            "with a full path); the AO2 native evaluator decision will then "
            "be produced via 'ao2 factory evaluate' and the nightly verifier "
            "will run for real instead of inheriting missing_inputs"
        ),
    }


def _build_produced_payload(
    *,
    inputs: dict[str, Any],
    ao2_result: dict[str, Any],
    ao2_decision_out: Path,
) -> dict[str, Any]:
    verdict_value = ao2_result.get("verdict")
    verdict_status: str | None = None
    if isinstance(verdict_value, dict):
        candidate = verdict_value.get("status")
        if isinstance(candidate, str):
            verdict_status = candidate
    elif isinstance(verdict_value, str):
        verdict_status = verdict_value
    return {
        "schema_version": PRODUCER_SCHEMA,
        "status": "produced",
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
        "ao2_native_decision_path": str(ao2_decision_out),
        "ao2_native_decision_schema": AO2_DECISION_SCHEMA,
        "ao2_native_decision_emitted": True,
        "ao2_native_decision_verdict": verdict_status,
        "ao2_native_decision_summary": {
            "schema_version": ao2_result.get("schema_version"),
            "owner": ao2_result.get("owner"),
            "verdict": verdict_status,
            "decision_path": ao2_result.get("decision_path"),
            "factory_v3_evaluator_compared_when_supplied": ao2_result.get(
                "factory_v3_evaluator_compared_when_supplied"
            ),
            "factory_v3_role": ao2_result.get("factory_v3_role"),
        },
        "inputs": inputs,
        "next_action": (
            "pass --ao2-native-decision pointing at ao2_native_decision_path "
            "(or --ao2-producer-summary pointing at this wrapper) to "
            "ao2_release_ao2_native_evaluator_verification.py so AO2 owns "
            "the verifier verdict"
        ),
    }


def _invoke_ao2_evaluate(
    *,
    ao2_binary: str,
    evidence_pack: Path,
    report: Path | None,
    factory_decision: Path | None,
    signing_key: Path | None,
    signer_id: str,
    ao2_decision_out: Path,
) -> dict[str, Any]:
    command = [
        ao2_binary,
        "factory",
        "evaluate",
        "--evidence-pack",
        str(evidence_pack),
        "--out",
        str(ao2_decision_out),
        "--signer-id",
        signer_id,
        "--json",
    ]
    if report is not None:
        command.extend(["--report", str(report)])
    if factory_decision is not None:
        command.extend(["--factory-decision", str(factory_decision)])
    if signing_key is not None:
        command.extend(["--signing-key", str(signing_key)])

    ao2_decision_out.parent.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "ao2 factory evaluate failed "
            f"(exit {completed.returncode}): "
            f"{completed.stderr.strip() or '<no stderr>'}"
        )
    stdout = completed.stdout.strip()
    if not stdout:
        raise SystemExit("ao2 factory evaluate produced no stdout JSON")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ao2 factory evaluate returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit("ao2 factory evaluate JSON was not an object")
    schema = payload.get("schema_version")
    if schema != AO2_DECISION_SCHEMA:
        raise SystemExit(
            "ao2 factory evaluate returned unexpected schema_version "
            f"{schema!r}; expected {AO2_DECISION_SCHEMA!r}"
        )
    if not ao2_decision_out.is_file():
        raise SystemExit(
            "ao2 factory evaluate did not write the AO2 native decision file at "
            f"{ao2_decision_out}"
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
        "--evidence-pack",
        type=Path,
        default=None,
        help="Path to the ao2.evidence-pack.v1 AO2 should evaluate",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to the report JSON passed to 'ao2 factory evaluate --report'",
    )
    parser.add_argument(
        "--factory-decision",
        type=Path,
        default=None,
        help=(
            "Optional path to a ao-operator evaluator decision used for "
            "parity comparison; AO2 still owns the verdict"
        ),
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        default=None,
        help="Optional path to AO2's signing key",
    )
    parser.add_argument(
        "--signer-id",
        default=EXPECTED_AO2_DECISION_OWNER,
        help=(
            "Signer identity recorded in the AO2 native evaluator decision "
            f"(default: {EXPECTED_AO2_DECISION_OWNER})"
        ),
    )
    parser.add_argument(
        "--ao2-decision-out",
        type=Path,
        required=True,
        help="Path the AO2 native evaluator decision JSON is written to",
    )
    parser.add_argument("--write-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    resolved = shutil.which(args.ao2_binary)
    inputs = _input_summary(
        ao2_binary=args.ao2_binary,
        ao2_binary_resolved=resolved,
        evidence_pack=args.evidence_pack,
        report=args.report,
        factory_decision=args.factory_decision,
        signing_key=args.signing_key,
        signer_id=args.signer_id,
        ao2_decision_out=args.ao2_decision_out,
    )

    missing: list[str] = []
    if args.evidence_pack is None:
        missing.append("evidence_pack")
    elif not args.evidence_pack.is_file():
        missing.append(f"evidence_pack_file_not_found:{args.evidence_pack}")
    if args.report is not None and not args.report.is_file():
        missing.append(f"report_file_not_found:{args.report}")
    if args.factory_decision is not None and not args.factory_decision.is_file():
        missing.append(f"factory_decision_file_not_found:{args.factory_decision}")
    if args.signing_key is not None and not args.signing_key.is_file():
        missing.append(f"signing_key_file_not_found:{args.signing_key}")
    if resolved is None:
        missing.append(f"ao2_binary_not_on_path:{args.ao2_binary}")

    if missing:
        payload = _build_missing_inputs_payload(inputs=inputs, missing=missing)
    else:
        assert args.evidence_pack is not None  # for type-checker
        ao2_result = _invoke_ao2_evaluate(
            ao2_binary=args.ao2_binary,
            evidence_pack=args.evidence_pack,
            report=args.report,
            factory_decision=args.factory_decision,
            signing_key=args.signing_key,
            signer_id=args.signer_id,
            ao2_decision_out=args.ao2_decision_out,
        )
        payload = _build_produced_payload(
            inputs=inputs,
            ao2_result=ao2_result,
            ao2_decision_out=args.ao2_decision_out,
        )

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.write_json.parent.mkdir(parents=True, exist_ok=True)
    args.write_json.write_text(text, encoding="utf-8")
    if args.json:
        print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
