#!/usr/bin/env python3
"""Remote-transfer SSH StrictHostKeyChecking enforcement gate.

Enforces the threat-model clause from docs/sdd/41-host-key-evidence-gate.md:

    "Remote transfer commands must use StrictHostKeyChecking=yes and
    UserKnownHostsFile."

A remote-transfer script that simply omits the flag inherits whatever the
operator's local ~/.ssh/config or system default says. On a host where
StrictHostKeyChecking is set to "no" or "ask" in personal config, the omission
silently allows MITM. Explicit-positive enforcement is the safe form.

The gate scans the repository tree for files under remote-transfer / remote-
worker path tokens that invoke ssh / scp / sftp / rsync. Every such file is
required to mention BOTH:

    - StrictHostKeyChecking=yes (or the space-separated `StrictHostKeyChecking yes` form)
    - UserKnownHostsFile

If either marker is absent from a file that contains a remote-transfer
invocation, the gate fail-closes with a finding describing the missing marker.

The gate exercises five deterministic cases against a temporary work directory
(no repo pollution, no provider dispatch, no AO, no real SSH executed):

* ``clean_repo_passes`` -- control: synthetic remote_transfer/ files that
  invoke ssh/scp with both required markers pass the scan with zero findings.
* ``ssh_invocation_missing_strict_flag_rejected`` -- mutation: an ssh
  invocation in remote_transfer/ that omits StrictHostKeyChecking=yes is
  fail-closed.
* ``ssh_invocation_missing_known_hosts_flag_rejected`` -- mutation: an ssh
  invocation in remote_transfer/ that omits UserKnownHostsFile is fail-closed.
* ``scp_invocation_with_both_flags_passes`` -- positive case: an scp
  invocation that has both required markers passes.
* ``rsync_e_ssh_invocation_with_both_flags_passes`` -- positive case: an
  rsync invocation using `-e ssh -o ...` form with both markers passes.

The gate exposes a ``scan_tree(root)`` helper so the SECURITY.md gate runner
can scan the live repo as well.

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
    "remote-transfer-ssh-strict-hostkey-enforced.json"
)
SCHEMA = "ao-operator/remote-transfer-ssh-strict-hostkey-enforced/v1"

# Path-segment tokens that mark a file as belonging to remote-transfer scope.
REMOTE_TRANSFER_PATH_TOKENS: tuple[str, ...] = (
    "remote_transfer",
    "remote-transfer",
    "remote_worker",
    "remote-worker",
)

# Suffixes we scan for remote-transfer invocations.
SCAN_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf"}
)

# Word-boundaried regex for the remote-transfer client binaries. Matches when
# preceded by start-of-line / whitespace / common shell delimiters, to avoid
# false positives like ``unsshable``.
INVOCATION_PATTERN = re.compile(
    r"(?:(?:^|[\s;&|`(\"'=])|/)(?:ssh|scp|sftp|rsync)\b",
    flags=re.MULTILINE,
)

# Both equals and space-separated forms of the required positive marker.
STRICT_YES_PATTERN = re.compile(
    r"StrictHostKeyChecking\s*[=\s]\s*yes",
    flags=re.IGNORECASE,
)

# Marker for the required UserKnownHostsFile directive. We don't validate the
# path value; presence of the directive is the gate.
USER_KNOWN_HOSTS_PATTERN = re.compile(r"UserKnownHostsFile", flags=re.IGNORECASE)

SELF_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "scripts/check_remote_transfer_ssh_strict_hostkey_enforced.py",
        "tests/test_check_remote_transfer_ssh_strict_hostkey_enforced.py",
    }
)

CASE_IDS = (
    "clean_repo_passes",
    "ssh_invocation_missing_strict_flag_rejected",
    "ssh_invocation_missing_known_hosts_flag_rejected",
    "scp_invocation_with_both_flags_passes",
    "rsync_e_ssh_invocation_with_both_flags_passes",
)

EXPECTED_VERDICTS = {
    "clean_repo_passes": "PASS",
    "ssh_invocation_missing_strict_flag_rejected": "FAIL",
    "ssh_invocation_missing_known_hosts_flag_rejected": "FAIL",
    "scp_invocation_with_both_flags_passes": "PASS",
    "rsync_e_ssh_invocation_with_both_flags_passes": "PASS",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def is_remote_transfer_path(rel_posix: str) -> bool:
    parts = set(rel_posix.lower().split("/"))
    return any(token in parts for token in REMOTE_TRANSFER_PATH_TOKENS)


def is_exempt(rel_posix: str) -> bool:
    return rel_posix in SELF_EXEMPT_FILES


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = relpath(root, path)
        if rel.startswith((".git/", "node_modules/", "target/", "dist/", ".venv/")):
            continue
        yield path


def scan_file_for_violations(path: Path, root: Path) -> list[dict[str, Any]]:
    rel = relpath(root, path)
    if is_exempt(rel):
        return []
    if not is_remote_transfer_path(rel):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not INVOCATION_PATTERN.search(text):
        return []
    has_strict_yes = bool(STRICT_YES_PATTERN.search(text))
    has_user_known_hosts = bool(USER_KNOWN_HOSTS_PATTERN.search(text))
    findings: list[dict[str, Any]] = []
    if not has_strict_yes:
        findings.append(
            {
                "path": rel,
                "issue": "missing_StrictHostKeyChecking_yes",
                "remediation": (
                    "Add `-o StrictHostKeyChecking=yes` to the ssh/scp/sftp/rsync "
                    "invocation in this remote-transfer file."
                ),
            }
        )
    if not has_user_known_hosts:
        findings.append(
            {
                "path": rel,
                "issue": "missing_UserKnownHostsFile",
                "remediation": (
                    "Add `-o UserKnownHostsFile=<path-to-reviewed-known_hosts>` "
                    "to the ssh/scp/sftp/rsync invocation in this remote-transfer file."
                ),
            }
        )
    return findings


def scan_tree(root: Path) -> list[dict[str, Any]]:
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
    transcript = case_dir / "remote-transfer-strict-hostkey-transcript.json"
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


_KNOWN_HOSTS_FRAG = "UserKnownHostsFile=evidence/known_hosts"


def run_clean_repo_passes(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "clean_repo_passes",
        {
            "remote_transfer/push.sh": (
                "#!/usr/bin/env bash\n"
                "ssh "
                "-o StrictHostKeyChecking=yes "
                f"-o {_KNOWN_HOSTS_FRAG} "
                "operator@target.example "
                "true\n"
            ),
            "remote_transfer/pull.sh": (
                "#!/usr/bin/env bash\n"
                "scp "
                "-o StrictHostKeyChecking=yes "
                f"-o {_KNOWN_HOSTS_FRAG} "
                "operator@target.example:/var/log/bundle.tar /tmp/\n"
            ),
            "docs/example.md": (
                "Documentation only; outside remote-transfer scope.\n"
            ),
        },
        expected_finding_paths=(),
        detail=(
            "control: synthetic remote_transfer/ files that invoke ssh/scp "
            "with both StrictHostKeyChecking=yes and UserKnownHostsFile pass "
            "the scan with zero findings"
        ),
    )


def run_ssh_invocation_missing_strict_flag_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "ssh_invocation_missing_strict_flag_rejected",
        {
            "remote_transfer/launch.sh": (
                "#!/usr/bin/env bash\n"
                "ssh "
                f"-o {_KNOWN_HOSTS_FRAG} "
                "operator@target.example uname -a\n"
            ),
        },
        expected_finding_paths=("remote_transfer/launch.sh",),
        detail=(
            "mutation: an ssh invocation in remote_transfer/ that omits "
            "StrictHostKeyChecking=yes is fail-closed; the verifier MUST reject"
        ),
    )


def run_ssh_invocation_missing_known_hosts_flag_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "ssh_invocation_missing_known_hosts_flag_rejected",
        {
            "remote_transfer/launch.sh": (
                "#!/usr/bin/env bash\n"
                "ssh "
                "-o StrictHostKeyChecking=yes "
                "operator@target.example uname -a\n"
            ),
        },
        expected_finding_paths=("remote_transfer/launch.sh",),
        detail=(
            "mutation: an ssh invocation in remote_transfer/ that omits "
            "UserKnownHostsFile is fail-closed; the verifier MUST reject"
        ),
    )


def run_scp_invocation_with_both_flags_passes(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "scp_invocation_with_both_flags_passes",
        {
            "remote_worker/upload.sh": (
                "#!/usr/bin/env bash\n"
                "scp "
                "-o StrictHostKeyChecking=yes "
                f"-o {_KNOWN_HOSTS_FRAG} "
                "/local/bundle.tar operator@target.example:/staging/\n"
            ),
        },
        expected_finding_paths=(),
        detail=(
            "positive case: an scp invocation with both required markers "
            "passes the scan"
        ),
    )


def run_rsync_e_ssh_invocation_with_both_flags_passes(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "rsync_e_ssh_invocation_with_both_flags_passes",
        {
            "remote_worker/sync.sh": (
                "#!/usr/bin/env bash\n"
                'rsync -av -e "ssh '
                "-o StrictHostKeyChecking=yes "
                f"-o {_KNOWN_HOSTS_FRAG}"
                '" '
                "/local/bundle/ operator@target.example:/staging/\n"
            ),
        },
        expected_finding_paths=(),
        detail=(
            "positive case: an rsync invocation using -e ssh with both "
            "required markers passes the scan"
        ),
    )


CASE_RUNNERS = {
    "clean_repo_passes": run_clean_repo_passes,
    "ssh_invocation_missing_strict_flag_rejected": run_ssh_invocation_missing_strict_flag_rejected,
    "ssh_invocation_missing_known_hosts_flag_rejected": run_ssh_invocation_missing_known_hosts_flag_rejected,
    "scp_invocation_with_both_flags_passes": run_scp_invocation_with_both_flags_passes,
    "rsync_e_ssh_invocation_with_both_flags_passes": run_rsync_e_ssh_invocation_with_both_flags_passes,
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
        "remote_transfer_path_tokens": list(REMOTE_TRANSFER_PATH_TOKENS),
        "scan_suffixes": sorted(SCAN_SUFFIXES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Remote-transfer SSH StrictHostKeyChecking gate is locked "
            "fail-closed; proceed with host-key evidence collection."
            if overall_pass
            else "Fix remote-transfer SSH strict-hostkey blockers before "
            "approving remote transfer execution."
        ),
    }


def repo_scan_report(*, root: Path) -> dict[str, Any]:
    findings = scan_tree(root)
    return {
        "schema": SCHEMA + "/repo-scan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "verdict": "PASS" if not findings else "FAIL",
        "findings": findings,
        "remote_transfer_path_tokens": list(REMOTE_TRANSFER_PATH_TOKENS),
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
        prefix="ao-operator-remote-transfer-strict-hostkey-"
    ) as tmp:
        return evaluate(work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate remote-transfer SSH StrictHostKeyChecking enforcement"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument(
        "--scan-repo",
        action="store_true",
        help="Run a production scan of --root for missing strict-hostkey markers in remote-transfer files",
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
                prefix="ao-operator-remote-transfer-strict-hostkey-"
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
