from __future__ import annotations

import json
import os

import prepare_windows_outbound_bootstrap as bootstrap


def test_bootstrap_script_uses_windows_outbound_tunnel_and_reverse_runtime_forward() -> None:
    body = bootstrap.bootstrap_ps1(
        ubuntu_target="ubuntu-user@ubuntu-host",
        node_id="windows-live-worker",
        tags="win",
        runtime_port=60053,
        token_placeholder="<token>",
    )

    assert "cross-host-tunnel.ps1" in body
    assert '"50051",' in body
    assert '"60053",' in body
    assert '$env:AO_WORKER_TAGS = "win"' in body
    assert "$env:AO_WORKER_RUNTIME_PUBLIC_URL" in body
    assert 'Join-Path $env:APPDATA "npm"' in body
    assert r'Join-Path $env:USERPROFILE ".cargo\bin\codex.exe"' in body
    assert "ao-operator-codex-forwarder.rs" in body
    assert "& $CodexExe --version | Out-Null" in body
    assert "$env:PATH" in body
    assert "ssh windows-v01" not in body


def test_write_outputs_keeps_real_token_out_of_committed_artifacts(tmp_path) -> None:
    report = bootstrap.write_outputs(
        output_dir=tmp_path,
        ubuntu_target="ubuntu-user@ubuntu-host",
        node_id="windows-live-worker",
        tags="win",
        runtime_port=60053,
        token_placeholder="<set AO_WORKER_ENROLLMENT_TOKEN>",
        secret_handoff=tmp_path.parent / "secret-token.env",
    )

    assert report["verdict"] == "READY_FOR_WINDOWS_INITIATED_RUN"
    script = (tmp_path / "bootstrap-windows-worker.ps1").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "windows-outbound-bootstrap.json").read_text(encoding="utf-8"))
    assert "<set AO_WORKER_ENROLLMENT_TOKEN>" in script
    assert manifest["codex_path_ready"] is True
    assert "secret-token" in manifest["secret_handoff"]
    assert "real-token" not in script
    if os.name != "nt":
        assert (tmp_path.parent / "secret-token.env").stat().st_mode & 0o777 == 0o600
