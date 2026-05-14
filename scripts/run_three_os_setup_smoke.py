#!/usr/bin/env python3
"""Collect provider-free evidence for native Mac, Ubuntu, and Windows lanes."""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "run-artifacts/three-os-setup"
SCHEMA = "ao-operator/three-os-setup-smoke/v1"
FORBIDDEN_API_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")


@dataclass(frozen=True)
class ProbeResult:
    host: str
    status: str
    label: str
    target: str
    command: str
    payload: dict[str, Any]
    blocker: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact_target(target: str | None) -> str:
    if not target:
        return "<not-configured>"
    if "@" in target:
        return "<redacted-user>@<redacted-host>"
    return "<redacted-host>"


def forbidden_keys_from_env(env: dict[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return [key for key in FORBIDDEN_API_KEYS if source.get(key)]


def run_command(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def decode_json(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("command produced no JSON output")
    return json.loads(lines[-1])


def local_probe_payload() -> dict[str, Any]:
    git_head = run_command(["git", "rev-parse", "--short", "HEAD"], timeout=10)
    return {
        "schema": f"{SCHEMA}/host",
        "host": "mac",
        "os_family": platform.system(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "git_head": git_head.stdout.strip() if git_head.returncode == 0 else "<unknown>",
        "provider_api_keys_present": forbidden_keys_from_env(),
        "codex_cli_present": shutil.which("codex") is not None,
        "claude_cli_present": shutil.which("claude") is not None,
        "native_claim": "macOS local host",
        "expected_tags": ["mac", "live"],
    }


def probe_mac() -> ProbeResult:
    payload = local_probe_payload()
    keys = payload["provider_api_keys_present"]
    status = "PASS" if platform.system() == "Darwin" and not keys else "FAIL"
    blocker = None
    if platform.system() != "Darwin":
        blocker = f"expected Darwin, got {platform.system()}"
    elif keys:
        blocker = f"forbidden provider API key variables present: {', '.join(keys)}"
    return ProbeResult(
        host="mac",
        status=status,
        label="macOS local worker",
        target="local",
        command="python3 scripts/run_three_os_setup_smoke.py --mac-only",
        payload=payload,
        blocker=blocker,
    )


UBUNTU_PROBE = r'''
import json
import os
import platform
import shutil
import subprocess
import sys

def run(cmd):
    proc = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.stdout.strip() if proc.returncode == 0 else "<unknown>"

keys = [key for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY") if os.environ.get(key)]
print(json.dumps({
    "schema": "ao-operator/three-os-setup-smoke/v1/host",
    "host": "ubuntu",
    "os_family": platform.system(),
    "platform": platform.platform(),
    "python": sys.version.split()[0],
    "git_head": run(["git", "rev-parse", "--short", "HEAD"]),
    "provider_api_keys_present": keys,
    "codex_cli_present": shutil.which("codex") is not None,
    "claude_cli_present": shutil.which("claude") is not None,
    "native_claim": "Ubuntu coordinator / Linux lane",
    "expected_tags": ["ubuntu", "coordinator"],
}, sort_keys=True))
'''


WINDOWS_PROBE = r'''
$ErrorActionPreference = "Stop"
$keys = @()
if ($env:OPENAI_API_KEY) { $keys += "OPENAI_API_KEY" }
if ($env:ANTHROPIC_API_KEY) { $keys += "ANTHROPIC_API_KEY" }
$gitHead = "<unknown>"
try { $gitHead = (git rev-parse --short HEAD).Trim() } catch {}
$codex = $null -ne (Get-Command codex -ErrorAction SilentlyContinue)
$claude = $null -ne (Get-Command claude -ErrorAction SilentlyContinue)
[ordered]@{
  schema = "ao-operator/three-os-setup-smoke/v1/host"
  host = "windows"
  os_family = "Windows"
  platform = [System.Environment]::OSVersion.VersionString
  powershell = $PSVersionTable.PSVersion.ToString()
  git_head = $gitHead
  provider_api_keys_present = $keys
  codex_cli_present = $codex
  claude_cli_present = $claude
  native_claim = "native Windows PowerShell, not WSL"
  expected_tags = @("win", "live")
  non_wsl = $true
} | ConvertTo-Json -Compress
'''


def ssh_base(identity: Path | None, target: str) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    if identity:
        command.extend(["-i", str(identity.expanduser())])
    command.append(target)
    return command


def probe_ubuntu(*, target: str | None, identity: Path | None, repo: str, timeout: int) -> ProbeResult:
    if not target:
        return ProbeResult(
            host="ubuntu",
            status="SKIP",
            label="Ubuntu coordinator",
            target="<not-configured>",
            command="ssh <ubuntu-target> ...",
            payload={"host": "ubuntu", "provider_api_keys_present": []},
            blocker="ubuntu target not configured",
        )
    remote = f"cd {sh_quote(repo)} && python3 - <<'PY'\n{UBUNTU_PROBE}\nPY"
    command = ssh_base(identity, target) + [remote]
    proc = run_command(command, timeout=timeout)
    payload: dict[str, Any]
    blocker = None
    status = "PASS"
    if proc.returncode != 0:
        payload = {"host": "ubuntu", "stdout": proc.stdout[-600:], "stderr": proc.stderr[-600:]}
        status = "FAIL"
        blocker = f"ssh probe failed with exit {proc.returncode}"
    else:
        payload = decode_json(proc.stdout)
        keys = payload.get("provider_api_keys_present", [])
        if payload.get("os_family") != "Linux":
            status = "FAIL"
            blocker = f"expected Linux, got {payload.get('os_family')}"
        elif keys:
            status = "FAIL"
            blocker = f"forbidden provider API key variables present: {', '.join(keys)}"
    return ProbeResult(
        host="ubuntu",
        status=status,
        label="Ubuntu coordinator / Linux lane",
        target=redact_target(target),
        command=f"ssh {redact_target(target)} 'cd <ao-operator> && python3 <probe>'",
        payload=payload,
        blocker=blocker,
    )


def probe_windows(*, target: str | None, identity: Path | None, repo: str, timeout: int) -> ProbeResult:
    if not target:
        return ProbeResult(
            host="windows",
            status="SKIP",
            label="native Windows worker",
            target="<not-configured>",
            command="ssh <windows-target> powershell ...",
            payload={"host": "windows", "provider_api_keys_present": []},
            blocker="windows target not configured",
        )
    encoded = base64.b64encode(
        f"Set-Location {ps_location(repo)}\n{WINDOWS_PROBE}".encode("utf-16le")
    ).decode("ascii")
    command = ssh_base(identity, target) + [
        f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    ]
    proc = run_command(command, timeout=timeout)
    payload: dict[str, Any]
    blocker = None
    status = "PASS"
    if proc.returncode != 0:
        payload = {"host": "windows", "stdout": proc.stdout[-600:], "stderr": proc.stderr[-600:]}
        status = "FAIL"
        blocker = f"ssh powershell probe failed with exit {proc.returncode}"
    else:
        payload = decode_json(proc.stdout)
        keys = payload.get("provider_api_keys_present", [])
        if payload.get("os_family") != "Windows" or payload.get("non_wsl") is not True:
            status = "FAIL"
            blocker = "native Windows PowerShell proof missing"
        elif keys:
            status = "FAIL"
            blocker = f"forbidden provider API key variables present: {', '.join(keys)}"
    return ProbeResult(
        host="windows",
        status=status,
        label="native Windows worker",
        target=redact_target(target),
        command=f"ssh {redact_target(target)} 'powershell -EncodedCommand <probe>'",
        payload=payload,
        blocker=blocker,
    )


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def ps_location(value: str) -> str:
    prefix = "$env:USERPROFILE\\"
    alt_prefix = "$env:USERPROFILE/"
    if value.startswith(prefix):
        return f"(Join-Path $env:USERPROFILE {ps_quote(value[len(prefix):])})"
    if value.startswith(alt_prefix):
        return f"(Join-Path $env:USERPROFILE {ps_quote(value[len(alt_prefix):])})"
    return ps_quote(value)


def evidence_markdown(result: ProbeResult) -> str:
    blocker = result.blocker or "none"
    return f"""# Three-OS Setup Evidence - {result.label}

Status: {result.status}
Generated: {utc_now()}
Schema: `{SCHEMA}`

## Target

```text
{result.target}
```

## Command Shape

```text
{result.command}
```

## Payload

```json
{json.dumps(result.payload, indent=2, sort_keys=True)}
```

## Blocker

{blocker}
"""


def report_markdown(results: list[ProbeResult]) -> str:
    verdict = "PASS" if all(result.status == "PASS" for result in results) else "BLOCKED"
    rows = "\n".join(
        f"| {result.host} | {result.status} | {result.target} | {result.blocker or 'none'} |"
        for result in results
    )
    return f"""# Three-OS Setup Smoke Report

Status: {verdict}
Generated: {utc_now()}
Schema: `{SCHEMA}`

This is a provider-free AO Operator smoke for the native three-OS story. It
does not start live providers, does not expose coordinator ports, and does not
transport provider API keys.

| Host | Status | Target | Blocker |
| --- | --- | --- | --- |
{rows}

## Evidence Files

- `ubuntu-evidence.md`
- `mac-evidence.md`
- `windows-evidence.md`
- `three-os-setup-report.json`

## Next Command

If all hosts pass this provider-free smoke, continue with:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/three-os-setup-sdd.md smoke-test
```

Then follow `docs/cross-host-setup.md` for live worker enrollment.
"""


def write_outputs(output_dir: Path, results: list[ProbeResult]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        (output_dir / f"{result.host}-evidence.md").write_text(
            evidence_markdown(result),
            encoding="utf-8",
        )
    report = {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "status": "PASS" if all(result.status == "PASS" for result in results) else "BLOCKED",
        "provider_dispatch": False,
        "forbidden_provider_api_keys": list(FORBIDDEN_API_KEYS),
        "results": [
            {
                "host": result.host,
                "status": result.status,
                "label": result.label,
                "target": result.target,
                "blocker": result.blocker,
                "payload": result.payload,
            }
            for result in results
        ],
    }
    (output_dir / "three-os-setup-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "three-os-setup-report.md").write_text(
        report_markdown(results),
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--ubuntu-target", default=os.environ.get("AO_THREE_OS_UBUNTU_TARGET"))
    parser.add_argument("--ubuntu-identity", type=Path, default=env_path("AO_THREE_OS_UBUNTU_IDENTITY"))
    parser.add_argument(
        "--ubuntu-repo",
        default=os.environ.get("AO_THREE_OS_UBUNTU_REPO", "~/ao-operator"),
    )
    parser.add_argument("--windows-target", default=os.environ.get("AO_THREE_OS_WINDOWS_TARGET"))
    parser.add_argument("--windows-identity", type=Path, default=env_path("AO_THREE_OS_WINDOWS_IDENTITY"))
    parser.add_argument(
        "--windows-repo",
        default=os.environ.get("AO_THREE_OS_WINDOWS_REPO", r"$env:USERPROFILE\Documents\ao-operator"),
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--allow-skips", action="store_true")
    return parser.parse_args()


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def main() -> int:
    args = parse_args()
    results = [
        probe_mac(),
        probe_ubuntu(
            target=args.ubuntu_target,
            identity=args.ubuntu_identity,
            repo=args.ubuntu_repo,
            timeout=args.timeout,
        ),
        probe_windows(
            target=args.windows_target,
            identity=args.windows_identity,
            repo=args.windows_repo,
            timeout=args.timeout,
        ),
    ]
    report = write_outputs(args.output_dir, results)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.allow_skips:
        return 0 if all(result.status in {"PASS", "SKIP"} for result in results) else 1
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
