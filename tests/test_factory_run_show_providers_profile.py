"""F-C regression: --show-providers must consult the active profile's task
list, not BASELINE_TASKS, when --profile is passed.

Surfaced by the Mac T5 live smoke (mac/v0.1.1-evidence-live-smoke.md §95):
operators inspecting `--show-providers --profile evidence` saw the
default-chain seven roles and assumed the profile flag was being ignored.
This test pins the expected output for the public profiles so the regression
cannot return silently.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _show(profile: str | None) -> str:
    cmd = [sys.executable, "scripts/factory_run.py", "--show-providers"]
    if profile is not None:
        cmd.extend(["--profile", profile])
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=30
    )
    assert proc.returncode == 0, (
        f"--show-providers --profile {profile!r} failed:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    return proc.stdout


def test_show_providers_no_flag_lists_default_chain():
    out = _show(None)
    assert "ao-operator providers:" in out
    assert "planner-intake" in out
    assert "implementer-slice" in out
    assert "evaluator-closer" in out
    assert "report-writer" not in out
    assert "secured-implementer" not in out


def test_show_providers_evidence_lists_six_evidence_roles():
    out = _show("evidence")
    assert "ao-operator providers (profile=evidence):" in out
    for rid in ("intake", "risk-scoper", "test-mapper",
                "evidence-collector", "qa-checklist", "report-writer"):
        assert rid in out, f"evidence role {rid!r} missing from --show-providers"
    assert "planner-intake" not in out
    assert "implementer-slice" not in out


def test_show_providers_default_explicit_matches_default_implicit():
    """Passing `--profile default` must behave the same as omitting --profile,
    because main() does not load the default profile JSON (preserving the
    legacy BASELINE_TASKS path)."""
    implicit = _show(None)
    explicit = _show("default")
    assert implicit == explicit


def test_show_providers_unknown_profile_exits_non_zero():
    """Unknown profile must fail before the show-providers branch even runs.
    Exit code 2 (loader error contract)."""
    proc = subprocess.run(
        [sys.executable, "scripts/factory_run.py", "--show-providers",
         "--profile", "not-a-real-profile"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=10,
    )
    assert proc.returncode == 2, (
        f"expected exit 2; got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "profile" in proc.stderr.lower()
