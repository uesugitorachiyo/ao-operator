from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_cross_host_tunnel_sh_syntax() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash is not available on this host")
    result = subprocess.run(
        ["bash", "-n", "scripts/cross-host-tunnel.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cross_host_tunnel_sh_uses_autossh_monitor_only_for_autossh() -> None:
    body = (ROOT / "scripts" / "cross-host-tunnel.sh").read_text(encoding="utf-8")
    assert 'exec autossh -M 0 "${ssh_args[@]}" "$ssh_host"' in body
    assert 'exec ssh "${ssh_args[@]}" "$ssh_host"' in body


def test_cross_host_tunnel_sh_supports_worker_runtime_reverse_forward() -> None:
    body = (ROOT / "scripts" / "cross-host-tunnel.sh").read_text(encoding="utf-8")
    assert "FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT" in body
    assert '-R "${worker_runtime_remote_port}:127.0.0.1:${worker_runtime_local_port}"' in body


def test_cross_host_tunnel_ps1_has_open_ssh_loop() -> None:
    body = (ROOT / "scripts" / "cross-host-tunnel.ps1").read_text(encoding="utf-8")
    assert "Get-Command ssh.exe" in body
    assert "ServerAliveInterval=30" in body
    assert "ServerAliveCountMax=3" in body
    assert "ExitOnForwardFailure=yes" in body
    assert "FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT" in body
    assert '"-R", "${WorkerRuntimeRemotePort}:127.0.0.1:${WorkerRuntimeLocalPort}"' in body
    assert "Start-Sleep -Seconds 5" in body
