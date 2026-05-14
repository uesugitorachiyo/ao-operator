from __future__ import annotations

import subprocess
import sys

import factory_ao_adapter


def test_resolve_ao_binary_accepts_runtime_path_override(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    ao = runtime / "target" / "release" / "ao"
    ao.parent.mkdir(parents=True)
    ao.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.delenv("FACTORY_V3_AO_BIN", raising=False)
    monkeypatch.delenv("AO_BIN", raising=False)
    monkeypatch.setenv("FACTORY_V3_AO_RUNTIME_PATH", str(runtime))

    resolved = factory_ao_adapter.resolve_ao_binary(
        default_runtime=tmp_path / "missing-runtime",
    )

    assert resolved == str(ao)


def test_extract_run_id_accepts_ao_stdout_forms():
    assert factory_ao_adapter.extract_run_id("ok run r-demo-123 completed") == "r-demo-123"
    assert factory_ao_adapter.extract_run_id("created r-demo-456") == "r-demo-456"
    assert factory_ao_adapter.extract_run_id("no run here") == "unknown"


def test_collect_events_uses_legacy_fallback_when_primary_command_fails(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run_command(cmd, cwd, env, timeout=3600):
        calls.append([str(part) for part in cmd])
        if cmd[:3] == ["ao", "run", "r-demo"]:
            return subprocess.CompletedProcess(cmd, 1, "", "primary failed")
        return subprocess.CompletedProcess(cmd, 0, "legacy events", "")

    monkeypatch.setattr(factory_ao_adapter, "run_command", fake_run_command)

    result = factory_ao_adapter.collect_events("ao", tmp_path / "ao-home", "r-demo", cwd=tmp_path)

    assert result is not None
    assert result.stdout == "legacy events"
    assert calls == [
        ["ao", "run", "r-demo", "events"],
        ["ao", "runs", "events", "r-demo"],
    ]


def test_run_command_returns_completed_process_on_timeout(tmp_path):
    result = factory_ao_adapter.run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        tmp_path,
        {},
        timeout=1,
    )

    assert result.returncode == 124
    assert "Command timed out after 1s" in result.stderr
