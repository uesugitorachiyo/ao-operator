#!/usr/bin/env python3
"""Print Factory evaluation verdict status."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALUATIONS = ROOT / "docs" / "evaluations"
VERDICT_RE = re.compile(r"^Verdict:\s*(\S+)\s*$", re.MULTILINE)
KNOWN_VERDICTS = {"ACCEPTED", "REJECTED", "BLOCKED"}


def read_verdict(path: Path) -> str:
    match = VERDICT_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return "UNKNOWN"
    verdict = match.group(1).upper()
    return verdict if verdict in KNOWN_VERDICTS else "UNKNOWN"


def evaluation_for(slug: str) -> Path:
    return EVALUATIONS / f"{slug}-evaluation.md"


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def print_status(slug: str, path: Path) -> str:
    verdict = read_verdict(path) if path.exists() else "UNKNOWN"
    print(f"slug={slug} verdict={verdict} evaluation={rel(path)}")
    return verdict


def run_slug(slug: str) -> int:
    print_status(slug, evaluation_for(slug))
    return 0


def run_all() -> int:
    counts = {"ACCEPTED": 0, "REJECTED": 0, "BLOCKED": 0, "UNKNOWN": 0}
    paths = sorted(EVALUATIONS.glob("*-evaluation.md"))
    for path in paths:
        slug = path.name.removesuffix("-evaluation.md")
        verdict = print_status(slug, path)
        counts[verdict] += 1
    print(
        f"total={len(paths)} accepted={counts['ACCEPTED']} "
        f"rejected={counts['REJECTED']} blocked={counts['BLOCKED']} "
        f"unknown={counts['UNKNOWN']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Factory slug to summarize")
    group.add_argument("--all", action="store_true", help="summarize all evaluations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all:
        return run_all()
    return run_slug(args.slug)


if __name__ == "__main__":
    raise SystemExit(main())
