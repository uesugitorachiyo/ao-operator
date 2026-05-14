#!/usr/bin/env python3
"""Validate cross-host worker TLS and tunnel posture artifacts.

This check is intentionally static. Ubuntu cannot reliably execute Mac or
MDM-managed Windows worker lanes directly, so the repo keeps the operator
contract executable by checking the committed runbooks, bootstrap files, and
tunnel scripts that those hosts consume.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    id: str
    path: str
    needles: tuple[str, ...]
    description: str


CHECKS: tuple[Check, ...] = (
    Check(
        id="runbook.coordinator_tls_config",
        path="docs/cross-host-setup.md",
        needles=(
            "[coordinator.tls]",
            "AO_DAEMON_COORDINATOR_TLS_CERT",
            "AO_DAEMON_COORDINATOR_TLS_KEY",
            "AO_DAEMON_COORDINATOR_MTLS_CA",
        ),
        description="Runbook documents daemon-owned coordinator TLS/mTLS config.",
    ),
    Check(
        id="runbook.worker_coordinator_tls_env",
        path="docs/cross-host-setup.md",
        needles=(
            "AO_COORDINATOR_TLS_CA",
            "AO_COORDINATOR_TLS_CLIENT_CERT",
            "AO_COORDINATOR_TLS_CLIENT_KEY",
            "AO_COORDINATOR_TLS_DOMAIN_NAME",
        ),
        description="Runbook documents worker-to-coordinator client TLS env.",
    ),
    Check(
        id="runbook.forbids_plain_lan",
        path="docs/cross-host-setup.md",
        needles=("Plain LAN exposure of unauthenticated write-capable endpoints is forbidden",),
        description="Runbook forbids unauthenticated write-capable LAN exposure.",
    ),
    Check(
        id="runbook.worker_runtime_guard",
        path="docs/cross-host-setup.md",
        needles=(
            "AO_WORKER_RUNTIME_BIND",
            "AO_WORKER_RUNTIME_NON_LOOPBACK_AUTH=authenticated-reverse-tunnel",
            "AO_WORKER_RUNTIME_TLS_CERT",
        ),
        description="Runbook documents worker RuntimeService non-loopback guard.",
    ),
    Check(
        id="tunnel.sh.reverse_forward_loopback",
        path="scripts/cross-host-tunnel.sh",
        needles=('-R "${worker_runtime_remote_port}:127.0.0.1:${worker_runtime_local_port}"',),
        description="Unix tunnel reverse-forwards worker RuntimeService to loopback only.",
    ),
    Check(
        id="tunnel.ps1.reverse_forward_loopback",
        path="scripts/cross-host-tunnel.ps1",
        needles=('"${WorkerRuntimeRemotePort}:127.0.0.1:${WorkerRuntimeLocalPort}"',),
        description="Windows tunnel reverse-forwards worker RuntimeService to loopback only.",
    ),
    Check(
        id="windows.generator.runtime_bind_loopback",
        path="scripts/prepare_windows_outbound_bootstrap.py",
        needles=(
            '$env:AO_WORKER_RUNTIME_BIND = "127.0.0.1:{runtime_port}"',
            '$env:AO_WORKER_RUNTIME_PUBLIC_URL = "http://127.0.0.1:{runtime_port}"',
        ),
        description="Windows bootstrap generator keeps RuntimeService on loopback.",
    ),
    Check(
        id="windows.artifact.runtime_bind_loopback",
        path="run-artifacts/release-v0.2/windows-outbound-bootstrap/bootstrap-windows-worker.ps1",
        needles=(
            '$env:AO_WORKER_RUNTIME_BIND = "127.0.0.1:60053"',
            '$env:AO_WORKER_RUNTIME_PUBLIC_URL = "http://127.0.0.1:60053"',
        ),
        description="Committed Windows bootstrap keeps RuntimeService on loopback.",
    ),
    Check(
        id="windows.artifact.reverse_forward_ports",
        path="run-artifacts/release-v0.2/windows-outbound-bootstrap/bootstrap-windows-worker.ps1",
        needles=(
            '"50051"',
            '"60053"',
            "scripts\\cross-host-tunnel.ps1",
        ),
        description="Committed Windows bootstrap starts coordinator and runtime tunnel ports.",
    ),
    Check(
        id="windows.status.mdm_outbound_topology",
        path="run-artifacts/release-v0.2/windows-outbound-bootstrap/windows-live-validation-progress.md",
        needles=(
            "Windows-started tunnel",
            "`-L 50051:127.0.0.1:50051`",
            "`-R 60053:127.0.0.1:60053`",
            "runtime bind `127.0.0.1:60053`",
        ),
        description="Windows live evidence records outbound SSH and loopback RuntimeService.",
    ),
    Check(
        id="tls.posture.baseline",
        path="run-artifacts/release-v0.2/ao-runtime-tls-posture.md",
        needles=(
            "e5a2b0dd",
            "15afe91f",
            "d9eb68a",
            "0cdcdd2",
            "0c5850b",
            "c47d7e4",
            "383bb56",
            "AO_WORKER_RUNTIME_TLS_CERT",
            "AO_COORDINATOR_TLS_CA",
            "[coordinator.tls]",
            "WAL HTTP is guarded to loopback",
            "[coordinator.wal_http.tls]",
            "AO_WAL_HTTP_TLS_CERT",
            "AO_WAL_HTTP_TLS_KEY",
            "publishers reject non-loopback binds",
            "followers reject non-loopback plain-HTTP WAL endpoints",
            "Plain WAL HTTP remains loopback-only",
            "Direct-network WAL replication uses `https://.../replication/wal`",
            "ao-runtime/advertised-primary/v1",
            "--expected-sha256",
            "non-loopback `http://` advertised-primary URLs are rejected",
            "oversized advertised-primary rejection before replica config mutation",
            "structured Mac launchd plist and Windows Task Scheduler XML parsing",
            "native Mac launchd installed-worker validation",
            "Windows native Task Scheduler validation remains blocked from Ubuntu",
        ),
        description="TLS posture records AO Runtime baseline, WAL HTTP loopback guard, and advertised-primary discovery.",
    ),
    Check(
        id="live.validation.references_tls_posture",
        path="run-artifacts/release-v0.2/LIVE-VALIDATION.md",
        needles=(
            "AO Runtime TLS posture",
            "Loopback plus",
            "authenticated SSH tunnels remains valid",
            "non-loopback worker RuntimeService bind requires TLS",
        ),
        description="Live validation status points operators to the secure transport posture.",
    ),
)


def _read_text(path: str) -> tuple[str | None, str | None]:
    candidate = Path(path) if path.startswith("/") else ROOT / path
    try:
        return candidate.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, str(exc)


def run_checks(checks: Iterable[Check] = CHECKS) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for check in checks:
        text, error = _read_text(check.path)
        missing: list[str] = []
        if text is None:
            missing = list(check.needles)
        else:
            missing = [needle for needle in check.needles if needle not in text]
        status = "PASS" if not missing and error is None else "FAIL"
        result: dict[str, object] = {
            "id": check.id,
            "status": status,
            "path": check.path,
            "description": check.description,
        }
        if error:
            result["error"] = error
        if missing:
            result["missing"] = missing
        results.append(result)

    verdict = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    return {"verdict": verdict, "checks": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    payload = run_checks()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"cross-host TLS posture: {payload['verdict']}")
        for check in payload["checks"]:
            print(f"{check['status']} {check['id']} ({check['path']})")
            for missing in check.get("missing", []):
                print(f"  missing: {missing}")
            if "error" in check:
                print(f"  error: {check['error']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
