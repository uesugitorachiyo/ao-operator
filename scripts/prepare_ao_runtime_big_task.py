#!/usr/bin/env python3
"""Prepare a separated AO Operator -> ao-runtime big-task harness."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AO_RUNTIME_DEFAULT = (ROOT / ".." / "ao-runtime").resolve()
# F5 cross-platform: tempfile.gettempdir() returns /tmp on POSIX and
# %TEMP% on Windows so the same defaults work on Mac/Ubuntu/Windows.
_TMP = Path(tempfile.gettempdir())
DEFAULT_RUNNER_WORKTREE = _TMP / "ao-operator-ao-runtime-runner"
DEFAULT_TARGET_WORKTREE = _TMP / "ao-operator-ao-runtime-target"
DEFAULT_QUEUE_ROOT = _TMP / "ao-operator-ao-runtime-big-task-queue"
DEFAULT_TARGET_BRANCH = "ao-operator/ao-runtime-big-task-target"
DEFAULT_SLUG = "ao-runtime-artifact-pipeline-big-task"
DEFAULT_BRIEF = ROOT / "examples" / "ao-runtime-big-task" / "artifact-pipeline-brief.md"
ALL_CODEX_PROFILE = ROOT / "examples" / "provider-profiles" / "all-codex.env"


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def require_git_repo(path: Path) -> None:
    completed = run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"])
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise RuntimeError(f"not a git worktree: {path}")


def short_head(path: Path) -> str:
    completed = run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip())
    return completed.stdout.strip()


def branch_name(path: Path) -> str | None:
    completed = run(["git", "-C", str(path), "branch", "--show-current"])
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def status_entries(path: Path) -> list[str]:
    completed = run(["git", "-C", str(path), "status", "--porcelain"])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip())
    return completed.stdout.splitlines()


def git_path(path: Path, relative: str) -> Path:
    completed = run(["git", "-C", str(path), "rev-parse", "--git-path", relative])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip())
    return Path(completed.stdout.strip())


def ignore_factory_metadata(path: Path) -> None:
    exclude = git_path(path, "info/exclude")
    exclude.parent.mkdir(parents=True, exist_ok=True)
    body = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if ".ao-operator/" not in body.splitlines():
        exclude.write_text(body.rstrip() + "\n.ao-operator/\n", encoding="utf-8")


def branch_exists(source: Path, branch: str) -> bool:
    completed = run(["git", "-C", str(source), "rev-parse", "--verify", "--quiet", branch])
    return completed.returncode == 0


def ensure_runner_worktree(source: Path, runner: Path, ref: str) -> dict[str, Any]:
    if runner.exists():
        require_git_repo(runner)
        action = "reused"
    else:
        completed = run(["git", "-C", str(source), "worktree", "add", "--detach", str(runner), ref])
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip())
        action = "created"

    dirty = status_entries(runner)
    if dirty:
        raise RuntimeError(f"runner AO worktree must be clean: {runner} ({len(dirty)} dirty entries)")
    return {
        "path": str(runner),
        "action": action,
        "head": short_head(runner),
        "branch": branch_name(runner),
        "dirty_entries": len(dirty),
    }


def ensure_target_worktree(source: Path, target: Path, branch: str, ref: str) -> dict[str, Any]:
    if target.exists():
        require_git_repo(target)
        action = "reused"
    else:
        if branch_exists(source, branch):
            command = ["git", "-C", str(source), "worktree", "add", str(target), branch]
        else:
            command = ["git", "-C", str(source), "worktree", "add", "-b", branch, str(target), ref]
        completed = run(command)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip())
        action = "created"

    ignore_factory_metadata(target)
    dirty = status_entries(target)
    if dirty:
        raise RuntimeError(f"target AO worktree must start clean: {target} ({len(dirty)} dirty entries)")
    return {
        "path": str(target),
        "action": action,
        "head": short_head(target),
        "branch": branch_name(target),
        "dirty_entries": len(dirty),
    }


def write_target_provider_env(target: Path) -> Path:
    ignore_factory_metadata(target)
    destination = target / ".ao-operator" / "all-codex.env"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(ALL_CODEX_PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def build_runner(runner: Path) -> dict[str, Any]:
    completed = run(["cargo", "build", "--release"], cwd=runner)
    return {
        "command": ["cargo", "build", "--release"],
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def command_strings(
    *,
    runner: Path,
    target: Path,
    provider_env: Path,
    queue_root: Path,
    slug: str,
    brief: Path,
) -> dict[str, str]:
    ao_bin = runner / "target" / "release" / "ao"
    env_prefix = f"FACTORY_V3_AO_BIN={ao_bin}"
    common = (
        f"{env_prefix} python3 scripts/factory_run.py "
        f"--brief {brief} "
        f"--slug {slug} "
        f"--provider-env {provider_env} "
        f"--workspace {target} "
        "--overwrite-artifacts "
        "--scrub-root-context"
    )
    return {
        "build_runner": f"cd {runner} && cargo build --release",
        "show_providers": (
            f"python3 scripts/factory_run.py --show-providers "
            f"--provider-env {provider_env}"
        ),
        "dry_run": f"{common} --dry-run",
        "live_run": f"{common} --run",
        "enqueue": (
            f"python3 scripts/worker_pool.py --queue-root {queue_root} "
            f"enqueue {brief} --slug {slug}"
        ),
        "worker_pool_live_once": (
            f"{env_prefix} python3 scripts/worker_pool.py --queue-root {queue_root} "
            f"pool --workers 1 --foreground --once --mode run "
            f"--workspace {target} --provider-env {provider_env}"
        ),
    }


def prepare(
    *,
    source: Path = AO_RUNTIME_DEFAULT,
    runner: Path = DEFAULT_RUNNER_WORKTREE,
    target: Path = DEFAULT_TARGET_WORKTREE,
    target_branch: str = DEFAULT_TARGET_BRANCH,
    ref: str = "HEAD",
    queue_root: Path = DEFAULT_QUEUE_ROOT,
    slug: str = DEFAULT_SLUG,
    brief: Path = DEFAULT_BRIEF,
    build: bool = False,
) -> dict[str, Any]:
    require_git_repo(source)
    if not brief.is_file():
        raise FileNotFoundError(f"brief not found: {brief}")

    runner_info = ensure_runner_worktree(source, runner, ref)
    target_info = ensure_target_worktree(source, target, target_branch, ref)
    provider_env = write_target_provider_env(target)
    target_info["dirty_entries"] = len(status_entries(target))
    build_result = build_runner(runner) if build else None
    commands = command_strings(
        runner=runner,
        target=target,
        provider_env=provider_env,
        queue_root=queue_root,
        slug=slug,
        brief=brief,
    )
    return {
        "verdict": "PASS" if not build_result or build_result["returncode"] == 0 else "FAIL",
        "source": {
            "path": str(source),
            "head": short_head(source),
            "branch": branch_name(source),
            "dirty_entries": len(status_entries(source)),
        },
        "runner": runner_info,
        "target": target_info,
        "provider_env": str(provider_env),
        "brief": str(brief),
        "slug": slug,
        "queue_root": str(queue_root),
        "commands": commands,
        "build": build_result,
    }


def print_text(data: dict[str, Any]) -> None:
    print(f"verdict={data['verdict']}")
    print(f"source={data['source']['path']} head={data['source']['head']} dirty_entries={data['source']['dirty_entries']}")
    print(f"runner={data['runner']['path']} action={data['runner']['action']} head={data['runner']['head']}")
    print(f"target={data['target']['path']} action={data['target']['action']} branch={data['target']['branch']}")
    print(f"provider_env={data['provider_env']}")
    print(f"brief={data['brief']}")
    print("commands:")
    for name, command in data["commands"].items():
        print(f"  {name}: {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare AO Operator ao-runtime big-task harness.")
    parser.add_argument("--source", default=str(AO_RUNTIME_DEFAULT))
    parser.add_argument("--runner", default=str(DEFAULT_RUNNER_WORKTREE))
    parser.add_argument("--target", default=str(DEFAULT_TARGET_WORKTREE))
    parser.add_argument("--target-branch", default=DEFAULT_TARGET_BRANCH)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--queue-root", default=str(DEFAULT_QUEUE_ROOT))
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--brief", default=str(DEFAULT_BRIEF))
    parser.add_argument("--build-runner", action="store_true", help="Build the clean runner AO binary")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = prepare(
            source=Path(args.source),
            runner=Path(args.runner),
            target=Path(args.target),
            target_branch=args.target_branch,
            ref=args.ref,
            queue_root=Path(args.queue_root),
            slug=args.slug,
            brief=Path(args.brief),
            build=args.build_runner,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"prepare_ao_runtime_big_task.py: {exc}", flush=True)
        return 2
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_text(data)
    return 0 if data["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
