from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import factory_run


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "factory_run.py"


def _intake(slug: str = "gate-strict-test") -> factory_run.Intake:
    return factory_run.Intake(
        slug=slug,
        brief_path=REPO_ROOT / "README.md",
        brief="Need deterministic gate validation. Scoped Writes: scripts/gate_b.py",
        classification="MODERATE",
        shape="greenfield",
        blocked=False,
        blocker="greenfield gate satisfied",
        acceptance=["Gate B emits a report."],
        scoped_reads=["scripts/factory_run.py"],
        scoped_writes=["scripts/gate_b.py"],
    )


def _spec(path: Path) -> Path:
    path.write_text(
        """# gate-strict-test Spec

Classification: MODERATE
Shape: greenfield

## Acceptance Criteria

- Gate B emits a report.

## Negative Constraints

- Do not dispatch invalid contracts.

## Verification

- pytest tests/test_factory_run_gates.py

## Sensitive Fields

- repo paths

## Trigger Hints

- docs
""",
        encoding="utf-8",
    )
    return path


def test_factory_run_help_exposes_strict_gate_flags():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0
    assert "--gate-b-strict" in result.stdout
    assert "--gate-r-strict" in result.stdout


def test_run_gate_b_strict_writes_report(tmp_path: Path):
    paths = {
        "spec": _spec(tmp_path / "gate-strict-test-spec.md"),
        "status_dir": tmp_path / "status",
    }

    report = factory_run.run_gate_b_strict(
        intake=_intake(),
        paths=paths,
        profile_name="default",
        contract=None,
        partition_slices=[
            {
                "id": "slice-1",
                "reads": ["docs/specs/<slug>-spec.md"],
                "writes": ["scripts/gate_b.py"],
                "verification": ["pytest tests/test_factory_run_gates.py"],
                "merge_owner": "integrator",
                "rejoin_artifact": "run-artifacts/<slug>/roles/integrator.md",
            }
        ],
    )

    output = paths["status_dir"] / "gate-b.json"
    assert report["verdict"] == "PASS"
    assert report["partition"]["slice_count"] == 1
    assert output.is_file()
    assert "planner-intake" in output.read_text(encoding="utf-8")


def test_gate_b_profile_path_resolves_starter_profiles():
    path = factory_run.profile_path_for_gate("smoke-test")

    assert path is not None
    assert path.as_posix().endswith("profiles/starters/smoke-test.json")
