from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "hermes_ao_bridge.py"


def bridge_evidence_fixture() -> dict:
    return {
        "schema": "ao-operator/start-ao2-run-from-role-runspec/v1",
        "mapping": {"digest": "deadbeef" * 8},
        "ao2_invocation": {
            "status": "planned",
            "plan_response": {
                "plan_sha256": "abc" * 21 + "x",
                "planning_evidence_path": "/tmp/plan-evidence.json",
                "signature": {
                    "signature_sha256": "11" * 32,
                    "public_key_sha256": "22" * 32,
                    "signed_payload_sha256": "33" * 32,
                },
            },
        },
    }


def evidence_pack_fixture() -> dict:
    return {
        "schema_version": "ao2.evidence-pack.v1",
        "run_id": "run-test-1",
        "closure_status": "accepted",
    }


def memory_record_fixture() -> dict:
    return {
        "schema_version": "ao2.memory-write-result.v1",
        "record_id": "mem-test-1",
        "sha256": "ff" * 32,
    }


def cp_receipt_fixture() -> dict:
    return {
        "schema_version": "ao2.cp-ingest-receipt.v1",
        "sha256": "ee" * 32,
        "stored_at": "2026-05-24T22:30:00Z",
        "ingested_schema_version": "ao2.evidence-pack.v1",
    }


def run_bridge(
    *args: str, expect_returncode: int = 0
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    result = subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    return json.loads(result.stdout), result


def write_inputs(tmp_path: Path, **payloads: dict) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    return paths


def test_context_with_ao2_refs_accepts_bridge_evidence(tmp_path: Path) -> None:
    paths = write_inputs(tmp_path, bridge=bridge_evidence_fixture())
    payload, _ = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "phase-2-demo",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--json",
    )
    assert payload is not None
    assert payload["schema"] == "ao-operator/hermes-ao-bridge/v1"
    assert payload["action"] == "context-with-ao2-refs"
    inner = payload["context_with_ao2_refs"]
    assert inner["schema"] == "ao-operator/hermes-context-with-ao2-refs/v1"
    assert inner["action"] == "hermes-context-with-ao2-refs"
    assert inner["slug"] == "phase-2-demo"
    assert inner["factory_v3_local_paths_omitted"] is True
    refs = inner["ao2_refs"]
    assert refs["ao2_plan_sha256"] == bridge_evidence_fixture()["ao2_invocation"]["plan_response"]["plan_sha256"]
    assert refs["ao2_provider_contract_mapping_digest"] == bridge_evidence_fixture()["mapping"]["digest"]
    assert refs["ao2_invocation_status"] == "planned"
    assert inner["trust_boundary"]["id_owner"] == (
        "ao2_owns_every_identifier_referenced_in_this_payload"
    )
    # Envelope: bridge_result only carries schema + action + handler fields.
    # No envelope-level trust_boundary; the AO2-refs payload owns its own.
    assert "trust_boundary" not in payload


def test_context_with_ao2_refs_accepts_all_inputs(tmp_path: Path) -> None:
    pack = evidence_pack_fixture()
    paths = write_inputs(
        tmp_path,
        bridge=bridge_evidence_fixture(),
        pack=pack,
        memory=memory_record_fixture(),
        receipt=cp_receipt_fixture(),
    )
    payload, _ = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "phase-2-all-inputs",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--evidence-pack",
        str(paths["pack"]),
        "--memory-record",
        str(paths["memory"]),
        "--control-plane-receipt",
        str(paths["receipt"]),
        "--json",
    )
    assert payload is not None
    refs = payload["context_with_ao2_refs"]["ao2_refs"]
    assert refs["ao2_run_id"] == "run-test-1"
    assert refs["ao2_closure_status"] == "accepted"
    assert refs["ao2_memory_record_id"] == "mem-test-1"
    assert refs["control_plane_ingest_sha256"] == "ee" * 32
    assert refs["control_plane_stored_at"] == "2026-05-24T22:30:00Z"
    assert refs["control_plane_ingested_schema_version"] == "ao2.evidence-pack.v1"
    # evidence_pack_sha256 is content-addressable: SHA of the pack file we wrote
    import hashlib
    expected_sha = hashlib.sha256(paths["pack"].read_bytes()).hexdigest()
    assert refs["ao2_evidence_pack_sha256"] == expected_sha


def test_context_with_ao2_refs_refuses_when_no_refs_supplied(tmp_path: Path) -> None:
    _, result = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "no-refs",
        "--json",
        expect_returncode=2,
    )
    assert "no AO2-owned identifiers supplied" in result.stderr


def test_context_with_ao2_refs_refuses_bad_bridge_schema(tmp_path: Path) -> None:
    bad = bridge_evidence_fixture()
    bad["schema"] = "wrong/v0"
    paths = write_inputs(tmp_path, bridge=bad)
    _, result = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "bad-schema",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--json",
        expect_returncode=2,
    )
    assert "bridge evidence schema must be" in result.stderr
    assert "ao-operator/start-ao2-run-from-role-runspec/v1" in result.stderr


