from __future__ import annotations

import os
import threading
import time

import factory_queue
import factory_v3_config
import worker_pool


def _brief(tmp_path, name: str = "brief.md"):
    path = tmp_path / name
    path.write_text("# Brief\n\nShape: greenfield\n", encoding="utf-8")
    return path


def test_desired_worker_count_is_zero_when_queue_empty(tmp_path):
    assert worker_pool.desired_worker_count(queue_root=tmp_path / "queue", max_workers=4) == 0


def test_desired_worker_count_ramps_to_max_workers(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(5):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 4)

    assert worker_pool.desired_worker_count(queue_root=root) == 4


def test_desired_worker_count_respects_provider_rate_limit_floor(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(5):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")

    assert worker_pool.desired_worker_count(
        queue_root=root,
        max_workers=4,
        provider_rate_limit_floor=2,
    ) == 2


def test_recover_stale_if_enabled_can_be_disabled(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="stale-disabled")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))

    recovered = worker_pool.recover_stale_if_enabled(queue_root=root, stale_after_seconds=0)

    assert recovered == []
    assert task.path.is_file()
    assert factory_queue.queue_depth(root) == 0


def test_adjusted_rate_limit_floor_halves_on_429_threshold():
    assert worker_pool.adjusted_rate_limit_floor(4, recent_429s=0) == 4
    assert worker_pool.adjusted_rate_limit_floor(4, recent_429s=1) == 2
    assert worker_pool.adjusted_rate_limit_floor(1, recent_429s=5) == 1


def test_provider_rate_limit_signal_detects_common_provider_throttles():
    assert worker_pool.provider_rate_limit_signal("provider returned 429 Too Many Requests") == "429"
    assert worker_pool.provider_rate_limit_signal("request failed: rate_limit_exceeded") == "rate_limit"
    assert worker_pool.provider_rate_limit_signal("all good") is None


def test_recent_provider_rate_limits_counts_only_recent_events(tmp_path):
    root = tmp_path / "queue"
    worker_pool.record_provider_rate_limit_event(
        queue_root=root,
        task_slug="recent",
        signal="429",
        now=1_000,
    )
    worker_pool.record_provider_rate_limit_event(
        queue_root=root,
        task_slug="old",
        signal="429",
        now=100,
    )

    assert worker_pool.recent_provider_rate_limits(queue_root=root, window_seconds=300, now=1_050) == 1


def test_run_foreground_uses_recent_rate_limit_floor_for_sizing(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(5):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 4)
    worker_pool.record_provider_rate_limit_event(queue_root=root, task_slug="previous", signal="429")

    results = worker_pool.run_foreground(queue_root=root, runner=lambda _command: 0, drain=False)

    assert len(results) == 2
    assert factory_queue.queue_depth(root) == 3


def test_process_one_records_provider_rate_limit_without_transcript(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="limited")

    result = worker_pool.process_one(
        queue_root=root,
        runner=lambda _command: worker_pool.RunnerResult(
            returncode=1,
            output="provider returned 429 Too Many Requests with details",
        ),
    )

    assert result.provider_rate_limited is True
    telemetry = (root / worker_pool.PROVIDER_RATE_LIMIT_TELEMETRY).read_text(encoding="utf-8")
    assert '"task": "limited"' in telemetry
    assert "Too Many Requests with details" not in telemetry


def test_status_payload_reports_provider_rate_limit_floor(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="limited")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 4)
    worker_pool.record_provider_rate_limit_event(queue_root=root, task_slug="previous", signal="429")

    payload = worker_pool.status_payload(root)

    assert payload["desired_workers"] == 1
    assert payload["provider_rate_limits"] == {
        "window_seconds": worker_pool.DEFAULT_PROVIDER_RATE_LIMIT_WINDOW_SECONDS,
        "recent_429s": 1,
        "provider_rate_limit_floor": 2,
    }


