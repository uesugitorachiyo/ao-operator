#!/usr/bin/env python3
"""SSH no-accept-new for high-risk actions gate.

Enforces the threat-model clause from docs/sdd/41-host-key-evidence-gate.md:

    "Do not use accept-new for remote DAST, manual pentest, or live remote
    worker transfer approval."

`StrictHostKeyChecking=accept-new` auto-trusts unknown SSH host keys on first
connection. For HIGH-risk action classes (remote DAST, manual pen-test, live
remote-worker transfer, live dispatch) that is unacceptable: an adversary on
the network path could serve their own host key on first contact and have it
trusted for the entire run.

The gate scans the repository tree for occurrences of
`StrictHostKeyChecking=accept-new` (and the space-separated form
`StrictHostKeyChecking accept-new`) inside files whose relative path matches
one of the HIGH-risk action tokens. Findings outside those tokens are not
flagged; this gate does not police low-risk documentation that mentions the
flag in prose.

The gate exercises four deterministic cases against a temporary work directory
(no repo pollution, no provider dispatch, no AO, no real SSH executed):

* ``clean_repo_has_no_accept_new_in_high_risk_paths`` -- control: a synthetic
  repo whose HIGH-risk paths contain only safe ssh invocations passes.
* ``accept_new_in_remote_dast_script_rejected`` -- mutation: a synthetic
  remote_dast/ shell script that uses StrictHostKeyChecking=accept-new is
  fail-closed.
* ``accept_new_in_pentest_yaml_rejected`` -- mutation: a synthetic pentest/
  yaml that uses StrictHostKeyChecking accept-new (space form) is fail-closed.
* ``accept_new_in_low_risk_path_allowed`` -- negative control: an occurrence of
  StrictHostKeyChecking=accept-new in a docs/ file outside any HIGH-risk path
  is NOT flagged (the gate does not police prose mentions in low-risk
  locations).

The gate exposes a ``scan_tree(root)`` helper so the SECURITY.md gate runner
can scan the live repo for findings as well.

The gate never invokes AO or provider CLIs and never authorizes dispatch.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "ssh-no-accept-new-for-high-risk-actions.json"
)
SCHEMA = "ao-operator/ssh-no-accept-new-for-high-risk-actions/v1"

# Path-segment tokens that mark a file as belonging to a HIGH-risk action class.
# Any file whose relative-path components include one of these tokens is
# subject to the no-accept-new scan.
HIGH_RISK_PATH_TOKENS: tuple[str, ...] = (
    "remote_dast",
    "remote-dast",
    "dast",
    "pentest",
    "manual_pentest",
    "manual-pentest",
    "remote_transfer",
    "remote-transfer",
    "remote_worker",
    "remote-worker",
    "live_dispatch",
    "live-dispatch",
)

# Suffixes we scan (text / config / scripts). Anything else is skipped to
# avoid binary noise and to keep the scan cheap on a large repo.
SCAN_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf"}
)

# The forbidden patterns. Both forms are valid ssh syntax:
#   ssh -o StrictHostKeyChecking=accept-new ...
#   ssh -o "StrictHostKeyChecking accept-new" ...
ACCEPT_NEW_PATTERN = re.compile(
    r"StrictHostKeyChecking\s*[=\s]\s*accept-new",
    flags=re.IGNORECASE,
)

# This gate's own source must contain the forbidden pattern (to scan for it).
# Exclude self and tests from the scan to avoid a false positive.
SELF_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "scripts/check_ssh_no_accept_new_for_high_risk_actions.py",
        "tests/test_check_ssh_no_accept_new_for_high_risk_actions.py",
    }
)

CASE_IDS = (
    "clean_repo_has_no_accept_new_in_high_risk_paths",
    "accept_new_in_remote_dast_script_rejected",
    "accept_new_in_pentest_yaml_rejected",
    "accept_new_in_low_risk_path_allowed",
)

EXPECTED_VERDICTS = {
    "clean_repo_has_no_accept_new_in_high_risk_paths": "PASS",
    "accept_new_in_remote_dast_script_rejected": "FAIL",
    "accept_new_in_pentest_yaml_rejected": "FAIL",
    "accept_new_in_low_risk_path_allowed": "PASS",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def is_high_risk_path(rel_posix: str) -> bool:
    """Return True if the relative path includes any HIGH-risk token."""
    parts = set(rel_posix.lower().split("/"))
    return any(token in parts for token in HIGH_RISK_PATH_TOKENS)


def is_exempt(rel_posix: str) -> bool:
    return rel_posix in SELF_EXEMPT_FILES


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = relpath(root, path)
        # Skip transient/build dirs.
        if rel.startswith((".git/", "node_modules/", "target/", "dist/", ".venv/")):
            continue
        yield path


def scan_file_for_violations(path: Path, root: Path) -> list[dict[str, Any]]:
    """Return a list of findings in this file. Empty list = clean."""
    rel = relpath(root, path)
    if is_exempt(rel):
        return []
    if not is_high_risk_path(rel):
        return []
    findings: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ACCEPT_NEW_PATTERN.search(line):
            findings.append(
                {
                    "path": rel,
                    "line": line_no,
                    "snippet": line.strip()[:200],
                }
            )
    return findings


def scan_tree(root: Path) -> list[dict[str, Any]]:
    """Scan a directory tree; return list of findings across all candidate files."""
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    for path in iter_candidate_files(root):
        findings.extend(scan_file_for_violations(path, root))
    return findings


def _materialize_fixture(work: Path, files: dict[str, str]) -> Path:
    fixture_root = work / "fixture"
    fixture_root.mkdir(parents=True, exist_ok=True)
    for rel, body in files.items():
        target = fixture_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return fixture_root


def _run_case(
    work: Path,
    case_id: str,
    files: dict[str, str],
    expected_finding_paths: tuple[str, ...],
    detail: str,
) -> dict[str, Any]:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    fixture_root = _materialize_fixture(case_dir, files)
    findings = scan_tree(fixture_root)
    expected = set(expected_finding_paths)
    actual = {f["path"] for f in findings}
    matches_expectation = actual == expected
    observed = "PASS" if not findings else "FAIL"
    transcript = case_dir / "ssh-no-accept-new-transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "fixture_files": sorted(files.keys()),
                "findings": findings,
                "expected_finding_paths": sorted(expected),
                "matches_expectation": matches_expectation,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "id": case_id,
        "detail": detail,
        "observed_verdict": observed,
        "findings": findings,
        "expected_finding_paths": sorted(expected),
        "matches_expectation": matches_expectation,
        "transcript": transcript.name,
    }


def run_clean_repo_has_no_accept_new_in_high_risk_paths(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "clean_repo_has_no_accept_new_in_high_risk_paths",
        {
            "remote_dast/probe.sh": (
                "#!/usr/bin/env bash\n"
                "ssh -o StrictHostKeyChecking=yes "
                "-o UserKnownHostsFile=evidence/known_hosts target.example "
                "true\n"
            ),
            "pentest/policies.yaml": "policies:\n  - name: refuse-opportunistic-trust\n",
            "docs/notes.md": "Mentions accept-new here in prose, not under a HIGH-risk path.\n",
        },
        expected_finding_paths=(),
        detail=(
            "control: a synthetic repo whose HIGH-risk paths contain only "
            "safe ssh invocations passes the scan with zero findings"
        ),
    )


def run_accept_new_in_remote_dast_script_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "accept_new_in_remote_dast_script_rejected",
        {
            "remote_dast/launch.sh": (
                "#!/usr/bin/env bash\n"
                "ssh -o StrictHostKeyChecking=accept-new target.example "
                "uname -a\n"
            ),
        },
        expected_finding_paths=("remote_dast/launch.sh",),
        detail=(
            "mutation: a synthetic remote_dast/ shell script that uses "
            "StrictHostKeyChecking=accept-new is fail-closed; the verifier "
            "MUST reject"
        ),
    )


def run_accept_new_in_pentest_yaml_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "accept_new_in_pentest_yaml_rejected",
        {
            "pentest/ssh-options.yaml": (
                "ssh_options:\n"
                '  - "StrictHostKeyChecking accept-new"\n'
            ),
        },
        expected_finding_paths=("pentest/ssh-options.yaml",),
        detail=(
            "mutation: a synthetic pentest/ yaml that uses the "
            "space-separated 'StrictHostKeyChecking accept-new' form is "
            "fail-closed; the verifier MUST reject"
        ),
    )


def run_accept_new_in_low_risk_path_allowed(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "accept_new_in_low_risk_path_allowed",
        {
            "docs/sdd/41-host-key-evidence-gate.md": (
                "Do not use StrictHostKeyChecking=accept-new for HIGH-risk "
                "actions.\n"
            ),
            "README.md": (
                "Avoid `StrictHostKeyChecking=accept-new` in remote ops "
                "scripts.\n"
            ),
        },
        expected_finding_paths=(),
        detail=(
            "negative control: an occurrence of accept-new in a docs/ file "
            "outside any HIGH-risk path is NOT flagged; the gate does not "
            "police prose mentions"
        ),
    )


CASE_RUNNERS = {
    "clean_repo_has_no_accept_new_in_high_risk_paths": run_clean_repo_has_no_accept_new_in_high_risk_paths,
    "accept_new_in_remote_dast_script_rejected": run_accept_new_in_remote_dast_script_rejected,
    "accept_new_in_pentest_yaml_rejected": run_accept_new_in_pentest_yaml_rejected,
    "accept_new_in_low_risk_path_allowed": run_accept_new_in_low_risk_path_allowed,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cases = [CASE_RUNNERS[case_id](work_dir) for case_id in CASE_IDS]
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
            errors.append(
                f"{case_id} finding-path set did not match expectation "
                f"(expected {case.get('expected_finding_paths')}, "
                f"got {[f['path'] for f in case.get('findings', [])]})"
            )
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
        "high_risk_path_tokens": list(HIGH_RISK_PATH_TOKENS),
        "scan_suffixes": sorted(SCAN_SUFFIXES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "SSH no-accept-new gate is locked fail-closed; proceed with "
            "remote-transfer host-key evidence verification."
            if overall_pass
            else "Fix SSH accept-new blockers before approving remote DAST "
            "or pen-test execution."
        ),
    }


def repo_scan_report(*, root: Path) -> dict[str, Any]:
    """Production-mode scan of the live repo. Used by SECURITY.md gate runs."""
    findings = scan_tree(root)
    return {
        "schema": SCHEMA + "/repo-scan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "verdict": "PASS" if not findings else "FAIL",
        "findings": findings,
        "high_risk_path_tokens": list(HIGH_RISK_PATH_TOKENS),
        "scan_suffixes": sorted(SCAN_SUFFIXES),
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(
        prefix="ao-operator-ssh-no-accept-new-"
    ) as tmp:
        return evaluate(work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate SSH no-accept-new invariant for HIGH-risk action classes"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument(
        "--scan-repo",
        action="store_true",
        help="Run a production scan of --root for accept-new in HIGH-risk paths instead of self-tests",
    )
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.scan_repo:
        payload = repo_scan_report(root=args.root.resolve())
    else:
        if args.work_dir is not None:
            payload = evaluate(work_dir=args.work_dir)
        else:
            with tempfile.TemporaryDirectory(
                prefix="ao-operator-ssh-no-accept-new-"
            ) as tmp:
                payload = evaluate(work_dir=Path(tmp))

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
