#!/usr/bin/env python3
"""Plan or execute validated AO Operator operator slices."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import validate_operator_slices


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples/remote-transfer-v2-stress/operator-slices.json"
MAX_CAPTURE_CHARS = 20000
REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"/home/[^\s\"']+/\.(?:codex|claude)(?:/[^\s\"']*)?"),
        "/home/[REDACTED_USER]/[REDACTED_PROVIDER_AUTH_PATH]",
    ),
    (
        re.compile(r"/tmp/ao-operator-ao-[^\s\"']+"),
        "/tmp/[REDACTED_AO_HOME]",
    ),
    (
        re.compile(r"(?i)\b(OPENAI_API_KEY|ANTHROPIC_API_KEY)\s*=\s*[^\s\"']+"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(access_token|refresh_token|session_token|api_key)([\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+"),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+"),
        r"\1[REDACTED]",
    ),
)


def _slice_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "")


def _slice_order(item: dict[str, Any]) -> int:
    value = item.get("order")
    return value if isinstance(value, int) else 0


def manifest_slices(data: dict[str, Any]) -> list[dict[str, Any]]:
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return []
    return sorted([item for item in slices if isinstance(item, dict)], key=_slice_order)


def select_slices(
    data: dict[str, Any],
    *,
    slice_id: str | None = None,
    from_slice: str | None = None,
    through: str | None = None,
    local_only: bool = False,
) -> list[dict[str, Any]]:
    slices = manifest_slices(data)
    if slice_id:
        selected = [item for item in slices if _slice_id(item) == slice_id]
    else:
        start_order = 0
        end_order: int | None = None
        if from_slice:
            start = find_slice(slices, from_slice)
            if start is None:
                selected = []
            else:
                start_order = _slice_order(start)
                selected = [item for item in slices if _slice_order(item) >= start_order]
        else:
            selected = slices
        if selected and through:
            target = find_slice(slices, through)
            if target is None:
                selected = []
            else:
                end_order = _slice_order(target)
                selected = [item for item in selected if start_order <= _slice_order(item) <= end_order]
        if from_slice and through and selected and end_order is not None and end_order < start_order:
            selected = []
    if local_only:
        selected = [item for item in selected if item.get("live_provider") is not True]
    return selected


def find_slice(slices: list[dict[str, Any]], selector: str) -> dict[str, Any] | None:
    return next((item for item in slices if _slice_id(item) == selector or str(_slice_order(item)) == selector), None)


def safety_blockers(item: dict[str, Any], *, allow_live: bool, allow_override: bool) -> list[str]:
    blockers: list[str] = []
    sid = _slice_id(item)
    if item.get("live_provider") is True and not allow_live:
        blockers.append(f"{sid}: live provider slice requires --allow-live")
    if item.get("requires_override") is True:
        approval_env = str(item.get("approval_env") or "FACTORY_V3_ALLOW_LARGE_LIVE_RUN")
        if not allow_override:
            blockers.append(f"{sid}: override-gated slice requires --allow-override")
        if os.environ.get(approval_env) != "1":
            blockers.append(f"{sid}: override-gated slice requires {approval_env}=1")
    return blockers


def compact(text: str) -> str:
    sanitized = sanitize_text(text)
    return sanitized if len(sanitized) <= MAX_CAPTURE_CHARS else sanitized[: MAX_CAPTURE_CHARS - 3] + "..."


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern, replacement in REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def command_env(item: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    values = item.get("env", {})
    if not isinstance(values, dict):
        return env
    path_prepend: list[str] = []
    for key, value in values.items():
        if not isinstance(key, str):
            continue
        if key == "PATH_PREPEND":
            if isinstance(value, str):
                path_prepend.append(value)
            elif isinstance(value, list):
                path_prepend.extend(str(item) for item in value if item)
            continue
        env[key] = str(value)
    if path_prepend:
        env["PATH"] = os.pathsep.join([*path_prepend, env.get("PATH", "")])
    return env


def _normalize_for_shlex(command: str) -> str:
    # POSIX shlex consumes backslashes as escape characters, which on
    # Windows mangles path arguments like C:\Users\op\file.txt. Pre-
    # escaping each backslash to `\\` lets POSIX shlex preserve them
    # while still stripping outer quotes correctly. Non-POSIX shlex is
    # NOT a viable alternative because it leaves outer quotes attached
    # to tokens, which breaks `python -c "raise SystemExit(1)"`-style
    # commands. Indirection (rather than inline `os.name == "nt"`) so
    # tests can flip the platform branch without patching os.name
    # globally (which breaks pathlib on Linux Python).
    if os.name == "nt":
        return command.replace("\\", "\\\\")
    return command


def split_command(command: str, env: dict[str, str] | None = None) -> tuple[list[str], dict[str, str]]:
    command_env_values = dict(env or os.environ)
    parts = shlex.split(_normalize_for_shlex(command))
    while parts and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[0]):
        key, value = parts.pop(0).split("=", 1)
        command_env_values[key] = value
    return parts, command_env_values


def run_command(command: str, *, timeout: int, env: dict[str, str] | None = None) -> dict[str, object]:
    try:
        argv, command_env_values = split_command(command, env)
    except ValueError as exc:
        return {
            "command": sanitize_text(command),
            "exit": 2,
            "stdout": "",
            "stderr": compact(f"command parse failed: {exc}"),
        }
    if not argv:
        return {
            "command": sanitize_text(command),
            "exit": 2,
            "stdout": "",
            "stderr": "empty command",
        }
    result = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=command_env_values,
    )
    return {
        "command": sanitize_text(command),
        "exit": result.returncode,
        "stdout": compact(result.stdout),
        "stderr": compact(result.stderr),
    }


def expected_exit(item: dict[str, Any]) -> int:
    if item.get("expected_blocked") is True:
        value = item.get("expected_exit")
        return value if isinstance(value, int) else 1
    return 0


def plan_item(item: dict[str, Any]) -> dict[str, object]:
    return {
        "order": item.get("order"),
        "id": item.get("id"),
        "mode": item.get("mode"),
        "live_provider": item.get("live_provider") is True,
        "expected_blocked": item.get("expected_blocked") is True,
        "requires_override": item.get("requires_override") is True,
        "task_count": item.get("task_count"),
        "env_keys": sorted(item.get("env", {}).keys()) if isinstance(item.get("env"), dict) else [],
        "timeout_seconds": item.get("timeout_seconds"),
        "commands": item.get("commands", []),
        "evidence": item.get("evidence", []),
        "stop_rules": item.get("stop_rules", []),
    }


def item_timeout(item: dict[str, Any], default: int) -> int:
    value = item.get("timeout_seconds")
    if isinstance(value, int) and value > 0:
        return value
    return default


def execute_slices(items: list[dict[str, Any]], *, timeout: int) -> tuple[str, list[dict[str, object]]]:
    reports: list[dict[str, object]] = []
    overall = "PASS"
    for item in items:
        commands = item.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        expected = expected_exit(item)
        timeout_for_item = item_timeout(item, timeout)
        command_reports: list[dict[str, object]] = []
        verdict = "PASS"
        env = command_env(item)
        for command in [value for value in commands if isinstance(value, str)]:
            command_report = run_command(command, timeout=timeout_for_item, env=env)
            command_reports.append(command_report)
            if command_report["exit"] != expected:
                verdict = "FAIL"
                overall = "FAIL"
                break
        reports.append(
            {
                "id": item.get("id"),
                "order": item.get("order"),
                "mode": item.get("mode"),
                "expected_exit": expected,
                "timeout_seconds": timeout_for_item,
                "verdict": verdict,
                "commands": command_reports,
            }
        )
        if verdict != "PASS":
            break
    return overall, reports


def write_report(slug: str, payload: dict[str, object]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    report_dir = ROOT / "run-artifacts" / slug / "operator-runs"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{timestamp}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute validated AO Operator operator slices")
    parser.add_argument("manifest", nargs="?", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--slice", dest="slice_id", help="Select one slice id")
    parser.add_argument("--from", dest="from_slice", help="Select slices starting from an id or numeric order")
    parser.add_argument("--through", help="Select all slices through an id or numeric order")
    parser.add_argument("--local-only", action="store_true", help="Omit live provider slices from selection")
    parser.add_argument("--execute", action="store_true", help="Execute selected commands; default only prints plan")
    parser.add_argument("--allow-live", action="store_true", help="Allow live_provider slices to execute")
    parser.add_argument("--allow-override", action="store_true", help="Allow override-gated slices when approval env is set")
    parser.add_argument("--timeout", type=int, default=600, help="Per-command timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = ROOT / manifest
    validation = validate_operator_slices.validate_path(manifest)
    if validation["verdict"] != "PASS":
        payload = {"verdict": "FAIL", "errors": validation["errors"], "results": [validation]}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(payload["errors"]))
        return 1

    data = validate_operator_slices.load_manifest(manifest)
    selected = select_slices(
        data,
        slice_id=args.slice_id,
        from_slice=args.from_slice,
        through=args.through,
        local_only=args.local_only,
    )
    if not selected:
        payload = {"verdict": "FAIL", "errors": ["no operator slices selected"], "slices": []}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "no operator slices selected")
        return 1

    blockers = [
        blocker
        for item in selected
        for blocker in safety_blockers(item, allow_live=args.allow_live, allow_override=args.allow_override)
    ]
    plan = [plan_item(item) for item in selected]
    if blockers:
        payload = {"verdict": "BLOCKED", "errors": blockers, "slices": plan}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(blockers))
        return 1

    if not args.execute:
        payload = {"verdict": "PLAN", "slices": plan, "execute": False}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(str(item["id"]) for item in plan))
        return 0

    verdict, reports = execute_slices(selected, timeout=max(1, args.timeout))
    payload = {
        "verdict": verdict,
        "manifest": str(manifest),
        "slug": data.get("slug"),
        "execute": True,
        "slices": reports,
    }
    report = write_report(str(data.get("slug") or "operator-slices"), payload)
    payload["report"] = str(report)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={verdict}\nreport={report}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