def test_report_payload_recommends_pool_run_with_rate_limited_floor(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(5):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 4)
    worker_pool.record_provider_rate_limit_event(
        queue_root=root,
        task_slug="previous",
        signal="429",
        now=1_000,
    )

    payload = worker_pool.report_payload(root, now=1_100)

    assert payload["counts"]["pending"] == 5
    assert payload["pending"] == ["task-0", "task-1", "task-2", "task-3", "task-4"]
    assert payload["provider_rate_limits"]["recent_429s"] == 1
    assert payload["provider_rate_limits"]["provider_rate_limit_floor"] == 2
    assert payload["suggested_workers"] == 2
    assert payload["suggested_action"] == "run-pool"
    assert "pool --workers 2 --once" in payload["suggested_command"]


def test_report_payload_marks_stale_inflight_before_run_pool(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="stale-task")
    task = factory_queue.claim_one(root)
    assert task is not None
    os.utime(task.path, (100, 100))

    payload = worker_pool.report_payload(root, stale_after_seconds=60, now=200)

    assert payload["stale_in_flight"] == 1
    assert payload["suggested_action"] == "recover-stale"
    assert payload["in_flight"] == [
        {
            "slug": "stale-task",
            "path": str(task.path),
            "age_seconds": 100,
            "stale": True,
        }
    ]
    assert "pool --workers 1 --once" in payload["suggested_command"]


def test_format_report_includes_operator_summary(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="task")
    payload = worker_pool.report_payload(root, workers=3)

    report = worker_pool.format_report(payload)

    assert f"queue_root={root}" in report
    assert "counts pending=1 in-flight=0 done=0 failed=0" in report
    assert "recommendation action=run-pool workers=1 stale_in_flight=0" in report
    assert "pending=task" in report


def test_main_report_json_and_text(tmp_path, capsys):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="task")

    json_rc = worker_pool.main(["--queue-root", str(root), "report", "--json"])
    json_out = capsys.readouterr().out
    text_rc = worker_pool.main(["--queue-root", str(root), "report"])
    text_out = capsys.readouterr().out

    assert json_rc == 0
    assert text_rc == 0
    assert '"suggested_action": "run-pool"' in json_out
    assert "recommendation action=run-pool" in text_out


def test_resolve_execution_options_defaults_live_to_isolated_promotion():
    options = worker_pool.resolve_execution_options(mode="run")

    assert options.isolate_workspace is True
    assert options.promote_artifacts is True


def test_resolve_execution_options_keeps_dry_run_shared_by_default():
    options = worker_pool.resolve_execution_options(mode="dry-run")

    assert options.isolate_workspace is False
    assert options.promote_artifacts is False


def test_resolve_execution_options_allows_live_shared_no_promotion():
    options = worker_pool.resolve_execution_options(
        mode="run",
        shared_workspace=True,
        no_promote_artifacts=True,
    )

    assert options.isolate_workspace is False
    assert options.promote_artifacts is False


def test_factory_run_command_prefers_workspace_script(tmp_path):
    workspace = tmp_path / "worker"
    script = workspace / "scripts" / "factory_run.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    task = factory_queue.QueueTask(path=tmp_path / "task.brief.md", slug="task")

    command = worker_pool.factory_run_command(task, workspace=workspace)

    assert command[1] == str(script)
    assert command[command.index("--workspace") + 1] == str(workspace)


def test_process_one_marks_done_on_runner_success(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="ok")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> int:
        commands.append(command)
        return 0

    result = worker_pool.process_one(queue_root=root, runner=runner)

    assert result.task is not None
    assert result.returncode == 0
    assert result.destination is not None
    assert result.destination.parent.name == "done"
    assert "--dry-run" in commands[0]
    assert "--slug" in commands[0]
    assert "ok" in commands[0]
    assert "--scrub-root-context" in commands[0]


def test_process_one_recovers_stale_inflight_before_claim(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="recover-once")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))

    result = worker_pool.process_one(
        queue_root=root,
        runner=lambda _command: 0,
        recover_stale_after_seconds=1800,
    )

    assert result.task is not None
    assert result.task.slug == "recover-once"
    assert result.destination is not None
    assert result.destination.parent.name == "done"


