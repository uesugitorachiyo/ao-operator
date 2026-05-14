#!/usr/bin/env python3
"""Run a deterministic larger-pile worker-pool canary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import factory_queue
import worker_pool

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TASKS = 6
DEFAULT_WORKERS = 3
LIVE_CONFIRMATION = "launch-live-providers"
AO_RUNTIME_DEFAULT = (ROOT / ".." / "ao-runtime").resolve()
MAX_STATUS_PREVIEW = 20


def compact_completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return output.strip()


def run_capture(command: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return completed.returncode, compact_completed_output(completed)


def _is_windows() -> bool:
    # Indirection so tests can flip the candidate-name branch without
    # patching os.name globally (which breaks pathlib on Linux Python).
    return os.name == "nt"


def ao_binary_provenance(env: dict[str, str] | None = None) -> dict[str, Any]:
    values = os.environ if env is None else env
    runtime_root = Path(values.get("FACTORY_V3_AO_RUNTIME_PATH", str(AO_RUNTIME_DEFAULT)))
    override = values.get("FACTORY_V3_AO_BIN") or values.get("AO_BIN")
    source = "FACTORY_V3_AO_BIN" if values.get("FACTORY_V3_AO_BIN") else "AO_BIN" if values.get("AO_BIN") else ""

    if override:
        ao_bin = Path(override)
    else:
        # F6e: on Windows the cargo-built binary is `ao.exe`; on POSIX
        # it is `ao`. Try the platform-native name first, then fall
        # through to PATH lookup which honours both.
        release_dir = runtime_root / "target" / "release"
        candidate_names = ("ao.exe", "ao") if _is_windows() else ("ao",)
        candidate = next(
            (release_dir / name for name in candidate_names if (release_dir / name).is_file()),
            release_dir / candidate_names[0],
        )
        if candidate.is_file():
            ao_bin = candidate
            source = "FACTORY_V3_AO_RUNTIME_PATH/default"
        else:
            found = shutil.which("ao")
            ao_bin = Path(found) if found else candidate
            source = "PATH" if found else "missing"

    exists = ao_bin.is_file()
    version = None
    version_error = None
    if exists:
        returncode, output = run_capture([str(ao_bin), "--version"])
        if returncode == 0:
            version = output
        else:
            version_error = output

    return {
        "path": str(ao_bin),
        "source": source,
        "exists": exists,
        "version": version,
        "version_error": version_error,
    }


def git_worktree_provenance(path: Path) -> dict[str, Any]:
    inside_code, inside = run_capture(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"])
    if inside_code != 0 or inside.strip() != "true":
        return {
            "path": str(path),
            "is_git_worktree": False,
            "head": None,
            "branch": None,
            "dirty": None,
            "dirty_entries": None,
            "status_preview": [],
        }

    _, head = run_capture(["git", "-C", str(path), "rev-parse", "--short", "HEAD"])
    _, branch = run_capture(["git", "-C", str(path), "branch", "--show-current"])
    status_code, status = run_capture(["git", "-C", str(path), "status", "--porcelain"])
    entries = status.splitlines() if status_code == 0 and status else []
    return {
        "path": str(path),
        "is_git_worktree": True,
        "head": head or None,
        "branch": branch or None,
        "dirty": bool(entries),
        "dirty_entries": len(entries),
        "status_preview": entries[:MAX_STATUS_PREVIEW],
    }


def runtime_provenance(env: dict[str, str] | None = None) -> dict[str, Any]:
    values = os.environ if env is None else env
    runtime_root = Path(values.get("FACTORY_V3_AO_RUNTIME_PATH", str(AO_RUNTIME_DEFAULT)))
    return {
        "ao_binary": ao_binary_provenance(values),
        "ao_runtime_worktree": git_worktree_provenance(runtime_root),
    }


def assert_live_runtime_allowed(provenance: dict[str, Any], *, allow_dirty_ao_runtime: bool = False) -> None:
    worktree = provenance.get("ao_runtime_worktree", {})
    if not isinstance(worktree, dict):
        return
    if worktree.get("dirty") is True and not allow_dirty_ao_runtime:
        raise ValueError(
            "live canary requires a clean AO runtime worktree; "
            "rerun with --allow-dirty-ao-runtime only for an explicitly non-baseline experiment "
            f"({worktree.get('path')} dirty_entries={worktree.get('dirty_entries')})"
        )


def write_canary_briefs(root: Path, count: int, *, execution_mode: str = "synthetic") -> list[Path]:
    briefs = root / "briefs"
    briefs.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(1, count + 1):
        path = briefs / f"pile-canary-{index:02d}.md"
        marker = f"docs/smoke/phase-3-live-pile-canary/pile-canary-{index:02d}.md"
        path.write_text(
            "\n".join(
                [
                    "# Worker Pile Canary",
                    "",
                    "Shape: refactor" if execution_mode == "live" else "Shape: greenfield",
                    "",
                    (
                        "Live provider queue-drain canary. Create exactly one marker file at "
                        f"`{marker}` with a single line: "
                        f"`Phase 3 live pile canary marker {index:02d}.`"
                        if execution_mode == "live"
                        else "Synthetic queue-drain canary. The runner is intentionally local and deterministic."
                    ),
                    "",
                    f"Scoped writes: {marker}" if execution_mode == "live" else "Scoped writes: none",
                    "Pinning suite: tests/test_worker_pool.py tests/test_worker_pile_canary.py"
                    if execution_mode == "live"
                    else "Verification: synthetic runner returns success.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def assert_canary_queue_empty(queue_root: Path) -> None:
    factory_queue.ensure_queue(queue_root)
    paths = factory_queue.queue_paths(queue_root)
    occupied = [
        path
        for state in factory_queue.QUEUE_DIRS
        for path in paths[state].iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    if occupied:
        raise FileExistsError(f"canary queue is not empty: {occupied[0]}")


def run_canary(
    *,
    tasks: int = DEFAULT_TASKS,
    workers: int = DEFAULT_WORKERS,
    queue_root: str | Path | None = None,
    execution_mode: str = "synthetic",
    workspace: str | Path | None = None,
    provider_env: str | Path | None = None,
    confirm_live: bool = False,
    allow_dirty_ao_runtime: bool = False,
    keep: bool = False,
) -> dict[str, Any]:
    if tasks <= 0:
        raise ValueError("--tasks must be greater than 0")
    if workers <= 0:
        raise ValueError("--workers must be greater than 0")
    if execution_mode not in {"synthetic", "live"}:
        raise ValueError("--mode must be synthetic or live")
    if execution_mode == "live" and not confirm_live:
        raise ValueError(f"--mode live requires --confirm-live {LIVE_CONFIRMATION!r}")
    provenance = runtime_provenance()
    if execution_mode == "live":
        assert_live_runtime_allowed(provenance, allow_dirty_ao_runtime=allow_dirty_ao_runtime)

    temp_root: Path | None = None
    if queue_root is None:
        temp_root = Path(tempfile.mkdtemp(prefix="ao-operator-pile-canary-"))
        queue_base = temp_root / "queue"
    else:
        queue_base = Path(queue_root)
        assert_canary_queue_empty(queue_base)

    work_root = temp_root or queue_base.parent
    briefs = write_canary_briefs(work_root, tasks, execution_mode=execution_mode)
    for index, brief in enumerate(briefs, start=1):
        factory_queue.enqueue(brief, root=queue_base, slug=f"pile-canary-{index:02d}")

    before = worker_pool.report_payload(queue_base, workers=workers)
    commands: list[list[str]] = []

    if execution_mode == "synthetic":
        def synthetic_runner(command: list[str]) -> int:
            commands.append(command)
            return 0

        results = worker_pool.run_foreground(
            queue_root=queue_base,
            workers=workers,
            runner=synthetic_runner,
            drain=True,
        )
    else:
        options = worker_pool.resolve_execution_options(mode="run")
        results = worker_pool.run_foreground(
            queue_root=queue_base,
            workers=workers,
            mode="run",
            workspace=Path.cwd() if workspace is None else workspace,
            provider_env=provider_env,
            runner=worker_pool.subprocess_runner,
            drain=True,
            isolate_workspace=options.isolate_workspace,
            promote_artifacts=options.promote_artifacts,
        )
    after = worker_pool.report_payload(queue_base, workers=workers)
    counts = after["counts"]
    verdict = (
        isinstance(counts, dict)
        and len(results) == tasks
        and (execution_mode == "live" or len(commands) == tasks)
        and counts == {"pending": 0, "in-flight": 0, "done": tasks, "failed": 0}
    )
    payload: dict[str, Any] = {
        "verdict": "PASS" if verdict else "FAIL",
        "execution_mode": execution_mode,
        "tasks": tasks,
        "workers": workers,
        "queue_root": str(queue_base),
        "processed": len(results),
        "commands": len(commands),
        "runtime_provenance": provenance,
        "before": before,
        "after": after,
        "kept": keep or queue_root is not None,
    }

    if temp_root is not None and not keep:
        shutil.rmtree(temp_root, ignore_errors=True)
        payload["queue_root"] = str(queue_base)
        payload["cleaned"] = True
    else:
        payload["cleaned"] = False
    return payload


def format_canary(payload: dict[str, Any]) -> str:
    after = payload["after"]
    counts = after["counts"] if isinstance(after, dict) else {}
    runtime = payload.get("runtime_provenance", {})
    ao_binary = runtime.get("ao_binary", {}) if isinstance(runtime, dict) else {}
    ao_worktree = runtime.get("ao_runtime_worktree", {}) if isinstance(runtime, dict) else {}
    return "\n".join(
        [
            f"verdict={payload['verdict']}",
            f"mode={payload['execution_mode']}",
            f"tasks={payload['tasks']} workers={payload['workers']} processed={payload['processed']}",
            f"ao_binary={ao_binary.get('path')} source={ao_binary.get('source')} version={ao_binary.get('version')}",
            (
                "ao_runtime "
                f"path={ao_worktree.get('path')} "
                f"head={ao_worktree.get('head')} "
                f"dirty={ao_worktree.get('dirty')} "
                f"dirty_entries={ao_worktree.get('dirty_entries')}"
            ),
            (
                "final_counts "
                f"pending={counts.get('pending')} "
                f"in-flight={counts.get('in-flight')} "
                f"done={counts.get('done')} "
                f"failed={counts.get('failed')}"
            ),
            f"queue_root={payload['queue_root']}",
            f"cleaned={payload['cleaned']}",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic worker-pile canary.")
    parser.add_argument("--tasks", type=int, default=DEFAULT_TASKS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--mode", choices=["synthetic", "live"], default="synthetic")
    parser.add_argument("--workspace", help="Factory workspace for live mode; defaults to current directory")
    parser.add_argument("--provider-env", help="Provider env file for live mode")
    parser.add_argument(
        "--confirm-live",
        help=f"Required for --mode live. Must equal {LIVE_CONFIRMATION!r}",
    )
    parser.add_argument(
        "--allow-dirty-ao-runtime",
        action="store_true",
        help="Allow --mode live to run when the configured AO runtime worktree is dirty",
    )
    parser.add_argument("--queue-root")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary queue after the canary")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = run_canary(
            tasks=args.tasks,
            workers=args.workers,
            queue_root=args.queue_root,
            execution_mode=args.mode,
            workspace=args.workspace,
            provider_env=args.provider_env,
            confirm_live=args.confirm_live == LIVE_CONFIRMATION,
            allow_dirty_ao_runtime=args.allow_dirty_ao_runtime,
            keep=args.keep,
        )
    except (FileExistsError, ValueError) as exc:
        print(f"worker_pile_canary.py: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else format_canary(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
