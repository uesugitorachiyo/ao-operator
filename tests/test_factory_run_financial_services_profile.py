"""Shape tests for the financial-services DAG-A profile scaffold."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import factory_run

REPO_ROOT = Path(__file__).resolve().parents[1]


EXPECTED_DAG_A_IDS = [
    "intake",
    "fetch-filings",
    "fetch-transcripts",
    "model-update",
    "draft-note",
    "citation-audit",
    "compliance-redact",
    "supervisory-review",
    "publish-stage",
]

EXPECTED_KYC_IDS = [
    "intake",
    "doc-classify",
    "pii-extract",
    "pii-redact",
    "rules-grid-evaluate",
    "risk-score",
    "exception-route",
    "supervisory-review",
    "cif-stage",
]


def test_financial_services_namespaced_profile_loads():
    profile = factory_run._load_profile("financial-services:earnings-note")

    assert profile["profile"] == "financial-services:earnings-note"
    assert [role["id"] for role in profile["roles"]] == EXPECTED_DAG_A_IDS


def test_list_profiles_includes_financial_services_namespace():
    names = {entry["name"] for entry in factory_run._list_profiles()}

    assert "financial-services:earnings-note" in names
    assert "financial-services:kyc-document-triage" in names


def test_financial_services_profile_matches_dag_a_dependencies():
    profile = factory_run._load_profile("financial-services:earnings-note")
    by_id = profile["roles_by_id"]

    assert by_id["intake"]["deps"] == []
    assert by_id["fetch-filings"]["deps"] == ["intake"]
    assert by_id["fetch-transcripts"]["deps"] == ["fetch-filings"]
    assert by_id["model-update"]["deps"] == ["fetch-filings", "fetch-transcripts"]
    assert by_id["draft-note"]["deps"] == ["model-update"]
    assert by_id["citation-audit"]["deps"] == [
        "draft-note",
        "fetch-filings",
        "fetch-transcripts",
    ]
    assert by_id["compliance-redact"]["deps"] == ["citation-audit"]
    assert by_id["supervisory-review"]["deps"] == ["compliance-redact"]
    assert by_id["publish-stage"]["deps"] == ["supervisory-review"]


def test_financial_services_profile_has_cross_provider_host_tags_and_overlay_skills():
    profile = factory_run._load_profile("financial-services:earnings-note")
    by_id = profile["roles_by_id"]

    assert by_id["draft-note"]["host_tag"] == ["live-claude"]
    assert by_id["citation-audit"]["host_tag"] == ["live-codex"]
    assert "skills/citation-audit/SKILL.md" in by_id["citation-audit"]["skills"]
    assert "skills/compliance-redact/SKILL.md" in by_id["compliance-redact"]["skills"]


def test_financial_services_profile_preserves_replay_contract():
    profile = factory_run._load_profile("financial-services:earnings-note")
    tasks = factory_run._tasks_from_profile(profile)
    by_id = {task["id"]: task for task in tasks}

    publish = by_id["publish-stage"]
    assert publish["deterministic"] is True
    assert publish["replay_outputs"] == ["financial-services-earnings-note-dag-a-replay.json"]


def test_financial_services_kyc_profile_loads_with_expected_dag():
    profile = factory_run._load_profile("financial-services:kyc-document-triage")

    assert profile["profile"] == "financial-services:kyc-document-triage"
    assert [role["id"] for role in profile["roles"]] == EXPECTED_KYC_IDS


def test_financial_services_kyc_profile_pins_pii_roles_and_replay_contract():
    profile = factory_run._load_profile("financial-services:kyc-document-triage")
    by_id = profile["roles_by_id"]
    tasks = factory_run._tasks_from_profile(profile)
    tasks_by_id = {task["id"]: task for task in tasks}

    assert by_id["pii-extract"]["host_tag"] == ["pii-tagged"]
    assert by_id["pii-redact"]["host_tag"] == ["pii-tagged"]
    assert by_id["supervisory-review"]["deps"] == ["exception-route"]
    assert tasks_by_id["cif-stage"]["deterministic"] is True
    assert tasks_by_id["cif-stage"]["replay_outputs"] == ["kyc-document-triage-replay.json"]


def test_financial_services_live_run_points_to_standalone_profile():
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/factory_run.py",
            "--brief",
            "run-artifacts/financial-services-mvp/sec-edgar-demo-fixture.md",
            "--slug",
            "financial-services-live-handoff",
            "--profile",
            "financial-services:earnings-note",
            "--run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert proc.returncode == 2
    assert "fsp run earnings-note --engine ao" in proc.stderr
    assert "run-artifacts/financial-services-profile-v0.3-standalone.md" in proc.stderr
