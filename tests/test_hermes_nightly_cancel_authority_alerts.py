"""Tests for the cancel-authority notification surface in
``hermes_nightly_ao2_advancement.py``.

Covers:

- ``cancel_authority_alerts(payload)`` returns the expected alert list
  for every status the wrapper writes.
- ``build_notification_payload(payload)`` integrates those alerts into
  severity, summary text, and the returned dict's
  ``cancel_authority_alerts`` field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hermes_nightly_ao2_advancement as nightly  # noqa: E402


# ---------------------------------------------------------------------------
# helpers


def _write_artifact(tmp_path: Path, artifact: dict[str, Any]) -> Path:
    out = tmp_path / "cancel-authority-dry-run.json"
    out.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
    return out


def _payload_with(artifact_path: Path | str) -> dict[str, Any]:
    return {
        "status": "running",
        "steps": [],
        "artifacts": {"cancel_authority_dry_run": str(artifact_path)},
    }


# ---------------------------------------------------------------------------
# cancel_authority_alerts — happy paths (no alert)


def test_no_artifact_path_returns_no_alerts() -> None:
    assert nightly.cancel_authority_alerts({}) == []
    assert nightly.cancel_authority_alerts({"artifacts": {}}) == []


def test_missing_file_returns_no_alerts(tmp_path: Path) -> None:
    payload = _payload_with(tmp_path / "absent.json")
    assert nightly.cancel_authority_alerts(payload) == []


def test_planned_status_emits_no_alert(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "planned",
        },
    )
    assert nightly.cancel_authority_alerts(_payload_with(path)) == []


def test_skipped_status_emits_no_alert(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "skipped",
            "skip_reason": "not_scheduled_weekday_iso1",
        },
    )
    assert nightly.cancel_authority_alerts(_payload_with(path)) == []


def test_executed_accepted_emits_no_alert(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "outcome": "accept_ao2_owns_watchdog_cancel",
            "accepted": True,
        },
    )
    assert nightly.cancel_authority_alerts(_payload_with(path)) == []


# ---------------------------------------------------------------------------
# cancel_authority_alerts — failure modes


def test_unreadable_artifact_alerts(tmp_path: Path) -> None:
    out = tmp_path / "cancel-authority-dry-run.json"
    out.write_text("not-json{", encoding="utf-8")
    alerts = nightly.cancel_authority_alerts(_payload_with(out))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_artifact_unreadable"
    assert str(out) in alerts[0]["message"]


def test_non_dict_artifact_alerts(tmp_path: Path) -> None:
    out = tmp_path / "cancel-authority-dry-run.json"
    out.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    alerts = nightly.cancel_authority_alerts(_payload_with(out))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_artifact_malformed"


def test_binary_missing_alerts(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "binary_missing",
            "ao2_bin": "/non/existent/ao2",
            "blockers": ["ao2_bin_not_found:/non/existent/ao2"],
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_binary_missing"
    assert "/non/existent/ao2" in alerts[0]["message"]


def test_capture_failed_alerts_with_blocker_message(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "capture_failed",
            "blockers": ["ao2 factory queue-list exited 137"],
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_capture_failed"
    assert alerts[0]["message"] == "ao2 factory queue-list exited 137"


def test_capture_failed_alerts_without_blockers_falls_back(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "capture_failed",
            "blockers": [],
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert "queue-list capture failed" in alerts[0]["message"]


def test_executed_refused_alerts(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "outcome": "watchdog_refused",
            "accepted": False,
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_round_trip_refused"
    assert "watchdog_refused" in alerts[0]["message"]


def test_executed_producer_refused_alerts(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "outcome": "producer_refused",
            "accepted": False,
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert "producer_refused" in alerts[0]["message"]


def test_unexpected_status_alerts(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "weird-new-thing",
        },
    )
    alerts = nightly.cancel_authority_alerts(_payload_with(path))
    assert len(alerts) == 1
    assert alerts[0]["name"] == "cancel_authority_unexpected_status"


# ---------------------------------------------------------------------------
# build_notification_payload integration


def test_notification_info_severity_when_no_alerts(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "outcome": "accept_ao2_owns_watchdog_cancel",
            "accepted": True,
        },
    )
    payload = {
        "status": "passed",
        "steps": [],
        "artifacts": {
            "cancel_authority_dry_run": str(path),
            "release_gate_dry_run": "/does/not/exist",
        },
        "generated_at_ms": 1700000000000,
    }
    notification = nightly.build_notification_payload(payload)
    assert notification["severity"] == "info"
    assert notification["cancel_authority_alerts"] == []
    assert "cancel_authority_alerts=0" in notification["text"]


def test_notification_failure_severity_when_refused(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "outcome": "watchdog_refused",
            "accepted": False,
        },
    )
    payload = {
        "status": "passed",
        "steps": [],
        "artifacts": {
            "cancel_authority_dry_run": str(path),
            "release_gate_dry_run": "/does/not/exist",
        },
        "generated_at_ms": 1700000000000,
    }
    notification = nightly.build_notification_payload(payload)
    assert notification["severity"] == "failure"
    assert len(notification["cancel_authority_alerts"]) == 1
    assert notification["cancel_authority_alerts"][0]["name"] == (
        "cancel_authority_round_trip_refused"
    )
    assert "cancel_authority_alerts=1" in notification["text"]
    assert "watchdog_refused" in notification["text"]


def test_notification_includes_binary_missing_in_text(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "binary_missing",
            "ao2_bin": "/no/such/ao2",
            "blockers": ["ao2_bin_not_found:/no/such/ao2"],
        },
    )
    payload = {
        "status": "passed",
        "steps": [],
        "artifacts": {
            "cancel_authority_dry_run": str(path),
        },
        "generated_at_ms": 1700000000000,
    }
    notification = nightly.build_notification_payload(payload)
    assert notification["severity"] == "failure"
    assert "/no/such/ao2" in notification["text"]


def test_notification_omits_cancel_authority_alerts_when_no_artifact() -> None:
    payload = {
        "status": "passed",
        "steps": [],
        "artifacts": {},
        "generated_at_ms": 1700000000000,
    }
    notification = nightly.build_notification_payload(payload)
    assert notification["cancel_authority_alerts"] == []
    assert "cancel_authority_alerts=0" in notification["text"]
    assert notification["severity"] == "info"


def test_skipped_artifact_keeps_info_severity(tmp_path: Path) -> None:
    """The most common day-to-day case: cron ran on a non-cadence day and
    the wrapper wrote status=skipped. No alert, no failure severity."""

    path = _write_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "skipped",
            "skip_reason": "not_scheduled_weekday_iso1",
        },
    )
    payload = {
        "status": "passed",
        "steps": [],
        "artifacts": {"cancel_authority_dry_run": str(path)},
        "generated_at_ms": 1700000000000,
    }
    notification = nightly.build_notification_payload(payload)
    assert notification["severity"] == "info"
    assert notification["cancel_authority_alerts"] == []
