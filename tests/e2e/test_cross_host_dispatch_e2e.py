"""v0.2 D7 live-gated cross-host dispatch test.

This test is intentionally skipped unless AO_LIVE_CROSS_HOST=1. When enabled,
it creates a temporary three-role profile that splits work across Ubuntu and
Mac host tags, runs AO Operator with --remote, and asserts the host-tagged
RunSpec plus final evidence artifact exist.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
PROFILE_NAME = "cross-host-dispatch-live"


def _live_cross_host_ready() -> tuple[bool, str]:
    if os.environ.get("AO_LIVE_CROSS_HOST", "").strip().lower() not in {"1", "true", "yes"}:
        return False, "AO_LIVE_CROSS_HOST is not set; cross-host live e2e gated off"
    if not os.environ.get("AO_HOME", "").strip():
        return False, "AO_HOME must point at the live coordinator state"
    return True, "cross-host live gate enabled"


def _write_live_profile(profile_path: Path) -> None:
    payload = {
        "profile": PROFILE_NAME,
        "schema": "ao-operator/profile/v1",
        "version": 1,
        "description": "Live cross-host D7 fixture: Ubuntu intake, Mac live provider, Ubuntu report writer.",
        "common_instructions": [
            "Return a STATUS block with Result, Artifact, Evidence, Concerns, and Blocker.",
            "Do not include secrets or full transcripts.",
        ],
        "roles": [
            {
                "id": "intake",
                "role": "Cross-host Intake",
                "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                "deps": [],
                "reads": ["task brief"],
                "writes": ["run-artifacts/<slug>/roles/intake.md"],
                "skills": ["skills/factory-intake/SKILL.md"],
                "instructions": [
                    "Summarize the brief and confirm the run is a cross-host dispatch check.",
                    "Record the declared host tag ubuntu in Evidence.",
                ],
                "host_tag": ["ubuntu"],
            },
            {
                "id": "live-provider",
                "role": "Mac Live Provider",
                "provider_key": "FACTORY_V3_INTEGRATOR_PROVIDER",
                "deps": ["intake"],
                "reads": ["run-artifacts/<slug>/roles/intake.md"],
                "writes": ["run-artifacts/<slug>/roles/live-provider.md"],
                "skills": ["skills/factory-intake/SKILL.md"],
                "instructions": [
                    "Confirm this role ran under the mac,live host-tag requirement.",
                    "Return DONE only if the current host is the live Mac worker or the AO dispatch evidence says the task was completed by the Mac worker.",
                ],
                "host_tag": ["mac", "live"],
            },
            {
                "id": "report-writer",
                "role": "Evidence Report Writer",
                "provider_key": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
                "deps": ["live-provider"],
                "reads": [
                    "run-artifacts/<slug>/roles/intake.md",
                    "run-artifacts/<slug>/roles/live-provider.md",
                ],
                "writes": ["docs/evidence/<slug>/evidence-report.md"],
                "skills": ["skills/factory-intake/SKILL.md", "skills/closure-verification/SKILL.md"],
                "instructions": [
                    "Write docs/evidence/<slug>/evidence-report.md.",
                    "Include the literal schema marker ao-operator/evidence-report/v1.",
                    "Include a line that says live-provider-host-tags: mac,live.",
                    "Return DONE only after the evidence report exists.",
                ],
                "host_tag": ["ubuntu"],
            },
        ],
    }
    profile_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _cleanup_slug(slug: str) -> None:
    for rel in (
        "docs/evidence",
        "run-artifacts",
        "docs/specs",
        "docs/plans",
        "docs/evaluations",
    ):
        parent = REPO_ROOT / rel
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if child.name.startswith(slug):
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)


@pytest.mark.live_providers
def test_cross_host_dispatch_e2e(tmp_path: Path) -> None:
    ready, reason = _live_cross_host_ready()
    if not ready:
        pytest.skip(reason)

    slug = "factoryv3-cross-host-d7-live"
    profile_path = REPO_ROOT / "profiles" / f"{PROFILE_NAME}.json"
    brief_path = tmp_path / "cross-host-brief.md"
    brief_path.write_text(
        "Produce a v0.2 cross-host dispatch smoke evidence artifact. "
        "Scope: intake and report writing stay on Ubuntu; "
        "the live-provider role must run on the Mac worker tagged mac,live.\n",
        encoding="utf-8",
    )

    _cleanup_slug(slug)
    try:
        _write_live_profile(profile_path)
        cmd = [
            PYTHON,
            "scripts/factory_run.py",
            "--brief",
            str(brief_path),
            "--slug",
            slug,
            "--profile",
            PROFILE_NAME,
            "--run",
            "--remote",
            "--overwrite-artifacts",
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        assert proc.returncode == 0, (
            f"cross-host run failed\n--- stdout ---\n{proc.stdout[-4000:]}"
            f"\n--- stderr ---\n{proc.stderr[-4000:]}"
        )

        runspec = REPO_ROOT / "run-artifacts" / slug / f"{slug}.runspec.yaml"
        events = REPO_ROOT / "run-artifacts" / slug / f"{slug}-ao-events.md"
        report = REPO_ROOT / "docs" / "evidence" / slug / "evidence-report.md"

        runspec_text = runspec.read_text(encoding="utf-8")
        assert 'hostTags: ["ubuntu"]' in runspec_text
        assert 'hostTags: ["mac", "live"]' in runspec_text
        events_text = events.read_text(encoding="utf-8")
        assert "live-provider" in events_text
        assert "Result: BLOCKED" not in events_text
        assert "`uname -s` = `Linux`" not in events_text
        live_role = REPO_ROOT / "run-artifacts" / slug / "roles" / "live-provider.md"
        live_role_text = live_role.read_text(encoding="utf-8")
        assert "Result: BLOCKED" not in live_role_text
        assert "`uname -s` = `Linux`" not in live_role_text
        assert report.is_file(), f"missing evidence report at {report}"
        report_text = report.read_text(encoding="utf-8")
        assert "ao-operator/evidence-report/v1" in report_text
        assert "live-provider-host-tags: mac,live" in report_text
    finally:
        profile_path.unlink(missing_ok=True)
