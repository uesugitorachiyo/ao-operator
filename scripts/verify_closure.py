#!/usr/bin/env python3
"""Run deterministic closure checks for ai-teams repos."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


def _command_exists(repo: Path, relative: str) -> bool:
    return (repo / relative).is_file()


def _portable_shell_args(item: str) -> list[str]:
    # F3 cross-platform: Windows native has no `bash` on PATH unless Git
    # Bash or WSL is installed, so a hardcoded ["bash", "-lc", item]
    # fails the closure check. Honor FACTORY_V3_SHELL for explicit
    # override (e.g. operators who want Git Bash on Windows or zsh on
    # macOS); otherwise pick the platform default: cmd /c on Windows,
    # bash -lc elsewhere. POSIX behavior unchanged.
    override = os.environ.get("FACTORY_V3_SHELL")
    if override:
        # On Windows, posix=False keeps backslash paths intact
        # (e.g. C:\Program Files\Git\bin\bash.exe -lc); on POSIX,
        # default posix=True handles quoting / escapes correctly.
        return shlex.split(override, posix=(os.name != "nt")) + [item]
    if os.name == "nt":
        return ["cmd", "/c", item]
    return ["bash", "-lc", item]


# ---------------------------------------------------------------------------
# Trigger-evidence enforcement (trigger_review_evidence_v2)
# ---------------------------------------------------------------------------

def _reviewer_evidence_present(eval_text: str, reviewer: str) -> bool:
    """Return True if *eval_text* contains reviewer-evidence for *reviewer*.

    Accepted patterns:
      A) **Reviewers:** ... <reviewer> ...
      B) - `<reviewer>`: APPROVED
      C/D) <reviewer> ... APPROVED / false positive / inline review
           (covers wave1-abf narrative style)
    """
    e = re.escape(reviewer)
    # Pattern A: **Reviewers:** line containing the reviewer name
    pat_a = r"\*\*Reviewers?\*\*:[^\n]*" + e
    # Pattern B: bullet item  - `reviewer`: APPROVED
    pat_b = r"-\s+`?" + e + r"`?\s*:\s*APPROVED"
    # Pattern C/D: reviewer name followed within 140 chars by APPROVED or
    # equivalent narrative (false positive acknowledgment, inline review)
    pat_cd = r"`?" + e + r"`?[^\n]{0,140}(?:APPROVED|approved|false\s+positive|inline\s+review)"
    pattern = re.compile(
        r"(?:" + pat_a + r"|" + pat_b + r"|" + pat_cd + r")",
        re.IGNORECASE,
    )
    return bool(pattern.search(eval_text))


def trigger_review_evidence_v2(repo: Path) -> dict[str, Any]:
    """Check that REQUIRED trigger-rule firings have matching reviewer evidence.

    Gated on ``run-artifacts/<slug>-trigger-rules.json`` artifacts.  If no
    artifact exists for a slug, the check is skipped for that slug — no false
    positives on legacy evals that predate the trigger-rules system.

    Returns a dict with keys:
      - ``verdict``: ``"PASS"`` or ``"FAIL"``
      - ``details``: list of failure strings (empty when PASS)
      - ``advisories``: list of advisory strings (RECOMMENDED misses, parse
        warnings; never causes FAIL)
    """
    status_dir = repo / "run-artifacts"
    evals_dir = repo / "docs" / "evaluations"

    failures: list[str] = []
    advisories: list[str] = []

    if not status_dir.is_dir():
        return {"verdict": "PASS", "details": [], "advisories": []}

    trigger_files = list(status_dir.glob("*-trigger-rules.json"))

    for trigger_path in trigger_files:
        # Derive slug: strip the "-trigger-rules.json" suffix
        slug = trigger_path.name[: -len("-trigger-rules.json")]

        try:
            trigger_data = json.loads(trigger_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            advisories.append(f"Could not parse {trigger_path.name}: {exc}")
            continue

        fired = trigger_data.get("fired", [])
        if not fired:
            continue

        # Find the matching eval file(s) — dated and/or dateless variants
        eval_files = list(evals_dir.glob(f"*{slug}*evaluation*.md"))
        if not eval_files:
            advisories.append(
                f"slug={slug}: trigger-rules artifact present but no matching "
                f"eval file found under {evals_dir}"
            )
            continue

        # Use the lexicographically latest file so dated > dateless
        eval_file = sorted(eval_files)[-1]
        eval_text = eval_file.read_text(encoding="utf-8")

        for entry in fired:
            reviewer = entry.get("reviewer", "").strip()
            level = entry.get("level", "RECOMMENDED").upper()
            trigger_hint = entry.get("trigger", "?")

            if not reviewer:
                continue

            has_evidence = _reviewer_evidence_present(eval_text, reviewer)

            if level == "REQUIRED":
                if not has_evidence:
                    failures.append(
                        f"slug={slug}: REQUIRED reviewer '{reviewer}' fired "
                        f"(trigger: {trigger_hint}) but no reviewer-evidence "
                        f"line found in {eval_file.name}"
                    )
            else:
                # RECOMMENDED or any unrecognised level — advisory only
                if not has_evidence:
                    advisories.append(
                        f"slug={slug}: RECOMMENDED reviewer '{reviewer}' — "
                        f"no evidence found (advisory, not blocking)"
                    )

    return {
        "verdict": "FAIL" if failures else "PASS",
        "details": failures,
        "advisories": advisories,
    }


def gate_r_contract_evidence(repo: Path) -> dict[str, Any]:
    """Run Gate R for committed Gate B reports that have role artifacts."""
    status_dir = repo / "run-artifacts"
    if not status_dir.is_dir():
        return {"verdict": "PASS", "details": [], "reports": []}

    import gate_r

    reports: list[dict[str, Any]] = []
    failures: list[str] = []
    for gate_b_path in sorted(status_dir.glob("*/gate-b.json")):
        slug = gate_b_path.parent.name
        if not (gate_b_path.parent / "roles").is_dir():
            continue
        report = gate_r.run_gate(repo=repo, slug=slug, gate_b_path=gate_b_path)
        reports.append(
            {
                "slug": slug,
                "gate_b": str(gate_b_path.relative_to(repo)),
                "verdict": report["verdict"],
                "error_count": len(report.get("errors", [])),
            }
        )
        if report["verdict"] != "PASS":
            failures.extend(f"slug={slug}: {error}" for error in report.get("errors", []))
    return {
        "verdict": "FAIL" if failures else "PASS",
        "details": failures,
        "reports": reports,
    }


def closure_commands(repo: Path, *, include_pytest: bool) -> list[list[str]]:
    commands: list[list[str]] = []

    if _command_exists(repo, "scripts/validate.py") and _command_exists(repo, "skills.toml"):
        commands.append([sys.executable, "scripts/validate.py"])

    if _command_exists(repo, "scripts/factory_doctor.py"):
        commands.append([sys.executable, "scripts/factory_doctor.py", "--json"])
    if _command_exists(repo, "scripts/self_check.py"):
        commands.append([sys.executable, "scripts/self_check.py", "--fast", "--json"])
    if _command_exists(repo, "scripts/build_ledger.py"):
        commands.append([sys.executable, "scripts/build_ledger.py", "--check", "--quiet"])
    if _command_exists(repo, "scripts/artifact_hygiene.py"):
        commands.append([sys.executable, "scripts/artifact_hygiene.py", "--strict"])

    if include_pytest and _command_exists(repo, "scripts/validate_workspace.py"):
        commands.append([sys.executable, "scripts/validate_workspace.py", "--ci"])
    elif include_pytest and ((repo / "tests").is_dir() or (repo / "pyproject.toml").is_file()):
        commands.append([sys.executable, "-m", "pytest", "-q"])

    return commands


def run_command(repo: Path, command: list[str], timeout: int) -> dict[str, Any]:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        duration = round(time.monotonic() - start, 3)
        return {
            "command": command,
            "returncode": completed.returncode,
            "duration_seconds": duration,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "verdict": "PASS" if completed.returncode == 0 else "FAIL",
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - start, 3)
        return {
            "command": command,
            "returncode": None,
            "duration_seconds": duration,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "verdict": "FAIL",
            "error": f"timed out after {timeout}s",
        }


def run(
    repo: Path,
    *,
    include_pytest: bool,
    timeout: int,
    dry_run: bool,
    extra: list[str],
) -> dict[str, Any]:
    commands = closure_commands(repo, include_pytest=include_pytest)
    for item in extra:
        commands.append(_portable_shell_args(item))

    if not commands:
        return {
            "repo": str(repo),
            "verdict": "WARN",
            "commands": [],
            "results": [],
            "errors": ["no known closure commands found"],
        }

    if dry_run:
        return {
            "repo": str(repo),
            "verdict": "PASS",
            "commands": commands,
            "results": [],
            "errors": [],
        }

    results = [run_command(repo, command, timeout) for command in commands]
    errors = [
        "{} failed".format(" ".join(result["command"]))
        for result in results
        if result["verdict"] != "PASS"
    ]

    # Run the trigger-evidence check (pure Python, no subprocess)
    trigger_result = trigger_review_evidence_v2(repo)
    if trigger_result["verdict"] == "FAIL":
        errors.extend(trigger_result["details"])

    gate_r_result = gate_r_contract_evidence(repo)
    if gate_r_result["verdict"] == "FAIL":
        errors.extend(gate_r_result["details"])

    return {
        "repo": str(repo),
        "verdict": "PASS" if not errors else "FAIL",
        "commands": commands,
        "results": results,
        "errors": errors,
        "trigger_evidence": trigger_result,
        "gate_r_evidence": gate_r_result,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        scripts = repo / "scripts"
        scripts.mkdir()
        (repo / "skills.toml").write_text("[globals]\n", encoding="utf-8")
        (scripts / "validate.py").write_text("print('ok')\n", encoding="utf-8")
        result = run(repo, include_pytest=False, timeout=10, dry_run=False, extra=[])
        if result["verdict"] != "PASS":
            print(json.dumps(result, indent=2), file=sys.stderr)
            return 1
        parent = repo / "parent"
        parent_scripts = parent / "scripts"
        parent_scripts.mkdir(parents=True)
        (parent_scripts / "validate_workspace.py").write_text("print('workspace ok')\n", encoding="utf-8")
        parent_result = run(parent, include_pytest=True, timeout=10, dry_run=True, extra=[])
        expected = [sys.executable, "scripts/validate_workspace.py", "--ci"]
        if expected not in parent_result["commands"]:
            print(json.dumps(parent_result, indent=2), file=sys.stderr)
            return 1
    print("OK verify_closure self-test")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic closure checks for an ai-teams repo."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repo root")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--with-pytest", action="store_true", help="include python3 -m pytest -q")
    parser.add_argument("--timeout", type=int, default=120, help="per-command timeout seconds")
    parser.add_argument("--dry-run", action="store_true", help="print selected commands without running")
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="extra shell command to run after built-in closure checks",
    )
    parser.add_argument("--self-test", action="store_true", help="run built-in self-test")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        return self_test()
    result = run(
        args.repo.resolve(),
        include_pytest=args.with_pytest,
        timeout=args.timeout,
        dry_run=args.dry_run,
        extra=args.extra,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["verdict"])
        for command in result["commands"]:
            print(" ".join(command))
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["verdict"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
