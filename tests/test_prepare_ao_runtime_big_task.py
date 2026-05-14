from __future__ import annotations

import subprocess

import prepare_ao_runtime_big_task


def git(command: list[str], cwd) -> None:
    completed = subprocess.run(
        ["git", *command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_prepare_creates_separate_runner_and_target_worktrees(tmp_path):
    source = tmp_path / "ao-runtime"
    source.mkdir()
    git(["init"], source)
    git(["config", "user.email", "test@example.com"], source)
    git(["config", "user.name", "Test User"], source)
    (source / "Cargo.toml").write_text("[workspace]\nmembers = []\n", encoding="utf-8")
    git(["add", "Cargo.toml"], source)
    git(["commit", "-m", "initial"], source)

    runner = tmp_path / "runner"
    target = tmp_path / "target"
    brief = tmp_path / "brief.md"
    brief.write_text("# Big task\n\nScoped writes: crates/ao-daemon/src/engine.rs\n", encoding="utf-8")

    payload = prepare_ao_runtime_big_task.prepare(
        source=source,
        runner=runner,
        target=target,
        target_branch="ao-operator/test-target",
        queue_root=tmp_path / "queue",
        brief=brief,
        slug="ao-runtime-test",
    )

    assert payload["verdict"] == "PASS"
    assert payload["runner"]["path"] == str(runner)
    assert payload["target"]["path"] == str(target)
    assert payload["runner"]["path"] != payload["target"]["path"]
    assert payload["target"]["branch"] == "ao-operator/test-target"
    assert (target / ".ao-operator" / "all-codex.env").is_file()
    assert "FACTORY_V3_AO_BIN=" + str(runner / "target" / "release" / "ao") in payload["commands"]["dry_run"]
    assert "--workspace " + str(target) in payload["commands"]["dry_run"]
    assert "--scrub-root-context" in payload["commands"]["dry_run"]
    assert "--scrub-root-context" in payload["commands"]["live_run"]
