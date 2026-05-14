#!/usr/bin/env python3
"""AO Operator cross-task worker pool scaffold."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Union

import factory_queue
import factory_v3_config


ROOT = Path(__file__).resolve().parents[1]
# F5 cross-platform: tempfile.gettempdir() returns /tmp on POSIX and
# %TEMP% on Windows, so worker worktrees land in a writable per-user
# location regardless of host. POSIX paths unchanged.
WORKER_WORKTREE_ROOT = Path(tempfile.gettempdir()) / "ao-operator-worker-worktrees"
DEFAULT_STALE_INFLIGHT_SECONDS = 1800
DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS = 1800
MAX_PROVIDER_OUTPUT_TAIL_CHARS = 65536
PROVIDER_RATE_LIMIT_TELEMETRY = Path("telemetry/provider-rate-limits.jsonl")
CLAUDE_MEM_BLOCK_RE = re.compile(
    r"\n*<claude-mem-context>.*?</claude-mem-context>\n*",
    re.DOTALL,
)
PROVIDER_RATE_LIMIT_PATTERNS = (
    ("429", re.compile(r"\b429\b", re.IGNORECASE)),
    ("too_many_requests", re.compile(r"too many requests", re.IGNORECASE)),
    ("rate_limit", re.compile(r"rate[-_ ]?limit(?:ed| exceeded)?", re.IGNORECASE)),
    ("quota_exceeded", re.compile(r"quota exceeded", re.IGNORECASE)),
)


@dataclass(frozen=True)
class RunnerResult:
    returncode: int
    output: str = ""
    provider_rate_limit_signal: str | None = None


@dataclass(frozen=True)
class WorkerResult:
    task: factory_queue.QueueTask | None
    returncode: int
    destination: Path | None
    command: list[str]
    promoted_artifacts: list[Path] | None = None
    provider_rate_limited: bool = False


Runner = Callable[[list[str]], Union[int, RunnerResult]]


@dataclass(frozen=True)
class WorkerExecutionOptions:
    isolate_workspace: bool
    promote_artifacts: bool


def scrub_root_claude_mem_context(workspace: str | Path = ROOT) -> list[str]:
    """Remove claude-mem context blocks from repo-level instruction files.

    Live provider CLIs can append these blocks to AGENTS.md/CLAUDE.md as
    environmental context. The direct factory runner blocks on that pollution;
    queue workers scrub it between tasks so a successful task does not poison
    the next queued task.
    """
    root = Path(workspace)
    scrubbed: list[str] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "<claude-mem-context>" not in content:
            continue
        cleaned = CLAUDE_MEM_BLOCK_RE.sub("\n", content).rstrip() + "\n"
        if cleaned != content:
            path.write_text(cleaned, encoding="utf-8")
            scrubbed.append(name)
    return scrubbed


def desired_worker_count(
    *,
    queue_root: str | Path | None = None,
    max_workers: int | None = None,
    provider_rate_limit_floor: int | None = None,
) -> int:
    depth = factory_queue.queue_depth(queue_root)
    cap = factory_v3_config.MAX_WORKERS if max_workers is None else max_workers
    floor = cap if provider_rate_limit_floor is None else provider_rate_limit_floor
    return max(0, min(depth, cap, floor))


def adjusted_rate_limit_floor(current_floor: int, *, recent_429s: int, threshold: int = 1) -> int:
    if recent_429s < threshold:
        return current_floor
    return max(1, current_floor // 2)


def provider_rate_limit_signal(output: str) -> str | None:
    for signal, pattern in PROVIDER_RATE_LIMIT_PATTERNS:
        if pattern.search(output):
            return signal
    return None


def provider_rate_limit_events_path(queue_root: str | Path | None = None) -> Path:
    base = factory_queue.ensure_queue(queue_root)
    path = base / PROVIDER_RATE_LIMIT_TELEMETRY
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_provider_rate_limit_event(
    *,
    queue_root: str | Path | None = None,
    task_slug: str,
    signal: str,
    now: float | None = None,
) -> Path:
    path = provider_rate_limit_events_path(queue_root)
    payload = {
        "timestamp": time.time() if now is None else now,
        "task": task_slug,
        "signal": signal,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def recent_provider_rate_limits(
    *,
    queue_root: str | Path | None = None,
    window_seconds: int = DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
    now: float | None = None,
) -> int:
    if window_seconds <= 0:
        return 0
    path = provider_rate_limit_events_path(queue_root)
    if not path.is_file():
        return 0
    current = time.time() if now is None else now
    cutoff = current - window_seconds
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = event.get("timestamp")
        if isinstance(timestamp, (int, float)) and timestamp >= cutoff:
            count += 1
    return count


def recent_provider_rate_limit_events(
    *,
    queue_root: str | Path | None = None,
    window_seconds: int = DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
    limit: int = 5,
    now: float | None = None,
) -> list[dict[str, object]]:
    if window_seconds <= 0 or limit <= 0:
        return []
    path = provider_rate_limit_events_path(queue_root)
    if not path.is_file():
        return []
    current = time.time() if now is None else now
    cutoff = current - window_seconds
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = event.get("timestamp")
        task = event.get("task")
        signal = event.get("signal")
        if not isinstance(timestamp, (int, float)) or timestamp < cutoff:
            continue
        if not isinstance(task, str) or not isinstance(signal, str):
            continue
        events.append(
            {
                "timestamp": timestamp,
                "age_seconds": max(0, int(current - timestamp)),
                "task": task,
                "signal": signal,
            }
        )
    return sorted(events, key=lambda item: float(item["timestamp"]), reverse=True)[:limit]


def provider_rate_limit_floor(
    *,
    queue_root: str | Path | None = None,
    max_workers: int | None = None,
    window_seconds: int = DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
) -> int:
    cap = factory_v3_config.MAX_WORKERS if max_workers is None else max_workers
    recent_429s = recent_provider_rate_limits(queue_root=queue_root, window_seconds=window_seconds)
    return adjusted_rate_limit_floor(cap, recent_429s=recent_429s)


def recover_stale_if_enabled(
    *,
    queue_root: str | Path | None = None,
    stale_after_seconds: int | None = DEFAULT_STALE_INFLIGHT_SECONDS,
) -> list[factory_queue.QueueTask]:
    if stale_after_seconds is None or stale_after_seconds <= 0:
        return []
    return factory_queue.recover_stale_inflight(
        root=queue_root,
        stale_after_seconds=stale_after_seconds,
    )


def factory_script_for_workspace(workspace: str | Path = ROOT) -> Path:
    workspace_path = Path(workspace)
    candidate = workspace_path / "scripts" / "factory_run.py"
    return candidate if candidate.is_file() else ROOT / "scripts" / "factory_run.py"


def factory_run_command(
    task: factory_queue.QueueTask,
    *,
    mode: str = "dry-run",
    workspace: str | Path = ROOT,
    provider_env: str | Path | None = None,
    overwrite_artifacts: bool = True,
    scrub_root_context: bool = True,
) -> list[str]:
    if mode not in {"dry-run", "render-only", "run"}:
        raise ValueError(f"unsupported worker mode: {mode}")
    workspace_path = Path(workspace)
    command = [
        sys.executable,
        str(factory_script_for_workspace(workspace_path)),
        "--brief",
        str(task.path),
        "--slug",
        task.slug,
        f"--{mode}",
        "--workspace",
        str(workspace_path),
    ]
    if provider_env is not None:
        command.extend(["--provider-env", str(provider_env)])
    if overwrite_artifacts:
        command.append("--overwrite-artifacts")
    if scrub_root_context:
        command.append("--scrub-root-context")
    return command


def subprocess_runner(command: list[str]) -> RunnerResult:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output_tail: list[str] = []
    output_tail_chars = 0
    rate_limit_signal: str | None = None
    if process.stdout is not None:
        for line in process.stdout:
            print(line, end="")
            if rate_limit_signal is None:
                rate_limit_signal = provider_rate_limit_signal(line)
            output_tail.append(line)
            output_tail_chars += len(line)
            while output_tail_chars > MAX_PROVIDER_OUTPUT_TAIL_CHARS and output_tail:
                output_tail_chars -= len(output_tail.pop(0))
    return RunnerResult(
        returncode=process.wait(),
        output="".join(output_tail),
        provider_rate_limit_signal=rate_limit_signal,
    )


def normalize_runner_result(result: int | RunnerResult) -> RunnerResult:
    if isinstance(result, RunnerResult):
        return result
    return RunnerResult(returncode=result)


def resolve_execution_options(
    *,
    mode: str,
    isolated_workspace: bool = False,
    shared_workspace: bool = False,
    promote_artifacts: bool = False,
    no_promote_artifacts: bool = False,
) -> WorkerExecutionOptions:
    if mode not in {"dry-run", "render-only", "run"}:
        raise ValueError(f"unsupported worker mode: {mode}")
    if isolated_workspace and shared_workspace:
        raise ValueError("--isolated-workspace and --shared-workspace are mutually exclusive")
    if promote_artifacts and no_promote_artifacts:
        raise ValueError("--promote-artifacts and --no-promote-artifacts are mutually exclusive")

    isolate = mode == "run"
    if isolated_workspace:
        isolate = True
    if shared_workspace:
        isolate = False

    promote = mode == "run"
    if promote_artifacts:
        promote = True
    if no_promote_artifacts:
        promote = False

    return WorkerExecutionOptions(isolate_workspace=isolate, promote_artifacts=promote)


def prepare_task_workspace(
    task: factory_queue.QueueTask,
    *,
    workspace: str | Path = ROOT,
    isolate_workspace: bool = False,
    worktree_root: str | Path = WORKER_WORKTREE_ROOT,
) -> Path:
    base = Path(workspace).resolve()
    if not isolate_workspace:
        return base
    target = Path(worktree_root) / task.slug
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=base,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if target.exists():
            shutil.rmtree(target)
    result = subprocess.run(
        ["git", "worktree", "add", "--force", "--detach", str(target), "HEAD"],
        cwd=base,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git worktree add failed")
    return target


def task_artifact_relpaths(slug: str) -> list[Path]:
    return [
        Path("docs/specs") / f"{slug}-spec.md",
        Path("docs/plans") / f"{slug}-plan.md",
        Path("run-artifacts") / slug,
        Path("docs/evaluations") / f"{slug}-evaluation.md",
    ]


def promote_task_artifacts(
    slug: str,
    *,
    source_workspace: str | Path,
    target_workspace: str | Path = ROOT,
) -> list[Path]:
    source_root = Path(source_workspace).resolve()
    target_root = Path(target_workspace).resolve()
    if source_root == target_root:
        return []

    promoted: list[Path] = []
    for relpath in task_artifact_relpaths(slug):
        source = source_root / relpath
        if not source.exists():
            continue
        target = target_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        promoted.append(target)
    return promoted


def process_one(
    *,
    queue_root: str | Path | None = None,
    mode: str = "dry-run",
    workspace: str | Path = ROOT,
    provider_env: str | Path | None = None,
    runner: Runner = subprocess_runner,
    isolate_workspace: bool = False,
    promote_artifacts: bool = False,
    recover_stale_after_seconds: int | None = DEFAULT_STALE_INFLIGHT_SECONDS,
) -> WorkerResult:
    recover_stale_if_enabled(queue_root=queue_root, stale_after_seconds=recover_stale_after_seconds)
    task = factory_queue.claim_one(queue_root)
    if task is None:
        return WorkerResult(task=None, returncode=0, destination=None, command=[])

    task_workspace = prepare_task_workspace(task, workspace=workspace, isolate_workspace=isolate_workspace)
    scrub_root_claude_mem_context(task_workspace)
    command = factory_run_command(task, mode=mode, workspace=task_workspace, provider_env=provider_env)
    runner_result = normalize_runner_result(runner(command))
    returncode = runner_result.returncode
    rate_limit_signal = runner_result.provider_rate_limit_signal or provider_rate_limit_signal(runner_result.output)
    if rate_limit_signal is not None:
        record_provider_rate_limit_event(
            queue_root=queue_root,
            task_slug=task.slug,
            signal=rate_limit_signal,
        )
    promoted_artifacts: list[Path] = []
    if promote_artifacts:
        try:
            promoted_artifacts = promote_task_artifacts(
                task.slug,
                source_workspace=task_workspace,
                target_workspace=workspace,
            )
        except (OSError, shutil.Error):
            if returncode == 0:
                returncode = 1
    if returncode == 0:
        finished = factory_queue.mark_done(task, root=queue_root)
    else:
        finished = factory_queue.mark_failed(task, root=queue_root)
    return WorkerResult(
        task=task,
        returncode=returncode,
        destination=finished.path,
        command=command,
        promoted_artifacts=promoted_artifacts,
        provider_rate_limited=rate_limit_signal is not None,
    )


def process_batch(
    *,
    count: int,
    queue_root: str | Path | None = None,
    mode: str = "dry-run",
    workspace: str | Path = ROOT,
    provider_env: str | Path | None = None,
    runner: Runner = subprocess_runner,
    isolate_workspace: bool = False,
    promote_artifacts: bool = False,
    recover_stale_after_seconds: int | None = DEFAULT_STALE_INFLIGHT_SECONDS,
) -> list[WorkerResult]:
    if count <= 0:
        return []
    results: list[WorkerResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        futures = [
            executor.submit(
                process_one,
                queue_root=queue_root,
                mode=mode,
                workspace=workspace,
                provider_env=provider_env,
                runner=runner,
                isolate_workspace=isolate_workspace,
                promote_artifacts=promote_artifacts,
                recover_stale_after_seconds=recover_stale_after_seconds,
            )
            for _ in range(count)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result.task is not None:
                results.append(result)
    return results


def run_foreground(
    *,
    queue_root: str | Path | None = None,
    workers: int | None = None,
    mode: str = "dry-run",
    workspace: str | Path = ROOT,
    provider_env: str | Path | None = None,
    runner: Runner = subprocess_runner,
    drain: bool = True,
    isolate_workspace: bool = False,
    promote_artifacts: bool = False,
    recover_stale_after_seconds: int | None = DEFAULT_STALE_INFLIGHT_SECONDS,
) -> list[WorkerResult]:
    results: list[WorkerResult] = []
    while True:
        recover_stale_if_enabled(queue_root=queue_root, stale_after_seconds=recover_stale_after_seconds)
        floor = provider_rate_limit_floor(queue_root=queue_root, max_workers=workers)
        count = desired_worker_count(
            queue_root=queue_root,
            max_workers=workers,
            provider_rate_limit_floor=floor,
        )
        if count <= 0:
            break
        batch = process_batch(
            count=count,
            queue_root=queue_root,
            mode=mode,
            workspace=workspace,
            provider_env=provider_env,
            runner=runner,
            isolate_workspace=isolate_workspace,
            promote_artifacts=promote_artifacts,
            recover_stale_after_seconds=recover_stale_after_seconds,
        )
        if not batch:
            break
        results.extend(batch)
        if not drain:
            break
    return results


def status_payload(root: str | Path | None = None) -> dict[str, object]:
    base = factory_queue.ensure_queue(root)
    paths = factory_queue.queue_paths(base)
    recent_429s = recent_provider_rate_limits(queue_root=base)
    floor = adjusted_rate_limit_floor(factory_v3_config.MAX_WORKERS, recent_429s=recent_429s)
    counts = {
        name: len([path for path in paths[name].iterdir() if path.is_file() and not path.name.startswith(".")])
        for name in factory_queue.QUEUE_DIRS
    }
    return {
        "queue_root": str(base),
        "counts": counts,
        "desired_workers": desired_worker_count(queue_root=base, provider_rate_limit_floor=floor),
        "provider_rate_limits": {
            "window_seconds": DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
            "recent_429s": recent_429s,
            "provider_rate_limit_floor": floor,
        },
    }


def task_slugs_for_state(root: str | Path | None, state: str) -> list[str]:
    paths = factory_queue.queue_paths(factory_queue.ensure_queue(root))
    return [
        factory_queue.slug_from_task(path)
        for path in sorted(paths[state].iterdir())
        if path.is_file() and not path.name.startswith(".")
    ]


def in_flight_task_reports(
    root: str | Path | None = None,
    *,
    stale_after_seconds: int = DEFAULT_STALE_INFLIGHT_SECONDS,
    now: float | None = None,
) -> list[dict[str, object]]:
    paths = factory_queue.queue_paths(factory_queue.ensure_queue(root))
    current = time.time() if now is None else now
    reports: list[dict[str, object]] = []
    for path in sorted(paths["in-flight"].iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        age_seconds = max(0, int(current - path.stat().st_mtime))
        reports.append(
            {
                "slug": factory_queue.slug_from_task(path),
                "path": str(path),
                "age_seconds": age_seconds,
                "stale": stale_after_seconds > 0 and age_seconds >= stale_after_seconds,
            }
        )
    return reports


def suggested_queue_action(*, counts: dict[str, int], stale_count: int, suggested_workers: int) -> str:
    if stale_count > 0:
        return "recover-stale"
    if counts["pending"] > 0 and suggested_workers > 0:
        return "run-pool"
    if counts["failed"] > 0:
        return "inspect-failed"
    return "idle"


def report_payload(
    root: str | Path | None = None,
    *,
    workers: int | None = None,
    stale_after_seconds: int = DEFAULT_STALE_INFLIGHT_SECONDS,
    rate_window_seconds: int = DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
    now: float | None = None,
) -> dict[str, object]:
    base = factory_queue.ensure_queue(root)
    status = status_payload(base)
    counts = status["counts"]
    if not isinstance(counts, dict):
        raise TypeError("status counts must be a dictionary")
    recent_429s = recent_provider_rate_limits(
        queue_root=base,
        window_seconds=rate_window_seconds,
        now=now,
    )
    floor = adjusted_rate_limit_floor(
        factory_v3_config.MAX_WORKERS if workers is None else workers,
        recent_429s=recent_429s,
    )
    suggested_workers = desired_worker_count(
        queue_root=base,
        max_workers=workers,
        provider_rate_limit_floor=floor,
    )
    in_flight = in_flight_task_reports(
        base,
        stale_after_seconds=stale_after_seconds,
        now=now,
    )
    stale_count = len([task for task in in_flight if task["stale"]])
    action = suggested_queue_action(
        counts={name: int(counts[name]) for name in factory_queue.QUEUE_DIRS},
        stale_count=stale_count,
        suggested_workers=suggested_workers,
    )
    command_workers = max(1, suggested_workers)
    suggested_command = None
    if action in {"recover-stale", "run-pool"}:
        suggested_command = (
            f"{sys.executable} scripts/worker_pool.py --queue-root {base} "
            f"pool --workers {command_workers} --once"
        )
    elif action == "inspect-failed":
        suggested_command = f"ls {factory_queue.queue_paths(base)['failed']}"

    return {
        "queue_root": str(base),
        "counts": counts,
        "pending": task_slugs_for_state(base, "pending"),
        "in_flight": in_flight,
        "done": task_slugs_for_state(base, "done"),
        "failed": task_slugs_for_state(base, "failed"),
        "provider_rate_limits": {
            "window_seconds": rate_window_seconds,
            "recent_429s": recent_429s,
            "provider_rate_limit_floor": floor,
            "recent_events": recent_provider_rate_limit_events(
                queue_root=base,
                window_seconds=rate_window_seconds,
                now=now,
            ),
        },
        "stale_after_seconds": stale_after_seconds,
        "stale_in_flight": stale_count,
        "suggested_workers": suggested_workers,
        "suggested_action": action,
        "suggested_command": suggested_command,
    }


def format_report(payload: dict[str, object]) -> str:
    counts = payload["counts"]
    if not isinstance(counts, dict):
        raise TypeError("report counts must be a dictionary")
    provider = payload["provider_rate_limits"]
    if not isinstance(provider, dict):
        raise TypeError("provider rate limits must be a dictionary")
    lines = [
        f"queue_root={payload['queue_root']}",
        (
            "counts "
            f"pending={counts['pending']} "
            f"in-flight={counts['in-flight']} "
            f"done={counts['done']} "
            f"failed={counts['failed']}"
        ),
        (
            "provider_rate_limits "
            f"recent_429s={provider['recent_429s']} "
            f"floor={provider['provider_rate_limit_floor']} "
            f"window_seconds={provider['window_seconds']}"
        ),
        (
            "recommendation "
            f"action={payload['suggested_action']} "
            f"workers={payload['suggested_workers']} "
            f"stale_in_flight={payload['stale_in_flight']}"
        ),
    ]
    command = payload.get("suggested_command")
    if command:
        lines.append(f"command={command}")
    for key in ("pending", "failed", "done"):
        values = payload.get(key)
        if isinstance(values, list) and values:
            lines.append(f"{key}=" + ",".join(str(value) for value in values))
    in_flight = payload.get("in_flight")
    if isinstance(in_flight, list) and in_flight:
        rendered = [
            f"{item['slug']}:{item['age_seconds']}s:{'stale' if item['stale'] else 'fresh'}"
            for item in in_flight
            if isinstance(item, dict)
        ]
        lines.append("in_flight=" + ",".join(rendered))
    recent_events = provider.get("recent_events")
    if isinstance(recent_events, list) and recent_events:
        rendered_events = [
            f"{item['task']}:{item['signal']}:{item['age_seconds']}s"
            for item in recent_events
            if isinstance(item, dict)
        ]
        lines.append("recent_rate_limits=" + ",".join(rendered_events))
    return "\n".join(lines)


def normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    normalized = list(argv)
    for index, item in enumerate(list(normalized)):
        if item == "--queue-root" and index + 1 < len(normalized) and index > 0:
            value = normalized[index + 1]
            del normalized[index : index + 2]
            normalized[0:0] = ["--queue-root", value]
            break
    return normalized


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AO Operator worker pool")
    parser.add_argument("--queue-root", help="Queue root; defaults to FACTORY_V3_QUEUE_ROOT or /tmp/ao-operator-queue")
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue", help="Enqueue a brief")
    enqueue.add_argument("brief")
    enqueue.add_argument("--slug")
    enqueue.add_argument("--json", action="store_true")

    run_once = sub.add_parser("run-once", help="Claim and process one queued task")
    run_once.add_argument("--mode", choices=["dry-run", "render-only", "run"], default="dry-run")
    run_once.add_argument("--workspace", default=str(ROOT))
    run_once.add_argument("--provider-env")
    run_once.add_argument("--isolated-workspace", action="store_true", help="Run this task from a per-task git worktree")
    run_once.add_argument("--shared-workspace", action="store_true", help="Run this task directly in --workspace, even in live mode")
    run_once.add_argument("--promote-artifacts", action="store_true", help="Copy this task's Factory artifacts back to --workspace")
    run_once.add_argument("--no-promote-artifacts", action="store_true", help="Do not copy task artifacts back to --workspace")
    run_once.add_argument(
        "--recover-stale-after",
        type=int,
        default=DEFAULT_STALE_INFLIGHT_SECONDS,
        help="Move in-flight tasks older than this many seconds back to pending before claiming; <=0 disables recovery",
    )
    run_once.add_argument("--json", action="store_true")

    pool = sub.add_parser("pool", help="Process up to W queued tasks in the foreground")
    pool.add_argument("--workers", type=int)
    pool.add_argument("--foreground", action="store_true", help="Compatibility flag; pool currently runs in foreground")
    pool.add_argument("--once", action="store_true", help="Process only one worker-width batch instead of draining the queue")
    pool.add_argument("--mode", choices=["dry-run", "render-only", "run"], default="dry-run")
    pool.add_argument("--workspace", default=str(ROOT))
    pool.add_argument("--provider-env")
    pool.add_argument("--isolated-workspaces", action="store_true", help="Run each task from its own per-task git worktree")
    pool.add_argument("--shared-workspaces", action="store_true", help="Run tasks directly in --workspace, even in live mode")
    pool.add_argument("--promote-artifacts", action="store_true", help="Copy task Factory artifacts back to --workspace")
    pool.add_argument("--no-promote-artifacts", action="store_true", help="Do not copy task artifacts back to --workspace")
    pool.add_argument(
        "--recover-stale-after",
        type=int,
        default=DEFAULT_STALE_INFLIGHT_SECONDS,
        help="Move in-flight tasks older than this many seconds back to pending before sizing workers; <=0 disables recovery",
    )
    pool.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Print queue status")
    status.add_argument("--json", action="store_true")

    report = sub.add_parser("report", help="Print an operator queue report")
    report.add_argument("--workers", type=int)
    report.add_argument(
        "--recover-stale-after",
        type=int,
        default=DEFAULT_STALE_INFLIGHT_SECONDS,
        help="Mark in-flight tasks older than this many seconds as stale; <=0 disables stale marking",
    )
    report.add_argument(
        "--rate-window",
        type=int,
        default=DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
        help="Provider rate-limit telemetry window in seconds",
    )
    report.add_argument("--json", action="store_true")

    return parser.parse_args(normalize_argv(argv))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "enqueue":
        task = factory_queue.enqueue(args.brief, root=args.queue_root, slug=args.slug)
        payload = {"verdict": "ENQUEUED", "slug": task.slug, "path": str(task.path)}
        print(json.dumps(payload, indent=2) if args.json else f"enqueued {task.slug}: {task.path}")
        return 0

    if args.command == "run-once":
        try:
            options = resolve_execution_options(
                mode=args.mode,
                isolated_workspace=args.isolated_workspace,
                shared_workspace=args.shared_workspace,
                promote_artifacts=args.promote_artifacts,
                no_promote_artifacts=args.no_promote_artifacts,
            )
        except ValueError as exc:
            print(f"worker_pool.py: {exc}", file=sys.stderr)
            return 2
        result = process_one(
            queue_root=args.queue_root,
            mode=args.mode,
            workspace=args.workspace,
            provider_env=args.provider_env,
            runner=subprocess_runner,
            isolate_workspace=options.isolate_workspace,
            promote_artifacts=options.promote_artifacts,
            recover_stale_after_seconds=args.recover_stale_after,
        )
        payload = {
            "verdict": "EMPTY" if result.task is None else ("DONE" if result.returncode == 0 else "FAILED"),
            "task": result.task.slug if result.task else None,
            "returncode": result.returncode,
            "destination": str(result.destination) if result.destination else None,
            "command": result.command,
            "promoted_artifacts": [str(path) for path in result.promoted_artifacts or []],
            "provider_rate_limited": result.provider_rate_limited,
        }
        print(json.dumps(payload, indent=2) if args.json else payload["verdict"])
        return 0 if result.returncode == 0 else result.returncode

    if args.command == "pool":
        try:
            options = resolve_execution_options(
                mode=args.mode,
                isolated_workspace=args.isolated_workspaces,
                shared_workspace=args.shared_workspaces,
                promote_artifacts=args.promote_artifacts,
                no_promote_artifacts=args.no_promote_artifacts,
            )
        except ValueError as exc:
            print(f"worker_pool.py: {exc}", file=sys.stderr)
            return 2
        results = run_foreground(
            queue_root=args.queue_root,
            workers=args.workers,
            mode=args.mode,
            workspace=args.workspace,
            provider_env=args.provider_env,
            runner=subprocess_runner,
            drain=not args.once,
            isolate_workspace=options.isolate_workspace,
            promote_artifacts=options.promote_artifacts,
            recover_stale_after_seconds=args.recover_stale_after,
        )
        payload = {
            "verdict": "PASS" if all(result.returncode == 0 for result in results) else "FAIL",
            "processed": len(results),
            "results": [
                {
                    "task": result.task.slug if result.task else None,
                    "returncode": result.returncode,
                    "destination": str(result.destination) if result.destination else None,
                    "promoted_artifacts": [str(path) for path in result.promoted_artifacts or []],
                    "provider_rate_limited": result.provider_rate_limited,
                }
                for result in results
            ],
        }
        print(json.dumps(payload, indent=2) if args.json else f"processed={len(results)} verdict={payload['verdict']}")
        return 0 if payload["verdict"] == "PASS" else 1

    if args.command == "status":
        payload = status_payload(args.queue_root)
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "report":
        payload = report_payload(
            args.queue_root,
            workers=args.workers,
            stale_after_seconds=args.recover_stale_after,
            rate_window_seconds=args.rate_window,
        )
        print(json.dumps(payload, indent=2) if args.json else format_report(payload))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
