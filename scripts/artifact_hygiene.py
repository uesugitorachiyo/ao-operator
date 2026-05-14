#!/usr/bin/env python3
"""Classify untracked AO Operator generated artifacts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERDICT_RE = re.compile(r"^Verdict:\s*(\S+)\s*$", re.MULTILINE)
KNOWN_VERDICTS = {"ACCEPTED", "REJECTED", "BLOCKED"}


@dataclass
class SlugArtifacts:
    slug: str
    spec: bool = False
    plan: bool = False
    evaluation: bool = False
    status: bool = False
    files: list[str] = field(default_factory=list)
    verdict: str = "UNKNOWN"
    recommendation: str = "REVIEW_INCOMPLETE"
    reason: str = ""


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def git_untracked_entries() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=ROOT,
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())

    entries: list[str] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if not text.startswith("?? "):
            continue
        entries.append(text[3:])
    return sorted(entries)


def expand_entries(entries: list[str]) -> list[str]:
    paths: list[str] = []
    for entry in entries:
        if entry.endswith("/"):
            root = ROOT / entry
            paths.extend(rel(item) for item in sorted(root.rglob("*")) if item.is_file())
            continue
        paths.append(entry)
    return sorted(paths)


def slug_from_path(path: str) -> tuple[str, str] | None:
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "docs":
        return None

    section = parts[1]
    name = parts[2]
    if section == "specs" and name.endswith("-spec.md"):
        return name.removesuffix("-spec.md"), "spec"
    if section == "plans" and name.endswith("-plan.md"):
        return name.removesuffix("-plan.md"), "plan"
    if section == "evaluations" and name.endswith("-evaluation.md"):
        return name.removesuffix("-evaluation.md"), "evaluation"
    if section == "status":
        return name, "status"
    return None


def read_verdict(slug: str) -> str:
    path = ROOT / "docs" / "evaluations" / f"{slug}-evaluation.md"
    if not path.is_file():
        return "UNKNOWN"
    match = VERDICT_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return "UNKNOWN"
    verdict = match.group(1).upper()
    return verdict if verdict in KNOWN_VERDICTS else "UNKNOWN"


def classify(item: SlugArtifacts) -> None:
    has_core = item.spec and item.plan and item.evaluation and item.status

    if item.verdict == "ACCEPTED" and has_core:
        item.recommendation = "PRESERVE_CANDIDATE"
        item.reason = "accepted evaluation with spec, plan, evaluation, and status artifacts"
    elif item.verdict in {"REJECTED", "BLOCKED"}:
        item.recommendation = "ARCHIVE_OR_DROP"
        item.reason = f"{item.verdict.lower()} evaluation should not be committed as baseline evidence"
    elif item.verdict == "ACCEPTED":
        item.recommendation = "REVIEW_INCOMPLETE"
        item.reason = "accepted evaluation exists, but one or more core artifact families are missing"
    else:
        item.recommendation = "REVIEW_INCOMPLETE"
        item.reason = "no accepted/rejected/blocking evaluation verdict found"


def scan(paths: list[str]) -> dict[str, SlugArtifacts]:
    slugs: dict[str, SlugArtifacts] = {}
    for path in paths:
        parsed = slug_from_path(path)
        if not parsed:
            continue
        slug, kind = parsed
        item = slugs.setdefault(slug, SlugArtifacts(slug=slug))
        setattr(item, kind, True)
        item.files.append(path)

    for item in slugs.values():
        item.verdict = read_verdict(item.slug)
        classify(item)
    return dict(sorted(slugs.items()))


def payload(
    slugs: dict[str, SlugArtifacts],
    *,
    untracked_entries: int,
    untracked_files: int,
) -> dict[str, Any]:
    recommendation_counts = Counter(item.recommendation for item in slugs.values())
    verdict_counts = Counter(item.verdict for item in slugs.values())
    return {
        "total_slugs": len(slugs),
        "total_untracked_entries": untracked_entries,
        "total_untracked_files": untracked_files,
        "recommendations": dict(sorted(recommendation_counts.items())),
        "verdicts": dict(sorted(verdict_counts.items())),
        "slugs": [
            {
                "slug": item.slug,
                "verdict": item.verdict,
                "recommendation": item.recommendation,
                "reason": item.reason,
                "families": {
                    "spec": item.spec,
                    "plan": item.plan,
                    "evaluation": item.evaluation,
                    "status": item.status,
                },
                "file_count": len(item.files),
            }
            for item in slugs.values()
        ],
    }


def print_table(data: dict[str, Any]) -> None:
    print(
        "total_slugs={total_slugs} total_untracked_entries={total_untracked_entries} "
        "total_untracked_files={total_untracked_files} "
        "preserve_candidates={preserve} archive_or_drop={archive} review_incomplete={review}".format(
            total_slugs=data["total_slugs"],
            total_untracked_entries=data["total_untracked_entries"],
            total_untracked_files=data["total_untracked_files"],
            preserve=data["recommendations"].get("PRESERVE_CANDIDATE", 0),
            archive=data["recommendations"].get("ARCHIVE_OR_DROP", 0),
            review=data["recommendations"].get("REVIEW_INCOMPLETE", 0),
        )
    )
    for item in data["slugs"]:
        print(
            "{recommendation:17} {verdict:8} {slug} ({file_count} files)".format(
                **item
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when untracked Factory artifacts are present",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = git_untracked_entries()
    files = expand_entries(entries)
    data = payload(
        scan(files),
        untracked_entries=len(entries),
        untracked_files=len(files),
    )
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_table(data)
    return 1 if args.strict and data["total_untracked_entries"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
