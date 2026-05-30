"""Tests for the cancel-authority markdown section in
``hermes_nightly_ao2_advancement.write_markdown``.

The notification slice (3c1b1da5) made the cancel-authority drift
visible to the operator pager. This slice adds the same visibility to
the human-readable nightly report so an operator scanning the
markdown sees the status without having to open the JSON artifact.
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


def _payload(artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "passed",
        "generated_at_ms": 1700000000000,
        "steps": [],
        "artifacts": artifacts,
    }


def _write_cancel_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    out = tmp_path / "cancel-authority-dry-run.json"
    out.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return out


def test_markdown_renders_planned_section(tmp_path: Path) -> None:
    artifact = _write_cancel_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "planned",
            "mode": "auto",
            "weekday_configured": 1,
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(artifact)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## Cancel-Authority Dry-Run" in text
    assert "status: `planned`" in text
    assert "mode: `auto`" in text
    assert "weekday_configured: `1`" in text
    # No alerts section when status is benign.
    assert "## Cancel-Authority Alerts" not in text


def test_markdown_renders_executed_accepted(tmp_path: Path) -> None:
    artifact = _write_cancel_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "mode": "force",
            "weekday_configured": 1,
            "weekday_observed": 2,
            "outcome": "accept_ao2_owns_watchdog_cancel",
            "accepted": True,
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(artifact)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## Cancel-Authority Dry-Run" in text
    assert "status: `executed`" in text
    assert "outcome: `accept_ao2_owns_watchdog_cancel`" in text
    assert "accepted: `True`" in text
    assert "weekday_observed: `2`" in text
    # Healthy round trip ⇒ no alerts section.
    assert "## Cancel-Authority Alerts" not in text


def test_markdown_renders_skipped_section(tmp_path: Path) -> None:
    artifact = _write_cancel_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "skipped",
            "mode": "auto",
            "weekday_configured": 1,
            "weekday_observed": 3,
            "skip_reason": "not_scheduled_weekday_iso1",
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(artifact)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "status: `skipped`" in text
    assert "skip_reason: `not_scheduled_weekday_iso1`" in text
    # Skipped is not an alert.
    assert "## Cancel-Authority Alerts" not in text


def test_markdown_renders_refused_with_alerts_section(tmp_path: Path) -> None:
    artifact = _write_cancel_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "executed",
            "mode": "force",
            "weekday_configured": 1,
            "outcome": "watchdog_refused",
            "accepted": False,
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(artifact)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "status: `executed`" in text
    assert "outcome: `watchdog_refused`" in text
    assert "accepted: `False`" in text
    assert "## Cancel-Authority Alerts" in text
    assert "cancel_authority_round_trip_refused" in text


def test_markdown_renders_binary_missing_with_alerts_section(tmp_path: Path) -> None:
    artifact = _write_cancel_artifact(
        tmp_path,
        {
            "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
            "status": "binary_missing",
            "ao2_bin": "/no/such/ao2",
            "blockers": ["ao2_bin_not_found:/no/such/ao2"],
            "skip_reason": "ao2_bin_not_found",
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(artifact)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "status: `binary_missing`" in text
    assert "skip_reason: `ao2_bin_not_found`" in text
    assert "## Cancel-Authority Alerts" in text
    assert "cancel_authority_binary_missing" in text
    assert "/no/such/ao2" in text


def test_markdown_renders_unreadable_artifact(tmp_path: Path) -> None:
    out = tmp_path / "cancel-authority-dry-run.json"
    out.write_text("not-json{", encoding="utf-8")
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({"cancel_authority_dry_run": str(out)}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## Cancel-Authority Dry-Run" in text
    assert "status: `unreadable`" in text
    assert "## Cancel-Authority Alerts" in text
    assert "cancel_authority_artifact_unreadable" in text


def test_markdown_omits_section_when_artifact_path_missing(tmp_path: Path) -> None:
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## Cancel-Authority Dry-Run" not in text
    assert "## Cancel-Authority Alerts" not in text


def test_markdown_renders_section_even_when_file_missing(tmp_path: Path) -> None:
    """When the artifact path is registered but the file hasn't landed
    yet (e.g. the cron just started and the dry-run step hasn't run),
    the section still renders with status=missing so the operator can
    see the cron is configured."""

    md_path = tmp_path / "report.md"
    artifact_path = tmp_path / "nightly" / "cancel-authority-dry-run.json"
    nightly.write_markdown(
        _payload({"cancel_authority_dry_run": str(artifact_path)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Cancel-Authority Dry-Run" in text
    assert "status: `missing`" in text
