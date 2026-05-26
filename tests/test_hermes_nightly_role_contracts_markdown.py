"""Tests for the role-contracts markdown section in
``hermes_nightly_ao2_advancement.write_markdown``.

The role-contracts block is owned by AO2 and emitted into the
``ao2.factory-bridge.v1`` evidence file at
``factory-compat-ao-operator-bridge-evidence.json``. This section
surfaces it to the operator's morning digest so the load-count and
missing-roles are visible without opening the JSON.

Trust boundary: this section is *read-only*. Factory-v3 must not
mutate the block — only render it. The same role_contracts_summary
envelope is independently surfaced by the ao-operator passthrough
script (``start_ao2_run_from_role_runspec.py``); this markdown is the
operator-facing view.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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


def _write_bridge_evidence(tmp_path: Path, payload: dict[str, Any]) -> Path:
    out = tmp_path / "factory-compat-ao-operator-bridge-evidence.json"
    out.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Happy path: a fully-populated role_contracts block renders every field the
# operator needs to triage. Mirrors a real AO2 bridge evidence file.
# ---------------------------------------------------------------------------


def test_markdown_renders_observed_role_contracts_section(tmp_path: Path) -> None:
    artifact = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "status": "mapping_resolved_dry_run",
            "role_contracts": {
                "owner": "ao2",
                "factory_v3_required_to_load": False,
                "loaded_count": 16,
                "missing_roles": [],
                "path": "/fake/agents",
            },
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "status: `observed`" in text
    assert "owner: `ao2`" in text
    assert "loaded_count: `16`" in text
    assert "factory_v3_required_to_load: `False`" in text
    assert "path: `/fake/agents`" in text
    assert "missing_role_count: `0`" in text
    # When there are no missing roles the preview must not be emitted.
    assert "missing_roles_preview" not in text


def test_markdown_surfaces_missing_roles_preview_when_some_unresolved(
    tmp_path: Path,
) -> None:
    artifact = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "role_contracts": {
                "owner": "ao2",
                "factory_v3_required_to_load": False,
                "loaded_count": 15,
                "missing_roles": [
                    "planner-intake",
                    "ghost-role",
                ],
                "path": "/fake/agents",
            },
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "missing_role_count: `2`" in text
    assert "missing_roles_preview: `planner-intake, ghost-role`" in text


def test_markdown_caps_missing_roles_preview_at_five(tmp_path: Path) -> None:
    artifact = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "role_contracts": {
                "owner": "ao2",
                "factory_v3_required_to_load": False,
                "loaded_count": 4,
                "missing_roles": [f"role-{n}" for n in range(8)],
                "path": "/fake/agents",
            },
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "missing_role_count: `8`" in text
    # The preview is capped at the first five.
    assert (
        "missing_roles_preview: `role-0, role-1, role-2, role-3, role-4`" in text
    )
    assert "role-5" not in text


# ---------------------------------------------------------------------------
# Trust boundary: AO2 may decline to emit the block at all. The section
# still renders so operators can see that the bridge ran but did not load
# role contracts.
# ---------------------------------------------------------------------------


def test_markdown_renders_absent_block_when_role_contracts_omitted(
    tmp_path: Path,
) -> None:
    artifact = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "status": "mapping_resolved_dry_run",
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "status: `absent`" in text
    # No role-contract fields surfaced because the block was not emitted.
    assert "owner: `ao2`" not in text
    assert "loaded_count" not in text
    assert "missing_role_count" not in text


# ---------------------------------------------------------------------------
# Robustness: the file may be present and unreadable, present and malformed,
# absent on disk, or its key may be missing from the artifacts dict entirely.
# ---------------------------------------------------------------------------


def test_markdown_renders_unreadable_artifact(tmp_path: Path) -> None:
    out = tmp_path / "factory-compat-ao-operator-bridge-evidence.json"
    out.write_text("not-json{", encoding="utf-8")
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(out)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "status: `unreadable`" in text


def test_markdown_renders_malformed_top_level_payload(tmp_path: Path) -> None:
    out = tmp_path / "factory-compat-ao-operator-bridge-evidence.json"
    out.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(out)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "status: `malformed`" in text


def test_markdown_renders_missing_when_artifact_file_not_yet_created(
    tmp_path: Path,
) -> None:
    md_path = tmp_path / "report.md"
    artifact_path = tmp_path / "nightly" / "factory-compat-ao-operator-bridge-evidence.json"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact_path)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    assert "status: `missing`" in text


def test_markdown_omits_section_when_artifact_key_missing(tmp_path: Path) -> None:
    md_path = tmp_path / "report.md"
    nightly.write_markdown(_payload({}), md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" not in text


# ---------------------------------------------------------------------------
# Integration: the section must come AFTER ## Cancel-Authority Dry-Run and
# BEFORE ## Phase 1 Promotion Checklist so morning-digest ordering matches
# the rest of the AO2 evidence flow (bridge → cancel → promotion).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Per-contract table: one row per *distinct* role_contract_ref name+sha in
# governed_run_plan.tasks. Numbered fan-outs collapse to the same row.
# ---------------------------------------------------------------------------


def _bridge_evidence_with_tasks(role_refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal ao2.factory-bridge.v1 payload with the given
    role_contract_ref objects attached one per synthetic task."""

    return {
        "schema": "ao2.factory-bridge.v1",
        "role_contracts": {
            "owner": "ao2",
            "factory_v3_required_to_load": False,
            "loaded_count": len({ref.get("name") for ref in role_refs}),
            "missing_roles": [],
            "path": "/fake/agents",
        },
        "governed_run_plan": {
            "tasks": [
                {"role_id": f"role-{idx}", "role_contract_ref": ref}
                for idx, ref in enumerate(role_refs)
            ],
        },
    }


