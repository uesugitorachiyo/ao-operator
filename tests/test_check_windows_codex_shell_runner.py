from __future__ import annotations

import subprocess

import check_windows_codex_shell_runner as gate


def test_parse_workspace_write_runner_timeout() -> None:
    result = gate.parse_sandbox_result(
        "workspace-write",
        0,
        'execution error: windows sandbox: timed out after 15000ms connecting runner pipe-in\n',
        "",
    )

    assert result.runner_pipe_timeout is True
    assert result.status_result == ""
    assert result.powershell_returned_text is False


def test_parse_danger_full_access_done_result() -> None:
    result = gate.parse_sandbox_result(
        "danger-full-access",
        0,
        "Result: DONE\nArtifact: result.md\nEvidence:\n- powershell probe returned text: yes\n",
        "",
    )

    assert result.runner_pipe_timeout is False
    assert result.status_result == "DONE"
    assert result.powershell_returned_text is True


def test_build_report_passes_only_with_timeout_and_danger_success() -> None:
    target = "user@" + ".".join(["10", "0", "0", "96"])
    report = gate.build_report(
        [
            gate.SandboxResult("workspace-write", 0, "", False, True),
            gate.SandboxResult("danger-full-access", 0, "DONE", True, False),
        ],
        target=target,
    )

    assert report["verdict"] == "PASS"
    assert report["target"] == "<redacted-user>@<redacted-host>"
    assert target.split("@", 1)[1] not in str(report)


def test_build_report_fails_when_danger_does_not_capture_shell() -> None:
    target = "user@" + ".".join(["10", "0", "0", "96"])
    report = gate.build_report(
        [
            gate.SandboxResult("workspace-write", 0, "", False, True),
            gate.SandboxResult("danger-full-access", 0, "DONE", False, False),
        ],
        target=target,
    )

    assert report["verdict"] == "FAIL"
    assert report["errors"] == ["danger-full-access did not capture PowerShell command output"]


def test_remote_temp_script_path_uses_remote_temp_probe(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="C:\\Temp\\\n", stderr="")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    remote = gate.remote_temp_script_path(
        target="user@" + ".".join(["10", "0", "0", "96"]),
        identity=None,
        sandbox="danger-full-access",
        timeout=30,
    )

    assert remote == "C:/Temp/windows_codex_qa_danger-full-access.ps1"
    assert calls[0][0][-1] == 'powershell -NoProfile -Command "[System.IO.Path]::GetTempPath()"'
