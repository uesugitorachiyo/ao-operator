"""Tests for the F3 cross-platform shell resolver in verify_closure.

`scripts/verify_closure.py` historically hardcoded ``["bash", "-lc", item]``
for any user-supplied closure-verification command (the ``--extra`` flag).
Native Windows hosts where bash isn't on PATH tripped on this. F3 swaps
that callsite to ``_portable_shell_args(item)`` which honors a
``FACTORY_V3_SHELL`` override and falls back to the platform default
(``cmd /c`` on Windows, ``bash -lc`` elsewhere).

These tests pin the resolver behavior so future refactors keep the
cross-platform contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_closure  # noqa: E402


def test_portable_shell_defaults_to_bash_on_posix(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("FACTORY_V3_SHELL", raising=False)
    assert verify_closure._portable_shell_args("echo hi") == ["bash", "-lc", "echo hi"]


def test_portable_shell_defaults_to_cmd_on_windows(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.delenv("FACTORY_V3_SHELL", raising=False)
    assert verify_closure._portable_shell_args("echo hi") == ["cmd", "/c", "echo hi"]


def test_portable_shell_honors_factory_v3_shell_override_windows(monkeypatch):
    # On Windows, posix=False keeps backslashes intact and preserves quote
    # characters in the token. A path without spaces avoids the quoting
    # ambiguity. Real Git Bash is typically at C:\Program Files\Git\bin
    # which Windows users would set via the cmd.exe-friendly /-style:
    # C:/Git/bin/bash.exe -lc (no spaces). subprocess on Windows accepts
    # forward slashes in paths.
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("FACTORY_V3_SHELL", "C:\\Git\\bin\\bash.exe -lc")
    assert verify_closure._portable_shell_args("echo hi") == [
        "C:\\Git\\bin\\bash.exe",
        "-lc",
        "echo hi",
    ]


def test_portable_shell_override_works_on_posix_too(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.setenv("FACTORY_V3_SHELL", "/bin/zsh -lc")
    assert verify_closure._portable_shell_args("uname -a") == ["/bin/zsh", "-lc", "uname -a"]


def test_portable_shell_empty_override_falls_back_to_platform_default(monkeypatch):
    # Empty string must not be treated as a valid override (would otherwise
    # produce subprocess.run([item], ...) which would try to execute the
    # user-supplied command as if it were an argv0).
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.setenv("FACTORY_V3_SHELL", "")
    assert verify_closure._portable_shell_args("echo hi") == ["bash", "-lc", "echo hi"]


def test_run_extra_command_uses_resolver_on_windows(monkeypatch, tmp_path):
    """run() must route --extra commands through the resolver, not the
    literal ['bash', '-lc', ...] argv shape, so Windows hosts work."""
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.delenv("FACTORY_V3_SHELL", raising=False)

    captured: list[list[str]] = []

    def fake_run_command(_repo, command, _timeout):
        captured.append(list(command))
        return {
            "command": command,
            "verdict": "PASS",
            "returncode": 0,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(verify_closure, "run_command", fake_run_command)
    monkeypatch.setattr(verify_closure, "trigger_review_evidence_v2",
                        lambda _r: {"verdict": "PASS", "details": []})
    # Pretend there are no closure_commands; only the --extra item flows.
    monkeypatch.setattr(verify_closure, "closure_commands",
                        lambda _r, include_pytest: [])

    result = verify_closure.run(
        repo=tmp_path,
        include_pytest=False,
        timeout=10,
        dry_run=False,
        extra=["python -m pytest"],
    )
    assert result["verdict"] == "PASS"
    # The captured command must be cmd /c on Windows, not bash -lc.
    assert captured == [["cmd", "/c", "python -m pytest"]]


def test_run_extra_command_uses_resolver_on_posix(monkeypatch, tmp_path):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("FACTORY_V3_SHELL", raising=False)

    captured: list[list[str]] = []

    def fake_run_command(_repo, command, _timeout):
        captured.append(list(command))
        return {
            "command": command,
            "verdict": "PASS",
            "returncode": 0,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(verify_closure, "run_command", fake_run_command)
    monkeypatch.setattr(verify_closure, "trigger_review_evidence_v2",
                        lambda _r: {"verdict": "PASS", "details": []})
    monkeypatch.setattr(verify_closure, "closure_commands",
                        lambda _r, include_pytest: [])

    result = verify_closure.run(
        repo=tmp_path,
        include_pytest=False,
        timeout=10,
        dry_run=False,
        extra=["python3 -m pytest"],
    )
    assert result["verdict"] == "PASS"
    # POSIX behavior is preserved: bash -lc.
    assert captured == [["bash", "-lc", "python3 -m pytest"]]
