from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_evaluator_decision.py"


def readiness_bridge(status: str = "ready", blockers: list[str] | None = None) -> dict:
    blockers = blockers or []
    return {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-readiness-status",
        "status": status,
        "frontend_status": {
            "status": status,
            "release_version": "0.4.79",
            "release_tag": "v0.4.79",
            "gate_count": 8,
            "blocked_gate_count": len(blockers),
            "blocker_count": len(blockers),
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
            "next_action": "ao-operator evaluator-closer may review this readiness summary",
        },
        "readiness_snapshot": {
            "schema_version": "ao2.cp-release-readiness.v1",
            "status": status,
            "release": {"version": "0.4.79", "release_tag": "v0.4.79"},
            "blockers": blockers,
            "operator_decision": {
                "factory_v3_evaluator_closer_required": True,
                "control_plane_approves_release": False,
            },
        },
        "links": {
            "release_readiness_json": "http://127.0.0.1:8744/api/v1/release/readiness.json",
            "release_candidate_handoff_json": "http://127.0.0.1:8744/api/v1/release/handoff.json",
        },
        "trust_boundary": {"mode": "release_readiness_read_only"},
    }


def handoff_checklist(status: str = "ready_for_evaluator_closer") -> dict:
    blocked = status != "ready_for_evaluator_closer"
    return {
        "schema": "ao-operator/ao2-release-handoff-checklist/v1",
        "status": status,
        "release": {"version": "0.4.79", "release_tag": "v0.4.79"},
        "checks": [
            {
                "id": "provider_acceptance",
                "label": "Provider acceptance",
                "observed": "live_complete" if not blocked else "planned",
                "expected": "live_complete",
                "status": "passed" if not blocked else "blocked",
            }
        ],
        "blockers": [] if not blocked else ["provider_acceptance: expected live_complete, observed planned"],
        "operator_decision": {
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
        },
        "trust_boundary": {
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
    }


def support_bundle_status(
    status: str = "assembled",
    candidate_correlation: str = "matched",
    version: str = "0.4.79",
) -> dict:
    return {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-support-bundle-status",
        "frontend_status": {
            "status": status,
            "release_candidate_version": version,
            "release_tag": f"v{version}",
            "candidate_correlation": candidate_correlation,
            "required_artifact_count": 6,
            "missing_artifact_count": 0 if status == "assembled" else 1,
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "next_action": "ao-operator evaluator-closer reviews this assembled same-candidate bundle",
        },
        "support_bundle_snapshot": {
            "schema_version": "ao2.cp-release-support-bundle.v1",
            "release_assembly": {
                "schema_version": "ao2.cp-release-assembly.v1",
                "status": status,
                "release_candidate_version": version,
                "release_tag": f"v{version}",
                "candidate_correlation": candidate_correlation,
                "required_artifacts": [
                    {"id": "release_publication", "status": "observed"},
                    {"id": "phase1_checklist", "status": "observed"},
                    {"id": "phase1_decision", "status": "observed"},
                    {"id": "three_os_smoke", "status": "observed"},
                    {
                        "id": "provider_acceptance_codex",
                        "status": "observed",
                        "release_candidate_version": version,
                    },
                    {
                        "id": "provider_acceptance_claude",
                        "status": "observed",
                        "release_candidate_version": version,
                    },
                ],
                "release_acceptance_owner": "ao-operator evaluator-closer",
                "control_plane_approves_release": False,
            },
        },
        "trust_boundary": {"mode": "release_support_bundle_read_only"},
    }


def run_decision(
    tmp_path: Path,
    readiness: dict,
    checklist: dict,
    support_bundle: dict | None = None,
) -> tuple[dict, str]:
    readiness_path = tmp_path / "release-readiness-status.json"
    checklist_path = tmp_path / "release-handoff-checklist.json"
    support_path = tmp_path / "release-support-bundle-status.json"
    json_path = tmp_path / "release-evaluator-decision.json"
    md_path = tmp_path / "release-evaluator-decision.md"
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
    checklist_path.write_text(json.dumps(checklist), encoding="utf-8")
    support_path.write_text(json.dumps(support_bundle or support_bundle_status()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--readiness",
            str(readiness_path),
            "--handoff-checklist",
            str(checklist_path),
            "--support-bundle-status",
            str(support_path),
            "--write-json",
            str(json_path),
            "--write-md",
            str(md_path),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    return payload, md_path.read_text(encoding="utf-8")


def test_release_evaluator_decision_accepts_clean_readiness_and_handoff(tmp_path: Path) -> None:
    payload, markdown = run_decision(tmp_path, readiness_bridge(), handoff_checklist())

    assert payload["schema"] == "ao-operator/ao2-release-evaluator-decision/v1"
    assert payload["status"] == "accepted"
    assert payload["decision"] == "accept_phase1_release_candidate"
    assert payload["release"]["release_tag"] == "v0.4.79"
    assert payload["blockers"] == []
    assert payload["trust_boundary"]["control_plane_approves_release"] is False
    assert payload["trust_boundary"]["release_acceptance_owner"] == "ao-operator evaluator-closer"
    assert payload["evidence"]["release_readiness_status"] == str(
        tmp_path / "release-readiness-status.json"
    )
    assert payload["evidence"]["release_support_bundle_status"] == str(
        tmp_path / "release-support-bundle-status.json"
    )
    assert any(check["id"] == "release_assembly_status" for check in payload["checks"])
    assert "AO2 Release Evaluator Decision" in markdown
    assert "accept_phase1_release_candidate" in markdown


def test_release_evaluator_decision_rejects_readiness_blockers(tmp_path: Path) -> None:
    payload, markdown = run_decision(
        tmp_path,
        readiness_bridge(status="blocked", blockers=["provider acceptance is missing"]),
        handoff_checklist(),
    )

    assert payload["status"] == "rejected"
    assert payload["decision"] == "reject_phase1_release_candidate"
    assert any("readiness_status" in blocker for blocker in payload["blockers"])
    assert any("provider acceptance is missing" in blocker for blocker in payload["blockers"])
    assert "reject_phase1_release_candidate" in markdown


def test_release_evaluator_decision_accepts_preexisting_self_reference_gap(
    tmp_path: Path,
) -> None:
    readiness = readiness_bridge(
        status="attention",
        blockers=[
            "release_evaluator_decision: expected accepted, observed missing",
            "candidate_correlation: expected matched, observed mismatched",
        ],
    )
    checklist = handoff_checklist()
    checklist["status"] = "blocked"
    checklist["blockers"] = ["handoff_status: expected ready, observed attention"]
    support = support_bundle_status(status="attention", candidate_correlation="mismatched")
    support["frontend_status"]["missing_artifact_count"] = 0
    assembly = support["support_bundle_snapshot"]["release_assembly"]
    assembly["missing_artifact_count"] = 0
    assembly["candidate_correlation_detail"] = {
        "blockers": [
            "release_evaluator_version unknown does not match release_version 0.4.79",
            "release_evaluator_tag unknown does not match release_tag v0.4.79",
        ],
        "claude_acceptance_version": "0.4.79",
        "codex_acceptance_version": "0.4.79",
        "release_evaluator_tag": "unknown",
        "release_evaluator_version": "unknown",
        "release_tag": "v0.4.79",
        "release_version": "0.4.79",
        "status": "mismatched",
        "three_os_version": "0.4.79",
    }

    payload, markdown = run_decision(tmp_path, readiness, checklist, support)

    assert payload["status"] == "accepted"
    assert payload["decision"] == "accept_phase1_release_candidate"
    assert payload["blockers"] == []
    assert payload["self_reference_exception"]["status"] == "applied"
    assert "self_reference_exception" in markdown


def test_release_evaluator_decision_rejects_unassembled_support_bundle(tmp_path: Path) -> None:
    payload, markdown = run_decision(
        tmp_path,
        readiness_bridge(),
        handoff_checklist(),
        support_bundle_status(status="attention", candidate_correlation="mismatched"),
    )

    assert payload["status"] == "rejected"
    assert payload["decision"] == "reject_phase1_release_candidate"
    assert any("release_assembly_status" in blocker for blocker in payload["blockers"])
    assert any("release_assembly_candidate_correlation" in blocker for blocker in payload["blockers"])
    assert "release_support_bundle_status" in markdown
