"""Tests for ao2_cancel_authority surfacing in the watchdog operator panel.

Phase 2 #5 follow-up: the watchdog status payload now carries an
``ao2_cancel_authority`` block (slice A). The operator panel JSON and
markdown should expose it so reviewers can read the cancel decision
without parsing the raw status JSON.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hermes_ao2_watchdog as watchdog  # noqa: E402


def _base_payload() -> dict[str, object]:
    return {
        "schema": watchdog.SCHEMA,
        "generated_at_ms": 1779700000000,
        "status": "started",
        "action": "recovered_overdue_hermes_oneshot",
        "next_check_seconds": 600,
        "backend_decision": {
            "mode": "normal_advancement",
            "reason": "no rejected pack found",
            "command": ["true"],
            "trust_boundary": {"frontend": "Hermes"},
        },
        "prompt": {"path": "/tmp/prompt.txt", "snapshot_path": "/tmp/snap.md"},
        "active_pid": 4242,
        "terminated_pid": 1111,
        "lock_dir": "/tmp/lock",
        "max_lock_age_seconds": 60,
        "logs": {"stdout": "/tmp/out.log"},
    }


def test_panel_payload_surfaces_legacy_unilateral_authority() -> None:
    payload = _base_payload()
    payload["ao2_cancel_authority"] = {
        "mode": "factory_v3_unilateral_legacy_pending_source_wiring",
        "decision": "allow_unilateral_legacy",
        "warning": watchdog.LEGACY_AUTHORITY_WARNING,
        "ao2_ownership": dict(watchdog._AO2_OWNERSHIP_DEFAULT),
        "sources": {
            "transitions": [],
            "no_active_ao2_runs_attestation": None,
        },
    }
    panel = watchdog.watchdog_panel_payload(payload)
    surfaced = panel["ao2_cancel_authority"]
    assert surfaced["mode"] == "factory_v3_unilateral_legacy_pending_source_wiring"
    assert surfaced["decision"] == "allow_unilateral_legacy"
    assert surfaced["warning"] == watchdog.LEGACY_AUTHORITY_WARNING
    assert surfaced["ao2_ownership"]["cancel_owner"] == "ao2-workbench-queue"
    assert surfaced["sources"] == {
        "transitions": [],
        "no_active_ao2_runs_attestation": None,
    }


def test_panel_payload_surfaces_ao2_owned_accepted_claim() -> None:
    payload = _base_payload()
    payload["ao2_cancel_authority"] = {
        "mode": "ao2_owned",
        "decision": "accept_ao2_owns_watchdog_cancel",
        "claim": {
            "status": "accepted",
            "decision": "accept_ao2_owns_watchdog_cancel",
            "terminated_pids": [1111],
            "pid_coverage": [{"terminated_pid": 1111, "covered": True}],
            "transition_count": 1,
        },
        "sources": {
            "transitions": ["/tmp/transition.json"],
            "no_active_ao2_runs_attestation": None,
        },
    }
    panel = watchdog.watchdog_panel_payload(payload)
    surfaced = panel["ao2_cancel_authority"]
    assert surfaced["mode"] == "ao2_owned"
    assert surfaced["decision"] == "accept_ao2_owns_watchdog_cancel"
    assert surfaced["claim"]["status"] == "accepted"
    assert surfaced["sources"]["transitions"] == ["/tmp/transition.json"]


def test_panel_payload_omits_field_when_absent() -> None:
    payload = _base_payload()  # no ao2_cancel_authority key
    panel = watchdog.watchdog_panel_payload(payload)
    assert "ao2_cancel_authority" not in panel


def test_panel_markdown_includes_cancel_authority_section_when_present() -> None:
    payload = _base_payload()
    payload["ao2_cancel_authority"] = {
        "mode": "ao2_owned",
        "decision": "accept_ao2_owns_watchdog_cancel",
        "claim": {"status": "accepted"},
        "sources": {
            "transitions": ["/tmp/t1.json"],
            "no_active_ao2_runs_attestation": "/tmp/att.json",
        },
    }
    panel = watchdog.watchdog_panel_payload(payload)
    md = watchdog.watchdog_panel_markdown(panel)
    assert "## AO2 Cancel Authority" in md
    assert "Mode: ao2_owned" in md
    assert "Decision: accept_ao2_owns_watchdog_cancel" in md
    assert "Claim status: accepted" in md
    assert "/tmp/t1.json" in md
    assert "/tmp/att.json" in md


def test_panel_markdown_includes_refused_authority_error() -> None:
    payload = _base_payload()
    payload["status"] = "refused"
    payload["action"] = "refused_overdue_termination_invalid_ao2_authority"
    payload["ao2_cancel_authority"] = {
        "mode": "refused_invalid_source",
        "decision": "refuse_invalid_ao2_authority_source",
        "error": "transition schema must be ao2.ao-operator-compat-workbench-queue-transition.v1; got 'wrong' in /tmp/bad.json",
        "sources": {
            "transitions": ["/tmp/bad.json"],
            "no_active_ao2_runs_attestation": None,
        },
    }
    panel = watchdog.watchdog_panel_payload(payload)
    md = watchdog.watchdog_panel_markdown(panel)
    assert "Mode: refused_invalid_source" in md
    assert (
        "Decision: refuse_invalid_ao2_authority_source" in md
    )
    assert "Error:" in md
    assert "wrong" in md


def test_panel_markdown_omits_section_when_authority_absent() -> None:
    payload = _base_payload()
    panel = watchdog.watchdog_panel_payload(payload)
    md = watchdog.watchdog_panel_markdown(panel)
    assert "## AO2 Cancel Authority" not in md
