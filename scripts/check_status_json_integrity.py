#!/usr/bin/env python3
"""Validate committed status/evaluation JSON artifacts remain parseable."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/status-json-integrity/v1"
DEFAULT_ROOTS = (Path("run-artifacts"), Path("docs/evaluations"))


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_json_files(root: Path, roots: Iterable[Path]) -> Iterable[Path]:
    for raw in roots:
        base = raw if raw.is_absolute() else root / raw
        if base.is_file() and base.suffix == ".json":
            yield base
        elif base.is_dir():
            yield from sorted(base.rglob("*.json"))


def summarize(root: Path = ROOT, *, roots: Iterable[Path] = DEFAULT_ROOTS) -> dict:
    root = root.resolve()
    files_checked = 0
    invalid_files: list[dict[str, str]] = []
    for path in iter_json_files(root, roots):
        files_checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            invalid_files.append({"path": relpath(root, path), "error": str(exc)})

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "roots": [raw.as_posix() for raw in roots],
        "files_checked": files_checked,
        "invalid_count": len(invalid_files),
        "invalid_files": invalid_files[:100],
        "invalid_files_omitted": max(0, len(invalid_files) - 100),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "verdict": "PASS" if not invalid_files else "FAIL",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate status/evaluation JSON artifacts")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifact-root", action="append", default=[], help="Artifact root or JSON file; may be repeated")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(value) for value in args.artifact_root] if args.artifact_root else list(DEFAULT_ROOTS)
    payload = summarize(args.root, roots=roots)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']} files_checked={payload['files_checked']} invalid_count={payload['invalid_count']}")
        for item in payload["invalid_files"]:
            print(f"invalid={item['path']} error={item['error']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
