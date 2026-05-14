"""Tests for the F2 cross-platform Python interpreter resolver.

`scripts/factory_run.py` historically hardcoded ``python3`` for its
local-validation subprocess invocations. Native Windows hosts where
the interpreter is ``python`` (or ``py -3``) tripped on this. F2 swaps
those callsites to ``_portable_python()`` which honors a
``FACTORY_V3_PYTHON`` override and falls back to ``sys.executable``.

These tests pin the resolver behavior so future refactors keep the
cross-platform contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import factory_run  # noqa: E402


def test_portable_python_defaults_to_sys_executable(monkeypatch):
    monkeypatch.delenv("FACTORY_V3_PYTHON", raising=False)
    assert factory_run._portable_python() == sys.executable


def test_portable_python_honors_env_override(monkeypatch, tmp_path):
    override = tmp_path / "my-python"
    monkeypatch.setenv("FACTORY_V3_PYTHON", str(override))
    assert factory_run._portable_python() == str(override)


def test_portable_python_empty_env_falls_back_to_sys_executable(monkeypatch):
    # Empty string must not be treated as a valid override (would otherwise
    # produce subprocess.run([""], ...) which raises FileNotFoundError).
    monkeypatch.setenv("FACTORY_V3_PYTHON", "")
    assert factory_run._portable_python() == sys.executable


def test_run_local_validation_uses_resolver(monkeypatch):
    """The first command emitted by run_local_validation must use the
    resolver output, not the literal string 'python3'."""
    captured: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run_command(cmd, _root, _env, timeout):  # noqa: ARG001
        captured.append(list(cmd))
        return _Result()

    monkeypatch.setattr(factory_run, "run_command", fake_run_command)
    monkeypatch.delenv("FACTORY_V3_PYTHON", raising=False)
    factory_run.run_local_validation("test-slug")

    assert captured, "run_local_validation should invoke run_command"
    assert captured[0][0] == sys.executable
    # And the second command (validate_scaffold) too.
    assert captured[1][0] == sys.executable


def test_run_factory_validation_uses_resolver(monkeypatch):
    captured: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run_command(cmd, _root, _env, timeout):  # noqa: ARG001
        captured.append(list(cmd))
        return _Result()

    monkeypatch.setattr(factory_run, "run_command", fake_run_command)
    monkeypatch.delenv("FACTORY_V3_PYTHON", raising=False)
    factory_run.run_factory_validation("test-slug")

    assert captured and captured[0][0] == sys.executable


def test_run_factory_validation_honors_factory_v3_python_override(monkeypatch, tmp_path):
    override = tmp_path / "py-override"
    captured: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run_command(cmd, _root, _env, timeout):  # noqa: ARG001
        captured.append(list(cmd))
        return _Result()

    monkeypatch.setattr(factory_run, "run_command", fake_run_command)
    monkeypatch.setenv("FACTORY_V3_PYTHON", str(override))
    factory_run.run_factory_validation("test-slug")

    assert captured and captured[0][0] == str(override)


def test_deterministic_replay_command_uses_portable_python(monkeypatch, tmp_path):
    override = tmp_path / "python.exe"
    monkeypatch.setenv("FACTORY_V3_PYTHON", str(override))

    resolved = factory_run._resolved_deterministic_command(["python3", "-c", "print('ok')"])

    assert resolved == [str(override), "-c", "print('ok')"]
