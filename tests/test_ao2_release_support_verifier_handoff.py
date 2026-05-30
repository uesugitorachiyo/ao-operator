from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_support_verifier_handoff.py"


def verifier_payload(**overrides: object) -> dict:
    payload = {
        "status": "passed",
        "checksum_verified": True,
        "bundle_sha256": "a" * 64,
        "surface_count": 6,
        "failures": [],
        "control_plane_role": "read_only_observer",
        "release_acceptance_owner": "ao-operator evaluator-closer",
        "mutates_ao_artifacts": False,
        "control_plane_approves_release": False,
    }
    payload.update(overrides)
    return payload


def manifest_payload() -> dict:
    return {
        "schema_version": "ao2.cp-release-support-bundle-manifest.v1",
        "status": "passed",
        "verifier_output_schema_sample": {
            "schema_version": "ao2.cp-release-support-bundle-verifier-output-sample.v1",
            "status": "passed",
            "checksum_verified": True,
            "bundle_sha256": "<64 lowercase sha256 hex from ao2.cp-release-support-bundle.v1 canonical JSON>",
            "surface_count": 6,
            "failures": [],
            "control_plane_role": "read_only_observer",
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
        },
    }


def run_handoff(
    tmp_path: Path,
    verifier: dict,
    manifest: dict | None = None,
    *,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    verifier_path = tmp_path / "verifier.json"
    json_path = tmp_path / "handoff.json"
    md_path = tmp_path / "handoff.md"
    verifier_path.write_text(json.dumps(verifier), encoding="utf-8")
    args = [
        sys.executable,
        str(SCRIPT),
        "--verifier-json",
        str(verifier_path),
        "--write-json",
        str(json_path),
        "--write-md",
        str(md_path),
        "--json",
    ]
    if manifest is not None:
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        args.extend(["--manifest-json", str(manifest_path)])
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )
    return result, json_path, md_path


def test_release_support_verifier_handoff_accepts_checksum_verified_output(
    tmp_path: Path,
) -> None:
    result, json_path, md_path = run_handoff(
        tmp_path, verifier_payload(), manifest_payload()
    )

    payload = json.loads(result.stdout)
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    assert payload["schema"] == "ao-operator/ao2-release-support-verifier-handoff/v1"
    assert payload["status"] == "ready_for_evaluator_closer"
    assert payload["verifier"]["checksum_verified"] is True
    assert payload["manifest"]["verifier_output_schema_sample"] == (
        "ao2.cp-release-support-bundle-verifier-output-sample.v1"
    )
    assert payload["operator_decision"]["factory_v3_evaluator_closer_required"] is True
    assert payload["operator_decision"]["control_plane_approves_release"] is False
    assert payload["blockers"] == []
    markdown = md_path.read_text(encoding="utf-8")
    assert "AO2 Release Support Verifier Handoff" in markdown
    assert "ao-operator evaluator-closer owns release acceptance" in markdown


def test_release_support_verifier_handoff_accepts_actual_control_plane_verifier_scope(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        {
            "status": "passed",
            "checksum_verified": True,
            "bundle_sha256": "b" * 64,
            "surface_count": 6,
            "failures": [],
            "trust_boundary": "read_only_observer",
            "control_plane_role": "read_only_observer",
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "verification_scope": "embedded support-bundle digest verification only; no AO2 artifact mutation and no release approval",
        },
        manifest_payload(),
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_evaluator_closer"
    assert payload["trust_boundary"]["mutates_ao_artifacts"] is False


def test_release_support_verifier_handoff_accepts_control_plane_handoff_endpoint(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        {
            "schema_version": "ao2.cp-release-support-verifier-handoff.v1",
            "status": "passed",
            "generated_from": "ao2.cp-release-support-bundle-verification.v1",
            "bundle_sha256": "c" * 64,
            "verification": {
                "schema_version": "ao2.cp-release-support-bundle-verification.v1",
                "status": "passed",
                "trust_boundary_status": "passed",
                "surface_count": 6,
                "blocker_count": 0,
            },
            "checks": [{"id": "release_publication", "status": "passed"}],
            "blockers": [],
            "control_plane_role": "read_only_observer",
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
            "safe_for_scheduler_indexing": True,
            "contains_bearer_token": False,
        },
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_evaluator_closer"
    assert payload["verifier"]["source_schema_version"] == (
        "ao2.cp-release-support-verifier-handoff.v1"
    )
    assert payload["verifier"]["checksum_verified"] is True
    assert payload["trust_boundary"]["source"] == "ao2-control-plane handoff endpoint"
    assert any(
        check["id"] == "control_plane_handoff_schema" and check["status"] == "passed"
        for check in payload["checks"]
    )


def test_release_support_verifier_handoff_blocks_control_plane_handoff_with_token(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        {
            "schema_version": "ao2.cp-release-support-verifier-handoff.v1",
            "status": "passed",
            "bundle_sha256": "d" * 64,
            "verification": {"status": "passed", "trust_boundary_status": "passed"},
            "checks": [],
            "blockers": [],
            "control_plane_role": "read_only_observer",
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
            "safe_for_scheduler_indexing": True,
            "contains_bearer_token": True,
        },
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert any("contains_bearer_token" in blocker for blocker in payload["blockers"])


def test_release_support_verifier_handoff_blocks_failed_checksum(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        verifier_payload(checksum_verified=False),
        manifest_payload(),
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert any("checksum_verified" in blocker for blocker in payload["blockers"])


def test_release_support_verifier_handoff_blocks_control_plane_approval(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        verifier_payload(control_plane_approves_release=True),
        manifest_payload(),
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert any("control_plane_approves_release" in blocker for blocker in payload["blockers"])


def test_release_support_verifier_handoff_blocks_secret_markers(
    tmp_path: Path,
) -> None:
    result, _, _ = run_handoff(
        tmp_path,
        verifier_payload(fetch_log="Authorization: " + "Bear" + "er should-not-be-in-evidence"),
        manifest_payload(),
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert any("secret_hygiene" in blocker for blocker in payload["blockers"])
