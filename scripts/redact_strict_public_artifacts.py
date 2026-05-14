#!/usr/bin/env python3
"""Redact operator-local markers from committed historical evidence artifacts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/strict-public-artifact-redaction/v1"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml"}
DEFAULT_ROOTS = (Path("run-artifacts"), Path("docs/evaluations"))

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "personal_path",
        re.compile(r"(?<!\[REDACTED_USER\])(?:/Users/[^\s`\"'\\]+|/home/(?!\[REDACTED_USER\])[^\s`\"'\\]+|/opt/ai-workstation/[^\s`\"'\\]+)"),
        "[REDACTED_LOCAL_PATH]",
    ),
    (
        "private_network_target",
        re.compile(r"(?:\b\w+@)?(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"),
        "${FACTORY_V3_REMOTE_HOST}",
    ),
    (
        "stale_context",
        re.compile(r"<claude-mem-context>|FACTORY_V3_LLM_WIKI_PATH|path:llm_wiki"),
        "[REDACTED_STALE_CONTEXT_MARKER]",
    ),
)


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_text_files(root: Path, roots: Iterable[Path]) -> Iterable[Path]:
    for raw in roots:
        base = raw if raw.is_absolute() else root / raw
        if base.is_file() and base.suffix in TEXT_SUFFIXES:
            yield base
        elif base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in TEXT_SUFFIXES:
                    yield path


def redact_text(body: str) -> tuple[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    redacted = body
    for name, pattern, replacement in PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        counts[name] += count
    return redacted, dict(counts)


def redact_tree(
    root: Path,
    *,
    roots: Iterable[Path] = DEFAULT_ROOTS,
    write: bool = False,
    fail_on_changes: bool = False,
) -> dict:
    root = root.resolve()
    totals: Counter[str] = Counter()
    changed_files: list[str] = []
    files_checked = 0

    for path in iter_text_files(root, roots):
        files_checked += 1
        original = path.read_text(encoding="utf-8", errors="replace")
        redacted, counts = redact_text(original)
        if redacted == original:
            continue
        totals.update(counts)
        changed_files.append(relpath(root, path))
        if write:
            path.write_text(redacted, encoding="utf-8")

    blockers = ["strict-public artifacts need redaction"] if fail_on_changes and changed_files else []
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "mode": "write" if write else "dry-run",
        "roots": [raw.as_posix() for raw in roots],
        "files_checked": files_checked,
        "files_changed": len(changed_files),
        "changed_files_sample": changed_files[:50],
        "changed_files_omitted": max(0, len(changed_files) - 50),
        "counts": dict(sorted(totals.items())),
        "blockers": blockers,
        "verdict": "PASS" if not blockers else "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def write_output(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redact local markers from committed status/evaluation artifacts")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifact-root", action="append", default=[], help="Artifact root or file to redact; may be repeated")
    parser.add_argument("--write", action="store_true", help="Write redactions; default is dry-run")
    parser.add_argument("--fail-on-changes", action="store_true", help="Fail when dry-run finds redactable artifacts")
    parser.add_argument("--write-output", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(value) for value in args.artifact_root] if args.artifact_root else list(DEFAULT_ROOTS)
    payload = redact_tree(args.root, roots=roots, write=args.write, fail_on_changes=args.fail_on_changes)
    if args.write_output:
        output = args.write_output if args.write_output.is_absolute() else args.root / args.write_output
        payload["output"] = relpath(args.root.resolve(), output.resolve())
        write_output(output, payload)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "verdict={verdict} mode={mode} files_checked={files_checked} files_changed={files_changed} counts={counts}".format(
                **payload
            )
        )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
