"""Tests for ``role_contracts_alerts`` in
``hermes_nightly_ao2_advancement``.

Mirrors the cancel-authority alert pattern. The producer reads the
AO2-owned ``role_contracts`` block from the
``factory-compat-ao-operator-bridge-evidence.json`` artifact (schema
``ao2.factory-bridge.v1``) and emits notification alerts when:

- ``missing_roles`` is non-empty (a previously-resolved role dropped out).
- ``loaded_count`` falls below the expected coverage threshold
  (default ``ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT`` = 17).
- The artifact is unreadable / malformed / has wrong schema.

Trust boundary: ao-operator owns the threshold (because it owns
``agents/*.toml``). AO2 owns the block. This producer reads
AO2 evidence and applies ao-operator's assertion.
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


def _payload(
    artifacts: dict[str, str], extras: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "passed",
        "generated_at_ms": 1700000000000,
        "steps": [],
        "artifacts": artifacts,
    }
    if extras:
        payload.update(extras)
    return payload


def _write_bridge_evidence(tmp_path: Path, payload: Any) -> Path:
    out = tmp_path / "factory-compat-ao-operator-bridge-evidence.json"
    if isinstance(payload, (dict, list)):
        out.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    else:
        out.write_text(str(payload), encoding="utf-8")
    return out


def _full_coverage_block() -> dict[str, Any]:
    return {
        "owner": "ao2",
        "factory_v3_required_to_load": False,
        "loaded_count": nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT,
        "missing_roles": [],
        "path": "/fake/agents",
    }


# ---------------------------------------------------------------------------
# Happy path: full coverage emits no alerts. The expected-default constant
# must match the canonical 17-task fan-out RunSpec after intake.toml landed.
# ---------------------------------------------------------------------------


def test_full_coverage_emits_no_alerts(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(
        tmp_path,
        {"schema": "ao2.factory-bridge.v1", "role_contracts": _full_coverage_block()},
    )
    payload = _payload({"factory_compat_bridge_evidence": str(bridge)})
    assert nightly.role_contracts_alerts(payload) == []


def test_default_expected_count_matches_canonical_runspec_size() -> None:
    """If intake.toml is the 17th role TOML and the canonical fan-out
    RunSpec resolves to 17 tasks, the default expected threshold must be
    17 — *not* 16. Locks against silent drift if a role is added without
    bumping the constant in lock-step.
    """
    assert nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT == 17


# ---------------------------------------------------------------------------
# Missing-roles: any non-empty list trips a single alert with preview.
# ---------------------------------------------------------------------------


def test_missing_roles_fires_alert_with_preview(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["missing_roles"] = ["planner-intake", "ghost-role"]
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_missing_roles"
    assert "2 role(s)" in alerts[0]["message"]
    assert "planner-intake" in alerts[0]["message"]
    assert "ghost-role" in alerts[0]["message"]


def test_missing_roles_preview_capped_at_five(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["missing_roles"] = [f"role-{n}" for n in range(8)]
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    # Count reflects all 8; preview only the first 5.
    assert "8 role(s)" in alerts[0]["message"]
    for keep in range(5):
        assert f"role-{keep}" in alerts[0]["message"]
    for drop in range(5, 8):
        assert f"role-{drop}" not in alerts[0]["message"]


# ---------------------------------------------------------------------------
# Loaded-count regression: even with no missing_roles, a drop below the
# expected threshold trips its own distinct alert (because AO2 may have
# silently stopped scanning agents/, not just failed individual lookups).
# ---------------------------------------------------------------------------


def test_loaded_count_below_threshold_fires_alert(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["loaded_count"] = 14
    block["missing_roles"] = []
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_loaded_count_regression"
    assert "loaded_count=14" in alerts[0]["message"]
    assert (
        f"threshold={nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT}"
        in alerts[0]["message"]
    )


def test_loaded_count_at_or_above_threshold_does_not_fire(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["loaded_count"] = nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT + 1
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    assert (
        nightly.role_contracts_alerts(
            _payload({"factory_compat_bridge_evidence": str(bridge)})
        )
        == []
    )


def test_payload_can_override_expected_threshold(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["loaded_count"] = nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    # Boost the threshold past the actual loaded_count — alert must fire
    # even though the static default would consider this run healthy.
    payload = _payload(
        {"factory_compat_bridge_evidence": str(bridge)},
        extras={
            "role_contracts_expected_loaded_count": (
                nightly.ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT + 5
            )
        },
    )
    alerts = nightly.role_contracts_alerts(payload)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_loaded_count_regression"


# ---------------------------------------------------------------------------
# Concurrent regressions: both alerts fire independently in a single run.
# ---------------------------------------------------------------------------


def test_concurrent_missing_and_regression_fire_both_alerts(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["loaded_count"] = 5
    block["missing_roles"] = ["planner-intake"]
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    names = {a["name"] for a in alerts}
    assert names == {
        "role_contracts_missing_roles",
        "role_contracts_loaded_count_regression",
    }


# ---------------------------------------------------------------------------
# Artifact pathology: unreadable / malformed / schema-drift / block-absent.
# ---------------------------------------------------------------------------


def test_unreadable_json_fires_alert(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(tmp_path, "not-json{")
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_artifact_unreadable"


def test_top_level_list_fires_malformed_alert(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(tmp_path, [1, 2, 3])
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_artifact_malformed"


def test_wrong_schema_fires_drift_alert(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v2-pretend",
            "role_contracts": _full_coverage_block(),
        },
    )
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_artifact_schema_drift"


def test_block_absent_fires_alert(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(tmp_path, {"schema": "ao2.factory-bridge.v1"})
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert len(alerts) == 1
    assert alerts[0]["name"] == "role_contracts_block_absent"


# ---------------------------------------------------------------------------
# Planning states: an unregistered artifact key OR a registered-but-not-yet-
# landed file must NOT fire any alerts. The nightly orchestrator may run
# before the bridge step lands the evidence; a transient absence is not
# itself a regression worth paging on.
# ---------------------------------------------------------------------------


def test_unregistered_artifact_key_is_silent(tmp_path: Path) -> None:
    assert nightly.role_contracts_alerts(_payload({})) == []


def test_registered_but_missing_file_is_silent(tmp_path: Path) -> None:
    not_yet_landed = tmp_path / "subdir" / "factory-compat-ao-operator-bridge-evidence.json"
    alerts = nightly.role_contracts_alerts(
        _payload({"factory_compat_bridge_evidence": str(not_yet_landed)})
    )
    assert alerts == []


# ---------------------------------------------------------------------------
# Notification + severity wiring: role-contracts alerts must propagate into
# build_notification_payload, count toward "failure" severity, and surface
# in the notification text.
# ---------------------------------------------------------------------------


def test_notification_payload_includes_role_contracts_alerts(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["missing_roles"] = ["ghost-role"]
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    notification = nightly.build_notification_payload(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert notification["severity"] == "failure"
    assert len(notification["role_contracts_alerts"]) == 1
    assert (
        notification["role_contracts_alerts"][0]["name"]
        == "role_contracts_missing_roles"
    )
    assert "role_contracts_alerts=1" in notification["text"]
    assert "role_contracts_missing_roles" in notification["text"]


def test_notification_payload_silent_on_full_coverage(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(
        tmp_path,
        {"schema": "ao2.factory-bridge.v1", "role_contracts": _full_coverage_block()},
    )
    notification = nightly.build_notification_payload(
        _payload({"factory_compat_bridge_evidence": str(bridge)})
    )
    assert notification["severity"] == "info"
    assert notification["role_contracts_alerts"] == []
    assert "role_contracts_alerts=0" in notification["text"]


# ---------------------------------------------------------------------------
# Markdown integration: ## Role Contracts Alerts section emits one bullet
# per alert and is omitted entirely when there are no alerts.
# ---------------------------------------------------------------------------


def test_markdown_renders_alerts_section_when_missing_roles(tmp_path: Path) -> None:
    block = _full_coverage_block()
    block["missing_roles"] = ["planner-intake"]
    bridge = _write_bridge_evidence(
        tmp_path, {"schema": "ao2.factory-bridge.v1", "role_contracts": block}
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(bridge)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts Alerts" in text
    assert "role_contracts_missing_roles" in text


def test_markdown_omits_alerts_section_on_full_coverage(tmp_path: Path) -> None:
    bridge = _write_bridge_evidence(
        tmp_path,
        {"schema": "ao2.factory-bridge.v1", "role_contracts": _full_coverage_block()},
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(bridge)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "## Role Contracts Alerts" not in text
