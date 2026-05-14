#!/usr/bin/env python3
"""Check Agent OS prompts and outputs for transcript, secret, and stale-context leakage."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-execution-hygiene.json"
SECRET_MARKERS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "Bearer "]
STALE_CONTEXT_MARKERS = ["<claude-mem-context>", "FACTORY_V3_LLM_WIKI_PATH", "path:llm_wiki"]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def check_hygiene(
    *,
    root: Path = ROOT,
    prompt_paths: list[str | Path] | None = None,
    role_outputs: list[str | Path] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    prompts = [resolve_path(root, item) for item in (prompt_paths or [])]
    outputs = [resolve_path(root, item) for item in (role_outputs or [])]
    for path in prompts:
        body = read_text(path)
        for marker in SECRET_MARKERS:
            if marker in body:
                errors.append(f"{path.name} contains forbidden secret marker {marker}")
        for marker in STALE_CONTEXT_MARKERS:
            if marker in body:
                errors.append(f"{path.name} contains stale context marker {marker}")
    for path in outputs:
        data = load_json(path)
        body = json.dumps(data, sort_keys=True)
        if str(data.get("full_transcript") or "").strip():
            errors.append(f"{path.name} contains full transcript")
        for marker in SECRET_MARKERS:
            if marker in body:
                errors.append(f"{path.name} contains forbidden secret marker {marker}")
        for marker in STALE_CONTEXT_MARKERS:
            if marker in body:
                errors.append(f"{path.name} contains stale context marker {marker}")
    return {
        "schema": "ao-operator/agent-os-execution-hygiene/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "prompts_checked": len(prompts),
        "role_outputs_checked": len(outputs),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS execution hygiene")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--prompt", action="append", default=[])
    parser.add_argument("--role-output", action="append", default=[])
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = check_hygiene(root=args.root, prompt_paths=args.prompt, role_outputs=args.role_output)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
