from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "hermes_context_with_ao2_refs.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hermes_context_with_ao2_refs as helper  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: minimal AO2-owned artifacts the helper consumes.
# ---------------------------------------------------------------------------


def _bridge_evidence(plan_sha256: str = "deadbeef" * 8) -> dict:
    return {
        "schema": helper.BRIDGE_EVIDENCE_SCHEMA,
        "action": "start-ao2-run-from-role-runspec",
        "status": "ao2_plan_started",
        "input_runspec": {"path": "examples/x.yaml", "sha256": "a" * 64},
        "mapping": {"digest": "c" * 64, "schema": "ao-operator/ao-operator-ao2-provider-contract/v1"},
        "ao2_invocation": {
            "status": "ao2_plan_succeeded",
            "exit_code": 0,
            "plan_response": {
                "plan_path": "/tmp/ao2-plan.json",
                "plan_sha256": plan_sha256,
                "planning_evidence_path": "/tmp/ao2-plan.planning-evidence.json",
                "signature": {
                    "signature_sha256": "11" * 32,
                    "public_key_sha256": "22" * 32,
                    "signed_payload_sha256": "33" * 32,
                },
            },
        },
        "resolved_roles": [],
        "unknown_roles": [],
    }


def _evidence_pack() -> dict:
    return {
        "schema_version": helper.AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": "r-bridge-demo-1778685620993228000",
        "closure_status": "accepted",
        "artifacts": [],
    }


def _memory_record() -> dict:
    return {
        "schema_version": "ao2.memory-write-result.v1",
        "record_id": "mem-2026-05-24-12345",
        "sha256": "ab" * 32,
    }


def _cp_receipt() -> dict:
    return {
        "schema_version": helper.AO2_CP_INGEST_RECEIPT_SCHEMA,
        "sha256": "cc" * 32,
        "stored_at": "2026-05-24T22:30:00Z",
        "ingested_schema_version": helper.AO2_EVIDENCE_PACK_SCHEMA,
    }


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["bridge"] = tmp_path / "bridge-evidence.json"
    paths["bridge"].write_text(json.dumps(_bridge_evidence()), encoding="utf-8")
    paths["pack"] = tmp_path / "ao2-evidence-pack.json"
    paths["pack"].write_text(json.dumps(_evidence_pack()), encoding="utf-8")
    paths["memory"] = tmp_path / "ao2-memory.json"
    paths["memory"].write_text(json.dumps(_memory_record()), encoding="utf-8")
    paths["receipt"] = tmp_path / "cp-receipt.json"
    paths["receipt"].write_text(json.dumps(_cp_receipt()), encoding="utf-8")
    return paths


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


# ---------------------------------------------------------------------------
# In-process build_payload tests.
# ---------------------------------------------------------------------------


def test_build_payload_with_only_bridge_evidence_records_ao2_plan_refs():
    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(plan_sha256="d" * 64),
    )
    assert payload["schema"] == helper.SCHEMA
    assert payload["slug"] == "demo-slug"
    assert payload["factory_v3_local_paths_omitted"] is True
    refs = payload["ao2_refs"]
    assert refs["ao2_plan_sha256"] == "d" * 64
    assert refs["ao2_provider_contract_mapping_digest"] == "c" * 64
    assert refs["ao2_planning_evidence_path"].endswith("planning-evidence.json")
    assert refs["ao2_invocation_status"] == "ao2_plan_succeeded"
    assert refs["ao2_plan_signature"]["signature_sha256"] == "11" * 32


def test_build_payload_with_evidence_pack_adds_pack_sha_and_run_id(tmp_path: Path):
    pack_path = tmp_path / "ao2-evidence-pack.json"
    pack_path.write_text(json.dumps(_evidence_pack()), encoding="utf-8")
    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        evidence_pack=_evidence_pack(),
        evidence_pack_path=pack_path,
    )
    refs = payload["ao2_refs"]
    assert refs["ao2_run_id"] == "r-bridge-demo-1778685620993228000"
    assert refs["ao2_closure_status"] == "accepted"
    assert len(refs["ao2_evidence_pack_sha256"]) == 64


def test_build_payload_with_memory_and_cp_receipt_includes_both():
    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        memory_record=_memory_record(),
        cp_receipt=_cp_receipt(),
    )
    refs = payload["ao2_refs"]
    assert refs["ao2_memory_record_id"] == "mem-2026-05-24-12345"
    assert refs["control_plane_ingest_sha256"] == "cc" * 32
    assert refs["control_plane_stored_at"] == "2026-05-24T22:30:00Z"


