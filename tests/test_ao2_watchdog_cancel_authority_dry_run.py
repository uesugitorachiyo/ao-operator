"""Tests for the AO2 watchdog cancel-authority dry-run round-trip script.

The dry-run script wires the producer
(``scripts/ao2_watchdog_cancel_authority_producer.py``) to the live
watchdog consumer
(``scripts/hermes_ao2_watchdog.evaluate_ao2_cancel_authority``) without
touching the launchd loop or the live ao2-control-plane data dir.

Tests use the offline ``--queue-list-json`` mode so the suite does not
depend on the ao2 binary being present in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "ao2_watchdog_cancel_authority_dry_run.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ao2_watchdog_cancel_authority_dry_run as _dry_run  # noqa: E402

QUEUE_LIST_SCHEMA = "ao2.ao-operator-compat-workbench-queue-list.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"
DRY_RUN_SCHEMA = "ao-operator/ao2-watchdog-cancel-authority-dry-run/v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"


def _empty_queue_list(queue_path: str = "/tmp/queue") -> dict:
    return {
        "schema_version": QUEUE_LIST_SCHEMA,
        "owner": "ao2-workbench-queue",
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "queue_path": queue_path,
        "entry_count": 0,
        "continuity_contract": {"schema": "ao2.queue-continuity.v1"},
        "entries": [],
    }


def _queue_list_with_active(queue_path: str = "/tmp/queue") -> dict:
    return {
        "schema_version": QUEUE_LIST_SCHEMA,
        "owner": "ao2-workbench-queue",
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "queue_path": queue_path,
        "entry_count": 2,
        "continuity_contract": {"schema": "ao2.queue-continuity.v1"},
        "entries": [
            {"run_id": "run-a", "status": "completed"},
            {"run_id": "run-b", "status": "running"},
        ],
    }


def _write_queue_list(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


# ---------------------------------------------------------------------------
# In-process API: round-trip outcome


def test_run_dry_run_accepts_empty_queue_in_process(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    evidence = _dry_run.run_dry_run(
        queue_list_payload=_empty_queue_list(),
        out_dir=out_dir,
        active_pid=4242,
        reason="unit-test",
        queue_list_source_label="file:test",
    )
    assert evidence["schema"] == DRY_RUN_SCHEMA
    assert evidence["outcome"] == "accept_ao2_owns_watchdog_cancel"
    assert evidence["queue_list"]["active_entry_count"] == 0
    assert evidence["attestation"]["schema"] == ATTESTATION_SCHEMA
    assert evidence["attestation"]["factory_v3_role"] == EXPECTED_FACTORY_V3_ROLE
    assert evidence["attestation"]["no_active_ao2_runs"] is True
    assert evidence["watchdog_decision"]["decision"] == "accept_ao2_owns_watchdog_cancel"
    assert evidence["watchdog_decision"]["mode"] == "ao2_owned"
    assert evidence["watchdog_decision"]["claim_status"] == "accepted"
    assert evidence["watchdog_decision"]["claim_blockers"] == []
    assert evidence["watchdog_decision"]["no_active_ao2_runs_attestation_provided"] is True
    assert evidence["active_pid"] == 4242
    assert evidence["ao2_ownership"]["cancel_owner"] == "ao2-workbench-queue"
    assert evidence["ao2_ownership"]["factory_v3_role"] == EXPECTED_FACTORY_V3_ROLE


def test_run_dry_run_records_producer_refusal_for_active_entry(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    evidence = _dry_run.run_dry_run(
        queue_list_payload=_queue_list_with_active(),
        out_dir=out_dir,
        active_pid=4242,
        reason="unit-test",
        queue_list_source_label="file:test",
    )
    assert evidence["outcome"] == "producer_refused"
    assert evidence["producer"]["refused"] is True
    assert "run-b=running" in evidence["producer"]["error"]
    assert evidence["attestation"] is None
    assert evidence["watchdog_decision"] is None
    assert evidence["queue_list"]["active_entry_count"] == 1


def test_run_dry_run_records_producer_refusal_for_unknown_schema(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    bad_payload = {
        "schema_version": "ao2.legacy.unknown.v0",
        "entries": [],
    }
    evidence = _dry_run.run_dry_run(
        queue_list_payload=bad_payload,
        out_dir=out_dir,
        active_pid=1,
        reason="unit-test",
        queue_list_source_label="file:test",
    )
    assert evidence["outcome"] == "producer_refused"
    # The producer rejects the unknown schema before classifying entries;
    # the dry-run records the producer's error string verbatim.
    assert evidence["producer"]["refused"] is True
    assert evidence["queue_list"]["active_entry_count"] == 0


# ---------------------------------------------------------------------------
# Artifact layout


def test_run_dry_run_writes_three_artifacts_to_out_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    _dry_run.run_dry_run(
        queue_list_payload=_empty_queue_list(),
        out_dir=out_dir,
        active_pid=99,
        reason="unit-test",
        queue_list_source_label="file:test",
    )
    queue_list_path = out_dir / "queue-list.json"
    attestation_path = out_dir / "no-active-ao2-runs-attestation.json"
    evidence_path = out_dir / "dry-run-evidence.json"
    assert queue_list_path.exists()
    assert attestation_path.exists()
    assert evidence_path.exists()

    queue_list = json.loads(queue_list_path.read_text(encoding="utf-8"))
    assert queue_list["schema_version"] == QUEUE_LIST_SCHEMA

    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    assert attestation["schema"] == ATTESTATION_SCHEMA
    assert attestation["factory_v3_role"] == EXPECTED_FACTORY_V3_ROLE
    assert attestation["no_active_ao2_runs"] is True
    assert attestation["source"]["active_entry_count"] == 0

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == DRY_RUN_SCHEMA
    assert evidence["outcome"] == "accept_ao2_owns_watchdog_cancel"
    # Evidence cross-links the on-disk attestation path
    assert Path(evidence["attestation"]["path"]).resolve() == attestation_path.resolve()


def test_run_dry_run_writes_only_two_artifacts_on_refusal(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    _dry_run.run_dry_run(
        queue_list_payload=_queue_list_with_active(),
        out_dir=out_dir,
        active_pid=1,
        reason="unit-test",
        queue_list_source_label="file:test",
    )
    # Producer refusal short-circuits before write_attestation
    assert (out_dir / "queue-list.json").exists()
    assert not (out_dir / "no-active-ao2-runs-attestation.json").exists()
    assert (out_dir / "dry-run-evidence.json").exists()


# ---------------------------------------------------------------------------
# CLI subprocess


def test_cli_with_queue_list_json_round_trip_returns_zero(tmp_path: Path) -> None:
    queue_list_path = tmp_path / "queue-list.json"
    _write_queue_list(queue_list_path, _empty_queue_list())
    out_dir = tmp_path / "evidence"

    result = _run_script(
        "--queue-list-json",
        str(queue_list_path),
        "--out-dir",
        str(out_dir),
        "--active-pid",
        "12345",
        "--strict",
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads((out_dir / "dry-run-evidence.json").read_text(encoding="utf-8"))
    assert evidence["outcome"] == "accept_ao2_owns_watchdog_cancel"
    assert evidence["queue_list"]["source"] == f"file:{queue_list_path}"
    assert evidence["active_pid"] == 12345


def test_cli_strict_exits_two_when_queue_has_active_entry(tmp_path: Path) -> None:
    queue_list_path = tmp_path / "queue-list.json"
    _write_queue_list(queue_list_path, _queue_list_with_active())
    out_dir = tmp_path / "evidence"

    result = _run_script(
        "--queue-list-json",
        str(queue_list_path),
        "--out-dir",
        str(out_dir),
        "--strict",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    evidence = json.loads((out_dir / "dry-run-evidence.json").read_text(encoding="utf-8"))
    assert evidence["outcome"] == "producer_refused"


def test_cli_non_strict_returns_zero_even_on_producer_refusal(tmp_path: Path) -> None:
    queue_list_path = tmp_path / "queue-list.json"
    _write_queue_list(queue_list_path, _queue_list_with_active())
    out_dir = tmp_path / "evidence"

    result = _run_script(
        "--queue-list-json",
        str(queue_list_path),
        "--out-dir",
        str(out_dir),
    )
    # Default mode emits the evidence and returns 0 so caller can decide
    # what to do with a refusal; --strict promotes to exit 2.
    assert result.returncode == 0, result.stderr
    evidence = json.loads((out_dir / "dry-run-evidence.json").read_text(encoding="utf-8"))
    assert evidence["outcome"] == "producer_refused"


def test_cli_requires_one_of_queue_list_or_ao2_bin(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    result = _run_script("--out-dir", str(out_dir))
    # argparse rejects with exit 2 when a required mutually-exclusive group
    # member is missing.
    assert result.returncode == 2
    assert "one of the arguments" in result.stderr or "required" in result.stderr


def test_cli_rejects_missing_queue_list_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    result = _run_script(
        "--queue-list-json",
        str(tmp_path / "does-not-exist.json"),
        "--out-dir",
        str(out_dir),
    )
    assert result.returncode == 2
    assert "does-not-exist.json" in result.stderr


# ---------------------------------------------------------------------------
# Schema contract


def test_dry_run_evidence_schema_constant_matches_artifact(tmp_path: Path) -> None:
    out_dir = tmp_path / "evidence"
    evidence = _dry_run.run_dry_run(
        queue_list_payload=_empty_queue_list(),
        out_dir=out_dir,
        active_pid=1,
        reason="schema-test",
        queue_list_source_label="file:test",
    )
    assert evidence["schema"] == _dry_run.DRY_RUN_SCHEMA == DRY_RUN_SCHEMA
    # Trust boundary mirrors ao2_watchdog_cancel_ownership.TRUST_BOUNDARY:
    # cancel_authority is the AO2 subsystem ("ao2_factory_queue"); the
    # owner record on AO2 ownership is the queue name ("ao2-workbench-queue").
    assert evidence["trust_boundary"]["cancel_authority"] == "ao2_factory_queue"
    assert evidence["trust_boundary"]["watchdog_role"] == (
        "executor_of_ao2_cancel_decision_or_unauthorized"
    )
    assert evidence["trust_boundary"]["factory_v3_role"] == EXPECTED_FACTORY_V3_ROLE
    assert evidence["trust_boundary"]["control_plane_role"] == "read_only_observer"
    assert evidence["trust_boundary"]["control_plane_approves_cancel"] is False
    assert evidence["trust_boundary"]["mutates_ao_artifacts"] is False
    assert evidence["ao2_ownership"]["cancel_owner"] == "ao2-workbench-queue"
    assert evidence["ao2_ownership"]["retry_owner"] == "ao2-workbench-queue"
