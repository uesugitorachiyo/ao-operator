#!/usr/bin/env python3
"""Pre-PR gate-delta check vs main.

Runs the SECURITY.md "Required Gates" command list against both the current
branch and a base ref (default: main), then diffs the results.

Catches self-inflicted regressions before commit:

  * REGRESSION: a gate that PASSED on main now FAILS on this branch ->
    this branch introduced the failure
  * IMPROVEMENT: a gate that FAILED on main now PASSES on this branch ->
    this branch fixed a pre-existing failure (informational)
  * PRE-EXISTING: a gate fails on both -> not this branch's fault, but
    noted in the report
  * UNCHANGED-PASS: a gate passes on both -> the common-case majority

The overall verdict is PASS iff the regression list is empty. Improvements
and pre-existing failures are reported but do not block.

The gate command list is parsed from SECURITY.md so this script stays in
sync with the canonical required-gates list. Add a new gate to
SECURITY.md and it is automatically picked up.

Base-ref execution uses a git worktree so the comparison runs in an
isolated checkout and never disturbs the current working tree. The
worktree is always removed in a finally block.

Six deterministic cases pin the diff logic with synthetic gate results
(no real subprocess invocation in the case-runner -- subprocess plumbing
is covered by a separate integration test):

  * clean_branch_matches_main_passes (control)
  * branch_introduces_new_failure_rejected (mutation)
  * branch_fixes_pre_existing_failure_passes (positive case)
  * pre_existing_failure_unchanged_is_informational (positive case)
  * gate_added_only_on_branch_failing_is_regression (mutation)
  * gate_removed_on_branch_is_neutral (positive case)

The gate never invokes AO or provider CLIs and never authorizes dispatch.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/gate-delta-vs-main.json"
SCHEMA = "ao-operator/gate-delta-vs-main/v1"
DEFAULT_BASE_REF = "main"

CODE_FENCE_PATTERN = re.compile(r"```(?:bash)?\s*\n(.*?)```", re.DOTALL)
GATE_COMMAND_PATTERN = re.compile(r"^python3\s+scripts/[A-Za-z0-9_./-]+.*$", re.MULTILINE)

CASE_IDS = (
    "clean_branch_matches_main_passes",
    "branch_introduces_new_failure_rejected",
    "branch_fixes_pre_existing_failure_passes",
    "pre_existing_failure_unchanged_is_informational",
    "gate_added_only_on_branch_failing_is_regression",
    "gate_removed_on_branch_is_neutral",
)

EXPECTED_VERDICTS = {
    "clean_branch_matches_main_passes": "PASS",
    "branch_introduces_new_failure_rejected": "FAIL",
    "branch_fixes_pre_existing_failure_passes": "PASS",
    "pre_existing_failure_unchanged_is_informational": "PASS",
    "gate_added_only_on_branch_failing_is_regression": "FAIL",
    "gate_removed_on_branch_is_neutral": "PASS",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def parse_security_md(text: str) -> list[str]:
    """Extract gate command lines from SECURITY.md.

    Looks for the first fenced code block containing `python3 scripts/` lines
    (the "Required Gates" block). Returns the commands in source order.
    """
    for fence_body in CODE_FENCE_PATTERN.findall(text):
        commands = [m.group(0).strip() for m in GATE_COMMAND_PATTERN.finditer(fence_body)]
        if commands:
            return commands
    return []


def strip_write_output_flag(command: str) -> str:
    """Remove --write-output (and any value) from a gate command.

    The delta check invokes each gate purely for its exit code; the
    --write-output side effect would pollute the working tree (and trip
    downstream gates like artifact_hygiene and redact_strict_public_artifacts
    on the second pass). Stripping the flag preserves exit-code semantics.

    Handles three forms:
      * ``--write-output``                  (bare; const default)
      * ``--write-output=value``            (equals form)
      * ``--write-output value``            (space form, where value does
                                            not start with '-')
    """
    tokens = shlex.split(command)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--write-output":
            i += 1
            # Skip a following value if it does not look like a flag.
            if i < len(tokens) and not tokens[i].startswith("-"):
                i += 1
            continue
        if tok.startswith("--write-output="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return shlex.join(out)


def run_gate(command: str, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    """Run one gate command. Returns dict with exit_code, duration, stdout_tail."""
    started = datetime.now(timezone.utc)
    args = shlex.split(command)
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        exit_code = result.returncode
        stdout_tail = (result.stdout or "")[-2000:]
        stderr_tail = (result.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        exit_code = 124
        stdout_tail = ""
        stderr_tail = f"timeout after {timeout}s"
    finished = datetime.now(timezone.utc)
    return {
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def gate_status(exit_code: int) -> str:
    return "PASS" if exit_code == 0 else "FAIL"


def compute_delta(
    base_results: dict[str, int],
    branch_results: dict[str, int],
) -> dict[str, list[str]]:
    """Classify each gate by transition between base and branch.

    base_results / branch_results map gate-command-string -> exit-code.
    Gates absent from either side are treated as a transition:
      - present on branch only: equivalent to base PASS implicit (it's a new gate)
      - present on base only: removed; not a regression

    Returns dict with five lists: regressions, improvements, pre_existing,
    unchanged_passing, removed.
    """
    out = {
        "regressions": [],
        "improvements": [],
        "pre_existing": [],
        "unchanged_passing": [],
        "removed": [],
    }
    branch_set = set(branch_results.keys())
    base_set = set(base_results.keys())

    for command in sorted(branch_set):
        branch_pass = branch_results[command] == 0
        if command in base_set:
            base_pass = base_results[command] == 0
            if base_pass and not branch_pass:
                out["regressions"].append(command)
            elif not base_pass and branch_pass:
                out["improvements"].append(command)
            elif base_pass and branch_pass:
                out["unchanged_passing"].append(command)
            else:
                out["pre_existing"].append(command)
        else:
            # New gate on branch only. Treat failing-new-gate as regression
            # (because the branch added it and it failed); passing-new-gate
            # as unchanged_passing.
            if branch_pass:
                out["unchanged_passing"].append(command)
            else:
                out["regressions"].append(command)

    for command in sorted(base_set - branch_set):
        out["removed"].append(command)

    return out


def derive_verdict(delta: dict[str, list[str]]) -> str:
    return "FAIL" if delta["regressions"] else "PASS"


def _setup_worktree(repo_root: Path, base_ref: str, target: Path) -> None:
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), base_ref],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _teardown_worktree(repo_root: Path, target: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def run_gate_chain_on_ref(
    repo_root: Path,
    commands: list[str],
    *,
    base_ref: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Run each command in repo_root (or a worktree of base_ref).

    Returns (per-command result records, command-string -> exit-code map).
    """
    if base_ref is None:
        work_dir = repo_root
        cleanup = lambda: None  # noqa: E731
    else:
        tmp = Path(tempfile.mkdtemp(prefix="ao-operator-gate-delta-worktree-"))
        wt = tmp / "wt"
        _setup_worktree(repo_root, base_ref, wt)
        work_dir = wt
        cleanup = lambda: (_teardown_worktree(repo_root, wt), shutil.rmtree(tmp, ignore_errors=True))  # noqa: E731

    try:
        records = [run_gate(cmd, work_dir) for cmd in commands]
        exit_map = {r["command"]: r["exit_code"] for r in records}
        return records, exit_map
    finally:
        cleanup()


def _run_case(
    case_id: str,
    base_results: dict[str, int],
    branch_results: dict[str, int],
    expected_kinds: dict[str, list[str]],
    detail: str,
) -> dict[str, Any]:
    delta = compute_delta(base_results, branch_results)
    observed = derive_verdict(delta)
    matches = all(
        set(delta.get(kind, [])) == set(expected_kinds.get(kind, []))
        for kind in ("regressions", "improvements", "pre_existing", "removed")
    )
    return {
        "id": case_id,
        "detail": detail,
        "observed_verdict": observed,
        "delta": delta,
        "expected_kinds": expected_kinds,
        "matches_expectation": matches,
    }


def run_clean_branch_matches_main_passes() -> dict[str, Any]:
    base = {"check_a.py": 0, "check_b.py": 0}
    branch = {"check_a.py": 0, "check_b.py": 0}
    return _run_case(
        "clean_branch_matches_main_passes",
        base,
        branch,
        {"regressions": [], "improvements": [], "pre_existing": [], "removed": []},
        "control: branch shares main's gate results; verdict PASS",
    )


def run_branch_introduces_new_failure_rejected() -> dict[str, Any]:
    base = {"check_a.py": 0, "check_b.py": 0}
    branch = {"check_a.py": 0, "check_b.py": 1}
    return _run_case(
        "branch_introduces_new_failure_rejected",
        base,
        branch,
        {
            "regressions": ["check_b.py"],
            "improvements": [],
            "pre_existing": [],
            "removed": [],
        },
        "mutation: a gate that passed on main now fails on branch; verdict FAIL",
    )


def run_branch_fixes_pre_existing_failure_passes() -> dict[str, Any]:
    base = {"check_a.py": 0, "check_b.py": 1}
    branch = {"check_a.py": 0, "check_b.py": 0}
    return _run_case(
        "branch_fixes_pre_existing_failure_passes",
        base,
        branch,
        {
            "regressions": [],
            "improvements": ["check_b.py"],
            "pre_existing": [],
            "removed": [],
        },
        "positive: branch fixes a pre-existing failure; verdict PASS",
    )


def run_pre_existing_failure_unchanged_is_informational() -> dict[str, Any]:
    base = {"check_a.py": 0, "check_b.py": 1}
    branch = {"check_a.py": 0, "check_b.py": 1}
    return _run_case(
        "pre_existing_failure_unchanged_is_informational",
        base,
        branch,
        {
            "regressions": [],
            "improvements": [],
            "pre_existing": ["check_b.py"],
            "removed": [],
        },
        "positive: branch and main share a failure; verdict PASS (informational)",
    )


def run_gate_added_only_on_branch_failing_is_regression() -> dict[str, Any]:
    base = {"check_a.py": 0}
    branch = {"check_a.py": 0, "check_b_new.py": 1}
    return _run_case(
        "gate_added_only_on_branch_failing_is_regression",
        base,
        branch,
        {
            "regressions": ["check_b_new.py"],
            "improvements": [],
            "pre_existing": [],
            "removed": [],
        },
        "mutation: SECURITY.md added a new gate that fails on branch; verdict FAIL",
    )


def run_gate_removed_on_branch_is_neutral() -> dict[str, Any]:
    base = {"check_a.py": 0, "check_b.py": 0}
    branch = {"check_a.py": 0}
    return _run_case(
        "gate_removed_on_branch_is_neutral",
        base,
        branch,
        {
            "regressions": [],
            "improvements": [],
            "pre_existing": [],
            "removed": ["check_b.py"],
        },
        "positive: SECURITY.md removed a gate on branch; not a regression; verdict PASS",
    )


CASE_RUNNERS = {
    "clean_branch_matches_main_passes": run_clean_branch_matches_main_passes,
    "branch_introduces_new_failure_rejected": run_branch_introduces_new_failure_rejected,
    "branch_fixes_pre_existing_failure_passes": run_branch_fixes_pre_existing_failure_passes,
    "pre_existing_failure_unchanged_is_informational": run_pre_existing_failure_unchanged_is_informational,
    "gate_added_only_on_branch_failing_is_regression": run_gate_added_only_on_branch_failing_is_regression,
    "gate_removed_on_branch_is_neutral": run_gate_removed_on_branch_is_neutral,
}


def evaluate() -> dict[str, Any]:
    cases = [CASE_RUNNERS[case_id]() for case_id in CASE_IDS]
    errors: list[str] = []
    by_id = {case["id"]: case for case in cases}
    for case_id, expected in EXPECTED_VERDICTS.items():
        case = by_id.get(case_id, {})
        observed = case.get("observed_verdict")
        if observed != expected:
            errors.append(
                f"{case_id} expected verdict {expected}, observed {observed or 'missing'}"
            )
        if not case.get("matches_expectation", False):
            errors.append(f"{case_id} delta classification did not match expectation")
    overall_pass = not errors
    mutation_case_ids = [cid for cid, v in EXPECTED_VERDICTS.items() if v == "FAIL"]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if overall_pass else "FAIL",
        "case_count": len(cases),
        "case_ids": list(CASE_IDS),
        "mutation_case_count": len(mutation_case_ids),
        "expected_case_verdicts": dict(EXPECTED_VERDICTS),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Gate-delta self-test is locked PASS; run --scan-repo against your "
            "branch to check for real regressions vs main."
            if overall_pass
            else "Fix gate-delta diff-logic blockers before relying on the check."
        ),
    }


