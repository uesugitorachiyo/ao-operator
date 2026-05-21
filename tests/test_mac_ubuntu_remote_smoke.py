from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

import run_mac_ubuntu_remote_smoke as smoke


def test_build_payload_has_safe_manifest_without_provider_dispatch(tmp_path):
    manifest = smoke.build_payload(
        tmp_path,
        smoke_id="smoke-test",
        source_commit="abc123",
        target="nucx@10.0.0.138",
        extra_bytes=128,
    )

    assert manifest["provider_dispatch"] is False
    assert manifest["forbidden"]["provider_api_keys"] == ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    assert {entry["path"] for entry in manifest["entries"]} == {
        "docs/notes.md",
        "input.txt",
        "large.bin",
    }
    for entry in manifest["entries"]:
        assert smoke.safe_rel(entry["path"])
        path = tmp_path / "workspace" / entry["path"]
        assert entry["sha256"] == smoke.sha256_file(path)


def write_return(path: Path, *, body: bytes = b"ubuntu remote smoke artifact\n") -> Path:
    payload = {
        "schema": "ao-operator/mac-ubuntu-remote-smoke-return/v1",
        "verdict": "PASS",
        "smoke_id": "smoke-test",
        "source_commit": "abc123",
        "entries_checked": 2,
        "errors": [],
        "artifact": {
            "path": "ubuntu-artifact.txt",
            "size_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "contents_b64": base64.b64encode(body).decode("ascii"),
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validate_return_manifest_accepts_matching_artifact(tmp_path):
    path = write_return(tmp_path / "return.json")

    payload = smoke.validate_return_manifest(path, smoke_id="smoke-test", source_commit="abc123")

    assert payload["local_validation"] == "PASS"
    assert payload["local_validation_errors"] == []


def test_validate_return_manifest_rejects_artifact_hash_mismatch(tmp_path):
    path = write_return(tmp_path / "return.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(smoke.SmokeError, match="artifact sha256 mismatch"):
        smoke.validate_return_manifest(path, smoke_id="smoke-test", source_commit="abc123")


def test_remote_script_enforces_relative_paths_and_provider_false():
    script = smoke.remote_script()

    assert "provider_dispatch must be false" in script
    assert "rel.startswith(\"/\")" in script
    assert "Path(rel).parts" in script
    assert "symlink forbidden" in script
    assert "tar -xzf" not in script
    assert "safe_extract_bundle" in script


def test_ssh_options_require_pinned_host_key_policy():
    ssh = smoke.ssh_base("nucx", "10.0.0.138", Path("/tmp/id"))
    scp = smoke.scp_base(Path("/tmp/id"))

    assert "StrictHostKeyChecking=yes" in ssh
    assert "StrictHostKeyChecking=yes" in scp
    assert "StrictHostKeyChecking=accept-new" not in ssh
    assert "StrictHostKeyChecking=accept-new" not in scp


def test_git_head_uses_requested_root(tmp_path, monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})

        class Result:
            stdout = "abcdef123456\n"

        return Result()

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    assert smoke.git_head(tmp_path) == "abcdef123456"
    assert calls[0]["cwd"] == tmp_path


def test_interrupted_upload_cli_does_not_require_return_manifest(tmp_path, monkeypatch):
    payload = {
        "schema": smoke.SCHEMA,
        "verdict": "PASS",
        "mode": "interrupted-upload-cleanup",
        "remote_cleanup_absent": True,
    }
    monkeypatch.setattr(smoke, "simulate_interrupted_upload_cleanup", lambda **_: payload)

    out = tmp_path / "report.json"
    rc = smoke.main(["--simulate-interrupted-upload", "--write-report", str(out), "--write-return-manifest", str(tmp_path / "ignored.json")])

    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["mode"] == "interrupted-upload-cleanup"
    assert not (tmp_path / "ignored.json").exists()