def test_context_with_ao2_refs_refuses_bad_evidence_pack_schema(tmp_path: Path) -> None:
    bad = evidence_pack_fixture()
    bad["schema_version"] = "ao2.wrong/v0"
    paths = write_inputs(tmp_path, pack=bad)
    _, result = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "bad-pack",
        "--evidence-pack",
        str(paths["pack"]),
        "--json",
        expect_returncode=2,
    )
    assert "AO2 evidence-pack schema must be" in result.stderr
    assert "ao2.evidence-pack.v1" in result.stderr


def test_context_with_ao2_refs_records_supplied_categories(tmp_path: Path) -> None:
    """Phase 2 #3: payload must surface which of the four AO2 ref categories
    were supplied so downstream consumers can assert four-category coverage
    without re-parsing every ref. Default mode (no strict flag) still emits
    the tracking block; only the strict flag changes failure behaviour.
    """
    paths = write_inputs(tmp_path, bridge=bridge_evidence_fixture())
    payload, _ = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "single-input",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--json",
    )
    assert payload is not None
    inner = payload["context_with_ao2_refs"]
    supplied = inner["ao2_ref_categories_supplied"]
    assert supplied == {
        "bridge_evidence": True,
        "cp_receipt": False,
        "evidence_pack": False,
        "memory_record": False,
    }
    assert inner["ao2_ref_categories_all_supplied"] is False
    assert inner["ao2_ref_categories_required_for_phase2_exit_gate_3"] == [
        "bridge_evidence",
        "evidence_pack",
        "memory_record",
        "cp_receipt",
    ]


def test_context_with_ao2_refs_strict_mode_passes_with_all_four_categories(
    tmp_path: Path,
) -> None:
    """Phase 2 #3 strict mode: when all four AO2 ref categories are supplied,
    the producer emits a payload with ao2_ref_categories_all_supplied=True
    and exit 0. This is the machine-checkable shape Phase 2 #3 asks for.
    """
    paths = write_inputs(
        tmp_path,
        bridge=bridge_evidence_fixture(),
        pack=evidence_pack_fixture(),
        memory=memory_record_fixture(),
        receipt=cp_receipt_fixture(),
    )
    payload, _ = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "strict-all-four",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--evidence-pack",
        str(paths["pack"]),
        "--memory-record",
        str(paths["memory"]),
        "--control-plane-receipt",
        str(paths["receipt"]),
        "--require-all-ao2-ref-categories",
        "--json",
    )
    assert payload is not None
    inner = payload["context_with_ao2_refs"]
    assert inner["ao2_ref_categories_all_supplied"] is True
    assert all(inner["ao2_ref_categories_supplied"].values())


def test_context_with_ao2_refs_strict_mode_rejects_missing_cp_receipt(
    tmp_path: Path,
) -> None:
    paths = write_inputs(
        tmp_path,
        bridge=bridge_evidence_fixture(),
        pack=evidence_pack_fixture(),
        memory=memory_record_fixture(),
    )
    _, result = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "strict-missing-receipt",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--evidence-pack",
        str(paths["pack"]),
        "--memory-record",
        str(paths["memory"]),
        "--require-all-ao2-ref-categories",
        "--json",
        expect_returncode=2,
    )
    assert "strict mode requires all four Phase 2 #3 AO2 ref categories" in result.stderr
    assert "missing: cp_receipt" in result.stderr


def test_context_with_ao2_refs_strict_mode_lists_all_missing_categories(
    tmp_path: Path,
) -> None:
    paths = write_inputs(tmp_path, bridge=bridge_evidence_fixture())
    _, result = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "strict-missing-multi",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--require-all-ao2-ref-categories",
        "--json",
        expect_returncode=2,
    )
    # Missing categories surface alphabetically so ops can grep for the
    # ordered list without depending on argparse parse order.
    assert "missing: cp_receipt, evidence_pack, memory_record" in result.stderr


def test_context_with_ao2_refs_default_mode_unchanged_by_strict_addition(
    tmp_path: Path,
) -> None:
    """The strict-mode flag is opt-in; the original 'at least one ref' rule
    still applies when the flag is absent. Regression guard for the
    pre-strict default behaviour.
    """
    paths = write_inputs(tmp_path, bridge=bridge_evidence_fixture())
    payload, _ = run_bridge(
        "context-with-ao2-refs",
        "--slug",
        "default-one-input-ok",
        "--bridge-evidence",
        str(paths["bridge"]),
        "--json",
    )
    assert payload is not None
    assert payload["context_with_ao2_refs"]["ao2_ref_categories_all_supplied"] is False