def test_process_one_uses_isolated_task_workspace(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="isolated")
    base_workspace = tmp_path / "repo"
    task_workspace = tmp_path / "worktrees" / "isolated"
    task_workspace.mkdir(parents=True)
    script = task_workspace / "scripts" / "factory_run.py"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(
        worker_pool,
        "prepare_task_workspace",
        lambda task, *, workspace, isolate_workspace, worktree_root=worker_pool.WORKER_WORKTREE_ROOT: task_workspace,
    )
    commands: list[list[str]] = []

    def runner(command: list[str]) -> int:
        commands.append(command)
        return 0

    result = worker_pool.process_one(
        queue_root=root,
        workspace=base_workspace,
        runner=runner,
        isolate_workspace=True,
    )

    assert result.returncode == 0
    assert commands[0][1] == str(script)
    assert commands[0][commands[0].index("--workspace") + 1] == str(task_workspace)


def test_process_one_marks_failed_on_runner_error(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="bad")

    result = worker_pool.process_one(queue_root=root, runner=lambda _command: 2)

    assert result.returncode == 2
    assert result.destination is not None
    assert result.destination.parent.name == "failed"


def test_run_foreground_once_processes_up_to_desired_worker_count(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(3):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 2)

    results = worker_pool.run_foreground(queue_root=root, runner=lambda _command: 0, drain=False)

    assert len(results) == 2
    assert factory_queue.queue_depth(root) == 1


def test_run_foreground_recovers_stale_inflight_before_sizing(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="recover-pool")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 2)

    results = worker_pool.run_foreground(
        queue_root=root,
        runner=lambda _command: 0,
        recover_stale_after_seconds=1800,
    )

    assert [result.task.slug for result in results if result.task] == ["recover-pool"]
    assert worker_pool.status_payload(root)["counts"] == {
        "pending": 0,
        "in-flight": 0,
        "done": 1,
        "failed": 0,
    }


def test_run_foreground_respects_disabled_stale_recovery(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="not-recovered")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))

    results = worker_pool.run_foreground(
        queue_root=root,
        runner=lambda _command: 0,
        recover_stale_after_seconds=0,
    )

    assert results == []
    assert worker_pool.status_payload(root)["counts"] == {
        "pending": 0,
        "in-flight": 1,
        "done": 0,
        "failed": 0,
    }


def test_run_foreground_processes_worker_batch_concurrently(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(2):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 2)
    started: list[str] = []
    lock = threading.Lock()
    both_started = threading.Event()

    def runner(command: list[str]) -> int:
        slug = command[command.index("--slug") + 1]
        with lock:
            started.append(slug)
            if len(started) == 2:
                both_started.set()
        return 0 if both_started.wait(1) else 9

    results = worker_pool.run_foreground(queue_root=root, runner=runner, workers=2, drain=False)

    assert sorted(result.returncode for result in results) == [0, 0]
    assert sorted(started) == ["task-0", "task-1"]
    assert worker_pool.status_payload(root)["counts"] == {
        "pending": 0,
        "in-flight": 0,
        "done": 2,
        "failed": 0,
    }


def test_main_pool_once_uses_one_batch(tmp_path, monkeypatch, capsys):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(3):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(worker_pool, "subprocess_runner", lambda _command: 0)

    rc = worker_pool.main(["--queue-root", str(root), "pool", "--workers", "2", "--once", "--json"])

    assert rc == 0
    assert '"processed": 2' in capsys.readouterr().out
    assert factory_queue.queue_depth(root) == 1


def test_main_run_once_processes_one_task(tmp_path, monkeypatch, capsys):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(2):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(worker_pool, "subprocess_runner", lambda _command: 0)

    rc = worker_pool.main(["--queue-root", str(root), "run-once", "--json"])

    assert rc == 0
    assert '"verdict": "DONE"' in capsys.readouterr().out
    assert factory_queue.queue_depth(root) == 1


