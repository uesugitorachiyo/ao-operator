from __future__ import annotations

import json
import os
from pathlib import Path

import check_provider_oauth_smoke as smoke


def _fake_binary(bin_dir: Path, name: str, output: str) -> None:
    if os.name == "nt":
        target = bin_dir / f"{name}.cmd"
        target.write_text(f"@echo off\r\necho {output}\r\n", encoding="utf-8")
    else:
        target = bin_dir / name
        target.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n", encoding="utf-8")
        target.chmod(0o755)


def _ready_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    return home


def test_provider_oauth_smoke_passes_with_cli_and_auth_markers(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "codex", "codex-cli 0.test")
    _fake_binary(bin_dir, "claude", "2.test (Claude Code)")

    report = smoke.build_report(
        root=tmp_path,
        home=_ready_home(tmp_path),
        env={"PATH": str(bin_dir)},
        path=str(bin_dir),
    )

    assert report["schema"] == "ao-operator/provider-oauth-smoke/v1"
    assert report["verdict"] == "PASS"
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False
    assert report["providers"]["codex"]["version"] == "codex-cli 0.test"
    assert report["providers"]["claude"]["auth_marker"] == "~/.claude/.credentials.json"


def test_provider_oauth_smoke_rejects_forbidden_api_key_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "codex", "codex-cli 0.test")
    _fake_binary(bin_dir, "claude", "2.test (Claude Code)")

    report = smoke.build_report(
        root=tmp_path,
        home=_ready_home(tmp_path),
        env={"PATH": str(bin_dir), "OPENAI_API_KEY": "redacted"},
        path=str(bin_dir),
    )

    assert report["verdict"] == "FAIL"
    assert "forbidden_env_present:OPENAI_API_KEY" in report["errors"]
    assert "redacted" not in json.dumps(report)


def test_provider_oauth_smoke_can_scope_to_codex_only(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "codex", "codex-cli 0.test")
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")

    report = smoke.build_report(
        root=tmp_path,
        home=home,
        env={"PATH": str(bin_dir)},
        path=str(bin_dir),
        selected_providers=["codex"],
    )

    assert report["verdict"] == "PASS"
    assert report["selected_providers"] == ["codex"]
    assert set(report["providers"]) == {"codex"}


def test_provider_oauth_smoke_cli_writes_json_and_markdown(tmp_path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "codex", "codex-cli 0.test")
    _fake_binary(bin_dir, "claude", "2.test (Claude Code)")
    home = _ready_home(tmp_path)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    output_json = tmp_path / "provider-smoke.json"
    output_md = tmp_path / "provider-smoke.md"

    code = smoke.main(
        [
            "--root",
            str(tmp_path),
            "--write-json",
            str(output_json),
            "--write-md",
            str(output_md),
            "--json",
        ]
    )

    assert code == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["verdict"] == "PASS"
    assert "Provider OAuth Smoke" in output_md.read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
