#!/usr/bin/env python3
"""Check local readiness before the bounded Remote Transfer v2 live run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
DEFAULT_CONTRACT = "examples/remote-transfer-v2-stress/spec-forge.live.contract.json"
DEFAULT_TOPOLOGY = "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml"
MAX_CAPTURE_CHARS = 12000


def compact(text: str) -> str:
    return text if len(text) <= MAX_CAPTURE_CHARS else text[: MAX_CAPTURE_CHARS - 3] + "..."


def command_env(ao_runtime_path: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if ao_runtime_path:
        env["FACTORY_V3_AO_RUNTIME_PATH"] = ao_runtime_path
        release = str(Path(ao_runtime_path) / "target" / "release")
        env["PATH"] = os.pathsep.join([release, env.get("PATH", "")])
    return env


def run_command(command: list[str], *, root: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = parse_json(result.stdout)
    return {
        "command": command,
        "exit": result.returncode,
        "json_verdict": payload.get("verdict") if payload else None,
        "stdout": compact(result.stdout),
        "stderr": compact(result.stderr),
    }


def parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def expected_verdict_ok(report: dict[str, Any], expected: str | None) -> bool:
    if expected is None:
        return True
    if report.get("json_verdict") == expected:
        return True
    payload = parse_json(str(report.get("stdout") or ""))
    return bool(payload and payload.get("verdict") == expected)


def check_command(
    check_id: str,
    command: list[str],
    *,
    root: Path,
    env: dict[str, str],
    expected_exit: int,
    expected_verdict: str | None = None,
    runner=None,
) -> dict[str, Any]:
    if runner is None:
        runner = run_command
    report = runner(command, root=root, env=env)
    exit_ok = report["exit"] == expected_exit
    verdict_ok = expected_verdict_ok(report, expected_verdict)
    status = "PASS" if exit_ok and verdict_ok else "FAIL"
    return {
        "id": check_id,
        "status": status,
        "expected_exit": expected_exit,
        "expected_verdict": expected_verdict,
        "report": report,
    }


def check_readiness(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    manifest: str = DEFAULT_MANIFEST,
    contract: str = DEFAULT_CONTRACT,
    topology: str = DEFAULT_TOPOLOGY,
    ao_runtime_path: str | None = None,
    runner=None,
) -> dict[str, Any]:
    if runner is None:
        runner = run_command
    env = command_env(ao_runtime_path)
    py = sys.executable
    checks = [
        check_command(
            "doctor.pass",
            [py, "scripts/factory_doctor.py", "--json"],
            root=root,
            env=env,
            expected_exit=0,
            expected_verdict="PASS",
            runner=runner,
        ),
        check_command(
            "intake.pass",
            [py, "scripts/validate_intake.py", contract, "--json"],
            root=root,
            env=env,
            expected_exit=0,
            expected_verdict="PASS",
            runner=runner,
        ),
        check_command(
            "factory.pass",
            [
                py,
                "scripts/validate_factory.py",
                "--slug",
                slug,
                "--topology",
                topology,
                "--contract",
                contract,
                "--json",
            ],
            root=root,
            env=env,
            expected_exit=0,
            expected_verdict="PASS",
            runner=runner,
        ),
        check_command(
            "live_slice.blocked_without_allow_live",
            [py, "scripts/run_operator_slice.py", manifest, "--slice", "17-run-bounded-live-10", "--json"],
            root=root,
            env=env,
            expected_exit=1,
            expected_verdict="BLOCKED",
            runner=runner,
        ),
        check_command(
            "acceptance.fails_before_live",
            [py, "scripts/check_live_acceptance.py", "--slug", slug, "--json"],
            root=root,
            env=env,
            expected_exit=1,
            expected_verdict="FAIL",
            runner=runner,
        ),
    ]
    verdict = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    return {
        "verdict": verdict,
        "slug": slug,
        "mode": "pre-live-readiness",
        "live_providers_run": False,
        "ao_runtime_path": ao_runtime_path or "",
        "checks": checks,
    }


def summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        report = check.get("report", {})
        if not isinstance(report, dict):
            report = {}
        checks.append(
            {
                "id": check.get("id"),
                "status": check.get("status"),
                "expected_exit": check.get("expected_exit"),
                "actual_exit": report.get("exit"),
                "expected_verdict": check.get("expected_verdict"),
                "actual_verdict": report.get("json_verdict"),
            }
        )
    return {
        "schema": "ao-operator/bounded-live-readiness-summary/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": payload.get("verdict"),
        "slug": payload.get("slug"),
        "mode": payload.get("mode"),
        "live_providers_run": payload.get("live_providers_run"),
        "ao_runtime_path": payload.get("ao_runtime_path"),
        "checks": checks,
        "concerns": [
            "This is pre-live readiness evidence only.",
            "Live acceptance is expected to fail until a real bounded live run writes accepted artifacts.",
            "Do not treat this summary as successful live evidence.",
        ],
    }


def default_summary_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "readiness" / "bounded-live-preflight-summary.json"


def write_summary(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"slug={payload['slug']}",
        f"mode={payload['mode']}",
        f"live_providers_run={str(payload['live_providers_run']).lower()}",
    ]
    for check in payload["checks"]:
        report = check["report"]
        lines.append(f"{check['status']} {check['id']}: exit={report['exit']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check bounded live pre-dispatch readiness")
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ao-runtime-path", default=os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", ""))
    parser.add_argument(
        "--write-summary",
        nargs="?",
        const="",
        help="Write sanitized summary JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_readiness(
        root=args.root,
        slug=args.slug,
        manifest=args.manifest,
        contract=args.contract,
        topology=args.topology,
        ao_runtime_path=args.ao_runtime_path or None,
    )
    summary_path = None
    if args.write_summary is not None:
        summary_path = Path(args.write_summary) if args.write_summary else default_summary_path(args.root, args.slug)
        if not summary_path.is_absolute():
            summary_path = args.root / summary_path
        write_summary(summary_path, summary_payload(payload))
        payload["summary"] = str(summary_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
