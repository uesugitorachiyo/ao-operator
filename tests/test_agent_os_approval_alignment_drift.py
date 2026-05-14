from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_alignment_drift


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def aligned_payload(schema: str) -> dict:
    return {
        "schema": schema,
        "provider_profile": ".env.example",
        "provider_profile_checked": True,
        "provider_profile_matches": True,
        "provider_mismatches": [],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def test_approval_alignment_drift_passes_when_artifacts_carry_provider_fields(tmp_path):
    write_json(
        tmp_path / "approval-validation.json",
        aligned_payload("ao-operator/agent-os-runspec-execution-approval-validation/v1"),
    )
    write_json(
        tmp_path / "execution-report.json",
        aligned_payload("ao-operator/agent-os-runspec-execution-report/v1"),
    )

    payload = check_agent_os_approval_alignment_drift.check_drift(
        root=tmp_path,
        artifact_paths=["approval-validation.json", "execution-report.json"],
    )

    assert payload["verdict"] == "PASS"
    assert payload["artifact_count"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_approval_alignment_drift_fails_when_provider_fields_are_missing(tmp_path):
    write_json(
        tmp_path / "approval-validation.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-validation/v1",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )

    payload = check_agent_os_approval_alignment_drift.check_drift(
        root=tmp_path,
        artifact_paths=["approval-validation.json"],
    )

    assert payload["verdict"] == "FAIL"
    assert "approval-validation.json missing provider_profile" in payload["errors"]
    assert "approval-validation.json provider_profile_checked must be true" in payload["errors"]
    assert "approval-validation.json provider_profile_matches must be true" in payload["errors"]
