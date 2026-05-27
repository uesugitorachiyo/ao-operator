#!/usr/bin/env python3
"""Drive an AO2 factory-compat run end-to-end for the nightly pipeline.

Phase 2 exit-gate items #1, #2, #4, and #5 all require nightly evidence
that AO Operator (ao-operator) can hand a RunSpec input to AO2 and let
AO2 own planning, queue execution, retry/cancel semantics, evaluator
closure, and the signed evidence pack. The preferred path is now
``ao2 factory governed-run``; the older plan/queue/pack command chain is
kept as an explicit compatibility path for older AO2 binaries and tests.

This orchestrator materialises a fresh factory-compat target by copying
a fixture repo, writes a deterministic ao-operator-style request +
RunSpec into a scratch workdir, then delegates the whole authoritative
chain to AO2's native governed-run command.

Factory-v3 never executes the run; it only orchestrates the CLI calls
and reports AO2's verdicts verbatim. Signing key material, when
supplied, is forwarded path-only to AO2 (``--signing-key``); AO2 owns
the key, the canonicalisation, and the sidecar writes.

The summary schema is ``ao-operator/ao2-factory-compat-nightly-run/v1``.
``status`` is one of ``produced``, ``missing_inputs``, or ``failed``.
When the orchestrator runs to completion, the populated
``factory_target`` directory is exactly what the downstream
``ao2_release_ao2_native_evidence_pack_producer.py`` expects for
``--ao2-target``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import hermes_context_with_ao2_refs as ao2_refs_helper  # noqa: E402
import start_ao2_run_from_role_runspec as bridge  # noqa: E402

ORCHESTRATOR_SCHEMA = "ao-operator/ao2-factory-compat-nightly-run/v1"
AO2_PLAN_SCHEMA = "ao2.ao-operator-compat-plan-result.v1"
AO2_QUEUE_SUBMIT_SCHEMA = "ao2.ao-operator-compat-workbench-queue-submit.v1"
AO2_QUEUE_RUN_NEXT_SCHEMA = "ao2.ao-operator-compat-workbench-queue-run-next.v1"
AO2_PACK_EVIDENCE_SCHEMA = "ao2.ao-operator-compat-pack-evidence.v1"
AO2_GOVERNED_RUN_SCHEMA = "ao2.ao-operator-compat-governed-run.v1"
AO2_EVIDENCE_PACK_SCHEMA = "ao2.evidence-pack.v1"
AO2_MEMORY_RECORD_SCHEMA = "ao2.memory-record.v1"

DEFAULT_MEMORY_RECORD_KIND = "ao-operator-compat-nightly-run"

EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-native-governed-run"
EXPECTED_CONTROL_PLANE_ROLE = "read_only_observer_after_signed_evidence"

DEFAULT_RUN_ID = "nightly-factory-compat-run"
DEFAULT_RUNSPEC_ID = "nightly-factory-compat"
DEFAULT_VERIFIER = "python -m pytest -q"
DEFAULT_REQUEST_TITLE = (
    "AO2 nightly factory-compat governed execution"
)
DEFAULT_REQUEST_OBJECTIVE = (
    "Hand a deterministic ao-operator-style RunSpec to AO2 and let AO2 own "
    "planning, queue execution, retry/cancel semantics, and the signed "
    "evidence pack while ao-operator remains a parity oracle."
)
DEFAULT_REQUEST_ACCEPTANCE = (
    "- AO2 owns the factory-compat plan, queue execution, evidence pack, "
    "and signature; ao-operator only observes the verdict."
)


def _input_summary(
    *,
    ao2_binary: str,
    ao2_binary_resolved: str | None,
    ao2_fixture: Path,
    factory_target: Path,
    run_id: str,
    signing_key: Path | None,
    signer_id: str | None,
    runspec_id: str,
    runspec_verifier: str,
    ao_operator_runspec: Path | None,
    bridge_evidence_out: Path | None,
    bridge_evidence_signing_key: Path | None,
    bridge_evidence_signer_id: str | None,
    hermes_context_out: Path | None,
    hermes_context_slug: str | None,
    control_plane_receipt: Path | None,
    memory_record_out: Path | None,
    memory_record_target: Path | None,
    memory_record_kind: str | None,
    memory_record_title: str | None,
    memory_record_body: str | None,
    require_all_ao2_ref_categories: bool = False,
) -> dict[str, Any]:
    return {
        "ao2_binary": ao2_binary,
        "ao2_binary_resolved": ao2_binary_resolved,
        "ao2_fixture": str(ao2_fixture),
        "factory_target": str(factory_target),
        "run_id": run_id,
        "signing_key": str(signing_key) if signing_key is not None else None,
        "signer_id": signer_id,
        "runspec_id": runspec_id,
        "runspec_verifier": runspec_verifier,
        "ao_operator_runspec": (
            str(ao_operator_runspec) if ao_operator_runspec is not None else None
        ),
        "bridge_evidence_out": (
            str(bridge_evidence_out) if bridge_evidence_out is not None else None
        ),
        "bridge_evidence_signing_key": (
            str(bridge_evidence_signing_key)
            if bridge_evidence_signing_key is not None
            else None
        ),
        "bridge_evidence_signer_id": (
            bridge_evidence_signer_id
            if bridge_evidence_signing_key is not None
            else None
        ),
        "hermes_context_out": (
            str(hermes_context_out) if hermes_context_out is not None else None
        ),
        "hermes_context_slug": hermes_context_slug,
        "control_plane_receipt": (
            str(control_plane_receipt) if control_plane_receipt is not None else None
        ),
        "memory_record_out": (
            str(memory_record_out) if memory_record_out is not None else None
        ),
        "memory_record_target": (
            str(memory_record_target) if memory_record_target is not None else None
        ),
        "memory_record_kind": memory_record_kind,
        "memory_record_title": memory_record_title,
        "memory_record_body": memory_record_body,
        "require_all_ao2_ref_categories": require_all_ao2_ref_categories,
    }


def _trust_boundary() -> dict[str, str]:
    return {
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "control_plane_role": EXPECTED_CONTROL_PLANE_ROLE,
    }


def _build_missing_inputs_payload(
    *, inputs: dict[str, Any], missing: list[str]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "missing_inputs",
        "stage": "preflight",
        "missing": missing,
        "inputs": inputs,
        "factory_target": None,
        "evidence_pack_path": None,
        "next_action": (
            "supply --ao2-binary that resolves on PATH, --ao2-fixture "
            "pointing at a factory-compat repo to copy, and a writeable "
            "--target; the orchestrator will then drive plan, "
            "queue-submit, queue-run-next, and pack-evidence end-to-end"
        ),
        "bridge_evidence": None,
        "hermes_context_with_ao2_refs": None,
        "memory_record": None,
    }
    payload.update(_trust_boundary())
    return payload


def _build_failed_payload(
    *,
    inputs: dict[str, Any],
    stage: str,
    reason: str,
    factory_target: Path,
    partial: dict[str, Any] | None = None,
    bridge_evidence_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "failed",
        "stage": stage,
        "failure_reason": reason,
        "inputs": inputs,
        "factory_target": str(factory_target),
        "evidence_pack_path": None,
        "partial": partial or {},
        "next_action": (
            f"resolve the {stage!r} failure surfaced in failure_reason and "
            "re-run; the orchestrator will not advance past a failing stage"
        ),
        "bridge_evidence": bridge_evidence_summary,
        "hermes_context_with_ao2_refs": None,
        "memory_record": None,
    }
    payload.update(_trust_boundary())
    return payload


def _build_produced_payload(
    *,
    inputs: dict[str, Any],
    factory_target: Path,
    run_id: str,
    plan_path: Path,
    plan_stdout: dict[str, Any],
    queue_submit_stdout: dict[str, Any],
    queue_run_next_stdout: dict[str, Any],
    pack_evidence_stdout: dict[str, Any],
    evidence_pack_path: Path,
    evidence_pack_sha256: str,
    governed_run_stdout: dict[str, Any] | None = None,
    bridge_evidence_summary: dict[str, Any] | None = None,
    hermes_context_summary: dict[str, Any] | None = None,
    memory_record_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "produced",
        "stage": "complete",
        "inputs": inputs,
        "factory_target": str(factory_target),
        "run_id": run_id,
        "plan_path": str(plan_path),
        "plan": {
            "schema_version": plan_stdout.get("schema_version"),
            "evidence_path": plan_stdout.get("evidence_path"),
            "plan_path": plan_stdout.get("plan_path"),
            "workflow_path": plan_stdout.get("workflow_path"),
            "factory_v3_drives_workflow": plan_stdout.get(
                "factory_v3_drives_workflow"
            ),
        },
        "queue_submit": {
            "schema_version": queue_submit_stdout.get("schema_version"),
            "run_id": queue_submit_stdout.get("run_id"),
            "status": queue_submit_stdout.get("status"),
            "queue_path": queue_submit_stdout.get("queue_path"),
        },
        "queue_run_next": {
            "schema_version": queue_run_next_stdout.get("schema_version"),
            "run_id": queue_run_next_stdout.get("run_id"),
            "status": queue_run_next_stdout.get("status"),
            "entry_status": (
                (queue_run_next_stdout.get("entry") or {}).get("status")
            ),
            "native_evaluator_verdict": (
                (queue_run_next_stdout.get("entry") or {}).get(
                    "native_evaluator_verdict"
                )
            ),
            "evidence_pack": (
                (queue_run_next_stdout.get("entry") or {}).get(
                    "evidence_pack"
                )
            ),
            "run_result_path": (
                (queue_run_next_stdout.get("entry") or {}).get(
                    "run_result_path"
                )
            ),
            "parity_checklist_progress": queue_run_next_stdout.get(
                "parity_checklist_progress"
            ),
        },
        "pack_evidence_summary": {
            "schema_version": pack_evidence_stdout.get("schema_version"),
            "run_id": pack_evidence_stdout.get("run_id"),
            "entry_status": pack_evidence_stdout.get("entry_status"),
            "native_evaluator_verdict": pack_evidence_stdout.get(
                "native_evaluator_verdict"
            ),
            "evidence_pack_source": pack_evidence_stdout.get(
                "evidence_pack_source"
            ),
            "evidence_pack_source_sha256": pack_evidence_stdout.get(
                "evidence_pack_source_sha256"
            ),
            "evidence_pack_execution_owner": pack_evidence_stdout.get(
                "evidence_pack_execution_owner"
            ),
        },
        "evidence_pack_path": str(evidence_pack_path),
        "evidence_pack_sha256": evidence_pack_sha256,
        "evidence_pack_schema": AO2_EVIDENCE_PACK_SCHEMA,
        # AO2 owns the signature + replay verdicts; surface them verbatim.
        "evidence_pack_signature": pack_evidence_stdout.get("signature"),
        "evidence_pack_deterministic_replay": pack_evidence_stdout.get(
            "deterministic_replay"
        ),
        "governed_run": (
            {
                "schema_version": governed_run_stdout.get("schema_version"),
                "status": governed_run_stdout.get("status"),
                "run_id": governed_run_stdout.get("run_id"),
                "artifacts": governed_run_stdout.get("artifacts"),
                "checklist": governed_run_stdout.get("governed_run_checklist"),
                "ao2_decision_owner": governed_run_stdout.get(
                    "ao2_decision_owner"
                ),
                "factory_v3_role": governed_run_stdout.get("factory_v3_role"),
                "control_plane_role": governed_run_stdout.get(
                    "control_plane_role"
                ),
            }
            if governed_run_stdout is not None
            else None
        ),
        "next_action": (
            "point ao2_release_ao2_native_evidence_pack_producer.py at "
            "factory_target so AO2's signed evidence pack feeds the "
            "downstream evaluator-decision producer for real"
        ),
        "bridge_evidence": bridge_evidence_summary,
        "hermes_context_with_ao2_refs": hermes_context_summary,
        "memory_record": memory_record_summary,
    }
    payload.update(_trust_boundary())
    return payload


def _materialise_target(*, fixture: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, target)


def _write_request_yaml(
    *,
    path: Path,
    title: str,
    objective: str,
    acceptance: str,
) -> None:
    body = (
        f"title: {title}\n"
        f"objective: {objective}\n"
        "acceptance:\n"
        f"{acceptance}\n"
    )
    path.write_text(body, encoding="utf-8")


def _write_runspec_yaml(
    *,
    path: Path,
    runspec_id: str,
    verifier: str,
) -> None:
    body = f"id: {runspec_id}\nverifier: {verifier}\n"
    path.write_text(body, encoding="utf-8")


def _run_ao2(
    *,
    ao2_binary: str,
    subcommand: list[str],
    expected_schema: str,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    command = [ao2_binary, *subcommand, "--json"]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise _AO2Failure(
            stage=subcommand[1] if len(subcommand) >= 2 else subcommand[0],
            reason=(
                f"ao2 {' '.join(subcommand)} failed (exit "
                f"{completed.returncode}): "
                f"{completed.stderr.strip() or '<no stderr>'}"
            ),
            completed=completed,
        )
    stdout = completed.stdout.strip()
    if not stdout:
        raise _AO2Failure(
            stage=subcommand[1] if len(subcommand) >= 2 else subcommand[0],
            reason=(
                f"ao2 {' '.join(subcommand)} produced no stdout JSON"
            ),
            completed=completed,
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise _AO2Failure(
            stage=subcommand[1] if len(subcommand) >= 2 else subcommand[0],
            reason=f"ao2 returned invalid JSON: {exc}",
            completed=completed,
        ) from exc
    if not isinstance(payload, dict):
        raise _AO2Failure(
            stage=subcommand[1] if len(subcommand) >= 2 else subcommand[0],
            reason="ao2 stdout JSON was not an object",
            completed=completed,
        )
    schema = payload.get("schema_version")
    if schema != expected_schema:
        raise _AO2Failure(
            stage=subcommand[1] if len(subcommand) >= 2 else subcommand[0],
            reason=(
                f"ao2 returned unexpected schema_version {schema!r}; "
                f"expected {expected_schema!r}"
            ),
            completed=completed,
        )
    return payload, completed


class _AO2Failure(Exception):
    def __init__(
        self,
        *,
        stage: str,
        reason: str,
        completed: subprocess.CompletedProcess[str] | None,
    ) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.completed = completed


def _ao2_factory_plan(
    *,
    ao2_binary: str,
    request_path: Path,
    runspec_path: Path,
    factory_target: Path,
    plan_out: Path,
) -> dict[str, Any]:
    payload, _ = _run_ao2(
        ao2_binary=ao2_binary,
        subcommand=[
            "factory",
            "plan",
            "--request",
            str(request_path),
            "--runspec",
            str(runspec_path),
            "--target",
            str(factory_target),
            "--out",
            str(plan_out),
        ],
        expected_schema=AO2_PLAN_SCHEMA,
    )
    return payload


def _ao2_factory_queue_submit(
    *,
    ao2_binary: str,
    plan_path: Path,
    factory_target: Path,
    run_id: str,
) -> dict[str, Any]:
    payload, _ = _run_ao2(
        ao2_binary=ao2_binary,
        subcommand=[
            "factory",
            "queue-submit",
            "--plan",
            str(plan_path),
            "--target",
            str(factory_target),
            "--run-id",
            run_id,
        ],
        expected_schema=AO2_QUEUE_SUBMIT_SCHEMA,
    )
    return payload


def _ao2_factory_queue_run_next(
    *,
    ao2_binary: str,
    factory_target: Path,
) -> dict[str, Any]:
    payload, _ = _run_ao2(
        ao2_binary=ao2_binary,
        subcommand=[
            "factory",
            "queue-run-next",
            "--target",
            str(factory_target),
        ],
        expected_schema=AO2_QUEUE_RUN_NEXT_SCHEMA,
    )
    return payload


def _ao2_factory_pack_evidence(
    *,
    ao2_binary: str,
    factory_target: Path,
    run_id: str,
    evidence_pack_out: Path,
    signing_key: Path | None,
    signer_id: str | None,
) -> dict[str, Any]:
    subcommand = [
        "factory",
        "pack-evidence",
        "--target",
        str(factory_target),
        "--run-id",
        run_id,
        "--out",
        str(evidence_pack_out),
    ]
    if signing_key is not None:
        subcommand.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        subcommand.extend(["--signer-id", signer_id])
    payload, _ = _run_ao2(
        ao2_binary=ao2_binary,
        subcommand=subcommand,
        expected_schema=AO2_PACK_EVIDENCE_SCHEMA,
    )
    pack_schema = payload.get("evidence_pack_schema_version")
    if pack_schema != AO2_EVIDENCE_PACK_SCHEMA:
        raise _AO2Failure(
            stage="pack-evidence",
            reason=(
                "ao2 factory pack-evidence reported evidence_pack_schema_"
                f"version {pack_schema!r}; expected "
                f"{AO2_EVIDENCE_PACK_SCHEMA!r}"
            ),
            completed=None,
        )
    if payload.get("status") != "produced":
        raise _AO2Failure(
            stage="pack-evidence",
            reason=(
                "ao2 factory pack-evidence reported status "
                f"{payload.get('status')!r}; expected 'produced'"
            ),
            completed=None,
        )
    if not evidence_pack_out.is_file():
        raise _AO2Failure(
            stage="pack-evidence",
            reason=(
                "ao2 factory pack-evidence did not write the evidence "
                f"pack file at {evidence_pack_out}"
            ),
            completed=None,
        )
    return payload


def _ao2_factory_governed_run(
    *,
    ao2_binary: str,
    request_path: Path,
    runspec_path: Path,
    factory_target: Path,
    run_id: str,
    out_dir: Path,
    evidence_pack_out: Path,
    signing_key: Path | None,
    signer_id: str | None,
) -> dict[str, Any]:
    subcommand = [
        "factory",
        "governed-run",
        "--request",
        str(request_path),
        "--runspec",
        str(runspec_path),
        "--target",
        str(factory_target),
        "--run-id",
        run_id,
        "--out-dir",
        str(out_dir),
    ]
    if signing_key is not None:
        subcommand.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        subcommand.extend(["--signer-id", signer_id])
    payload, _ = _run_ao2(
        ao2_binary=ao2_binary,
        subcommand=subcommand,
        expected_schema=AO2_GOVERNED_RUN_SCHEMA,
    )
    status = payload.get("status")
    if status != "accepted":
        raise _AO2Failure(
            stage="governed-run",
            reason=(
                "ao2 factory governed-run reported status "
                f"{status!r}; expected 'accepted'"
            ),
            completed=None,
        )

    pack_payload = payload.get("pack_evidence") or {}
    pack_schema = pack_payload.get("evidence_pack_schema_version")
    if pack_schema != AO2_EVIDENCE_PACK_SCHEMA:
        raise _AO2Failure(
            stage="governed-run",
            reason=(
                "ao2 factory governed-run reported evidence_pack_schema_"
                f"version {pack_schema!r}; expected "
                f"{AO2_EVIDENCE_PACK_SCHEMA!r}"
            ),
            completed=None,
        )

    packed_evidence = (payload.get("artifacts") or {}).get("packed_evidence")
    source = Path(str(packed_evidence)) if packed_evidence else evidence_pack_out
    if not source.is_file():
        raise _AO2Failure(
            stage="governed-run",
            reason=(
                "ao2 factory governed-run did not write the packed "
                f"evidence file at {source}"
            ),
            completed=None,
        )
    if source.resolve() != evidence_pack_out.resolve():
        evidence_pack_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, evidence_pack_out)
        for suffix in (".sig", ".public.pem", ".signed-payload.json"):
            source_sidecar = Path(str(source) + suffix)
            if source_sidecar.is_file():
                shutil.copyfile(source_sidecar, Path(str(evidence_pack_out) + suffix))
    return payload


def _ao2_memory_write(
    *,
    ao2_binary: str,
    memory_target: Path,
    kind: str,
    title: str,
    body: str,
    source_run_id: str,
) -> dict[str, Any]:
    """Run ``ao2 memory write --json`` and return the AO2-owned record.

    The AO2 CLI canonicalises the record id (``mem-<ms>-<digest12>``),
    sets ``schema_version=ao2.memory-record.v1``, and appends the record
    to ``<memory_target>/.ao2/memory/records.jsonl``. We only consume the
    returned JSON; the records.jsonl side effect is incidental to the
    factory-compat target and gets cleared on the next nightly when the
    target dir is rebuilt from fixture.
    """
    try:
        payload, _ = _run_ao2(
            ao2_binary=ao2_binary,
            subcommand=[
                "memory",
                "write",
                "--target",
                str(memory_target),
                "--kind",
                kind,
                "--title",
                title,
                "--body",
                body,
                "--source-run-id",
                source_run_id,
            ],
            expected_schema=AO2_MEMORY_RECORD_SCHEMA,
        )
    except _AO2Failure as failure:
        # _run_ao2 infers stage from subcommand[1] ("write"); rewrap so
        # the produced/failed payload surfaces the unambiguous AO2 verb.
        raise _AO2Failure(
            stage="memory-write",
            reason=failure.reason,
            completed=failure.completed,
        ) from failure
    if not payload.get("id"):
        raise _AO2Failure(
            stage="memory-write",
            reason=(
                "ao2 memory write returned no id field; cannot pin a "
                "memory record id into the Hermes AO2-refs payload"
            ),
            completed=None,
        )
    return payload


def _memory_record_summary(
    *,
    record: dict[str, Any],
    record_path: Path,
) -> dict[str, Any]:
    """Trim the AO2 memory record to AO2-owned fields downstream consumes."""
    source = record.get("source") or {}
    return {
        "schema_version": record.get("schema_version"),
        "memory_record_id": record.get("id"),
        "memory_record_path": str(record_path),
        "memory_record_sha256": _sha256_file(record_path),
        "kind": record.get("kind"),
        "title": record.get("title"),
        "source_run_id": source.get("run_id"),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_bridge_evidence_from_runspec(
    *,
    ao_operator_runspec: Path,
    bridge_evidence_out: Path,
) -> dict[str, Any]:
    """Run the AO Operator -> AO2 bridge in mapping-only dry-run mode.

    The orchestrator only needs the deterministic role -> AO2 provider-
    contract mapping recorded in evidence; the actual AO2 invocation
    happens through the dedicated factory-compat CLI verbs the
    orchestrator already drives. This keeps the bridge as a single-
    purpose canonicalizer and avoids double-invoking ``ao2 factory plan``.

    Emits the ao-operator-compat bridge evidence schema
    ``ao-operator/start-ao2-run-from-role-runspec/v1``. When the caller
    supplies an AO2-owned signing key via the CLI shell-out helper
    (`_build_bridge_evidence_via_cli`) instead, the orchestrator emits
    the AO2-native ``ao2.factory-bridge.v1`` schema and the signed
    sidecar set so downstream consumers can verify via
    ``ao2 factory verify-bridge-evidence``.
    """
    runspec_value = bridge._load_runspec(ao_operator_runspec)
    resolved_roles, unknown_roles = bridge._resolve_roles_with_unknowns(
        runspec_value
    )
    if unknown_roles:
        raise _AO2Failure(
            stage="bridge-canonicalize",
            reason=(
                "AO Operator RunSpec contained role ids the deterministic "
                "AO2 provider-contract mapping could not resolve: "
                f"{unknown_roles!r}"
            ),
            completed=None,
        )
    evidence = bridge.build_bridge_evidence(
        runspec_path=ao_operator_runspec,
        runspec_value=runspec_value,
        resolved_roles=resolved_roles,
        unknown_roles=unknown_roles,
        ao2_invocation=None,
    )
    bridge.write_evidence(evidence, bridge_evidence_out)
    return evidence


def _build_bridge_evidence_via_cli(
    *,
    ao2_binary: str,
    ao_operator_runspec: Path,
    bridge_evidence_out: Path,
    signing_key: Path,
    signer_id: str,
) -> dict[str, Any]:
    """Shell out to ``ao2 factory bridge --signing-key`` to produce
    AO2-native bridge evidence end-to-end.

    Emits the AO2-native schema ``ao2.factory-bridge.v1`` (not the
    ao-operator compat schema). When invoked with ``--signing-key``,
    AO2 writes the ``signed-payload`` JSON, the ``.json.sig``
    detached signature, and the ``workbench-evidence-signing-public.pem``
    sidecar next to ``bridge_evidence_out``. Downstream consumers can
    then call ``ao2 factory verify-bridge-evidence --evidence
    <bridge_evidence_out>`` to verify the full signature chain — and
    ao-operator passthrough's slice-12 default-on verification will
    accept it without operator intervention.

    Factory-v3 only forwards the discovered key path; AO2 owns the key
    material and the sidecar writes. The bridge evidence dict is read
    back from ``bridge_evidence_out`` and returned so the rest of the
    orchestrator path is identical to the Python-helper path.
    """
    bridge_evidence_out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ao2_binary,
        "factory",
        "bridge",
        "--runspec",
        str(ao_operator_runspec),
        "--out",
        str(bridge_evidence_out),
        "--signing-key",
        str(signing_key),
        "--signer-id",
        signer_id,
        "--json",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise _AO2Failure(
            stage="bridge-canonicalize",
            reason=(
                "ao2 factory bridge exited "
                f"{completed.returncode}: "
                f"{completed.stderr.strip() or '<no stderr>'}"
            ),
            completed=None,
        )
    if not bridge_evidence_out.is_file():
        raise _AO2Failure(
            stage="bridge-canonicalize",
            reason=(
                "ao2 factory bridge succeeded but did not write the "
                f"evidence file at {bridge_evidence_out}"
            ),
            completed=None,
        )
    evidence = json.loads(bridge_evidence_out.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise _AO2Failure(
            stage="bridge-canonicalize",
            reason=(
                "ao2 factory bridge produced non-object JSON at "
                f"{bridge_evidence_out}"
            ),
            completed=None,
        )
    return evidence


def _build_hermes_context_payload(
    *,
    slug: str,
    bridge_evidence: dict[str, Any] | None,
    evidence_pack_path: Path,
    hermes_context_out: Path,
    control_plane_receipt_path: Path | None = None,
    memory_record_path: Path | None = None,
    require_all_ao2_ref_categories: bool = False,
) -> dict[str, Any]:
    """Emit Hermes context payload that references AO2-owned IDs.

    The orchestrator passes the freshly-written bridge evidence, the
    AO2-signed evidence pack, the AO2 memory record (when wired in),
    and (optionally) an ao2-control-plane ingest receipt so the payload
    pins:

    - the AO2 provider-contract mapping digest;
    - the AO2 evidence-pack sha256 + AO2 run id + closure status;
    - the AO2 memory record id + record sha256 + schema_version;
    - the control-plane ingest receipt sha256 + stored_at when supplied.

    The helper raises ``MissingAo2RefsError`` if none of the inputs
    surface an AO2 identifier, which would mean the orchestrator failed
    to wire the inputs correctly. When ``require_all_ao2_ref_categories``
    is true, the helper additionally raises
    ``MissingAo2RefCategoryError`` if any of the four Phase 2 #3 AO2
    ref categories (bridge_evidence, evidence_pack, memory_record,
    cp_receipt) are absent. The orchestrator's caller converts that
    exception into a ``status=failed`` summary with
    ``stage=hermes-context-strict-mode`` so operators see exactly which
    category was missing.
    """
    pack_value = ao2_refs_helper._load_json(evidence_pack_path)
    cp_receipt: dict[str, Any] | None = None
    if control_plane_receipt_path is not None:
        cp_receipt = ao2_refs_helper._load_json(control_plane_receipt_path)
    memory_record: dict[str, Any] | None = None
    if memory_record_path is not None:
        memory_record = ao2_refs_helper._load_json(memory_record_path)
    payload = ao2_refs_helper.build_payload(
        slug,
        bridge_evidence=bridge_evidence,
        evidence_pack=pack_value,
        evidence_pack_path=evidence_pack_path,
        memory_record=memory_record,
        memory_record_path=memory_record_path,
        cp_receipt=cp_receipt,
        require_all_ao2_ref_categories=require_all_ao2_ref_categories,
    )
    hermes_context_out.parent.mkdir(parents=True, exist_ok=True)
    hermes_context_out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


EXPECTED_FACTORY_V3_DECISION_OWNER = "parity_oracle_only"


def _bridge_evidence_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    """Trim the bridge evidence dict down to AO2-relevant fields.

    Surfaces the AO2-native `governed_run_plan` fields the ao2 commit
    `e129070` added (decision_owner / factory_v3_decision_owner /
    native_gates) when the bridge evidence is AO2-native. Legacy
    Python-helper-produced evidence has no `governed_run_plan` block,
    in which case the corresponding summary fields are `None`.

    The ao-operator boundary check (factory_v3_decision_owner ==
    `parity_oracle_only`) is enforced in
    `_assert_factory_v3_decision_owner_boundary` so the failure surfaces
    as a normal `_AO2Failure(stage="bridge-canonicalize")` rather than a
    silently degraded summary.
    """
    mapping = evidence.get("mapping") or {}
    resolved_roles = evidence.get("resolved_roles") or []
    plan = evidence.get("governed_run_plan") or {}
    native_gates = plan.get("native_gates") or []
    return {
        "schema": evidence.get("schema"),
        "status": evidence.get("status"),
        "mapping_digest": mapping.get("digest"),
        "mapping_version": mapping.get("version"),
        "resolved_role_count": len(resolved_roles),
        "resolved_roles": [
            {
                "role_id": r.get("role_id"),
                "ao2_provider_contract_id": r.get("ao2_provider_contract_id"),
            }
            for r in resolved_roles
        ],
        "unknown_role_count": len(evidence.get("unknown_roles") or []),
        "input_runspec_sha256": (
            (evidence.get("input_runspec") or {}).get("sha256")
        ),
        "governed_run_plan_schema": plan.get("schema") if plan else None,
        "governed_run_plan_status": plan.get("status") if plan else None,
        "governed_run_plan_decision_owner": (
            plan.get("decision_owner") if plan else None
        ),
        "governed_run_plan_factory_v3_decision_owner": (
            plan.get("factory_v3_decision_owner") if plan else None
        ),
        "governed_run_plan_native_gates_count": len(native_gates),
        "governed_run_plan_native_gate_stages": [
            gate.get("stage") for gate in native_gates
        ],
        "governed_run_plan_native_gate_emits": [
            gate.get("emits") for gate in native_gates
        ],
    }


def _assert_factory_v3_decision_owner_boundary(
    evidence: dict[str, Any],
) -> None:
    """Defend the parity-oracle boundary at the consumer side.

    The AO2-native `governed_run_plan.factory_v3_decision_owner` field
    encodes ao-operator's role for the run. The only acceptable value is
    `parity_oracle_only` — anything else would mean the bridge evidence
    is claiming ao-operator owns a decision that AO2 must own. Raise
    `_AO2Failure(stage="bridge-canonicalize")` so the orchestrator
    surfaces a normal `failed` summary instead of silently consuming a
    boundary-violating run plan.

    Legacy Python-helper-produced bridge evidence has no
    `governed_run_plan` block, in which case this check is a no-op
    (preserves the pre-AO2-native code path verbatim).
    """
    plan = evidence.get("governed_run_plan")
    if not isinstance(plan, dict):
        return
    observed = plan.get("factory_v3_decision_owner")
    if observed is None:
        return
    if observed != EXPECTED_FACTORY_V3_DECISION_OWNER:
        raise _AO2Failure(
            stage="bridge-canonicalize",
            reason=(
                "AO2-native bridge evidence declares "
                f"governed_run_plan.factory_v3_decision_owner={observed!r} "
                f"but must be {EXPECTED_FACTORY_V3_DECISION_OWNER!r}; "
                "ao-operator is the parity oracle, not the decision owner"
            ),
            completed=None,
        )


def _hermes_context_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim the Hermes AO2-refs payload to the ID fields downstream consumes.

    Surfaces the AO2-native ``governed_run_plan_*`` fields the slice-16
    Hermes-context wiring forwards from the bridge evidence (only
    populated when the bridge is in AO2-native mode, i.e.
    ``ao2.factory-bridge.v1``). For legacy Python-helper bridge
    evidence, these fields are absent from the refs block and the
    summary surfaces ``None`` / ``0`` / ``[]`` accordingly.
    """
    refs = payload.get("ao2_refs") or {}
    return {
        "schema": payload.get("schema"),
        "slug": payload.get("slug"),
        "factory_v3_local_paths_omitted": payload.get(
            "factory_v3_local_paths_omitted"
        ),
        "ao2_ref_keys": sorted(refs.keys()),
        "ao2_plan_sha256": refs.get("ao2_plan_sha256"),
        "ao2_provider_contract_mapping_digest": refs.get(
            "ao2_provider_contract_mapping_digest"
        ),
        "ao2_evidence_pack_sha256": refs.get("ao2_evidence_pack_sha256"),
        "ao2_run_id": refs.get("ao2_run_id"),
        "ao2_closure_status": refs.get("ao2_closure_status"),
        "control_plane_ingest_sha256": refs.get("control_plane_ingest_sha256"),
        "control_plane_stored_at": refs.get("control_plane_stored_at"),
        "control_plane_ingested_schema_version": refs.get(
            "control_plane_ingested_schema_version"
        ),
        "ao2_memory_record_id": refs.get("ao2_memory_record_id"),
        "ao2_memory_record_sha256": refs.get("ao2_memory_record_sha256"),
        "ao2_memory_record_schema": refs.get("ao2_memory_record_schema"),
        "ao2_governed_run_plan_schema": refs.get(
            "ao2_governed_run_plan_schema"
        ),
        "ao2_governed_run_plan_status": refs.get(
            "ao2_governed_run_plan_status"
        ),
        "ao2_governed_run_plan_decision_owner": refs.get(
            "ao2_governed_run_plan_decision_owner"
        ),
        "ao2_governed_run_plan_factory_v3_decision_owner": refs.get(
            "ao2_governed_run_plan_factory_v3_decision_owner"
        ),
        "ao2_governed_run_plan_native_gates_count": refs.get(
            "ao2_governed_run_plan_native_gates_count", 0
        ),
        "ao2_governed_run_plan_native_gate_stages": refs.get(
            "ao2_governed_run_plan_native_gate_stages", []
        ),
        "ao2_governed_run_plan_native_gate_emits": refs.get(
            "ao2_governed_run_plan_native_gate_emits", []
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ao2-binary",
        default="ao2",
        help="Name or path of the ao2 binary (default: ao2)",
    )
    parser.add_argument(
        "--ao2-fixture",
        type=Path,
        required=True,
        help=(
            "Source factory-compat repo directory to copy into --target "
            "before driving plan/queue/pack-evidence. Typically the "
            "ao2/fixtures/discount-service directory."
        ),
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help=(
            "Directory the orchestrator materialises the factory-compat "
            "target into. Recreated on every run. Pass this path to "
            "ao2_release_ao2_native_evidence_pack_producer.py "
            "--ao2-target downstream."
        ),
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        required=True,
        help=(
            "Directory the orchestrator writes scratch request/runspec/plan "
            "files into. Created if missing."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_ID,
        help=f"Run ID to pass to AO2 (default: {DEFAULT_RUN_ID})",
    )
    parser.add_argument(
        "--runspec-id",
        default=DEFAULT_RUNSPEC_ID,
        help=f"RunSpec id field (default: {DEFAULT_RUNSPEC_ID})",
    )
    parser.add_argument(
        "--runspec-verifier",
        default=DEFAULT_VERIFIER,
        help=f"RunSpec verifier (default: {DEFAULT_VERIFIER!r})",
    )
    parser.add_argument(
        "--request-title",
        default=DEFAULT_REQUEST_TITLE,
        help="title: line in the generated request.yaml",
    )
    parser.add_argument(
        "--request-objective",
        default=DEFAULT_REQUEST_OBJECTIVE,
        help="objective: line in the generated request.yaml",
    )
    parser.add_argument(
        "--request-acceptance",
        default=DEFAULT_REQUEST_ACCEPTANCE,
        help=(
            "acceptance: block in the generated request.yaml. Must "
            "already begin with the YAML bullet syntax (e.g. '  - ...')."
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
            "Optional AO2-owned RSA private key (PKCS8/PKCS1 PEM) "
            "forwarded path-only to `ao2 factory pack-evidence "
            "--signing-key`. AO2 writes the .sig + .public.pem sidecars."
        ),
    )
    parser.add_argument(
        "--signer-id",
        default=None,
        help=(
            "Optional signer identifier forwarded to AO2 when "
            "--signing-key is supplied; ignored otherwise."
        ),
    )
    parser.add_argument(
        "--ao-operator-runspec",
        type=Path,
        default=None,
        help=(
            "Path to a real AO Operator RunSpec (ao-operator/runspec/v1 or "
            "ao.dev/v1 Run). When supplied, the orchestrator first runs "
            "the deterministic role -> AO2 provider-contract bridge to "
            "produce bridge evidence and then hands the RunSpec to "
            "`ao2 factory plan --runspec` instead of writing a synthetic "
            "scratch RunSpec. Wires Phase 2 exit-gate items #1 and #2 "
            "into the nightly chain."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-out",
        type=Path,
        default=None,
        help=(
            "Where to write the bridge evidence JSON produced from "
            "--ao-operator-runspec. Required when --ao-operator-runspec "
            "is supplied; ignored otherwise."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-signing-key",
        type=Path,
        default=None,
        help=(
            "Optional AO2-owned RSA private key (PKCS8/PKCS1 PEM) that "
            "switches bridge canonicalization from the Python-local "
            "helper to a shell-out to "
            "`ao2 factory bridge --signing-key`. When supplied, the "
            "orchestrator emits AO2-native `ao2.factory-bridge.v1` "
            "schema bridge evidence plus the signed sidecars "
            "(`.signed-payload.json` + `.json.sig` + "
            "`workbench-evidence-signing-public.pem`), so downstream "
            "consumers can verify via "
            "`ao2 factory verify-bridge-evidence` and ao-operator's "
            "slice-12 default-on passthrough verifier accepts the "
            "evidence without operator intervention. Requires "
            "--ao-operator-runspec + --bridge-evidence-out. Factory-v3 "
            "only forwards the path; AO2 owns the key material."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-signer-id",
        default="ao2-factory-bridge",
        help=(
            "Signer id forwarded to `ao2 factory bridge --signer-id` "
            "when --bridge-evidence-signing-key is supplied "
            "(default: ao2-factory-bridge)."
        ),
    )
    parser.add_argument(
        "--hermes-context-out",
        type=Path,
        default=None,
        help=(
            "Where to write the Hermes context payload that references "
            "AO2-owned identifiers (mapping digest + AO2 run id + "
            "evidence-pack sha256) instead of ao-operator-local paths. "
            "Wires Phase 2 exit-gate item #3 into the nightly chain."
        ),
    )
    parser.add_argument(
        "--hermes-context-slug",
        default=DEFAULT_RUN_ID,
        help=(
            f"Slug field for the emitted Hermes context payload "
            f"(default: {DEFAULT_RUN_ID})."
        ),
    )
    parser.add_argument(
        "--control-plane-receipt",
        type=Path,
        default=None,
        help=(
            "Optional path to an ao2-control-plane ingest receipt JSON "
            "(schema_version: ao2.cp-ingest-receipt.v1) written by "
            "`ao2 control-plane ingest --json`. When supplied with "
            "--hermes-context-out, the Hermes AO2-refs payload pins the "
            "receipt sha256 + stored_at + ingested schema alongside the "
            "AO2 evidence-pack sha256. Closes the ao2-control-plane "
            "observer half of Phase 2 exit-gate item #3."
        ),
    )
    parser.add_argument(
        "--memory-record-out",
        type=Path,
        default=None,
        help=(
            "Path the orchestrator writes the AO2 memory record JSON to. "
            "When supplied, the orchestrator invokes `ao2 memory write "
            "--json` after pack-evidence and pins the record id + record "
            "sha256 into the Hermes AO2-refs payload. Closes the memory "
            "record identifier half of Phase 2 exit-gate item #3. "
            "Requires --hermes-context-out."
        ),
    )
    parser.add_argument(
        "--memory-record-target",
        type=Path,
        default=None,
        help=(
            "Directory the AO2 memory record is appended to (creates "
            "<target>/.ao2/memory/records.jsonl). Defaults to --target "
            "so the record sits next to the factory-compat run that "
            "produced it. Used only when --memory-record-out is supplied."
        ),
    )
    parser.add_argument(
        "--memory-record-kind",
        default=DEFAULT_MEMORY_RECORD_KIND,
        help=(
            f"AO2 memory record kind tag (default: "
            f"{DEFAULT_MEMORY_RECORD_KIND!r}). Used only when "
            "--memory-record-out is supplied."
        ),
    )
    parser.add_argument(
        "--memory-record-title",
        default=None,
        help=(
            "AO2 memory record title. Defaults to a deterministic title "
            "derived from --run-id. Used only when --memory-record-out is "
            "supplied."
        ),
    )
    parser.add_argument(
        "--memory-record-body",
        default=None,
        help=(
            "AO2 memory record body. Defaults to a deterministic line "
            "carrying run_id + evidence_pack_sha256 + mapping_digest "
            "(when bridge active). Used only when --memory-record-out is "
            "supplied."
        ),
    )
    parser.add_argument(
        "--require-all-ao2-ref-categories",
        action="store_true",
        help=(
            "Strict-mode flag: refuse to emit the Hermes context payload "
            "unless ALL four Phase 2 #3 AO2 ref categories are present "
            "(bridge_evidence, evidence_pack, memory_record, cp_receipt). "
            "When set, missing categories yield "
            "stage=hermes-context-strict-mode with the missing category "
            "names in the failure reason. Disabled by default so "
            "operators can opt in once the CP receipt producer is wired."
        ),
    )
    parser.add_argument(
        "--native-governed-run",
        action="store_true",
        help=(
            "Delegate the factory-compat chain to "
            "`ao2 factory governed-run` instead of driving the legacy "
            "plan -> queue-submit -> queue-run-next -> pack-evidence "
            "subcommands from ao-operator. This is the preferred Hermes "
            "nightly path because AO2 owns evaluator closure end-to-end."
        ),
    )
    parser.add_argument("--write-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _write_summary(*, summary: dict[str, Any], path: Path, emit: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if emit:
        json.dump(summary, sys.stdout)
        sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.signer_id is not None and args.signing_key is None:
        raise SystemExit(
            "--signer-id requires --signing-key; AO2 only honours "
            "signer_id when key material is supplied"
        )
    if args.ao_operator_runspec is not None and args.bridge_evidence_out is None:
        raise SystemExit(
            "--ao-operator-runspec requires --bridge-evidence-out so the "
            "deterministic role -> AO2 provider-contract mapping is "
            "captured as committable evidence"
        )
    if args.bridge_evidence_out is not None and args.ao_operator_runspec is None:
        raise SystemExit(
            "--bridge-evidence-out requires --ao-operator-runspec; the "
            "bridge has no input to canonicalise otherwise"
        )
    if args.bridge_evidence_signing_key is not None and (
        args.ao_operator_runspec is None or args.bridge_evidence_out is None
    ):
        raise SystemExit(
            "--bridge-evidence-signing-key requires --ao-operator-runspec "
            "and --bridge-evidence-out; AO2 needs both to produce the "
            "signed `ao2.factory-bridge.v1` evidence + sidecars"
        )
    if args.control_plane_receipt is not None and args.hermes_context_out is None:
        raise SystemExit(
            "--control-plane-receipt requires --hermes-context-out; the "
            "receipt is only pinned into the Hermes AO2-refs payload"
        )
    if args.memory_record_out is not None and args.hermes_context_out is None:
        raise SystemExit(
            "--memory-record-out requires --hermes-context-out; the "
            "memory record id is only pinned into the Hermes AO2-refs "
            "payload"
        )
    if args.memory_record_out is None and (
        args.memory_record_target is not None
        or args.memory_record_title is not None
        or args.memory_record_body is not None
        or args.memory_record_kind != DEFAULT_MEMORY_RECORD_KIND
    ):
        raise SystemExit(
            "--memory-record-target/--memory-record-title/"
            "--memory-record-body/--memory-record-kind require "
            "--memory-record-out; the AO2 memory write step only fires "
            "when an output path is supplied"
        )

    memory_record_target = args.memory_record_target or args.target
    resolved = shutil.which(args.ao2_binary)
    inputs = _input_summary(
        ao2_binary=args.ao2_binary,
        ao2_binary_resolved=resolved,
        ao2_fixture=args.ao2_fixture,
        factory_target=args.target,
        run_id=args.run_id,
        signing_key=args.signing_key,
        signer_id=args.signer_id,
        runspec_id=args.runspec_id,
        runspec_verifier=args.runspec_verifier,
        ao_operator_runspec=args.ao_operator_runspec,
        bridge_evidence_out=args.bridge_evidence_out,
        bridge_evidence_signing_key=args.bridge_evidence_signing_key,
        bridge_evidence_signer_id=args.bridge_evidence_signer_id,
        hermes_context_out=args.hermes_context_out,
        hermes_context_slug=args.hermes_context_slug,
        control_plane_receipt=args.control_plane_receipt,
        memory_record_out=args.memory_record_out,
        memory_record_target=(
            memory_record_target if args.memory_record_out is not None else None
        ),
        memory_record_kind=(
            args.memory_record_kind if args.memory_record_out is not None else None
        ),
        memory_record_title=args.memory_record_title,
        memory_record_body=args.memory_record_body,
        require_all_ao2_ref_categories=(
            args.require_all_ao2_ref_categories
        ),
    )

    missing: list[str] = []
    if resolved is None:
        missing.append(f"ao2_binary_not_on_path:{args.ao2_binary}")
    if not args.ao2_fixture.is_dir():
        missing.append(f"ao2_fixture_not_a_directory:{args.ao2_fixture}")
    if args.signing_key is not None and not args.signing_key.is_file():
        missing.append(f"signing_key_not_found:{args.signing_key}")
    if (
        args.bridge_evidence_signing_key is not None
        and not args.bridge_evidence_signing_key.is_file()
    ):
        missing.append(
            f"bridge_evidence_signing_key_not_found:{args.bridge_evidence_signing_key}"
        )
    if (
        args.ao_operator_runspec is not None
        and not args.ao_operator_runspec.is_file()
    ):
        missing.append(
            f"ao_operator_runspec_not_found:{args.ao_operator_runspec}"
        )
    if (
        args.control_plane_receipt is not None
        and not args.control_plane_receipt.is_file()
    ):
        missing.append(
            f"control_plane_receipt_not_found:{args.control_plane_receipt}"
        )

    if missing:
        summary = _build_missing_inputs_payload(
            inputs=inputs, missing=missing
        )
        _write_summary(summary=summary, path=args.write_json, emit=args.json)
        return 0

    args.workdir.mkdir(parents=True, exist_ok=True)
    request_path = args.workdir / "request.yaml"
    plan_path = args.workdir / "plan.json"
    _write_request_yaml(
        path=request_path,
        title=args.request_title,
        objective=args.request_objective,
        acceptance=args.request_acceptance,
    )

    bridge_evidence: dict[str, Any] | None = None
    bridge_summary: dict[str, Any] | None = None
    if args.ao_operator_runspec is not None:
        try:
            if args.bridge_evidence_signing_key is not None:
                bridge_evidence = _build_bridge_evidence_via_cli(
                    ao2_binary=args.ao2_binary,
                    ao_operator_runspec=args.ao_operator_runspec,
                    bridge_evidence_out=args.bridge_evidence_out,
                    signing_key=args.bridge_evidence_signing_key,
                    signer_id=args.bridge_evidence_signer_id,
                )
            else:
                bridge_evidence = _build_bridge_evidence_from_runspec(
                    ao_operator_runspec=args.ao_operator_runspec,
                    bridge_evidence_out=args.bridge_evidence_out,
                )
            _assert_factory_v3_decision_owner_boundary(bridge_evidence)
        except _AO2Failure as failure:
            summary = _build_failed_payload(
                inputs=inputs,
                stage=failure.stage,
                reason=failure.reason,
                factory_target=args.target,
            )
            _write_summary(
                summary=summary, path=args.write_json, emit=args.json
            )
            return 0
        bridge_summary = _bridge_evidence_summary(bridge_evidence)
        runspec_path = args.ao_operator_runspec
    else:
        runspec_path = args.workdir / "runspec.yaml"
        _write_runspec_yaml(
            path=runspec_path,
            runspec_id=args.runspec_id,
            verifier=args.runspec_verifier,
        )

    try:
        _materialise_target(fixture=args.ao2_fixture, target=args.target)
    except OSError as exc:
        summary = _build_failed_payload(
            inputs=inputs,
            stage="materialise_target",
            reason=f"failed to copy fixture: {exc}",
            factory_target=args.target,
            bridge_evidence_summary=bridge_summary,
        )
        _write_summary(summary=summary, path=args.write_json, emit=args.json)
        return 0

    partial: dict[str, Any] = {}
    governed_run_stdout: dict[str, Any] | None = None
    try:
        if args.native_governed_run:
            governed_run_stdout = _ao2_factory_governed_run(
                ao2_binary=args.ao2_binary,
                request_path=request_path,
                runspec_path=runspec_path,
                factory_target=args.target,
                run_id=args.run_id,
                out_dir=args.workdir / "governed-run",
                evidence_pack_out=args.evidence_pack_out,
                signing_key=args.signing_key,
                signer_id=args.signer_id,
            )
            partial["governed_run"] = governed_run_stdout
            plan_stdout = governed_run_stdout.get("plan") or {}
            queue_submit_stdout = governed_run_stdout.get("queue_submit") or {}
            queue_run_next_stdout = (
                governed_run_stdout.get("queue_run_next") or {}
            )
            pack_evidence_stdout = (
                governed_run_stdout.get("pack_evidence") or {}
            )
            plan_artifact = (
                governed_run_stdout.get("artifacts") or {}
            ).get("plan")
            if plan_artifact:
                plan_path = Path(str(plan_artifact))
        else:
            plan_stdout = _ao2_factory_plan(
                ao2_binary=args.ao2_binary,
                request_path=request_path,
                runspec_path=runspec_path,
                factory_target=args.target,
                plan_out=plan_path,
            )
            partial["plan"] = plan_stdout
            queue_submit_stdout = _ao2_factory_queue_submit(
                ao2_binary=args.ao2_binary,
                plan_path=plan_path,
                factory_target=args.target,
                run_id=args.run_id,
            )
            partial["queue_submit"] = queue_submit_stdout
            queue_run_next_stdout = _ao2_factory_queue_run_next(
                ao2_binary=args.ao2_binary,
                factory_target=args.target,
            )
            partial["queue_run_next"] = queue_run_next_stdout
            pack_evidence_stdout = _ao2_factory_pack_evidence(
                ao2_binary=args.ao2_binary,
                factory_target=args.target,
                run_id=args.run_id,
                evidence_pack_out=args.evidence_pack_out,
                signing_key=args.signing_key,
                signer_id=args.signer_id,
            )
            partial["pack_evidence"] = pack_evidence_stdout
        entry = queue_run_next_stdout.get("entry") or {}
        entry_status = entry.get("status")
        if entry_status != "accepted":
            raise _AO2Failure(
                stage="queue-run-next",
                reason=(
                    "ao2 factory queue-run-next produced entry status "
                    f"{entry_status!r}; expected 'accepted'"
                ),
                completed=None,
            )
    except _AO2Failure as failure:
        summary = _build_failed_payload(
            inputs=inputs,
            stage=failure.stage,
            reason=failure.reason,
            factory_target=args.target,
            partial=partial,
            bridge_evidence_summary=bridge_summary,
        )
        _write_summary(summary=summary, path=args.write_json, emit=args.json)
        return 0

    evidence_pack_sha256 = _sha256_file(args.evidence_pack_out)

    memory_record_summary: dict[str, Any] | None = None
    if args.memory_record_out is not None:
        mapping_digest = None
        if bridge_evidence is not None:
            mapping_digest = (bridge_evidence.get("mapping") or {}).get("digest")
        default_title = (
            f"AO2 nightly factory-compat run {args.run_id}"
        )
        default_body = (
            f"run_id={args.run_id} "
            f"evidence_pack_sha256={evidence_pack_sha256} "
            f"mapping_digest={mapping_digest or 'none'}"
        )
        memory_title = args.memory_record_title or default_title
        memory_body = args.memory_record_body or default_body
        try:
            memory_record = _ao2_memory_write(
                ao2_binary=args.ao2_binary,
                memory_target=memory_record_target,
                kind=args.memory_record_kind,
                title=memory_title,
                body=memory_body,
                source_run_id=args.run_id,
            )
        except _AO2Failure as failure:
            summary = _build_failed_payload(
                inputs=inputs,
                stage=failure.stage,
                reason=failure.reason,
                factory_target=args.target,
                partial=partial,
                bridge_evidence_summary=bridge_summary,
            )
            _write_summary(
                summary=summary, path=args.write_json, emit=args.json
            )
            return 0
        args.memory_record_out.parent.mkdir(parents=True, exist_ok=True)
        args.memory_record_out.write_text(
            json.dumps(memory_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        memory_record_summary = _memory_record_summary(
            record=memory_record,
            record_path=args.memory_record_out,
        )

    hermes_summary: dict[str, Any] | None = None
    if args.hermes_context_out is not None:
        try:
            hermes_payload = _build_hermes_context_payload(
                slug=args.hermes_context_slug,
                bridge_evidence=bridge_evidence,
                evidence_pack_path=args.evidence_pack_out,
                hermes_context_out=args.hermes_context_out,
                control_plane_receipt_path=args.control_plane_receipt,
                memory_record_path=args.memory_record_out,
                require_all_ao2_ref_categories=(
                    args.require_all_ao2_ref_categories
                ),
            )
        except ao2_refs_helper.MissingAo2RefCategoryError as exc:
            summary = _build_failed_payload(
                inputs=inputs,
                stage="hermes-context-strict-mode",
                reason=str(exc),
                factory_target=args.target,
                partial=partial,
                bridge_evidence_summary=bridge_summary,
            )
            _write_summary(
                summary=summary, path=args.write_json, emit=args.json
            )
            return 0
        except ao2_refs_helper.MissingAo2RefsError as exc:
            summary = _build_failed_payload(
                inputs=inputs,
                stage="hermes-context",
                reason=str(exc),
                factory_target=args.target,
                partial=partial,
                bridge_evidence_summary=bridge_summary,
            )
            _write_summary(
                summary=summary, path=args.write_json, emit=args.json
            )
            return 0
        hermes_summary = _hermes_context_summary(hermes_payload)

    summary = _build_produced_payload(
        inputs=inputs,
        factory_target=args.target,
        run_id=args.run_id,
        plan_path=plan_path,
        plan_stdout=plan_stdout,
        queue_submit_stdout=queue_submit_stdout,
        queue_run_next_stdout=queue_run_next_stdout,
        pack_evidence_stdout=pack_evidence_stdout,
        evidence_pack_path=args.evidence_pack_out,
        evidence_pack_sha256=evidence_pack_sha256,
        governed_run_stdout=governed_run_stdout,
        bridge_evidence_summary=bridge_summary,
        hermes_context_summary=hermes_summary,
        memory_record_summary=memory_record_summary,
    )
    _write_summary(summary=summary, path=args.write_json, emit=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
