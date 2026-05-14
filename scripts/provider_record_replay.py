#!/usr/bin/env python3
"""Record and replay provider calls for deterministic AO Operator tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/provider-record/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_params(items: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"param must be KEY=VALUE: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"param key must be non-empty: {item!r}")
        params[key] = value
    return dict(sorted(params.items()))


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def call_key(provider: str, task_id: str, prompt_text: str, params: dict[str, str]) -> str:
    material = {
        "provider": provider,
        "task_id": task_id,
        "prompt_sha256": sha256_text(prompt_text),
        "params": params,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def summarize_tools(stdout: str, stderr: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type:
            counts[item_type] = counts.get(item_type, 0) + 1
        tool_name = str(item.get("name") or item.get("tool") or "")
        if tool_name:
            counts[f"tool:{tool_name}"] = counts.get(f"tool:{tool_name}", 0) + 1
    return {
        "stdout_lines": len(stdout.splitlines()),
        "stderr_lines": len(stderr.splitlines()),
        "json_event_counts": counts,
    }


def ao_event_lines(task_id: str, stdout: str, returncode: int) -> list[str]:
    payload = json.dumps({"line": stdout.rstrip("\n")}, sort_keys=True)
    return [
        f"{utc_now()}  agent.stdout              task={task_id}  {payload}",
        f"{utc_now()}  task.completed           task={task_id}  {json.dumps({'returncode': returncode}, sort_keys=True)}",
    ]


def build_record(
    *,
    provider: str,
    task_id: str,
    prompt_file: Path,
    params: dict[str, str],
    stdout: str,
    stderr: str,
    returncode: int,
    command: list[str],
) -> dict[str, Any]:
    prompt_text = load_prompt(prompt_file)
    key = call_key(provider, task_id, prompt_text, params)
    return {
        "schema": SCHEMA,
        "kind": "provider_call",
        "key": key,
        "generated_at": utc_now(),
        "provider": provider,
        "task_id": task_id,
        "prompt": {
            "path": str(prompt_file),
            "sha256": sha256_text(prompt_text),
            "text": prompt_text,
        },
        "params": params,
        "command": command,
        "response": {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        },
        "tool_summary": summarize_tools(stdout, stderr),
        "ao_events": ao_event_lines(task_id, stdout, returncode),
        "dispatch_authorized": False,
        "live_providers_run": bool(command),
    }


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def iter_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("schema") == SCHEMA:
            records.append(item)
    return records


def find_record(path: Path, *, provider: str, task_id: str, prompt_file: Path, params: dict[str, str]) -> dict[str, Any] | None:
    prompt_text = load_prompt(prompt_file)
    key = call_key(provider, task_id, prompt_text, params)
    for record in reversed(iter_records(path)):
        if record.get("key") == key:
            return record
    return None


def run_record(args: argparse.Namespace) -> int:
    params = normalize_params(args.param)
    if args.command:
        completed = subprocess.run(
            args.command,
            cwd=args.cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            input=load_prompt(args.prompt_file) if args.stdin_prompt else None,
            check=False,
            env=os.environ.copy(),
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
        command = args.command
    else:
        if not args.response_file:
            print("record requires --response-file or -- command", file=sys.stderr)
            return 2
        stdout = args.response_file.read_text(encoding="utf-8")
        stderr = ""
        returncode = 0
        command = []
    record = build_record(
        provider=args.provider,
        task_id=args.task_id,
        prompt_file=args.prompt_file,
        params=params,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        command=command,
    )
    append_record(args.recording, record)
    print(json.dumps({"schema": SCHEMA, "verdict": "PASS", "key": record["key"]}, indent=2, sort_keys=True))
    return 0 if returncode == 0 else returncode


def run_replay(args: argparse.Namespace) -> int:
    params = normalize_params(args.param)
    record = find_record(
        args.recording,
        provider=args.provider,
        task_id=args.task_id,
        prompt_file=args.prompt_file,
        params=params,
    )
    if not record:
        print("recording not found for provider/task/prompt/params", file=sys.stderr)
        return 1
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    stdout = str(response.get("stdout") or "")
    if args.ao_events:
        for line in record.get("ao_events", []):
            print(line)
    elif args.json:
        payload = {
            "schema": SCHEMA,
            "verdict": "PASS",
            "key": record["key"],
            "provider": record["provider"],
            "task_id": record["task_id"],
            "response": response,
            "tool_summary": record.get("tool_summary", {}),
            "live_providers_run": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    return int(response.get("returncode") or 0)


def run_verify(args: argparse.Namespace) -> int:
    records = iter_records(args.recording)
    errors = []
    for index, record in enumerate(records, start=1):
        prompt = record.get("prompt") if isinstance(record.get("prompt"), dict) else {}
        text = str(prompt.get("text") or "")
        if prompt.get("sha256") != sha256_text(text):
            errors.append(f"record {index}: prompt sha256 mismatch")
        if not record.get("key"):
            errors.append(f"record {index}: missing key")
        if not isinstance(record.get("response"), dict):
            errors.append(f"record {index}: missing response")
    payload = {
        "schema": SCHEMA,
        "verdict": "PASS" if not errors else "FAIL",
        "record_count": len(records),
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record/replay provider calls")
    sub = parser.add_subparsers(dest="command_name", required=True)

    record = sub.add_parser("record")
    record.add_argument("--recording", type=Path, required=True)
    record.add_argument("--provider", required=True, choices=["codex", "claude"])
    record.add_argument("--task-id", required=True)
    record.add_argument("--prompt-file", type=Path, required=True)
    record.add_argument("--response-file", type=Path)
    record.add_argument("--param", action="append", default=[])
    record.add_argument("--cwd", type=Path, default=Path.cwd())
    record.add_argument("--stdin-prompt", action="store_true")
    record.add_argument("command", nargs=argparse.REMAINDER)
    record.set_defaults(func=run_record)

    replay = sub.add_parser("replay")
    replay.add_argument("--recording", type=Path, required=True)
    replay.add_argument("--provider", required=True, choices=["codex", "claude"])
    replay.add_argument("--task-id", required=True)
    replay.add_argument("--prompt-file", type=Path, required=True)
    replay.add_argument("--param", action="append", default=[])
    replay.add_argument("--json", action="store_true")
    replay.add_argument("--ao-events", action="store_true")
    replay.set_defaults(func=run_replay)

    verify = sub.add_parser("verify")
    verify.add_argument("--recording", type=Path, required=True)
    verify.set_defaults(func=run_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) and args.command[0] == "--":
        args.command = args.command[1:]
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
