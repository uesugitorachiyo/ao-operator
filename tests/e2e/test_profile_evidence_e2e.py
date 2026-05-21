"""T9 e2e skeleton — `evidence` profile.

Dry-run (always on Ubuntu): verifies the profile-driven runner accepts
`--profile evidence`, dispatches the six evidence roles, materializes the
RunSpec, and exits with `verdict: DRY_RUN`. Does not exercise live
providers — that is the live-run test's job, gated behind
`FACTORY_V3_E2E_LIVE=1` + provider env keys.

Live-run (Mac only when gated on): verifies the `--run` path produces the
final artifact `docs/evidence/<slug>/evidence-report.md` matching schema
`ao-operator/evidence-report/v1`. This is the V2 closure criterion in
run-artifacts/release-v0.1.1/PLAN.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import live_providers_only, run_factory


EVIDENCE_ROLES = (
    "intake",
    "risk-scoper",
    "test-mapper",
    "evidence-collector",
    "qa-checklist",
    "report-writer",
)


def _parse_dry_run_stdout(stdout: str) -> dict:
    """The runner emits a single JSON object on dry-run. Find and parse it."""
    decoder = json.JSONDecoder()
    text = stdout
    idx = 0
    while idx < len(text):
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict) and obj.get("verdict") == "DRY_RUN":
            return obj
        idx = end
    raise AssertionError(
        f"no DRY_RUN JSON object found in factory_run stdout:\n{stdout!r}"
    )


def test_evidence_profile_dry_run_exits_clean(
    smoke_brief: Path, ao_home: Path, cleanup_smoke_artifacts: list[str], repo_root: Path
) -> None:
    """Skeleton check: `--profile evidence --dry-run` returns 0 and emits the
    DRY_RUN JSON envelope. Ubuntu-runnable; no live providers required."""
    slug = "factoryv3-smoke-e2e-evidence-dry"
    cleanup_smoke_artifacts.append(slug)

    proc = run_factory(
        slug=slug,
        profile="evidence",
        mode="dry-run",
        ao_home=ao_home,
        repo_root=repo_root,
    )
    assert proc.returncode == 0, (
        f"factory_run --profile evidence --dry-run failed:\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )

    summary = _parse_dry_run_stdout(proc.stdout)
    assert summary["slug"] == slug
    assert "runspec" in summary
    runspec_path = repo_root / summary["runspec"]
    assert runspec_path.is_file(), f"rendered RunSpec missing at {runspec_path}"


def test_evidence_profile_dry_run_dispatches_six_roles(
    smoke_brief: Path, ao_home: Path, cleanup_smoke_artifacts: list[str], repo_root: Path
) -> None:
    """The rendered RunSpec for the `evidence` profile must mention all six
    evidence-profile roles. Asserted as substring presence in the YAML so
    the test does not pin an exact YAML schema layout."""
    slug = "factoryv3-smoke-e2e-evidence-roles"
    cleanup_smoke_artifacts.append(slug)

    proc = run_factory(
        slug=slug,
        profile="evidence",
        mode="dry-run",
        ao_home=ao_home,
        repo_root=repo_root,
    )
    assert proc.returncode == 0, proc.stderr

    summary = _parse_dry_run_stdout(proc.stdout)
    runspec_text = (repo_root / summary["runspec"]).read_text(encoding="utf-8")
    for role_id in EVIDENCE_ROLES:
        assert role_id in runspec_text, (
            f"role {role_id!r} missing from rendered RunSpec; got:\n{runspec_text}"
        )


def test_unknown_profile_fails_with_exit_2(
    smoke_brief: Path, ao_home: Path, cleanup_smoke_artifacts: list[str], repo_root: Path
) -> None:
    """A bad `--profile` name must be rejected with exit 2 and a helpful
    error pointing the user at `--list-profiles` (loader contract)."""
    slug = "factoryv3-smoke-e2e-evidence-bad"
    cleanup_smoke_artifacts.append(slug)

    proc = run_factory(
        slug=slug,
        profile="not-a-real-profile",
        mode="dry-run",
        ao_home=ao_home,
        repo_root=repo_root,
    )
    assert proc.returncode == 2, (
        f"expected exit 2 for unknown profile; got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "profile" in proc.stderr.lower()


@live_providers_only
@pytest.mark.live_providers
def test_evidence_profile_live_run_produces_report(
    smoke_brief: Path, ao_home: Path, cleanup_smoke_artifacts: list[str], repo_root: Path
) -> None:
    """V2 closure check. Skipped unless FACTORY_V3_E2E_LIVE=1 and every
    FACTORY_V3_*_PROVIDER env is set. Mac lane runs this; Ubuntu CI does not."""
    slug = "factoryv3-smoke-e2e-evidence-live"
    cleanup_smoke_artifacts.append(slug)

    proc = run_factory(
        slug=slug,
        profile="evidence",
        mode="run",
        ao_home=ao_home,
        repo_root=repo_root,
        timeout=900,
    )
    assert proc.returncode == 0, (
        f"live evidence run failed:\n--- stderr ---\n{proc.stderr[-4000:]}"
    )
    report = repo_root / "docs" / "evidence" / slug / "evidence-report.md"
    assert report.is_file(), f"missing evidence report at {report}"
    body = report.read_text(encoding="utf-8")
    assert "ao-operator/evidence-report/v1" in body, (
        f"evidence report missing schema header in {report}"
    )
    assert f"slug: {slug}" in body, (
        f"evidence report missing slug field in {report}"
    )