def repo_scan_report(*, root: Path, base_ref: str, security_md: Path) -> dict[str, Any]:
    text = security_md.read_text(encoding="utf-8")
    commands = parse_security_md(text)
    if not commands:
        return {
            "schema": SCHEMA + "/repo-scan",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "verdict": "FAIL",
            "errors": [f"No gate commands found in {security_md.name}"],
            "dispatch_authorized": False,
            "live_providers_run": False,
        }

    self_command_substr = "check_gate_delta_vs_main.py"
    commands = [c for c in commands if self_command_substr not in c]

    # Strip --write-output so the delta check doesn't pollute the working
    # tree (the JSON status files would otherwise trip artifact_hygiene
    # and redact_strict_public_artifacts on the second-pass comparison).
    commands = [strip_write_output_flag(c) for c in commands]

    base_records, base_exit = run_gate_chain_on_ref(root, commands, base_ref=base_ref)
    branch_records, branch_exit = run_gate_chain_on_ref(root, commands, base_ref=None)
    delta = compute_delta(base_exit, branch_exit)
    verdict = derive_verdict(delta)

    return {
        "schema": SCHEMA + "/repo-scan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "base_ref": base_ref,
        "command_count": len(commands),
        "delta": delta,
        "base_results": [
            {"command": r["command"], "status": gate_status(r["exit_code"]), "exit_code": r["exit_code"]}
            for r in base_records
        ],
        "branch_results": [
            {"command": r["command"], "status": gate_status(r["exit_code"]), "exit_code": r["exit_code"]}
            for r in branch_records
        ],
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "No regressions vs main; safe to open the PR."
            if verdict == "PASS"
            else f"Fix {len(delta['regressions'])} regression(s) before opening the PR."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize() -> dict[str, Any]:
    return evaluate()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run SECURITY.md gates on this branch vs main; report regressions"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument(
        "--security-md",
        type=Path,
        default=None,
        help="Path to SECURITY.md (default: <root>/SECURITY.md)",
    )
    parser.add_argument(
        "--scan-repo",
        action="store_true",
        help="Run the production gate-delta check against the live repo",
    )
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.scan_repo:
        sec = args.security_md if args.security_md is not None else args.root / "SECURITY.md"
        payload = repo_scan_report(root=args.root.resolve(), base_ref=args.base_ref, security_md=sec)
    else:
        payload = evaluate()

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(
        json.dumps(payload, indent=2, sort_keys=True)
        if args.json
        else f"verdict={payload['verdict']}"
    )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
