#!/usr/bin/env python3
"""Hermes context export with AO2-owned identifiers instead of local IDs.

The legacy `hermes_context_payload(slug)` in `factory_run.py` returns a
context block whose `artifacts` section is a set of ao-operator-local file
paths (status markdown, runspec yaml, obligation ledger, evidence-pack
directories). Phase 2 exit-gate item #3 requires that ao-operator / Hermes
context exports instead reference AO2 run IDs, AO2 evidence-pack SHAs,
AO2 memory record IDs, and ao2-control-plane ingest receipts -- not
ao-operator-local IDs.

This module produces a new schema, `ao-operator/hermes-context-with-ao2-refs/v1`,
that drops the local-path artifacts block and replaces it with an
`ao2_refs` block populated from explicitly-supplied AO2-owned inputs:

- the AO2 plan sha256 + planning-evidence path + mapping digest, from the
  bridge evidence written by `scripts/start_ao2_run_from_role_runspec.py`;
- the AO2 evidence-pack sha256 + AO2 run id, from a local AO2 evidence
  pack JSON (`schema_version: ao2.evidence-pack.v1`);
- the AO2 memory record id, from the JSON `ao2 memory write --json`
  emits (`schema_version: ao2.memory-write-result.v1` or similar);
- the ao2-control-plane ingest receipt sha256 + stored_at, from
  `schema_version: ao2.cp-ingest-receipt.v1`.

The script refuses to emit a payload that has zero AO2-owned references,
which is exactly the property the exit gate asks for: "references AO2 IDs,
not ao-operator-local IDs".
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/hermes-context-with-ao2-refs/v1"
ACTION = "hermes-context-with-ao2-refs"

BRIDGE_EVIDENCE_SCHEMA = "ao-operator/start-ao2-run-from-role-runspec/v1"
AO2_NATIVE_BRIDGE_EVIDENCE_SCHEMA = "ao2.factory-bridge.v1"
ACCEPTED_BRIDGE_EVIDENCE_SCHEMAS = frozenset(
    {BRIDGE_EVIDENCE_SCHEMA, AO2_NATIVE_BRIDGE_EVIDENCE_SCHEMA}
)
AO2_EVIDENCE_PACK_SCHEMA = "ao2.evidence-pack.v1"
AO2_CP_INGEST_RECEIPT_SCHEMA = "ao2.cp-ingest-receipt.v1"

TRUST_BOUNDARY: dict[str, str] = {
    "factory_v3_role": "ao_operator_compatibility_layer_emits_ao2_owned_refs",
    "ao2_role": "trusted_execution_runtime_and_signed_evidence_owner",
    "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
    "hermes_role": "front_end_and_memory_reader_consumes_ao2_refs",
    "id_owner": "ao2_owns_every_identifier_referenced_in_this_payload",
}


class MissingAo2RefsError(RuntimeError):
    """Raised when the payload would contain no AO2-owned references."""


class MissingAo2RefCategoryError(RuntimeError):
    """Raised when strict-mode is on and a required AO2 ref category is missing.

    Phase 2 exit-gate item #3 requires ao-operator / Hermes context exports
    to reference AO2 run IDs, AO2 evidence-pack SHAs, AO2 memory record
    IDs, *and* ao2-control-plane ingest receipts. With strict mode on
    (``--require-all-ao2-ref-categories``), the producer refuses to emit
    a payload that omits any of the four input categories so the
    contract becomes machine-checkable instead of "supply at least one".
    """


REQUIRED_AO2_REF_CATEGORIES: tuple[str, ...] = (
    "bridge_evidence",
    "evidence_pack",
    "memory_record",
    "cp_receipt",
)


def _utc_now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clean_slug(slug: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    if not cleaned:
        raise ValueError("slug must contain at least one safe path character")
    return cleaned


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} did not parse to a JSON object")
    return value


def _refs_from_bridge_evidence(bridge: dict[str, Any]) -> dict[str, Any]:
    """Extract AO2-owned references from a bridge-evidence dict.

    Accepts both bridge-evidence schemas:

    - ``ao-operator/start-ao2-run-from-role-runspec/v1`` — emitted by the
      legacy Python helper. Pulls mapping digest +
      ``ao2_invocation.plan_response`` fields (plan_sha256,
      planning_evidence_path, signature triple, invocation status).
    - ``ao2.factory-bridge.v1`` — emitted by ``ao2 factory bridge``
      (and any caller that shells out to it; slice 14 wires the
      orchestrator's signing path through this surface). Pulls the
      mapping digest + the AO2-native ``governed_run_plan`` declaration
      added by ao2 commit ``e129070`` (decision_owner /
      factory_v3_decision_owner / native_gates stages + emits).
    """
    schema = bridge.get("schema")
    if schema not in ACCEPTED_BRIDGE_EVIDENCE_SCHEMAS:
        raise SystemExit(
            "bridge evidence schema must be one of "
            f"{sorted(ACCEPTED_BRIDGE_EVIDENCE_SCHEMAS)!r}; "
            f"got {schema!r}"
        )
    refs: dict[str, Any] = {}
    mapping = bridge.get("mapping") or {}
    if mapping.get("digest"):
        refs["ao2_provider_contract_mapping_digest"] = mapping["digest"]
    if schema == BRIDGE_EVIDENCE_SCHEMA:
        invocation = bridge.get("ao2_invocation") or {}
        plan = invocation.get("plan_response") or {}
        if plan.get("plan_sha256"):
            refs["ao2_plan_sha256"] = plan["plan_sha256"]
        if plan.get("planning_evidence_path"):
            refs["ao2_planning_evidence_path"] = plan["planning_evidence_path"]
        sig = plan.get("signature") or {}
        if isinstance(sig, dict):
            for key in (
                "signature_sha256",
                "public_key_sha256",
                "signed_payload_sha256",
            ):
                if sig.get(key):
                    refs.setdefault("ao2_plan_signature", {})[key] = sig[key]
        if invocation.get("status"):
            refs["ao2_invocation_status"] = invocation["status"]
    elif schema == AO2_NATIVE_BRIDGE_EVIDENCE_SCHEMA:
        plan = bridge.get("governed_run_plan")
        if isinstance(plan, dict):
            for source_key, ref_key in (
                ("schema", "ao2_governed_run_plan_schema"),
                ("status", "ao2_governed_run_plan_status"),
                ("decision_owner", "ao2_governed_run_plan_decision_owner"),
                (
                    "factory_v3_decision_owner",
                    "ao2_governed_run_plan_factory_v3_decision_owner",
                ),
            ):
                value = plan.get(source_key)
                if value is not None:
                    refs[ref_key] = value
            native_gates = plan.get("native_gates") or []
            refs["ao2_governed_run_plan_native_gates_count"] = len(native_gates)
            refs["ao2_governed_run_plan_native_gate_stages"] = [
                gate.get("stage") for gate in native_gates
            ]
            refs["ao2_governed_run_plan_native_gate_emits"] = [
                gate.get("emits") for gate in native_gates
            ]
        if bridge.get("status"):
            refs["ao2_invocation_status"] = bridge["status"]
    return refs


def _refs_from_evidence_pack(pack: dict[str, Any], pack_path: Path) -> dict[str, Any]:
    if pack.get("schema_version") != AO2_EVIDENCE_PACK_SCHEMA:
        raise SystemExit(
            f"AO2 evidence-pack schema must be {AO2_EVIDENCE_PACK_SCHEMA!r}; "
            f"got {pack.get('schema_version')!r}"
        )
    refs: dict[str, Any] = {
        "ao2_evidence_pack_sha256": sha256_file(pack_path),
    }
    if pack.get("run_id"):
        refs["ao2_run_id"] = pack["run_id"]
    elif pack.get("ticket_id"):
        refs["ao2_run_id"] = pack["ticket_id"]
    if pack.get("closure_status"):
        refs["ao2_closure_status"] = pack["closure_status"]
    return refs


def _refs_from_memory_record(
    record: dict[str, Any],
    memory_record_path: Path | None = None,
) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    rid = record.get("record_id") or record.get("memory_record_id") or record.get("id")
    if rid:
        refs["ao2_memory_record_id"] = str(rid)
    if record.get("sha256"):
        refs["ao2_memory_record_sha256"] = record["sha256"]
    elif memory_record_path is not None:
        refs["ao2_memory_record_sha256"] = sha256_file(memory_record_path)
    if record.get("schema_version"):
        refs["ao2_memory_record_schema"] = record["schema_version"]
    return refs


def _refs_from_cp_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    if receipt.get("schema_version") != AO2_CP_INGEST_RECEIPT_SCHEMA:
        raise SystemExit(
            f"control-plane receipt schema must be {AO2_CP_INGEST_RECEIPT_SCHEMA!r}; "
            f"got {receipt.get('schema_version')!r}"
        )
    refs: dict[str, Any] = {}
    if receipt.get("sha256"):
        refs["control_plane_ingest_sha256"] = receipt["sha256"]
    if receipt.get("stored_at"):
        refs["control_plane_stored_at"] = receipt["stored_at"]
    if receipt.get("ingested_schema_version"):
        refs["control_plane_ingested_schema_version"] = receipt["ingested_schema_version"]
    return refs


def build_payload(
    slug: str,
    *,
    bridge_evidence: dict[str, Any] | None = None,
    evidence_pack: dict[str, Any] | None = None,
    evidence_pack_path: Path | None = None,
    memory_record: dict[str, Any] | None = None,
    memory_record_path: Path | None = None,
    cp_receipt: dict[str, Any] | None = None,
    require_all_ao2_ref_categories: bool = False,
) -> dict[str, Any]:
    if require_all_ao2_ref_categories:
        category_inputs = {
            "bridge_evidence": bridge_evidence,
            "evidence_pack": evidence_pack,
            "memory_record": memory_record,
            "cp_receipt": cp_receipt,
        }
        missing = sorted(
            name for name, value in category_inputs.items() if value is None
        )
        if missing:
            raise MissingAo2RefCategoryError(
                "strict mode requires all four Phase 2 #3 AO2 ref "
                "categories (bridge_evidence, evidence_pack, "
                "memory_record, cp_receipt); missing: " + ", ".join(missing)
            )
    clean = _clean_slug(slug)
    ao2_refs: dict[str, Any] = {}
    if bridge_evidence is not None:
        ao2_refs.update(_refs_from_bridge_evidence(bridge_evidence))
    if evidence_pack is not None:
        if evidence_pack_path is None:
            raise SystemExit("evidence_pack supplied without evidence_pack_path")
        ao2_refs.update(_refs_from_evidence_pack(evidence_pack, evidence_pack_path))
    if memory_record is not None:
        ao2_refs.update(
            _refs_from_memory_record(memory_record, memory_record_path)
        )
    if cp_receipt is not None:
        ao2_refs.update(_refs_from_cp_receipt(cp_receipt))

    if not ao2_refs:
        raise MissingAo2RefsError(
            "no AO2-owned identifiers supplied; provide at least one of "
            "--bridge-evidence, --evidence-pack, --memory-record, or "
            "--control-plane-receipt so the payload references AO2 IDs "
            "instead of ao-operator-local IDs"
        )

    supplied_categories = {
        "bridge_evidence": bridge_evidence is not None,
        "evidence_pack": evidence_pack is not None,
        "memory_record": memory_record is not None,
        "cp_receipt": cp_receipt is not None,
    }
    return {
        "schema": SCHEMA,
        "action": ACTION,
        "generated_at": _utc_now_iso(),
        "slug": clean,
        "factory_v3_local_paths_omitted": True,
        "ao2_refs": dict(sorted(ao2_refs.items())),
        "ao2_ref_categories_supplied": dict(sorted(supplied_categories.items())),
        "ao2_ref_categories_required_for_phase2_exit_gate_3": list(
            REQUIRED_AO2_REF_CATEGORIES
        ),
        "ao2_ref_categories_all_supplied": all(supplied_categories.values()),
        "trust_boundary": dict(sorted(TRUST_BOUNDARY.items())),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit a Hermes context payload that references AO2-owned "
            "identifiers (run IDs, evidence-pack SHAs, memory record IDs, "
            "control-plane receipts) instead of ao-operator-local paths."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--bridge-evidence", type=Path, default=None)
    parser.add_argument("--evidence-pack", type=Path, default=None)
    parser.add_argument("--memory-record", type=Path, default=None)
    parser.add_argument("--control-plane-receipt", type=Path, default=None)
    parser.add_argument(
        "--require-all-ao2-ref-categories",
        action="store_true",
        help=(
            "Strict mode: refuse to emit a payload unless all four Phase "
            "2 exit-gate #3 AO2 ref categories (bridge_evidence, "
            "evidence_pack, memory_record, cp_receipt) are supplied. "
            "Makes the four-category contract machine-checkable instead "
            "of relying on the looser 'at least one' default."
        ),
    )
    parser.add_argument("--out", type=Path, default=None, help="optional file to write payload")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = _load_json(args.bridge_evidence) if args.bridge_evidence else None
    pack = _load_json(args.evidence_pack) if args.evidence_pack else None
    record = _load_json(args.memory_record) if args.memory_record else None
    receipt = _load_json(args.control_plane_receipt) if args.control_plane_receipt else None
    try:
        payload = build_payload(
            args.slug,
            bridge_evidence=bridge,
            evidence_pack=pack,
            evidence_pack_path=args.evidence_pack,
            memory_record=record,
            memory_record_path=args.memory_record,
            cp_receipt=receipt,
            require_all_ao2_ref_categories=args.require_all_ao2_ref_categories,
        )
    except (MissingAo2RefsError, MissingAo2RefCategoryError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
