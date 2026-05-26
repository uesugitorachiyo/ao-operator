"""Tests for the native Windows validation rerun helper."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

import windows_validation_rerun as rerun


def test_pytest_command_targets_exact_windows_regressions() -> None:
    command = rerun.pytest_command("python", rerun.WINDOWS_VALIDATION_TESTS)

    assert command[:3] == ["python", "-m", "pytest"]
    assert command[-1] == "-q"
    assert command[3:-1] == [
        "tests/test_check_gate_delta_vs_main.py::test_run_gate_subprocess_returns_exit_code",
        "tests/test_check_gate_delta_vs_main.py::test_run_gate_chain_on_ref_without_worktree_runs_locally",
        "tests/test_check_gate_delta_vs_main.py::test_split_gate_command_preserves_windows_absolute_paths",
        "tests/test_check_gate_delta_vs_main.py::test_split_gate_command_strips_windows_quotes",
        "tests/test_factory_run_host_tag.py::test_runtime_capture_workspace_label_redacts_absolute_paths",
    ]


def test_execute_no_pull_writes_pass_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "ao-operator"
    repo_root.mkdir()
    calls: list[list[str]] = []

    def runner(command: Sequence[str], cwd: Path, timeout: int) -> rerun.CommandResult:
        assert cwd == repo_root
        assert timeout == 120
        calls.append(list(command))
        stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "--short"] else f"ok {repo_root}\n"
        return rerun.CommandResult(
            command=list(command),
            exit_code=0,
            stdout_tail=stdout,
            stderr_tail="",
            duration_seconds=0.1,
        )

    report, exit_code = rerun.execute(
        repo_root=repo_root,
        remote="origin",
        branch="main",
        no_pull=True,
        python="/opt/python/python.exe",
        output_dir=tmp_path / "status",
        timeout=120,
        runner=runner,
    )

    assert exit_code == 0
    assert report["status"] == "passed"
    assert report["pytest_exit_code"] == 0
    assert report["before_head"] == "abc123"
    assert report["after_head"] == "abc123"
    assert calls == [
        ["git", "rev-parse", "--short", "HEAD"],
        ["git", "rev-parse", "--short", "HEAD"],
        rerun.pytest_command("/opt/python/python.exe", rerun.WINDOWS_VALIDATION_TESTS),
    ]
    assert (tmp_path / "status" / "latest.json").exists()
    assert (tmp_path / "status" / "latest.md").exists()
    commands = report["commands"]
    assert isinstance(commands, list)
    assert commands[-1]["command"][0] == "<python-current>"
    assert "${FACTORY_V3_ROOT}" in commands[-1]["stdout_tail"]
    assert str(repo_root) not in commands[-1]["stdout_tail"]


@pytest.mark.parametrize("failed_step", ["fetch", "pull"])
def test_execute_git_sync_failure_stops_before_pytest(tmp_path: Path, failed_step: str) -> None:
    repo_root = tmp_path / "ao-operator"
    repo_root.mkdir()
    calls: list[list[str]] = []

    def runner(command: Sequence[str], cwd: Path, timeout: int) -> rerun.CommandResult:
        calls.append(list(command))
        if command[:3] == ["git", "rev-parse", "--short"]:
            return rerun.CommandResult(list(command), 0, "abc123\n", "", 0.1)
        if command[:3] == ["git", "fetch", "origin"] and failed_step == "fetch":
            return rerun.CommandResult(list(command), 23, "", "fetch failed", 0.1)
        if command[:4] == ["git", "pull", "--ff-only", "origin"] and failed_step == "pull":
            return rerun.CommandResult(list(command), 24, "", "pull failed", 0.1)
        return rerun.CommandResult(list(command), 0, "", "", 0.1)

    report, exit_code = rerun.execute(
        repo_root=repo_root,
        remote="origin",
        branch="main",
        no_pull=False,
        python="python",
        output_dir=tmp_path / "status",
        timeout=120,
        runner=runner,
    )

    assert report["status"] == "failed"
    assert report["pytest_exit_code"] == exit_code
    assert exit_code == (23 if failed_step == "fetch" else 24)
    assert not any("-m" in command and "pytest" in command for command in calls)


def test_execute_pytest_failure_returns_pytest_exit(tmp_path: Path) -> None:
    repo_root = tmp_path / "ao-operator"
    repo_root.mkdir()

    def runner(command: Sequence[str], cwd: Path, timeout: int) -> rerun.CommandResult:
        if command[:3] == ["git", "rev-parse", "--short"]:
            return rerun.CommandResult(list(command), 0, "abc123\n", "", 0.1)
        if "-m" in command and "pytest" in command:
            return rerun.CommandResult(list(command), 7, "", "pytest failed", 0.1)
        return rerun.CommandResult(list(command), 0, "", "", 0.1)

    report, exit_code = rerun.execute(
        repo_root=repo_root,
        remote="origin",
        branch="main",
        no_pull=True,
        python="python",
        output_dir=tmp_path / "status",
        timeout=120,
        runner=runner,
    )

    assert exit_code == 7
    assert report["status"] == "failed"
    assert report["pytest_exit_code"] == 7
