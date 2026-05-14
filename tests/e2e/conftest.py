"""Shared fixtures for the v0.1.1 T9 e2e profile test skeleton.

The skeleton runs `python3 scripts/factory_run.py` as a subprocess so the
end-to-end CLI surface (argparse + profile loader + dispatch + materialize)
is exercised exactly the way the Mac handoff prompts run it.

Two execution modes:

- **Dry-run** (always-on, Ubuntu and Mac): `--dry-run` exits without launching
  AO and emits a JSON line with `verdict: DRY_RUN` and the rendered RunSpec
  path. Verifies the runner accepts each profile, materializes the right
  artifacts, and produces a runspec without touching live providers.

- **Live-run** (Mac only, gated): `--run` actually dispatches against
  configured providers and produces the profile's final artifact (evidence-
  report.md or compliance-report.md). Gated behind `pytest.mark.live_providers`
  + the `FACTORY_V3_E2E_LIVE` env signal so Ubuntu CI cannot accidentally
  burn provider credits.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SMOKE_BRIEF = REPO_ROOT / "examples" / "complex-app-smoke" / "task-brief.md"

PROVIDER_ENV_KEYS = (
    "FACTORY_V3_PLANNER_PROVIDER",
    "FACTORY_V3_PLAN_HARDENER_PROVIDER",
    "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
    "FACTORY_V3_IMPLEMENTER_PROVIDER",
    "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
    "FACTORY_V3_INTEGRATOR_PROVIDER",
    "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
)


def pytest_configure(config) -> None:
    """Register the live_providers marker so pytest does not warn on it."""
    config.addinivalue_line(
        "markers",
        "live_providers: requires FACTORY_V3_E2E_LIVE=1 and every "
        "FACTORY_V3_*_PROVIDER env var; gated to skip on Ubuntu CI",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def smoke_brief() -> Path:
    if not SMOKE_BRIEF.is_file():
        pytest.skip(f"smoke brief not found at {SMOKE_BRIEF}; cannot run e2e profile tests")
    return SMOKE_BRIEF


@pytest.fixture
def ao_home(tmp_path: Path) -> Path:
    home = tmp_path / "ao-home"
    home.mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def cleanup_smoke_artifacts():
    """Yield, then remove generated docs/{evidence,compliance,specs,plans,evaluations,status}
    directories matching `factoryv3-smoke-*` for the slugs the test created.

    Even though those paths are gitignored, we clean them so a repeat test run
    is not poisoned by stale state from a prior run.
    """
    created_slugs: list[str] = []
    yield created_slugs
    for slug in created_slugs:
        for parent_rel in (
            "docs/evidence",
            "docs/compliance",
            "run-artifacts",
            "docs/specs",
            "docs/plans",
            "docs/evaluations",
        ):
            parent = REPO_ROOT / parent_rel
            if not parent.is_dir():
                continue
            for child in parent.iterdir():
                if child.name.startswith(slug):
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        try:
                            child.unlink()
                        except FileNotFoundError:
                            pass


def run_factory(
    *,
    slug: str,
    profile: str,
    mode: str,
    ao_home: Path,
    repo_root: Path = REPO_ROOT,
    extra_args: tuple[str, ...] = (),
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run scripts/factory_run.py against the smoke brief with the given profile.

    `mode` is one of "dry-run", "run", "render-only". The flag is passed
    verbatim. Returns the CompletedProcess; the caller asserts on returncode
    and parses stdout/stderr.
    """
    flag = "--" + mode
    cmd = [
        PYTHON,
        "scripts/factory_run.py",
        "--slug", slug,
        "--brief", str(SMOKE_BRIEF),
        flag,
        "--profile", profile,
        "--ao-home", str(ao_home),
        "--overwrite-artifacts",
        *extra_args,
    ]
    return subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def live_providers_ready() -> tuple[bool, str]:
    """Return (ready, reason). Ready iff the live-run gate signal is set
    AND every required FACTORY_V3_*_PROVIDER env var has a non-empty value.

    The signal is `FACTORY_V3_E2E_LIVE=1`. This prevents Ubuntu CI from
    accidentally invoking live providers when keys happen to be present.
    """
    if os.environ.get("FACTORY_V3_E2E_LIVE", "").strip() not in ("1", "true", "yes"):
        return False, "FACTORY_V3_E2E_LIVE is not set; live e2e gated off"
    missing = [k for k in PROVIDER_ENV_KEYS if not os.environ.get(k, "").strip()]
    if missing:
        return False, f"FACTORY_V3_*_PROVIDER not set for: {', '.join(missing)}"
    return True, "all live-provider preconditions met"


live_providers_only = pytest.mark.skipif(
    not live_providers_ready()[0],
    reason=live_providers_ready()[1],
)
