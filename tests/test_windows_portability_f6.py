"""F6 cross-platform: Windows portability regressions.

These tests pin the contract that origin/main works on Windows without
the POSIX-assumption gaps captured in
run-artifacts/release-v0.1.1/windows/cross-platform-verify-win-blocker.md
(21 pytest failures grouped into path serialization, command parsing,
queue concurrency, and .exe handling).

Each test exercises the Windows-shaped code path on POSIX by either
inspecting POSIX-compatible output (``as_posix`` always emits ``/``)
or by monkeypatching ``os.name`` so the platform branch executes.
POSIX behavior on Linux/macOS is preserved.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import agent_os_operator_cockpit  # noqa: E402
import agent_os_phase_compiler  # noqa: E402
import check_clean_clone_readiness  # noqa: E402
import factory_queue  # noqa: E402
import factory_run  # noqa: E402
import ingest_agent_os_role_outputs  # noqa: E402
import preserve_live_failure_diagnostics  # noqa: E402
import run_operator_slice  # noqa: E402
import worker_pile_canary  # noqa: E402


# --- F6a: factory_run.rel() emits POSIX paths -------------------------------


def test_rel_emits_posix_separators_for_relative_path():
    target = factory_run.ROOT / "run-artifacts" / "release-v0.1.1" / "PLAN.md"
    rel = factory_run.rel(target)
    assert "\\" not in rel
    assert rel == "run-artifacts/release-v0.1.1/PLAN.md"


def test_rel_emits_posix_for_path_outside_root(tmp_path):
    outside = tmp_path / "x" / "y"
    rel = factory_run.rel(outside)
    assert "\\" not in rel
    # Outside-root paths fall through to as_posix() which still uses /.
    assert rel.endswith("/x/y")


def test_display_path_relative_input_is_posix():
    raw = Path("docs") / "status" / "release-v0.1.1" / "PLAN.md"
    out = factory_run.display_path(raw)
    assert "\\" not in out
    assert out == "run-artifacts/release-v0.1.1/PLAN.md"


# --- F6b: run_operator_slice.split_command honors Windows shlex mode --------


def test_split_command_preserves_backslashes_on_windows(monkeypatch):
    monkeypatch.setattr(
        run_operator_slice,
        "_normalize_for_shlex",
        lambda command: command.replace("\\", "\\\\"),
    )
    parts, _env = run_operator_slice.split_command(r"python C:\Users\op\file.py")
    assert parts == ["python", r"C:\Users\op\file.py"]


def test_split_command_preserves_quoted_python_expression_on_windows(monkeypatch):
    # Regression: under non-POSIX shlex (the original F6b approach) the
    # outer quotes leak into the argument and `python -c "raise SystemExit(1)"`
    # never actually raises. Pre-escape + POSIX shlex strips the quotes.
    monkeypatch.setattr(
        run_operator_slice,
        "_normalize_for_shlex",
        lambda command: command.replace("\\", "\\\\"),
    )
    parts, _env = run_operator_slice.split_command(
        r'C:\Python313\python.exe -c "raise SystemExit(1)"'
    )
    assert parts == [r"C:\Python313\python.exe", "-c", "raise SystemExit(1)"]


def test_split_command_strips_backslashes_on_posix(monkeypatch):
    monkeypatch.setattr(run_operator_slice, "_normalize_for_shlex", lambda c: c)
    parts, _env = run_operator_slice.split_command("python /tmp/x")
    assert parts == ["python", "/tmp/x"]


def test_split_command_assigns_leading_env_assignments():
    parts, env = run_operator_slice.split_command("FOO=bar python -V")
    assert parts == ["python", "-V"]
    assert env["FOO"] == "bar"


# --- F6c: claim_one concurrency safety + slug_from_task strips token --------


def _brief(tmp_path: Path, name: str = "brief.md") -> Path:
    path = tmp_path / name
    path.write_text("# Brief\n\nShape: greenfield\n", encoding="utf-8")
    return path


def test_claim_one_uses_unique_destination_filename(tmp_path):
    root = tmp_path / "queue"
    factory_queue.enqueue(_brief(tmp_path), root=root, slug="solo")
    task = factory_queue.claim_one(root)
    assert task is not None
    assert task.slug == "solo"
    assert task.path.name.endswith(factory_queue.BRIEF_SUFFIX)
    assert factory_queue.CLAIM_TOKEN_SEP in task.path.name
    assert task.path.parent.name == "in-flight"


def test_slug_from_task_strips_claim_token():
    tokened = Path(
        f"abc-12345678{factory_queue.CLAIM_TOKEN_SEP}my-slug{factory_queue.BRIEF_SUFFIX}"
    )
    plain = Path(f"my-slug{factory_queue.BRIEF_SUFFIX}")
    assert factory_queue.slug_from_task(tokened) == "my-slug"
    assert factory_queue.slug_from_task(plain) == "my-slug"


def test_concurrent_claim_one_never_yields_same_destination(tmp_path):
    root = tmp_path / "queue"
    for index in range(8):
        source = _brief(tmp_path, f"b{index}.md")
        factory_queue.enqueue(source, root=root, slug=f"task-{index}")

    claimed: list[factory_queue.QueueTask] = []
    lock = threading.Lock()

    def worker():
        while True:
            task = factory_queue.claim_one(root)
            if task is None:
                return
            with lock:
                claimed.append(task)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    paths = factory_queue.queue_paths(root)
    assert len(claimed) == 8
    destinations = {task.path for task in claimed}
    assert len(destinations) == 8
    slugs = sorted(task.slug for task in claimed)
    assert slugs == sorted(f"task-{i}" for i in range(8))
    assert list(paths["pending"].iterdir()) == []
    assert sum(1 for _ in paths["in-flight"].iterdir()) == 8


def test_enqueue_rejects_duplicate_after_claim(tmp_path):
    root = tmp_path / "queue"
    source = _brief(tmp_path)
    factory_queue.enqueue(source, root=root, slug="dupe")
    task = factory_queue.claim_one(root)
    assert task is not None

    with pytest.raises(FileExistsError):
        factory_queue.enqueue(source, root=root, slug="dupe")


def test_recover_stale_inflight_returns_canonical_slug(tmp_path):
    import time

    root = tmp_path / "queue"
    factory_queue.enqueue(_brief(tmp_path), root=root, slug="stale")
    task = factory_queue.claim_one(root)
    assert task is not None
    old = time.time() - 3600
    os.utime(task.path, (old, old))

    recovered = factory_queue.recover_stale_inflight(root=root, stale_after_seconds=1800)

    assert [item.slug for item in recovered] == ["stale"]
    assert recovered[0].path.parent.name == "pending"
    assert recovered[0].path.name == f"stale{factory_queue.BRIEF_SUFFIX}"


# --- F6d: relpath() helpers in 4 scripts emit POSIX paths -------------------


@pytest.mark.parametrize(
    "module",
    [
        ingest_agent_os_role_outputs,
        agent_os_operator_cockpit,
        agent_os_phase_compiler,
        preserve_live_failure_diagnostics,
    ],
)
def test_relpath_emits_posix_separators(module, tmp_path):
    root = tmp_path
    inside = root / "a" / "b" / "c.json"
    out = module.relpath(root, inside)
    assert "\\" not in out
    assert out == "a/b/c.json"


@pytest.mark.parametrize(
    "module",
    [
        ingest_agent_os_role_outputs,
        agent_os_operator_cockpit,
        agent_os_phase_compiler,
        preserve_live_failure_diagnostics,
    ],
)
def test_relpath_outside_root_still_posix(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "x.json"
    out = module.relpath(root, outside)
    assert "\\" not in out


# --- F6e: ao_binary_provenance tries .exe candidate on Windows --------------


def test_ao_binary_provenance_prefers_ao_exe_on_windows(monkeypatch, tmp_path):
    runtime = tmp_path / "ao-runtime"
    release = runtime / "target" / "release"
    release.mkdir(parents=True)
    (release / "ao.exe").write_text("stub", encoding="utf-8")

    monkeypatch.setattr(worker_pile_canary, "_is_windows", lambda: True)
    monkeypatch.setattr(
        worker_pile_canary,
        "run_capture",
        lambda *args, **kwargs: (0, "ao stub-version"),
    )

    payload = worker_pile_canary.ao_binary_provenance(
        env={"FACTORY_V3_AO_RUNTIME_PATH": str(runtime)}
    )

    assert payload["path"].endswith("ao.exe")
    assert payload["source"] == "FACTORY_V3_AO_RUNTIME_PATH/default"
    assert payload["exists"] is True


def test_ao_binary_provenance_uses_ao_on_posix(monkeypatch, tmp_path):
    runtime = tmp_path / "ao-runtime"
    release = runtime / "target" / "release"
    release.mkdir(parents=True)
    (release / "ao").write_text("#!/bin/sh\nprintf 'ao test'\n", encoding="utf-8")

    monkeypatch.setattr(worker_pile_canary, "_is_windows", lambda: False)
    monkeypatch.setattr(
        worker_pile_canary,
        "run_capture",
        lambda *args, **kwargs: (0, "ao test"),
    )

    payload = worker_pile_canary.ao_binary_provenance(
        env={"FACTORY_V3_AO_RUNTIME_PATH": str(runtime)}
    )

    assert payload["path"].endswith(os.sep + "ao")
    assert payload["source"] == "FACTORY_V3_AO_RUNTIME_PATH/default"


# --- F6f: sanitize / redact_ao_home POSIX-tail normalization ---------------


def test_redact_ao_home_normalizes_backslash_tail():
    text = r"C:\Users\op\.ao\runs\r-test\events.jsonl"
    redacted = preserve_live_failure_diagnostics.redact_ao_home(
        text, r"C:\Users\op\.ao"
    )
    assert redacted == "/tmp/[REDACTED_AO_HOME]/runs/r-test/events.jsonl"


def test_redact_ao_home_handles_posix_input_unchanged():
    text = "/tmp/factory-ao/runs/r-test/events.jsonl"
    redacted = preserve_live_failure_diagnostics.redact_ao_home(
        text, "/tmp/factory-ao"
    )
    assert redacted == "/tmp/[REDACTED_AO_HOME]/runs/r-test/events.jsonl"


def test_redact_ao_home_handles_nested_dict_and_list():
    payload = {"events": r"C:\ao\runs\r1\events.jsonl", "items": [r"C:\ao\runs\r2"]}
    out = preserve_live_failure_diagnostics.redact_ao_home(payload, r"C:\ao")
    assert out == {
        "events": "/tmp/[REDACTED_AO_HOME]/runs/r1/events.jsonl",
        "items": ["/tmp/[REDACTED_AO_HOME]/runs/r2"],
    }


def test_clean_clone_sanitize_normalizes_backslash_tail(tmp_path):
    root = tmp_path
    clone = tmp_path / "ao-operator-clean-clone-abc" / "ao-operator"
    # Inject Windows-style strings even though the host is POSIX.
    payload = {
        "repo": str(root).replace("/", "\\"),
        "clone_path": str(clone).replace("/", "\\"),
    }
    sanitized = check_clean_clone_readiness.sanitize(payload, root=root)
    assert sanitized["repo"] == "${FACTORY_V3_ROOT}"
    assert sanitized["clone_path"] == "${FACTORY_V3_ROOT}/ao-operator-clean-clone-abc/ao-operator"


def test_public_artifact_path_outside_root_is_posix(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "report.json"
    try:
        out = outside.relative_to(root).as_posix()
    except ValueError:
        out = outside.as_posix()
    assert "\\" not in out


def test_ao_binary_provenance_missing_fallback_uses_native_name(monkeypatch, tmp_path):
    runtime = tmp_path / "ao-runtime"
    monkeypatch.setattr(worker_pile_canary, "_is_windows", lambda: True)
    monkeypatch.setattr(worker_pile_canary.shutil, "which", lambda _name: None)

    payload = worker_pile_canary.ao_binary_provenance(
        env={"FACTORY_V3_AO_RUNTIME_PATH": str(runtime)}
    )

    assert payload["exists"] is False
    assert payload["source"] == "missing"
    assert payload["path"].endswith("ao.exe")
