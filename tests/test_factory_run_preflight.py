from __future__ import annotations

from pathlib import Path
import sys

import factory_run
import verify_closure


def test_claude_mem_context_paths_detects_root_agent_files(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# Agents\n\n<claude-mem-context>\nnoise\n</claude-mem-context>\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Clean\n", encoding="utf-8")

    assert factory_run.claude_mem_context_paths(tmp_path) == ["AGENTS.md"]


def test_preflight_blocks_slug_collision_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    slug = "existing-slug"
    spec = tmp_path / "docs" / "specs" / f"{slug}-spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# existing\n", encoding="utf-8")

    blockers = factory_run.preflight_blockers(slug, overwrite_artifacts=False)

    assert len(blockers) == 1
    assert "generated artifacts already exist" in blockers[0]
    assert "docs/specs/existing-slug-spec.md" in blockers[0]


def test_preflight_allows_slug_collision_with_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    slug = "existing-slug"
    status_dir = tmp_path / "run-artifacts" / slug
    status_dir.mkdir(parents=True)

    assert factory_run.preflight_blockers(slug, overwrite_artifacts=True) == []


def test_preflight_blocks_claude_mem_pollution(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "<claude-mem-context>\nnoise\n</claude-mem-context>\n",
        encoding="utf-8",
    )

    blockers = factory_run.preflight_blockers("fresh-slug", overwrite_artifacts=False)

    assert len(blockers) == 1
    assert "claude-mem context pollution" in blockers[0]


def test_scrub_root_claude_mem_context_allows_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Agents\n\n<claude-mem-context>\nnoise\n</claude-mem-context>\n",
        encoding="utf-8",
    )

    scrubbed = factory_run.scrub_root_claude_mem_context(tmp_path)

    assert scrubbed == ["AGENTS.md"]
    assert agents.read_text(encoding="utf-8") == "# Agents\n"
    assert factory_run.preflight_blockers("fresh-slug", overwrite_artifacts=False) == []


def test_live_run_blockers_allow_bounded_task_count(monkeypatch):
    monkeypatch.delenv(factory_run.MAX_LIVE_TASKS_ENV, raising=False)
    monkeypatch.delenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, raising=False)
    tasks = [{"id": f"task-{i}"} for i in range(factory_run.DEFAULT_MAX_LIVE_TASKS)]

    assert factory_run.live_run_blockers(tasks, run=True) == []


def test_live_run_blockers_ignore_non_live_modes(monkeypatch):
    monkeypatch.delenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, raising=False)
    tasks = [{"id": f"task-{i}"} for i in range(factory_run.DEFAULT_MAX_LIVE_TASKS + 1)]

    assert factory_run.live_run_blockers(tasks, run=False) == []


def test_live_run_blockers_block_large_default(monkeypatch):
    monkeypatch.delenv(factory_run.MAX_LIVE_TASKS_ENV, raising=False)
    monkeypatch.delenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, raising=False)
    tasks = [{"id": f"task-{i}"} for i in range(factory_run.DEFAULT_MAX_LIVE_TASKS + 1)]

    blockers = factory_run.live_run_blockers(tasks, run=True)

    assert len(blockers) == 1
    assert "live run task count 51 exceeds FACTORY_V3_MAX_LIVE_TASKS=50" in blockers[0]
    assert "FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1" in blockers[0]


def test_live_run_blockers_respect_custom_limit(monkeypatch):
    monkeypatch.setenv(factory_run.MAX_LIVE_TASKS_ENV, "10")
    monkeypatch.delenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, raising=False)
    tasks = [{"id": f"task-{i}"} for i in range(11)]

    blockers = factory_run.live_run_blockers(tasks, run=True)

    assert len(blockers) == 1
    assert "live run task count 11 exceeds FACTORY_V3_MAX_LIVE_TASKS=10" in blockers[0]


def test_live_run_blockers_allow_explicit_override(monkeypatch):
    monkeypatch.setenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, "1")
    tasks = [{"id": f"task-{i}"} for i in range(1000)]

    assert factory_run.live_run_blockers(tasks, run=True) == []


def test_workspace_claude_mem_blocker_reports_workspace_root(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text(
        "# Agents\n\n<claude-mem-context>\nnoise\n</claude-mem-context>\n",
        encoding="utf-8",
    )

    blocker = factory_run.workspace_claude_mem_blocker(workspace)

    assert blocker is not None
    assert "claude-mem context pollution detected in workspace" in blocker
    assert str(workspace) in blocker
    assert "AGENTS.md" in blocker


def test_ao_binary_accepts_runtime_path_override(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    ao = runtime / "target" / "release" / "ao"
    ao.parent.mkdir(parents=True)
    ao.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.delenv("FACTORY_V3_AO_BIN", raising=False)
    monkeypatch.delenv("AO_BIN", raising=False)
    monkeypatch.setenv("FACTORY_V3_AO_RUNTIME_PATH", str(runtime))

    assert factory_run.ao_binary() == str(ao)


def test_run_command_returns_completed_process_on_timeout(tmp_path):
    result = factory_run.run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        tmp_path,
        {},
        timeout=1,
    )

    assert result.returncode == 124
    assert "Command timed out after 1s" in result.stderr


def test_write_normalizes_generated_artifact_trailing_whitespace(tmp_path):
    artifact = tmp_path / "run-artifacts" / "slug" / "prompts" / "task.md"

    factory_run.write(artifact, "alpha  \n   \nbeta\t\n")

    assert artifact.read_text(encoding="utf-8") == "alpha\n\nbeta\n"


def test_verify_closure_includes_artifact_hygiene_when_present(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "artifact_hygiene.py").write_text("print('ok')\n", encoding="utf-8")

    commands = verify_closure.closure_commands(tmp_path, include_pytest=False)

    assert [verify_closure.sys.executable, "scripts/artifact_hygiene.py", "--strict"] in commands
