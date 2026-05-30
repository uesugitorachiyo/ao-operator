"""Tests for ``scripts/hermes_nightly_cancel_authority_dry_run.py``.

Covers the cadence wrapper that publishes the AO2 watchdog cancel-authority
dry-run outcome on a weekly cadence. The wrapper never touches the live
launchd loop; these tests confirm that the cadence gating, ao2-binary
discovery, and round-trip pass-through all behave correctly without
exercising the live ``ao2`` binary (which is the operator host's
concern, not pytest's).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hermes_nightly_cancel_authority_dry_run as wrapper  # noqa: E402


# ---------------------------------------------------------------------------
# helpers


def _monday_utc() -> datetime:
    # 2026-05-25 is a Monday (ISO weekday 1).
    return datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


def _tuesday_utc() -> datetime:
    return datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)


def _make_ao2_bin(tmp_path: Path) -> Path:
    """Create a stand-in executable file so ``Path.exists()`` is True.

    The wrapper never invokes this file directly when
    ``capture_queue_list_live`` is monkeypatched, but the existence check
    happens before the patch fires for the executed path.
    """

    fake = tmp_path / "ao2"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    return fake


def _fake_evidence(outcome: str) -> dict[str, Any]:
    return {
        "schema": wrapper.DRY_RUN_SCHEMA,
        "outcome": outcome,
        "active_pid": 4242,
        "queue_list": {
            "source": "monkeypatched",
            "snapshot_path": "/dev/null",
            "schema_version": 1,
            "entry_count": 0,
            "active_entry_count": 0,
        },
        "producer": {"refused": False},
        "attestation": {"path": "/dev/null"},
        "watchdog_decision": {"decision": outcome},
    }


# ---------------------------------------------------------------------------
# input validation


def test_run_step_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        wrapper.run_step(
            ao2_bin=tmp_path / "absent-ao2",
            out_path=tmp_path / "out.json",
            mode="bogus",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("weekday", [0, 8, -1, 100])
def test_run_step_rejects_out_of_range_weekday(tmp_path: Path, weekday: int) -> None:
    with pytest.raises(ValueError, match="weekday must be 1..7"):
        wrapper.run_step(
            ao2_bin=tmp_path / "absent-ao2",
            out_path=tmp_path / "out.json",
            mode="force",
            weekday=weekday,
        )


# ---------------------------------------------------------------------------
# cadence gating


def test_mode_off_writes_skipped_artifact(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    artifact = wrapper.run_step(
        ao2_bin=tmp_path / "absent-ao2",
        out_path=out_path,
        mode="off",
        weekday=1,
        now=_monday_utc(),
    )
    assert artifact["status"] == "skipped"
    assert artifact["skip_reason"] == "mode_off"
    assert artifact["dry_run_evidence"] is None
    assert artifact["blockers"] == []
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk == artifact
    assert on_disk["schema"] == "ao-operator/hermes-nightly-cancel-authority-dry-run/v1"


def test_mode_auto_off_cadence_writes_skipped_artifact(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    artifact = wrapper.run_step(
        ao2_bin=tmp_path / "absent-ao2",
        out_path=out_path,
        mode="auto",
        weekday=1,
        now=_tuesday_utc(),
    )
    assert artifact["status"] == "skipped"
    assert artifact["skip_reason"] == "not_scheduled_weekday_iso1"
    assert artifact["weekday_observed"] == 2
    assert artifact["dry_run_evidence"] is None


def test_mode_auto_matched_cadence_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ao2_bin = _make_ao2_bin(tmp_path)
    out_path = tmp_path / "cancel-authority-dry-run.json"

    captured: dict[str, Any] = {}

    def fake_capture(bin_path: Path) -> tuple[dict[str, Any], str]:
        captured["bin"] = bin_path
        return ({"schema_version": 1, "entries": [], "entry_count": 0}, "monkey")

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _fake_evidence("accept_ao2_owns_watchdog_cancel")

    monkeypatch.setattr(wrapper._dry_run, "capture_queue_list_live", fake_capture)
    monkeypatch.setattr(wrapper._dry_run, "run_dry_run", fake_run)

    artifact = wrapper.run_step(
        ao2_bin=ao2_bin,
        out_path=out_path,
        mode="auto",
        weekday=1,
        now=_monday_utc(),
    )

    assert artifact["status"] == "executed"
    assert artifact["accepted"] is True
    assert artifact["outcome"] == "accept_ao2_owns_watchdog_cancel"
    assert artifact["dry_run_evidence"]["outcome"] == "accept_ao2_owns_watchdog_cancel"
    assert artifact["blockers"] == []
    assert captured["bin"] == ao2_bin
    # The dry-run write target must be a fresh tempdir, NOT the nightly out-path.
    inner_out_dir = captured["out_dir"]
    assert isinstance(inner_out_dir, Path)
    assert inner_out_dir != out_path.parent
    assert not inner_out_dir.exists(), "tempdir must be cleaned up before return"


# ---------------------------------------------------------------------------
# ao2 binary discovery


def test_binary_missing_in_force_mode(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    artifact = wrapper.run_step(
        ao2_bin=tmp_path / "absent-ao2",
        out_path=out_path,
        mode="force",
        weekday=1,
        now=_monday_utc(),
    )
    assert artifact["status"] == "binary_missing"
    assert artifact["skip_reason"] == "ao2_bin_not_found"
    assert artifact["blockers"]
    assert "ao2_bin_not_found" in artifact["blockers"][0]
    assert artifact["dry_run_evidence"] is None


def test_binary_missing_in_auto_mode_on_cadence(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    artifact = wrapper.run_step(
        ao2_bin=tmp_path / "absent-ao2",
        out_path=out_path,
        mode="auto",
        weekday=1,
        now=_monday_utc(),
    )
    assert artifact["status"] == "binary_missing"


# ---------------------------------------------------------------------------
# capture-failure pass-through


def test_capture_failure_records_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ao2_bin = _make_ao2_bin(tmp_path)
    out_path = tmp_path / "cancel-authority-dry-run.json"

    def fake_capture(bin_path: Path) -> tuple[dict[str, Any], str]:
        raise wrapper._dry_run.LiveCaptureError("queue-list exited 1")

    monkeypatch.setattr(wrapper._dry_run, "capture_queue_list_live", fake_capture)

    artifact = wrapper.run_step(
        ao2_bin=ao2_bin,
        out_path=out_path,
        mode="force",
        weekday=1,
        now=_monday_utc(),
    )
    assert artifact["status"] == "capture_failed"
    assert artifact["skip_reason"] == "ao2_queue_list_capture_failed"
    assert artifact["blockers"] == ["queue-list exited 1"]
    assert artifact["dry_run_evidence"] is None


# ---------------------------------------------------------------------------
# round-trip refusal pass-through


def test_refused_round_trip_surfaces_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ao2_bin = _make_ao2_bin(tmp_path)
    out_path = tmp_path / "cancel-authority-dry-run.json"

    monkeypatch.setattr(
        wrapper._dry_run,
        "capture_queue_list_live",
        lambda b: ({"schema_version": 1, "entries": [], "entry_count": 0}, "fake"),
    )
    monkeypatch.setattr(
        wrapper._dry_run,
        "run_dry_run",
        lambda **_: _fake_evidence("watchdog_refused"),
    )

    artifact = wrapper.run_step(
        ao2_bin=ao2_bin,
        out_path=out_path,
        mode="force",
        weekday=1,
        now=_monday_utc(),
    )
    assert artifact["status"] == "executed"
    assert artifact["accepted"] is False
    assert artifact["outcome"] == "watchdog_refused"
    assert artifact["blockers"] == ["watchdog_outcome:watchdog_refused"]


# ---------------------------------------------------------------------------
# CLI surface


SCRIPT = SCRIPTS / "hermes_nightly_cancel_authority_dry_run.py"


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_strict_off_mode_exits_zero(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    result = _run_cli(
        [
            "--ao2-bin",
            str(tmp_path / "absent-ao2"),
            "--out-path",
            str(out_path),
            "--mode",
            "off",
            "--strict",
        ],
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["status"] == "skipped"


def test_cli_strict_binary_missing_exits_two(tmp_path: Path) -> None:
    out_path = tmp_path / "cancel-authority-dry-run.json"
    result = _run_cli(
        [
            "--ao2-bin",
            str(tmp_path / "absent-ao2"),
            "--out-path",
            str(out_path),
            "--mode",
            "force",
            "--strict",
        ],
        cwd=ROOT,
    )
    assert result.returncode == 2, result.stderr
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["status"] == "binary_missing"


# ---------------------------------------------------------------------------
# nightly script integration


NIGHTLY_SCRIPT = SCRIPTS / "hermes_nightly_ao2_advancement.py"


def test_nightly_dry_run_registers_cancel_authority_artifact(tmp_path: Path) -> None:
    out_dir = tmp_path / "nightly"
    result = subprocess.run(
        [
            sys.executable,
            str(NIGHTLY_SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(ROOT.parent / "ao2"),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--provider-acceptance-root",
            str(tmp_path / "empty-provider-acceptance-root"),
            "--out-dir",
            str(out_dir),
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    expected_path = out_dir / "cancel-authority-dry-run.json"

    # registered in payload artifacts
    assert payload["artifacts"]["cancel_authority_dry_run"] == str(expected_path)

    # planned artifact exists on disk
    assert expected_path.exists()
    planned = json.loads(expected_path.read_text(encoding="utf-8"))
    assert planned["schema"] == "ao-operator/hermes-nightly-cancel-authority-dry-run/v1"
    assert planned["status"] == "planned"
    assert planned["mode"] == "auto"
    assert planned["weekday_configured"] == 1
    assert planned["dry_run_evidence"] is None

    # step is registered in payload steps
    step_ids = {step.get("id") for step in payload["steps"]}
    assert "cancel-authority-dry-run" in step_ids
    step = next(s for s in payload["steps"] if s.get("id") == "cancel-authority-dry-run")
    command = step["command"]
    assert "hermes_nightly_cancel_authority_dry_run.py" in " ".join(command)
    assert "--out-path" in command
    assert str(expected_path) in command
    assert "--mode" in command
    assert "auto" in command