def test_build_payload_memory_record_path_pins_file_sha256(tmp_path: Path):
    """When the record dict has no sha256, the helper sha256s the file."""
    record = {
        "schema_version": "ao2.memory-record.v1",
        "id": "mem-from-path-1",
        # Deliberately no top-level "sha256" field.
    }
    record_path = tmp_path / "memory-record.json"
    record_text = json.dumps(record, sort_keys=True)
    record_path.write_text(record_text, encoding="utf-8")

    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        memory_record=record,
        memory_record_path=record_path,
    )
    refs = payload["ao2_refs"]
    assert refs["ao2_memory_record_id"] == "mem-from-path-1"
    assert refs["ao2_memory_record_sha256"] == helper.sha256_file(record_path)
    # Schema travels through as well.
    assert refs["ao2_memory_record_schema"] == "ao2.memory-record.v1"


def test_build_payload_memory_record_explicit_sha256_wins_over_file(tmp_path: Path):
    """If the record dict has sha256, it takes precedence over file hashing."""
    record = {
        "schema_version": "ao2.memory-record.v1",
        "id": "mem-explicit-sha-1",
        "sha256": "ab" * 32,
    }
    record_path = tmp_path / "memory-record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        memory_record=record,
        memory_record_path=record_path,
    )
    assert payload["ao2_refs"]["ao2_memory_record_sha256"] == "ab" * 32


def test_build_payload_refs_are_sorted_for_review_friendliness():
    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        memory_record=_memory_record(),
        cp_receipt=_cp_receipt(),
    )
    refs = payload["ao2_refs"]
    assert list(refs.keys()) == sorted(refs.keys())


def test_build_payload_without_any_ao2_refs_refuses_to_emit():
    with pytest.raises(helper.MissingAo2RefsError):
        helper.build_payload("demo-slug")


def test_build_payload_rejects_wrong_bridge_schema():
    bridge = _bridge_evidence()
    bridge["schema"] = "ao-operator/some-other-bridge/v1"
    with pytest.raises(SystemExit):
        helper.build_payload("demo-slug", bridge_evidence=bridge)


def test_build_payload_rejects_wrong_evidence_pack_schema(tmp_path: Path):
    bad = _evidence_pack()
    bad["schema_version"] = "ao2.something-else.v1"
    pack_path = tmp_path / "ao2-evidence-pack.json"
    pack_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit):
        helper.build_payload(
            "demo-slug",
            bridge_evidence=_bridge_evidence(),
            evidence_pack=bad,
            evidence_pack_path=pack_path,
        )


def test_build_payload_rejects_wrong_cp_receipt_schema():
    receipt = _cp_receipt()
    receipt["schema_version"] = "ao2.cp-something-else.v1"
    with pytest.raises(SystemExit):
        helper.build_payload(
            "demo-slug",
            bridge_evidence=_bridge_evidence(),
            cp_receipt=receipt,
        )


def test_build_payload_cleans_unsafe_slug_chars():
    payload = helper.build_payload(
        "demo slug!! v2",
        bridge_evidence=_bridge_evidence(),
    )
    assert payload["slug"] == "demo-slug-v2"


def test_build_payload_rejects_empty_slug_after_cleaning():
    with pytest.raises(ValueError):
        helper.build_payload("///", bridge_evidence=_bridge_evidence())


# ---------------------------------------------------------------------------
# Property: the payload must NEVER carry ao-operator-local artifact paths.
# This is the whole point of the schema and is what the exit-gate item asks
# for. The body MAY mention paths (e.g. ao2_planning_evidence_path), but only
# if those are AO2-owned identifiers, not ao-operator status / runspec /
# obligation-ledger / evidence-pack-dir paths.
# ---------------------------------------------------------------------------


FORBIDDEN_LOCAL_KEYS = (
    "status_dir",
    "artifacts",
    "obligation_ledger",
    "runspec",
)


def test_payload_never_contains_factory_v3_local_artifact_keys():
    payload = helper.build_payload(
        "demo-slug",
        bridge_evidence=_bridge_evidence(),
        memory_record=_memory_record(),
        cp_receipt=_cp_receipt(),
    )
    flat = json.dumps(payload)
    for forbidden in FORBIDDEN_LOCAL_KEYS:
        assert f'"{forbidden}":' not in flat, (
            f"payload must not include ao-operator-local key {forbidden!r}; "
            "the whole point of this schema is AO2-owned IDs only"
        )


# ---------------------------------------------------------------------------
# CLI end-to-end.
# ---------------------------------------------------------------------------


