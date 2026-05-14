#!/usr/bin/env python3
"""Deterministic AO Runtime adapter for AO Operator.

This module is the boundary between the Factory runner control plane and AO
Runtime's execution plane. It intentionally contains no agentic decision logic.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def run_command(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int = 3600,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        timeout_note = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        stderr = (stderr + "\n" + timeout_note).strip()
        return subprocess.CompletedProcess(cmd, 124, stdout, stderr)


def resolve_ao_binary(*, default_runtime: Path) -> str:
    override = os.environ.get("FACTORY_V3_AO_BIN") or os.environ.get("AO_BIN")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(override)
        if found:
            return found
        raise FileNotFoundError(f"AO binary override not found: {override}")

    runtime_override = os.environ.get("FACTORY_V3_AO_RUNTIME_PATH")
    if runtime_override:
        runtime = Path(runtime_override)
        candidate = runtime / "target" / "release" / "ao" if runtime.is_dir() else runtime
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(
            f"AO runtime override did not contain target/release/ao: {runtime_override}"
        )

    candidate = default_runtime / "target" / "release" / "ao"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("ao")
    if found:
        return found
    raise FileNotFoundError("ao binary not found; set FACTORY_V3_AO_RUNTIME_PATH or add ao to PATH")


def ensure_ao_home(ao_bin: str, ao_home: Path, *, cwd: Path) -> None:
    ao_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AO_HOME"] = str(ao_home)
    if not (ao_home / "config.yaml").exists():
        run_command([ao_bin, "init"], cwd, env, timeout=60)


def extract_run_id(text: str) -> str:
    match = re.search(r"\brun\s+(r-[a-zA-Z0-9_.:-]+)\b", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(r-[a-zA-Z0-9_.:-]+)\b", text)
    return match.group(1) if match else "unknown"


def collect_events(
    ao_bin: str,
    ao_home: Path,
    run_id: str,
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str] | None:
    if run_id == "unknown":
        return None
    env = os.environ.copy()
    env["AO_HOME"] = str(ao_home)
    result = run_command([ao_bin, "run", run_id, "events"], cwd, env, timeout=180)
    if result.returncode == 0:
        return result
    alt = run_command([ao_bin, "runs", "events", run_id], cwd, env, timeout=180)
    return alt if alt.returncode == 0 else result
