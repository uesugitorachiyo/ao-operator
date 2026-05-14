#!/usr/bin/env python3
"""Agent OS router default state-version gate.

Proves that the Agent OS mission router CLI defaults to ``state v2`` while
remaining backward-compatible with explicit ``--state-version v1`` callers.

The gate inspects ``scripts/agent_os_router.py`` argparse default and runs
three deterministic CLI invocations:

* default invocation (no ``--state-version``) — must emit
  ``ao-operator/agent-os-state/v2`` with ``architecture_ready=true`` when the
  required architecture readiness artifact passes.
* explicit ``--state-version v1`` invocation — must still emit
  ``ao-operator/agent-os-state/v1``.
* explicit ``--state-version v2`` invocation — must match the default
  invocation's schema.

The gate never invokes AO or provider CLIs and never authorizes dispatch.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_router

ROOT = Path(__file__).resolve().parents[1]
ROUTER_SOURCE = "scripts/agent_os_router.py"
DEFAULT_BRIEF = "examples/agent-os/mission-router-state-brief.md"
DEFAULT_READINESS = (
    "run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json"
)
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "agent-os-router-default-state-version.json"
)
SCHEMA = "ao-operator/agent-os-router-default-state-version/v1"
STATE_SCHEMA_V1 = "ao-operator/agent-os-state/v1"
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"

CASE_IDS = (
    "default_emits_state_v2",
    "explicit_v1_remains_supported",
    "explicit_v2_matches_default",
)


def resolve_path(root: Path, value: str | Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def parse_state_version_default(source: str) -> str | None:
    pattern = re.compile(
        r'parser\.add_argument\(\s*"--state-version".*?default\s*=\s*"(v[12])"',
        re.DOTALL,
    )
    match = pattern.search(source)
    return match.group(1) if match else None


def run_router(
    *,
    brief: Path,
    readiness: Path,
    write_state: Path,
    state_version: str | None,
) -> tuple[int, dict[str, Any]]:
    argv = ["--brief", str(brief), "--label", "release"]
    if state_version is not None:
        argv += ["--state-version", state_version]
    argv += [
        "--architecture-readiness",
        str(readiness),
        "--write-state",
        str(write_state),
        "--json",
    ]
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        code = agent_os_router.main(argv)
    payload = (
        json.loads(write_state.read_text(encoding="utf-8"))
        if write_state.exists()
        else {}
    )
    return code, payload


def evaluate(*, root: Path, brief: Path, readiness: Path, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    router_source = (root / ROUTER_SOURCE).read_text(encoding="utf-8")
    parsed_default = parse_state_version_default(router_source)

    cases: list[dict[str, Any]] = []
    errors: list[str] = []

    if parsed_default != "v2":
        errors.append(
            f"router argparse default for --state-version must be 'v2', got {parsed_default!r}"
        )

    state_default = work_dir / "state-default.json"
    state_v1 = work_dir / "state-v1.json"
    state_v2 = work_dir / "state-v2.json"

    code_default, payload_default = run_router(
        brief=brief,
        readiness=readiness,
        write_state=state_default,
        state_version=None,
    )
    default_schema = payload_default.get("schema")
    default_pass = (
        code_default == 0
        and default_schema == STATE_SCHEMA_V2
        and payload_default.get("architecture_ready") is True
        and payload_default.get("dispatch_authorized") is False
        and payload_default.get("live_providers_run") is False
    )
    if not default_pass:
        errors.append("default router invocation must emit state v2 PASS")
    cases.append(
        {
            "id": "default_emits_state_v2",
            "observed_verdict": "PASS" if default_pass else "FAIL",
            "observed_schema": default_schema,
            "exit_code": code_default,
            "dispatch_authorized": False,
            "live_providers_run": False,
        }
    )

    code_v1, payload_v1 = run_router(
        brief=brief,
        readiness=readiness,
        write_state=state_v1,
        state_version="v1",
    )
    v1_schema = payload_v1.get("schema")
    v1_pass = (
        code_v1 == 0
        and v1_schema == STATE_SCHEMA_V1
        and payload_v1.get("live_providers_run") is False
    )
    if not v1_pass:
        errors.append("explicit --state-version v1 must still emit state v1")
    cases.append(
        {
            "id": "explicit_v1_remains_supported",
            "observed_verdict": "PASS" if v1_pass else "FAIL",
            "observed_schema": v1_schema,
            "exit_code": code_v1,
            "dispatch_authorized": False,
            "live_providers_run": False,
        }
    )

    code_v2, payload_v2 = run_router(
        brief=brief,
        readiness=readiness,
        write_state=state_v2,
        state_version="v2",
    )
    v2_schema = payload_v2.get("schema")
    v2_matches_default = (
        code_v2 == 0
        and v2_schema == default_schema
        and v2_schema == STATE_SCHEMA_V2
    )
    if not v2_matches_default:
        errors.append("explicit --state-version v2 must match default invocation schema")
    cases.append(
        {
            "id": "explicit_v2_matches_default",
            "observed_verdict": "PASS" if v2_matches_default else "FAIL",
            "observed_schema": v2_schema,
            "exit_code": code_v2,
            "dispatch_authorized": False,
            "live_providers_run": False,
        }
    )

    overall_pass = not errors
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if overall_pass else "FAIL",
        "router_source": ROUTER_SOURCE,
        "argparse_default": parsed_default,
        "case_count": len(cases),
        "case_ids": list(CASE_IDS),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Router default state-version is v2 with v1 backward-compat preserved; continue Agent OS architecture work."
            if overall_pass
            else "Fix router default state-version blockers before continuing."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(
    *,
    root: Path = ROOT,
    brief: Path | None = None,
    readiness: Path | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    brief_path = resolve_path(root, brief) if brief else resolve_path(root, DEFAULT_BRIEF)
    readiness_path = (
        resolve_path(root, readiness) if readiness else resolve_path(root, DEFAULT_READINESS)
    )
    if work_dir is not None:
        return evaluate(root=root, brief=brief_path, readiness=readiness_path, work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-router-default-state-version-") as tmp:
        return evaluate(root=root, brief=brief_path, readiness=readiness_path, work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--brief", type=Path, default=Path(DEFAULT_BRIEF))
    parser.add_argument("--architecture-readiness", type=Path, default=Path(DEFAULT_READINESS))
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    brief_path = resolve_path(root, args.brief)
    readiness_path = resolve_path(root, args.architecture_readiness)

    if args.work_dir is not None:
        payload = evaluate(root=root, brief=brief_path, readiness=readiness_path, work_dir=args.work_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="ao-operator-router-default-state-version-") as tmp:
            payload = evaluate(root=root, brief=brief_path, readiness=readiness_path, work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(root, args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(root, output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