def test_cli_emits_payload_from_all_four_inputs(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    out = tmp_path / "context.json"
    result = _run(
        [
            "--slug",
            "demo",
            "--bridge-evidence",
            str(paths["bridge"]),
            "--evidence-pack",
            str(paths["pack"]),
            "--memory-record",
            str(paths["memory"]),
            "--control-plane-receipt",
            str(paths["receipt"]),
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["schema"] == helper.SCHEMA
    refs = body["ao2_refs"]
    for required in (
        "ao2_plan_sha256",
        "ao2_run_id",
        "ao2_evidence_pack_sha256",
        "ao2_memory_record_id",
        "control_plane_ingest_sha256",
    ):
        assert required in refs, f"missing AO2-owned ref {required!r}"


def test_cli_refuses_when_no_ao2_refs_supplied(tmp_path: Path):
    result = _run(["--slug", "demo"])
    assert result.returncode == 2
    assert "no AO2-owned identifiers" in result.stderr


def test_cli_writes_pretty_sorted_json(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    out = tmp_path / "context.json"
    _run(
        [
            "--slug",
            "demo",
            "--bridge-evidence",
            str(paths["bridge"]),
            "--out",
            str(out),
        ]
    )
    text = out.read_text(encoding="utf-8")
    # Pretty-printed: indent=2 means second line starts with 2 spaces.
    second_line = text.splitlines()[1]
    assert second_line.startswith("  "), "expected indent=2 pretty JSON"
    # Sorted: schema appears before slug appears before trust_boundary.
    assert text.index('"schema":') < text.index('"slug":') < text.index('"trust_boundary":')


# ---------------------------------------------------------------------------
# Phase 2 exit-gate #3: AO2-native bridge-evidence schema (slice 16).
#
# Slice 14 wires the orchestrator's signing path through `ao2 factory
# bridge --signing-key`, which emits the `ao2.factory-bridge.v1` schema
# instead of the legacy `ao-operator/start-ao2-run-from-role-runspec/v1`
# schema. Before slice 16, `_refs_from_bridge_evidence` hard-rejected
# anything other than the legacy schema -- so any caller that combined
# the slice-14 signing path with this Hermes context helper would crash.
#
# Slice 16 extends the helper to accept both schemas. For the AO2-native
# schema, it surfaces the `governed_run_plan_*` fields ao2 commit
# `e129070` added (decision_owner / factory_v3_decision_owner /
# native_gates stages + emits).
# ---------------------------------------------------------------------------


def _ao2_native_bridge_evidence(
    *,
    include_governed_run_plan: bool = True,
    factory_v3_decision_owner: str = "parity_oracle_only",
) -> dict:
    """Minimal `ao2.factory-bridge.v1` bridge evidence dict.

    Mirrors the shape ao2 commit `e129070` emits: the top-level fields
    diverge from the legacy Python-helper schema (no `ao2_invocation`
    block; `status` is at the top level; `governed_run_plan` is the
    AO2-native declaration with `native_gates`).
    """
    payload: dict = {
        "schema": helper.AO2_NATIVE_BRIDGE_EVIDENCE_SCHEMA,
        "action": "factory-bridge",
        "status": "ao2_native_bridge_succeeded",
        "input_runspec": {"path": "examples/x.yaml", "sha256": "a" * 64},
        "mapping": {
            "digest": "c" * 64,
            "schema": "ao-operator/ao-operator-ao2-provider-contract/v1",
        },
        "resolved_roles": [],
        "unknown_roles": [],
    }
    if include_governed_run_plan:
        payload["governed_run_plan"] = {
            "schema": "ao2.governed-run-plan.v1",
            "status": "materialized_dry_run",
            "decision_owner": "ao2_native_evaluator_closer",
            "factory_v3_decision_owner": factory_v3_decision_owner,
            "native_gates": [
                {
                    "stage": "midpoint",
                    "decision_logic": "ao2_obligation_gate_midpoint",
                    "required_evidence": ["ao2.obligation-gate.midpoint.v1"],
                    "emits": "ao2.obligation-gate.midpoint.v1",
                },
                {
                    "stage": "closure",
                    "decision_logic": "ao2_evaluator_closer_decision",
                    "required_evidence": [
                        "ao2.obligation-gate.closure.v1",
                        "ao2.evaluator-closer-decision.v1",
                    ],
                    "emits": "ao2.evaluator-closer-decision.v1",
                },
            ],
        }
    return payload


def test_refs_from_bridge_evidence_accepts_ao2_native_schema():
    """Slice 16: helper must extract refs from `ao2.factory-bridge.v1`
    bridge evidence, not just the legacy Python-helper schema."""
    bridge = _ao2_native_bridge_evidence()
    refs = helper._refs_from_bridge_evidence(bridge)
    assert refs["ao2_provider_contract_mapping_digest"] == "c" * 64
    assert refs["ao2_invocation_status"] == "ao2_native_bridge_succeeded"
    assert refs["ao2_governed_run_plan_schema"] == "ao2.governed-run-plan.v1"
    assert refs["ao2_governed_run_plan_status"] == "materialized_dry_run"
    assert (
        refs["ao2_governed_run_plan_decision_owner"]
        == "ao2_native_evaluator_closer"
    )
    assert (
        refs["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert refs["ao2_governed_run_plan_native_gates_count"] == 2
    assert refs["ao2_governed_run_plan_native_gate_stages"] == [
        "midpoint",
        "closure",
    ]
    assert refs["ao2_governed_run_plan_native_gate_emits"] == [
        "ao2.obligation-gate.midpoint.v1",
        "ao2.evaluator-closer-decision.v1",
    ]


def test_refs_from_bridge_evidence_ao2_native_without_governed_run_plan():
    """An AO2-native bridge evidence emitted by an ao2 binary that
    predates commit `e129070` has no `governed_run_plan` block. The
    helper must still extract the mapping digest + top-level status
    without crashing; the governed_run_plan_* refs are absent (not
    explicit-null) so downstream consumers can rely on `in refs`
    membership checks."""
    bridge = _ao2_native_bridge_evidence(include_governed_run_plan=False)
    refs = helper._refs_from_bridge_evidence(bridge)
    assert refs["ao2_provider_contract_mapping_digest"] == "c" * 64
    assert refs["ao2_invocation_status"] == "ao2_native_bridge_succeeded"
    assert "ao2_governed_run_plan_schema" not in refs
    assert "ao2_governed_run_plan_status" not in refs
    assert "ao2_governed_run_plan_decision_owner" not in refs
    assert "ao2_governed_run_plan_factory_v3_decision_owner" not in refs
    assert "ao2_governed_run_plan_native_gates_count" not in refs


def test_refs_from_bridge_evidence_rejects_unknown_schema():
    """An unknown schema string must still raise SystemExit, but the
    error message now references the accepted schema set instead of a
    single schema."""
    bridge = _ao2_native_bridge_evidence()
    bridge["schema"] = "ao-operator/some-other-bridge/v1"
    with pytest.raises(SystemExit) as excinfo:
        helper._refs_from_bridge_evidence(bridge)
    msg = str(excinfo.value)
    assert helper.BRIDGE_EVIDENCE_SCHEMA in msg
    assert helper.AO2_NATIVE_BRIDGE_EVIDENCE_SCHEMA in msg
    assert "ao-operator/some-other-bridge/v1" in msg


def test_build_payload_with_ao2_native_bridge_evidence_pins_run_plan_refs():
    """End-to-end build_payload() call with an AO2-native bridge
    evidence dict yields a payload whose `ao2_refs` block surfaces the
    new governed_run_plan_* keys. This is the surface downstream
    Hermes consumers see."""
    payload = helper.build_payload(
        "ao2-native-slug",
        bridge_evidence=_ao2_native_bridge_evidence(),
    )
    refs = payload["ao2_refs"]
    assert (
        refs["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert refs["ao2_governed_run_plan_native_gates_count"] == 2
    # The payload is sortable JSON (no None/tuple sentinels leaked).
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    assert '"ao2_governed_run_plan_native_gate_emits":' in encoded


def test_cli_emits_payload_from_ao2_native_bridge_evidence(tmp_path: Path):
    """CLI end-to-end: feeding an AO2-native bridge evidence file
    through the script produces a Hermes context whose ao2_refs block
    pins the governed_run_plan_* fields. Guards against the slice-16
    rewrite ever re-introducing a schema-hardcoded SystemExit."""
    bridge_path = tmp_path / "ao2-native-bridge.json"
    bridge_path.write_text(
        json.dumps(_ao2_native_bridge_evidence()), encoding="utf-8"
    )
    out = tmp_path / "context.json"
    result = _run(
        [
            "--slug",
            "ao2-native-cli-slug",
            "--bridge-evidence",
            str(bridge_path),
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["schema"] == helper.SCHEMA
    refs = body["ao2_refs"]
    assert (
        refs["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert refs["ao2_governed_run_plan_native_gate_stages"] == [
        "midpoint",
        "closure",
    ]
    # Sanity-check: the trust_boundary block is still present (the
    # AO2-native branch should not have changed the payload shape).
    assert "trust_boundary" in body