def test_markdown_renders_per_contract_table_with_one_row_per_distinct_contract(
    tmp_path: Path,
) -> None:
    intake_ref = {
        "name": "intake",
        "sha256": "13b7f4c289dff6ad6190a3f460b79a220d0906ce45fa1f732e8ee9fb25fcbad1",
        "contract_status": "loaded",
        "path": "/fake/agents/intake.toml",
        "owner": "ao2",
    }
    implementer_ref = {
        "name": "implementer",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "contract_status": "loaded",
        "path": "/fake/agents/implementer.toml",
        "owner": "ao2",
    }
    artifact = _write_bridge_evidence(
        tmp_path,
        _bridge_evidence_with_tasks(
            # Same implementer ref appears 6 times (numbered fan-out);
            # the table must collapse all 6 to a single row.
            [intake_ref] + [implementer_ref] * 6
        ),
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "### Loaded contracts" in text
    assert "| contract | status | sha256 | path |" in text
    # Both contracts present, exactly once each.
    assert text.count("| `intake` |") == 1
    assert text.count("| `implementer` |") == 1
    # sha256 truncated to first 12 chars + ellipsis.
    assert "`13b7f4c289df…`" in text
    assert "`aaaaaaaaaaaa…`" in text
    # Path rendered as basename only.
    assert "`intake.toml`" in text
    assert "`implementer.toml`" in text


def test_markdown_table_rows_sorted_alphabetically_by_contract_name(
    tmp_path: Path,
) -> None:
    refs = [
        {
            "name": name,
            "sha256": "0" * 64,
            "contract_status": "loaded",
            "path": f"/fake/agents/{name}.toml",
            "owner": "ao2",
        }
        for name in ("reviewer", "intake", "planner")
    ]
    artifact = _write_bridge_evidence(
        tmp_path, _bridge_evidence_with_tasks(refs)
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    intake_idx = text.index("| `intake` |")
    planner_idx = text.index("| `planner` |")
    reviewer_idx = text.index("| `reviewer` |")
    assert intake_idx < planner_idx < reviewer_idx


def test_markdown_omits_table_when_no_tasks_carry_role_contract_refs(
    tmp_path: Path,
) -> None:
    artifact = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "role_contracts": {
                "owner": "ao2",
                "factory_v3_required_to_load": False,
                "loaded_count": 0,
                "missing_roles": [],
                "path": "/fake/agents",
            },
            "governed_run_plan": {"tasks": []},
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "## Role Contracts" in text
    # No table when no contracts loaded.
    assert "### Loaded contracts" not in text
    assert "| contract | status |" not in text


def test_markdown_table_tolerates_refs_missing_name_or_sha(tmp_path: Path) -> None:
    """Defensive: skip rows that don't carry both name and sha — don't
    crash the report. Real AO2 evidence always carries both, but a
    malformed bridge could omit one."""
    refs = [
        {"name": "intake", "sha256": "deadbeef" * 8, "contract_status": "loaded", "path": "/fake/agents/intake.toml"},
        {"name": "", "sha256": "feedface" * 8},  # missing name → skip
        {"name": "implementer"},  # missing sha → skip
    ]
    artifact = _write_bridge_evidence(
        tmp_path, _bridge_evidence_with_tasks(refs)
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload({"factory_compat_bridge_evidence": str(artifact)}), md_path
    )
    text = md_path.read_text(encoding="utf-8")
    assert "### Loaded contracts" in text
    assert text.count("| `intake` |") == 1
    assert text.count("| `implementer` |") == 0
    # Row count: header + separator + 1 data row = 3 pipe-prefixed lines.
    assert sum(1 for line in text.splitlines() if line.startswith("|")) == 3


def test_role_contracts_section_renders_between_cancel_and_checklist(
    tmp_path: Path,
) -> None:
    cancel_path = tmp_path / "cancel-authority-dry-run.json"
    cancel_path.write_text(
        json.dumps(
            {
                "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
                "status": "planned",
                "mode": "auto",
                "weekday_configured": 1,
            }
        ),
        encoding="utf-8",
    )
    bridge_path = _write_bridge_evidence(
        tmp_path,
        {
            "schema": "ao2.factory-bridge.v1",
            "role_contracts": {
                "owner": "ao2",
                "factory_v3_required_to_load": False,
                "loaded_count": 16,
                "missing_roles": [],
                "path": "/fake/agents",
            },
        },
    )
    md_path = tmp_path / "report.md"
    nightly.write_markdown(
        _payload(
            {
                "cancel_authority_dry_run": str(cancel_path),
                "factory_compat_bridge_evidence": str(bridge_path),
                # An empty path entry must not invent a Phase 1 Promotion
                # Checklist section; only the headers we care about should
                # appear in the rendered markdown.
            }
        ),
        md_path,
    )
    text = md_path.read_text(encoding="utf-8")
    cancel_idx = text.index("## Cancel-Authority Dry-Run")
    role_idx = text.index("## Role Contracts")
    assert cancel_idx < role_idx, (
        "## Role Contracts must render after ## Cancel-Authority Dry-Run"
    )
