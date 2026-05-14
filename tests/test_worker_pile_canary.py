from __future__ import annotations

import json
import os

import pytest

import factory_queue
import worker_pool
import worker_pile_canary


def test_run_canary_drains_larger_pile(tmp_path):
    payload = worker_pile_canary.run_canary(
        tasks=6,
        workers=3,
        queue_root=tmp_path / "queue",
    )

    assert payload["verdict"] == "PASS"
    assert payload["execution_mode"] == "synthetic"
    assert payload["processed"] == 6
    assert payload["commands"] == 6
    assert payload["before"]["counts"] == {
        "pending": 6,
        "in-flight": 0,
        "done": 0,
        "failed": 0,
    }
    assert payload["after"]["counts"] == {
        "pending": 0,
        "in-flight": 0,
        "done": 6,
        "failed": 0,
    }
    assert payload["after"]["suggested_action"] == "idle"
    assert "runtime_provenance" in payload
    assert "ao_binary" in payload["runtime_provenance"]
    assert "ao_runtime_worktree" in payload["runtime_provenance"]


def test_run_canary_rejects_non_empty_queue(tmp_path):
    root = tmp_path / "queue"
    brief = tmp_path / "brief.md"
    brief.write_text("# Brief\n\nShape: greenfield\n", encoding="utf-8")
    factory_queue.enqueue(brief, root=root, slug="existing")

    try:
        worker_pile_canary.run_canary(tasks=1, workers=1, queue_root=root)
    except FileExistsError as exc:
        assert "canary queue is not empty" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")


def test_main_json_outputs_pass(tmp_path, capsys):
    rc = worker_pile_canary.main([
        "--tasks",
        "4",
        "--workers",
        "2",
        "--queue-root",
        str(tmp_path / "queue"),
        "--json",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"
    assert payload["after"]["counts"]["done"] == 4
    assert payload["runtime_provenance"]["ao_binary"]["path"]


@pytest.mark.skipif(
    os.name == "nt",
    reason=(
        "Synthetic `#!/bin/sh` ao binary cannot be executed on Windows. "
        "F6e Windows code path (ao.exe candidate) is covered by "
        "tests/test_windows_portability_f6.py::test_ao_binary_provenance_prefers_ao_exe_on_windows."
    ),
)
def test_runtime_provenance_uses_configured_ao_runtime_path(tmp_path, monkeypatch):
    runtime = tmp_path / "ao-runtime"
    ao_bin = runtime / "target" / "release" / "ao"
    ao_bin.parent.mkdir(parents=True)
    ao_bin.write_text("#!/bin/sh\nprintf 'ao test-version\\n'\n", encoding="utf-8")
    ao_bin.chmod(0o755)
    monkeypatch.setenv("FACTORY_V3_AO_RUNTIME_PATH", str(runtime))

    payload = worker_pile_canary.runtime_provenance()

    assert payload["ao_binary"] == {
        "path": str(ao_bin),
        "source": "FACTORY_V3_AO_RUNTIME_PATH/default",
        "exists": True,
        "version": "ao test-version",
        "version_error": None,
    }
    assert payload["ao_runtime_worktree"]["path"] == str(runtime)
    assert payload["ao_runtime_worktree"]["is_git_worktree"] is False


def test_main_rejects_invalid_task_count(capsys):
    rc = worker_pile_canary.main(["--tasks", "0"])

    assert rc == 2
    assert "--tasks must be greater than 0" in capsys.readouterr().err


def test_live_canary_requires_explicit_confirmation(tmp_path):
    try:
        worker_pile_canary.run_canary(
            tasks=1,
            workers=1,
            queue_root=tmp_path / "queue",
            execution_mode="live",
        )
    except ValueError as exc:
        assert "--mode live requires --confirm-live" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_live_canary_rejects_dirty_ao_runtime_before_enqueue(tmp_path, monkeypatch):
    monkeypatch.setattr(
        worker_pile_canary,
        "runtime_provenance",
        lambda: {
            "ao_binary": {"path": "/tmp/ao", "source": "test", "exists": True, "version": "ao test"},
            "ao_runtime_worktree": {
                "path": "/tmp/ao-runtime",
                "is_git_worktree": True,
                "head": "abc123",
                "branch": "main",
                "dirty": True,
                "dirty_entries": 2,
                "status_preview": [" M crates/ao-daemon/src/engine.rs"],
            },
        },
    )

    try:
        worker_pile_canary.run_canary(
            tasks=1,
            workers=1,
            queue_root=tmp_path / "queue",
            execution_mode="live",
            confirm_live=True,
        )
    except ValueError as exc:
        assert "live canary requires a clean AO runtime worktree" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert not (tmp_path / "queue").exists()


def test_live_canary_allows_dirty_ao_runtime_with_explicit_override(tmp_path, monkeypatch):
    observed: dict[str, object] = {}
    provenance = {
        "ao_binary": {"path": "/tmp/ao", "source": "test", "exists": True, "version": "ao test"},
        "ao_runtime_worktree": {
            "path": "/tmp/ao-runtime",
            "is_git_worktree": True,
            "head": "abc123",
            "branch": "main",
            "dirty": True,
            "dirty_entries": 2,
            "status_preview": [" M crates/ao-daemon/src/engine.rs"],
        },
    }

    def fake_run_foreground(**kwargs):
        observed.update(kwargs)
        results = []
        while True:
            task = factory_queue.claim_one(kwargs["queue_root"])
            if task is None:
                break
            done = factory_queue.mark_done(task, root=kwargs["queue_root"])
            results.append(
                worker_pool.WorkerResult(
                    task=task,
                    returncode=0,
                    destination=done.path,
                    command=["synthetic-live"],
                )
            )
        return results

    monkeypatch.setattr(worker_pile_canary, "runtime_provenance", lambda: provenance)
    monkeypatch.setattr(worker_pile_canary.worker_pool, "run_foreground", fake_run_foreground)

    payload = worker_pile_canary.run_canary(
        tasks=2,
        workers=2,
        queue_root=tmp_path / "queue",
        execution_mode="live",
        workspace=tmp_path / "workspace",
        provider_env=tmp_path / "provider.env",
        confirm_live=True,
        allow_dirty_ao_runtime=True,
    )

    assert payload["verdict"] == "PASS"
    assert payload["execution_mode"] == "live"
    assert payload["runtime_provenance"] == provenance
    assert observed["mode"] == "run"
    assert observed["workspace"] == tmp_path / "workspace"
    assert observed["provider_env"] == tmp_path / "provider.env"
    assert observed["isolate_workspace"] is True
    assert observed["promote_artifacts"] is True
    assert observed["drain"] is True


def test_main_live_requires_confirmation(capsys):
    rc = worker_pile_canary.main(["--mode", "live", "--tasks", "1"])

    assert rc == 2
    assert "--mode live requires --confirm-live" in capsys.readouterr().err
