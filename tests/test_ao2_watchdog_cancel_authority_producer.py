"""Tests for the AO2 cancel-authority producer (Phase 2 #5 follow-up).

The producer reads an ``ao2 factory queue-list`` JSON
(``ao2.ao-operator-compat-workbench-queue-list.v1``) and emits the
``ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1`` payload the
live watchdog consumes via ``--no-active-ao2-runs-attestation``.

The producer does NOT shell out to the ao2 binary; the launchd plist
captures the queue-list JSON to disk first and hands the path to this
script. That keeps the producer pure and offline-testable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_watchdog_cancel_authority_producer.py"

QUEUE_LIST_SCHEMA = "ao2.ao-operator-compat-workbench-queue-list.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"


def _write_queue_list(
    path: Path, *, entries: list[dict[str, str]], queue_path: str = "/tmp/queue"
) -> None:
    payload = {
        "schema_version": QUEUE_LIST_SCHEMA,
        "owner": "ao2-workbench-queue",
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "queue_path": queue_path,
        "entry_count": len(entries),
        "continuity_contract": {"schema": "ao2.queue-continuity.v1"},
        "entries": entries,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _run_producer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_producer_emits_attestation_when_queue_is_empty(tmp_path: Path) -> None:
    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(queue_list, entries=[])
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json",
        str(queue_list),
        "--out",
        str(out),
        "--reason",
        "Hermes one-shot stuck without any AO2 run in flight",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == ATTESTATION_SCHEMA
    assert payload["factory_v3_role"] == EXPECTED_FACTORY_V3_ROLE
    assert payload["no_active_ao2_runs"] is True
    assert payload["reason"] == "Hermes one-shot stuck without any AO2 run in flight"
    assert payload["source"]["schema_version"] == QUEUE_LIST_SCHEMA
    assert payload["source"]["queue_path"] == "/tmp/queue"
    assert payload["source"]["entry_count"] == 0
    assert payload["source"]["active_entry_count"] == 0
    assert isinstance(payload["produced_at_ms"], int) and payload["produced_at_ms"] > 0


def test_producer_emits_attestation_when_all_entries_are_terminal(
    tmp_path: Path,
) -> None:
    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(
        queue_list,
        entries=[
            {"run_id": "run-a", "status": "completed"},
            {"run_id": "run-b", "status": "cancelled"},
            {"run_id": "run-c", "status": "failed"},
        ],
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["no_active_ao2_runs"] is True
    assert payload["source"]["entry_count"] == 3
    assert payload["source"]["active_entry_count"] == 0
    assert payload["source"]["status_counts"] == {
        "completed": 1,
        "cancelled": 1,
        "failed": 1,
    }
    assert payload["reason"]  # default reason populated


def test_producer_refuses_when_a_queued_entry_is_present(tmp_path: Path) -> None:
    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(
        queue_list,
        entries=[
            {"run_id": "run-a", "status": "completed"},
            {"run_id": "run-b", "status": "queued"},
        ],
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 2
    assert not out.exists()
    assert "active AO2 queue entries" in result.stderr
    assert "run-b" in result.stderr
    assert "queued" in result.stderr


def test_producer_refuses_when_a_running_entry_is_present(tmp_path: Path) -> None:
    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(
        queue_list, entries=[{"run_id": "live", "status": "running"}]
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 2
    assert not out.exists()
    assert "running" in result.stderr
    assert "live" in result.stderr


def test_producer_refuses_when_a_cancel_requested_entry_is_present(
    tmp_path: Path,
) -> None:
    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(
        queue_list,
        entries=[{"run_id": "midcancel", "status": "cancel_requested"}],
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 2
    assert not out.exists()
    assert "cancel_requested" in result.stderr
    assert "midcancel" in result.stderr


def test_producer_rejects_wrong_schema(tmp_path: Path) -> None:
    queue_list = tmp_path / "queue-list.json"
    queue_list.write_text(
        json.dumps({"schema_version": "not.a.queue.list.v1", "entries": []}),
        encoding="utf-8",
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 2
    assert not out.exists()
    assert "schema_version" in result.stderr
    assert QUEUE_LIST_SCHEMA in result.stderr


def test_producer_rejects_missing_input(tmp_path: Path) -> None:
    queue_list = tmp_path / "does-not-exist.json"
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 2
    assert not out.exists()
    assert "queue-list-json" in result.stderr or "missing" in result.stderr


def test_producer_attestation_is_consumable_by_live_watchdog_validator(
    tmp_path: Path,
) -> None:
    """Round-trip: producer's output should pass the watchdog's validator."""

    queue_list = tmp_path / "queue-list.json"
    _write_queue_list(
        queue_list,
        entries=[{"run_id": "done", "status": "completed"}],
    )
    out = tmp_path / "attestation.json"
    result = _run_producer(
        "--queue-list-json", str(queue_list), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import ao2_watchdog_cancel_ownership as cancel  # type: ignore

        payload = json.loads(out.read_text(encoding="utf-8"))
        cancel._validate_attestation(payload, out)
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Passthrough mode: AO2 emits the attestation natively via
# `ao2 factory cancel-authority`; the ao-operator producer validates and
# re-emits it verbatim so ao-operator observes an AO2-native receipt instead
# of duplicating the producer logic. Phase 2 exit-gate item #5.
# ---------------------------------------------------------------------------


def _write_native_attestation(
    path: Path,
    *,
    schema: str = ATTESTATION_SCHEMA,
    factory_v3_role: str = EXPECTED_FACTORY_V3_ROLE,
    no_active_ao2_runs: bool = True,
    reason: str = "AO2-native attestation",
    produced_at_ms: int = 1_748_140_000_000,
    source_schema_version: str = QUEUE_LIST_SCHEMA,
    queue_path: str = "/tmp/queue.json",
    entry_count: int = 0,
    active_entry_count: int = 0,
    status_counts: dict[str, int] | None = None,
) -> None:
    payload = {
        "schema": schema,
        "factory_v3_role": factory_v3_role,
        "no_active_ao2_runs": no_active_ao2_runs,
        "reason": reason,
        "produced_at_ms": produced_at_ms,
        "source": {
            "schema_version": source_schema_version,
            "queue_path": queue_path,
            "entry_count": entry_count,
            "active_entry_count": active_entry_count,
            "status_counts": status_counts or {},
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_passthrough_accepts_valid_ao2_native_attestation(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native)
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(out.read_text(encoding="utf-8"))
    expected = json.loads(native.read_text(encoding="utf-8"))
    assert written == expected, "passthrough must preserve native payload exactly"


def test_passthrough_emits_passthrough_marker_in_stdout(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native)
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["attestation_path"] == str(out)
    assert summary["mode"] == "passthrough_ao2_native"


def test_passthrough_rejects_attestation_with_wrong_schema(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native, schema="ao-operator/some-other-schema/v1")
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert not out.exists()
    assert "schema" in result.stderr


def test_passthrough_rejects_attestation_with_no_active_runs_false(
    tmp_path: Path,
) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native, no_active_ao2_runs=False)
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert not out.exists()
    assert "no_active_ao2_runs" in result.stderr


def test_passthrough_rejects_wrong_factory_v3_role(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native, factory_v3_role="executor_of_ao2")
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert "factory_v3_role" in result.stderr


def test_passthrough_rejects_missing_source_schema(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(
        native, source_schema_version="ao2.ao-operator-compat-workbench-queue-list.v0"
    )
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert "source" in result.stderr or "schema_version" in result.stderr


def test_passthrough_rejects_when_source_active_entry_count_is_nonzero(
    tmp_path: Path,
) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native, active_entry_count=1)
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert "active_entry_count" in result.stderr


def test_passthrough_rejects_missing_input_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    out = tmp_path / "passthrough.json"
    result = _run_producer(
        "--ao2-native-attestation", str(missing), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert not out.exists()


def test_passthrough_rejects_invalid_json(tmp_path: Path) -> None:
    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    native.write_text("not json", encoding="utf-8")
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 2, result.stdout
    assert "JSON" in result.stderr or "json" in result.stderr


def test_producer_requires_exactly_one_input_mode(tmp_path: Path) -> None:
    out = tmp_path / "passthrough.json"
    # Neither mode supplied → reject
    result = _run_producer("--out", str(out))
    assert result.returncode != 0
    # Both modes supplied → reject (mutually exclusive)
    native = tmp_path / "native-attestation.json"
    queue = tmp_path / "queue-list.json"
    _write_native_attestation(native)
    _write_queue_list(queue, entries=[])
    result = _run_producer(
        "--ao2-native-attestation",
        str(native),
        "--queue-list-json",
        str(queue),
        "--out",
        str(out),
    )
    assert result.returncode != 0


def test_passthrough_output_passes_watchdog_validator(tmp_path: Path) -> None:
    """End-to-end: AO2-native → passthrough → watchdog validator must accept."""

    native = tmp_path / "native-attestation.json"
    out = tmp_path / "passthrough.json"
    _write_native_attestation(native)
    result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import ao2_watchdog_cancel_ownership as cancel  # type: ignore

        payload = json.loads(out.read_text(encoding="utf-8"))
        cancel._validate_attestation(payload, out)
    finally:
        sys.path.pop(0)


def test_passthrough_against_real_ao2_cli_output_byte_compatible(
    tmp_path: Path,
) -> None:
    """If a current-build ao2 binary is available, ensure its native
    `ao2 factory cancel-authority` output passes ao-operator's passthrough
    validator. Skipped otherwise so the test suite stays hermetic on
    hosts without a current ao2 build (the AO2_BIN env var lets the
    runner point at a freshly-built target/debug binary)."""

    import os
    import shutil

    import pytest

    ao2_binary = os.environ.get("AO2_BIN") or shutil.which("ao2")
    if ao2_binary is None:
        pytest.skip("ao2 binary not on PATH and AO2_BIN unset")

    probe = subprocess.run(
        [ao2_binary, "factory", "cancel-authority", "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip(
            "ao2 binary at "
            f"{ao2_binary} does not expose `factory cancel-authority` "
            "(older build); set AO2_BIN to a freshly-built ao2 to "
            "exercise the live byte-compat path"
        )

    queue = tmp_path / "queue-list.json"
    _write_queue_list(queue, entries=[{"run_id": "done", "status": "completed"}])
    native = tmp_path / "native-attestation.json"
    result = subprocess.run(
        [
            ao2_binary,
            "factory",
            "cancel-authority",
            "--queue-list-json",
            str(queue),
            "--produced-at-ms",
            "1748140000000",
            "--out",
            str(native),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert native.exists()

    out = tmp_path / "passthrough.json"
    pass_result = _run_producer(
        "--ao2-native-attestation", str(native), "--out", str(out)
    )
    assert pass_result.returncode == 0, pass_result.stderr
