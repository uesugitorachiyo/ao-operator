#!/usr/bin/env python3
"""Check native Windows Codex shell-runner behavior over SSH.

This is a live release gate. It intentionally compares the two Codex sandbox
modes that matter for AO Operator's Windows worker proof:

- workspace-write: currently times out on native Windows before the runner pipe
  connects.
- danger-full-access: permits the PowerShell command runner to execute and lets
  the role return sanitized OS evidence.

The gate does not expose hostnames, usernames, private paths, private IPs, or
provider credentials in its committed output.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/windows-codex-shell-runner-qa/v1"
DEFAULT_OUTPUT = ROOT / "run-artifacts/windows-codex-shell-runner-qa-20260514.json"


@dataclass(frozen=True)
class SandboxResult:
    sandbox: str
    exit_code: int
    status_result: str
    powershell_returned_text: bool
    runner_pipe_timeout: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "sandbox": self.sandbox,
            "exit_code": self.exit_code,
            "status_result": self.status_result,
            "powershell_returned_text": self.powershell_returned_text,
            "runner_pipe_timeout": self.runner_pipe_timeout,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact_target(target: str) -> str:
    if "@" in target:
        return "<redacted-user>@<redacted-host>"
    return "<redacted-host>"


def ssh_base(identity: Path | None, target: str) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    if identity is not None:
        command.extend(["-i", str(identity.expanduser())])
    command.append(target)
    return command


def codex_probe_script(sandbox: str) -> str:
    return f"""$ErrorActionPreference = "Stop"
$dir = Join-Path $env:TEMP 'ao-windows-codex-shell-runner-qa-{sandbox}'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Set-Location $dir
Remove-Item -Force result.md -ErrorAction SilentlyContinue
$prompt = @'
Run this exact PowerShell command: [System.Environment]::OSVersion.VersionString
Then write exactly one file named result.md with:
Result: DONE
Artifact: result.md
Evidence:
- powershell probe returned text: yes/no
Concerns:
- none unless the command failed
Blocker: none
Do not include hostname, username, private paths, or IP addresses.
'@
$prompt | codex exec --model gpt-5.5 --json --skip-git-repo-check --sandbox {sandbox}
if (Test-Path result.md) {{ Get-Content result.md }} else {{ 'NO_RESULT_FILE' }}
"""


def remote_temp_script_path(*, target: str, identity: Path | None, sandbox: str, timeout: int) -> str:
    proc = subprocess.run(
        ssh_base(identity, target)
        + ['powershell -NoProfile -Command "[System.IO.Path]::GetTempPath()"'],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    temp_dir = proc.stdout.strip().splitlines()[-1].strip().replace("\\", "/").rstrip("/")
    if not temp_dir:
        raise RuntimeError("Windows temp directory probe returned no path")
    return f"{temp_dir}/windows_codex_qa_{sandbox}.ps1"


def parse_sandbox_result(sandbox: str, exit_code: int, stdout: str, stderr: str) -> SandboxResult:
    text = stdout + "\n" + stderr
    result_match = re.search(r"(?m)^Result:\s*([A-Z_]+)\s*$", text)
    returned_yes = re.search(r"(?mi)powershell probe returned text:\s*yes\s*$", text) is not None
    return SandboxResult(
        sandbox=sandbox,
        exit_code=exit_code,
        status_result=result_match.group(1) if result_match else "",
        powershell_returned_text=returned_yes,
        runner_pipe_timeout="windows sandbox: timed out" in text
        and "runner pipe-in" in text,
    )


def run_remote_probe(*, target: str, identity: Path | None, sandbox: str, timeout: int) -> SandboxResult:
    with tempfile.TemporaryDirectory(prefix="ao-windows-codex-qa-") as tmp:
        script = Path(tmp) / f"windows_codex_qa_{sandbox}.ps1"
        script.write_text(codex_probe_script(sandbox), encoding="utf-8")
        remote = remote_temp_script_path(
            target=target,
            identity=identity,
            sandbox=sandbox,
            timeout=timeout,
        )
        scp_command = ["scp"]
        if identity is not None:
            scp_command.extend(["-i", str(identity.expanduser())])
        scp_command.extend(["-q", str(script), f"{target}:{remote}"])
        subprocess.run(
            scp_command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        proc = subprocess.run(
            ssh_base(identity, target)
            + [f"powershell -NoProfile -ExecutionPolicy Bypass -File {remote}"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    return parse_sandbox_result(sandbox, proc.returncode, proc.stdout, proc.stderr)


def build_report(results: list[SandboxResult], *, target: str) -> dict[str, Any]:
    by_sandbox = {result.sandbox: result for result in results}
    workspace = by_sandbox.get("workspace-write")
    danger = by_sandbox.get("danger-full-access")
    errors: list[str] = []
    if workspace is None:
        errors.append("workspace-write result missing")
    elif not workspace.runner_pipe_timeout:
        errors.append("workspace-write did not reproduce runner pipe timeout")
    if danger is None:
        errors.append("danger-full-access result missing")
    elif danger.status_result != "DONE" or not danger.powershell_returned_text:
        errors.append("danger-full-access did not capture PowerShell command output")
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "target": redact_target(target),
        "results": [result.to_json() for result in results],
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "recommended_factory_v3_action": (
            "Use codex_sandbox=danger-full-access only for native Windows live-dispatch roles "
            "until Codex workspace-write shell runner is fixed on Windows."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-target", required=True)
    parser.add_argument("--windows-identity", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = [
        run_remote_probe(
            target=args.windows_target,
            identity=args.windows_identity,
            sandbox="workspace-write",
            timeout=args.timeout,
        ),
        run_remote_probe(
            target=args.windows_target,
            identity=args.windows_identity,
            sandbox="danger-full-access",
            timeout=args.timeout,
        ),
    ]
    report = build_report(results, target=args.windows_target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"verdict={report['verdict']}")
        for error in report["errors"]:
            print(f"error={error}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
