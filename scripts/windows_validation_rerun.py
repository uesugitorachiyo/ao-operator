#!/usr/bin/env python3
"""Pull and rerun the Windows portability validation slice.

This helper lets a native Windows operator sync the repo and rerun the exact
tests that previously caught Windows path handling regressions without copying
a long pytest command by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/windows-validation-rerun/v1"
DEFAULT_OUTPUT_DIR = Path("run-artifacts/windows-validation-rerun")
WINDOWS_VALIDATION_TESTS = (
    "tests/test_check_gate_delta_vs_main.py::test_run_gate_subprocess_returns_exit_code",
    "tests/test_check_gate_delta_vs_main.py::test_run_gate_chain_on_ref_without_worktree_runs_locally",
    "tests/test_check_gate_delta_vs_main.py::test_split_gate_command_preserves_windows_absolute_paths",
    "tests/test_check_gate_delta_vs_main.py::test_split_gate_command_strips_windows_quotes",
    "tests/test_factory_run_host_tag.py::test_runtime_capture_workspace_label_redacts_absolute_paths",
)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    exit_code: int
    stdout_tail: str
    stderr_tail: str
    duration_seconds: float


Runner = Callable[[Sequence[str], Path, int], CommandResult]


def redact_repo_root(value: str, repo_root: Path) -> str:
    return value.replace(str(repo_root.resolve()), "${FACTORY_V3_ROOT}")


def run_command(command: Sequence[str], cwd: Path, timeout: int) -> CommandResult:
    started = datetime.now(timezone.utc)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    return CommandResult(
        command=list(command),
        exit_code=completed.returncode,
        stdout_tail=(completed.stdout or "")[-4000:],
        stderr_tail=(completed.stderr or "")[-4000:],
        duration_seconds=round((finished - started).total_seconds(), 3),
    )


def run_git_text(command: Sequence[str], repo_root: Path, runner: Runner, timeout: int) -> tuple[str, CommandResult]:
    result = runner(command, repo_root, timeout)
    return result.stdout_tail.strip(), result


def pytest_command(python: str, tests: Sequence[str]) -> list[str]:
    return [python, "-m", "pytest", *tests, "-q"]


def build_report(
    *,
    repo_root: Path,
    remote: str,
    branch: str,
    no_pull: bool,
    python: str,
    command_results: list[CommandResult],
    before_head: str,
    after_head: str,
    pytest_exit_code: int,
) -> dict[str, object]:
    status = "passed" if pytest_exit_code == 0 and all(r.exit_code == 0 for r in command_results) else "failed"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "repo": "${FACTORY_V3_ROOT}",
        "remote": remote,
        "branch": branch,
        "no_pull": no_pull,
        "before_head": before_head,
        "after_head": after_head,
        "python": Path(python).name if python else "python",
        "tests": list(WINDOWS_VALIDATION_TESTS),
        "pytest_exit_code": pytest_exit_code,
        "commands": [
            {
                "command": ["<python-current>" if part == python else part for part in result.command],
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
                "stdout_tail": redact_repo_root(result.stdout_tail, repo_root),
                "stderr_tail": redact_repo_root(result.stderr_tail, repo_root),
            }
            for result in command_results
        ],
    }


def write_artifacts(report: dict[str, object], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    md_path = output_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    tests = report.get("tests") or []
    commands = report.get("commands") or []
    lines = [
        "# Windows Validation Rerun",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Before HEAD: `{report.get('before_head')}`",
        f"- After HEAD: `{report.get('after_head')}`",
        f"- Pytest exit code: `{report.get('pytest_exit_code')}`",
        f"- Pull skipped: `{report.get('no_pull')}`",
        "",
        "## Tests",
        "",
    ]
    lines.extend(f"- `{test}`" for test in tests)
    lines.extend(["", "## Commands", ""])
    for command in commands:
        if isinstance(command, dict):
            rendered = " ".join(str(part) for part in command.get("command", []))
            lines.append(f"- exit `{command.get('exit_code')}`: `{rendered}`")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def execute(
    *,
    repo_root: Path,
    remote: str,
    branch: str,
    no_pull: bool,
    python: str,
    output_dir: Path,
    timeout: int,
    runner: Runner = run_command,
) -> tuple[dict[str, object], int]:
    command_results: list[CommandResult] = []
    before_head, before_result = run_git_text(["git", "rev-parse", "--short", "HEAD"], repo_root, runner, timeout)
    command_results.append(before_result)

    if not no_pull:
        fetch_result = runner(["git", "fetch", remote], repo_root, timeout)
        command_results.append(fetch_result)
        if fetch_result.exit_code != 0:
            report = build_report(
                repo_root=repo_root,
                remote=remote,
                branch=branch,
                no_pull=no_pull,
                python=python,
                command_results=command_results,
                before_head=before_head,
                after_head=before_head,
                pytest_exit_code=fetch_result.exit_code,
            )
            write_artifacts(report, output_dir)
            return report, fetch_result.exit_code

        pull_result = runner(["git", "pull", "--ff-only", remote, branch], repo_root, timeout)
        command_results.append(pull_result)
        if pull_result.exit_code != 0:
            report = build_report(
                repo_root=repo_root,
                remote=remote,
                branch=branch,
                no_pull=no_pull,
                python=python,
                command_results=command_results,
                before_head=before_head,
                after_head=before_head,
                pytest_exit_code=pull_result.exit_code,
            )
            write_artifacts(report, output_dir)
            return report, pull_result.exit_code

    after_head, after_result = run_git_text(["git", "rev-parse", "--short", "HEAD"], repo_root, runner, timeout)
    command_results.append(after_result)

    pytest_result = runner(pytest_command(python, WINDOWS_VALIDATION_TESTS), repo_root, timeout)
    command_results.append(pytest_result)

    report = build_report(
        repo_root=repo_root,
        remote=remote,
        branch=branch,
        no_pull=no_pull,
        python=python,
        command_results=command_results,
        before_head=before_head,
        after_head=after_head,
        pytest_exit_code=pytest_result.exit_code,
    )
    write_artifacts(report, output_dir)
    return report, pytest_result.exit_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--python", default=os.environ.get("FACTORY_V3_PYTHON", sys.executable))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    repo_root = args.repo_root.resolve()
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    report, exit_code = execute(
        repo_root=repo_root,
        remote=args.remote,
        branch=args.branch,
        no_pull=args.no_pull,
        python=args.python,
        output_dir=output_dir,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"windows_validation_rerun={report['status']}")
        print(f"artifact_json={output_dir / 'latest.json'}")
        print(f"artifact_md={output_dir / 'latest.md'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