def test_main_run_once_live_defaults_to_isolation_and_promotion(tmp_path, monkeypatch, capsys):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="live-default")
    base_workspace = tmp_path / "repo"
    task_workspace = tmp_path / "worktrees" / "live-default"
    (task_workspace / "scripts").mkdir(parents=True)
    (task_workspace / "scripts" / "factory_run.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    def prepare(task, *, workspace, isolate_workspace, worktree_root=worker_pool.WORKER_WORKTREE_ROOT):
        assert workspace == str(base_workspace)
        assert isolate_workspace is True
        return task_workspace

    def runner(command: list[str]) -> int:
        assert command[1] == str(task_workspace / "scripts" / "factory_run.py")
        assert command[command.index("--workspace") + 1] == str(task_workspace)
        (task_workspace / "docs/evaluations").mkdir(parents=True)
        (task_workspace / "docs/evaluations/live-default-evaluation.md").write_text("# Evaluation\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(worker_pool, "prepare_task_workspace", prepare)
    monkeypatch.setattr(worker_pool, "subprocess_runner", runner)

    rc = worker_pool.main([
        "--queue-root",
        str(root),
        "run-once",
        "--mode",
        "run",
        "--workspace",
        str(base_workspace),
        "--json",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert '"verdict": "DONE"' in out
    assert "live-default-evaluation.md" in out
    assert (base_workspace / "docs/evaluations/live-default-evaluation.md").is_file()


def test_main_pool_live_shared_no_promotion_opt_out(tmp_path, monkeypatch, capsys):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="live-shared")
    base_workspace = tmp_path / "repo"
    base_workspace.mkdir()
    observed: dict[str, object] = {}

    def prepare(task, *, workspace, isolate_workspace, worktree_root=worker_pool.WORKER_WORKTREE_ROOT):
        observed["workspace"] = workspace
        observed["isolate_workspace"] = isolate_workspace
        return base_workspace

    def runner(command: list[str]) -> int:
        (base_workspace / "docs/evaluations").mkdir(parents=True)
        (base_workspace / "docs/evaluations/live-shared-evaluation.md").write_text("# Evaluation\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(worker_pool, "prepare_task_workspace", prepare)
    monkeypatch.setattr(worker_pool, "subprocess_runner", runner)

    rc = worker_pool.main([
        "--queue-root",
        str(root),
        "pool",
        "--mode",
        "run",
        "--workspace",
        str(base_workspace),
        "--shared-workspaces",
        "--no-promote-artifacts",
        "--once",
        "--json",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert observed == {"workspace": str(base_workspace), "isolate_workspace": False}
    assert '"promoted_artifacts": []' in out


def test_process_one_scrubs_root_claude_mem_context_before_runner(tmp_path):
    root = tmp_path / "queue"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agents = workspace / "AGENTS.md"
    agents.write_text(
        "# Agents\n\n<claude-mem-context>\nnoise\n</claude-mem-context>\n",
        encoding="utf-8",
    )
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="task-0")

    def runner(_command: list[str]) -> int:
        assert "<claude-mem-context>" not in agents.read_text(encoding="utf-8")
        return 0

    result = worker_pool.process_one(queue_root=root, workspace=workspace, runner=runner)

    assert result.returncode == 0
    assert agents.read_text(encoding="utf-8") == "# Agents\n"


def test_prepare_task_workspace_creates_git_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    worker_pool.subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    worker_pool.subprocess.run(["git", "config", "user.email", "t@example.test"], cwd=repo, check=True)
    worker_pool.subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    worker_pool.subprocess.run(["git", "add", "AGENTS.md"], cwd=repo, check=True)
    worker_pool.subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo, check=True)
    task = factory_queue.QueueTask(path=tmp_path / "task.brief.md", slug="task-iso")

    workspace = worker_pool.prepare_task_workspace(
        task,
        workspace=repo,
        isolate_workspace=True,
        worktree_root=tmp_path / "worktrees",
    )

    assert workspace == tmp_path / "worktrees" / "task-iso"
    assert (workspace / ".git").exists()
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n"


def test_promote_task_artifacts_copies_known_factory_outputs(tmp_path):
    source = tmp_path / "worker"
    target = tmp_path / "main"
    slug = "task-artifacts"
    (source / "docs/specs").mkdir(parents=True)
    (source / "docs/specs" / f"{slug}-spec.md").write_text("# Spec\n", encoding="utf-8")
    (source / "docs/plans").mkdir(parents=True)
    (source / "docs/plans" / f"{slug}-plan.md").write_text("# Plan\n", encoding="utf-8")
    (source / "run-artifacts" / slug / "roles").mkdir(parents=True)
    (source / "run-artifacts" / slug / f"{slug}-status.md").write_text("# Status\n", encoding="utf-8")
    (source / "run-artifacts" / slug / "roles" / "planner-intake.md").write_text("done\n", encoding="utf-8")
    (source / "docs/evaluations").mkdir(parents=True)
    (source / "docs/evaluations" / f"{slug}-evaluation.md").write_text("# Evaluation\n", encoding="utf-8")

    promoted = worker_pool.promote_task_artifacts(slug, source_workspace=source, target_workspace=target)

    assert sorted(path.relative_to(target).as_posix() for path in promoted) == [
        f"docs/evaluations/{slug}-evaluation.md",
        f"docs/plans/{slug}-plan.md",
        f"docs/specs/{slug}-spec.md",
        f"run-artifacts/{slug}",
    ]
    assert (target / "docs/specs" / f"{slug}-spec.md").read_text(encoding="utf-8") == "# Spec\n"
    assert (target / "run-artifacts" / slug / "roles" / "planner-intake.md").read_text(encoding="utf-8") == "done\n"


def test_process_one_promotes_isolated_artifacts_after_success(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source_brief = _brief(tmp_path)
    factory_queue.enqueue(source_brief, root=root, slug="promote-me")
    base_workspace = tmp_path / "repo"
    task_workspace = tmp_path / "worktrees" / "promote-me"
    (task_workspace / "docs/specs").mkdir(parents=True)
    (task_workspace / "docs/specs" / "promote-me-spec.md").write_text("# Spec\n", encoding="utf-8")
    (task_workspace / "scripts").mkdir(parents=True)
    (task_workspace / "scripts" / "factory_run.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(
        worker_pool,
        "prepare_task_workspace",
        lambda task, *, workspace, isolate_workspace, worktree_root=worker_pool.WORKER_WORKTREE_ROOT: task_workspace,
    )

    result = worker_pool.process_one(
        queue_root=root,
        workspace=base_workspace,
        runner=lambda _command: 0,
        isolate_workspace=True,
        promote_artifacts=True,
    )

    assert result.returncode == 0
    assert result.promoted_artifacts == [base_workspace.resolve() / "docs/specs/promote-me-spec.md"]
    assert (base_workspace / "docs/specs/promote-me-spec.md").read_text(encoding="utf-8") == "# Spec\n"


def test_process_one_promotes_isolated_artifacts_after_failure(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source_brief = _brief(tmp_path)
    factory_queue.enqueue(source_brief, root=root, slug="failed-promote")
    base_workspace = tmp_path / "repo"
    task_workspace = tmp_path / "worktrees" / "failed-promote"
    (task_workspace / "docs/evaluations").mkdir(parents=True)
    (task_workspace / "docs/evaluations" / "failed-promote-evaluation.md").write_text(
        "# Evaluation\n\nVerdict: REJECTED\n",
        encoding="utf-8",
    )
    (task_workspace / "scripts").mkdir(parents=True)
    (task_workspace / "scripts" / "factory_run.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(
        worker_pool,
        "prepare_task_workspace",
        lambda task, *, workspace, isolate_workspace, worktree_root=worker_pool.WORKER_WORKTREE_ROOT: task_workspace,
    )

    result = worker_pool.process_one(
        queue_root=root,
        workspace=base_workspace,
        runner=lambda _command: 7,
        isolate_workspace=True,
        promote_artifacts=True,
    )

    assert result.returncode == 7
    assert result.destination is not None
    assert result.destination.parent.name == "failed"
    assert result.promoted_artifacts == [base_workspace.resolve() / "docs/evaluations/failed-promote-evaluation.md"]
    assert (base_workspace / "docs/evaluations/failed-promote-evaluation.md").is_file()


def test_run_foreground_drains_queue_in_worker_sized_batches(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    for index in range(5):
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")
    monkeypatch.setattr(factory_v3_config, "MAX_WORKERS", 2)
    commands: list[list[str]] = []

    def runner(command: list[str]) -> int:
        commands.append(command)
        return 0

    results = worker_pool.run_foreground(queue_root=root, runner=runner)

    assert len(results) == 5
    assert len(commands) == 5
    assert factory_queue.queue_depth(root) == 0
    assert worker_pool.status_payload(root)["counts"] == {
        "pending": 0,
        "in-flight": 0,
        "done": 5,
        "failed": 0,
    }
