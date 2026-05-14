#!/usr/bin/env python3
"""Prepare a larger live profile in an isolated dry-run worktree."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_stress_fixture import task_count


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_REPORT = Path("run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json")
DEFAULT_WORKTREE_BASE = Path("/tmp/ao-operator-live-profile-prep")
REPORT_ROOT = ROOT / "run-artifacts/remote-transfer-v2-stress/profile-prep"
PRESERVED_EVIDENCE_PATHS = [
    ROOT / "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
    ROOT / "examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
    ROOT / "examples/remote-transfer-v2-stress/task-brief-live.md",
    ROOT / "examples/remote-transfer-v2-stress/expected-throughput-live.md",
    ROOT / "docs/specs/remote-transfer-v2-stress-live-spec.md",
    ROOT / "docs/plans/remote-transfer-v2-stress-live-plan.md",
    ROOT / "docs/evaluations/remote-transfer-v2-stress-live-evaluation.md",
    ROOT / "run-artifacts/remote-transfer-v2-stress-live",
]


def command_text(argv: list[str]) -> str:
    return " ".join(argv)


def prep_commands(slices: int) -> list[list[str]]:
    return [
        ["python3", "scripts/generate_stress_fixture.py", "--live-slices", str(slices), "--write-live-profile"],
        [
            "python3",
            "scripts/factory_run.py",
            "--brief",
            "examples/remote-transfer-v2-stress/task-brief-live.md",
            "--slug",
            DEFAULT_SLUG,
            "--provider-env",
            "examples/remote-transfer-v2-stress/provider.env",
            "--topology",
            "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
            "--dry-run",
            "--overwrite-artifacts",
            "--scrub-root-context",
        ],
        [
            "python3",
            "scripts/validate_intake.py",
            "examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
            "--json",
        ],
        [
            "python3",
            "scripts/validate_factory.py",
            "--slug",
            DEFAULT_SLUG,
            "--topology",
            "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
            "--contract",
            "examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
            "--json",
        ],
    ]


def run_checked(argv: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command_text(argv),
            "exit": 124,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"\ntimeout after {timeout} seconds",
        }
    return {
        "command": command_text(argv),
        "exit": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def resolve_safe_report(path: Path) -> Path:
    report = path if path.is_absolute() else ROOT / path
    resolved = report.resolve(strict=False)
    report_root = REPORT_ROOT.resolve(strict=False)
    if resolved.parent != report_root:
        raise ValueError(f"report must be written directly under {REPORT_ROOT.relative_to(ROOT)}")
    if resolved.suffix != ".json":
        raise ValueError("report must be a JSON file")
    return resolved


def resolve_safe_worktree(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise ValueError("prep worktree must be outside the main repository")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_snapshot() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in PRESERVED_EVIDENCE_PATHS:
        if path.is_file():
            snapshot[str(path.relative_to(ROOT))] = sha256_file(path)
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                snapshot[str(child.relative_to(ROOT))] = sha256_file(child)
    return snapshot


def evidence_preserved(before: dict[str, str], after: dict[str, str]) -> bool:
    return before == after and bool(before)


def remove_worktree(path: Path) -> None:
    path = resolve_safe_worktree(path)
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if path.exists():
        shutil.rmtree(path)


def add_worktree(path: Path) -> None:
    path = resolve_safe_worktree(path)
    remove_worktree(path)
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(path), "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "git worktree add failed")


def report_payload(
    *,
    slices: int,
    worktree: Path,
    report: Path = DEFAULT_REPORT,
    commands: list[dict[str, Any]],
    preserved_main_evidence: bool,
) -> dict[str, Any]:
    passed = all(item.get("exit") == 0 for item in commands)
    return {
        "schema": "ao-operator/live-profile-dry-run-prep/v1",
        "slug": DEFAULT_SLUG,
        "mode": "dry-run-temp-worktree",
        "verdict": "PASS" if passed and preserved_main_evidence else "FAIL",
        "slices": slices,
        "tasks": task_count(slices),
        "source_commit": source_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "worktree": str(worktree),
        "accepted_live_evidence_preserved_in_main": preserved_main_evidence,
        "committable_outputs": [
            str(report),
            "run-artifacts/remote-transfer-v2-stress/operator-runs/<operator-run>.json",
        ],
        "non_committable_temp_outputs": [
            "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
            "examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
            "examples/remote-transfer-v2-stress/task-brief-live.md",
            "examples/remote-transfer-v2-stress/expected-throughput-live.md",
            "docs/specs/remote-transfer-v2-stress-live-spec.md",
            "docs/plans/remote-transfer-v2-stress-live-plan.md",
            "run-artifacts/remote-transfer-v2-stress-live/",
        ],
        "commands": commands,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slices", type=int, default=50)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--worktree", default="")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--keep-worktree", action="store_true")
    args = parser.parse_args(argv)

    worktree = resolve_safe_worktree(
        Path(args.worktree) if args.worktree else DEFAULT_WORKTREE_BASE.with_name(f"{DEFAULT_WORKTREE_BASE.name}-{args.slices}")
    )
    report = resolve_safe_report(Path(args.report))

    command_reports: list[dict[str, Any]] = []
    before_evidence = evidence_snapshot()
    try:
        add_worktree(worktree)
        for command in prep_commands(args.slices):
            command_report = run_checked(command, cwd=worktree, timeout=args.timeout_seconds)
            command_reports.append(command_report)
            if command_report["exit"] != 0:
                break
    finally:
        if not args.keep_worktree:
            remove_worktree(worktree)
    preserved_main_evidence = evidence_preserved(before_evidence, evidence_snapshot())

    payload = report_payload(
        slices=args.slices,
        worktree=worktree,
        report=report.relative_to(ROOT) if report.is_relative_to(ROOT) else report,
        commands=command_reports,
        preserved_main_evidence=preserved_main_evidence,
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "verdict": payload["verdict"],
                "mode": payload["mode"],
                "report": str(report),
                "slices": payload["slices"],
                "tasks": payload["tasks"],
                "commands": [
                    {"command": item["command"], "exit": item["exit"]}
                    for item in command_reports
                ],
            },
            indent=2,
        )
    )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
