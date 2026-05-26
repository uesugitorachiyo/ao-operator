#!/usr/bin/env python3
"""Run deterministic closure checks for ai-teams repos."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


# Phase 2 exit-gate item #4 wiring. The AO2 native evaluator decision is
# written by `ao2 factory evaluator-decision`; the verification artifact is
# emitted by `ao2 factory verify-evaluator-decision --decision <path> --json`.
# When closure consults the AO2 verdict, only the verifier's view is
# load-bearing — ao-operator must never re-derive the verdict from the raw
# decision JSON itself, so AO2 stays the closure authority.
AO2_NATIVE_EVALUATOR_DECISION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-result.v1"
AO2_NATIVE_EVALUATOR_VERIFICATION_SCHEMA = (
    "ao2.ao-operator-compat-native-evaluator-verification.v1"
)
AO2_NATIVE_EVALUATOR_VERIFICATION_OWNER = "ao2-native-evaluator-decision-verifier"
AO2_NATIVE_EVALUATOR_FACTORY_V3_ROLE = "parity_oracle_only"


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


def obligation_ledger_evidence(repo: Path, *, require: bool) -> dict[str, Any]:
    """Verify AO2 obligation ledgers when a run emits them.

    This is the deterministic spec-delta closure loop: a provider may claim
    DONE, but closure still fails if any durable MUST/rubric/content
    obligation remains failed or unverified.
    """
    candidates = [
        *repo.glob("run-artifacts/**/obligation-ledger.json"),
        *repo.glob("docs/evaluations/**/*obligation*.json"),
        *repo.glob(".ao2/**/obligation-ledger.json"),
    ]
    ledgers = sorted({path.resolve() for path in candidates})
    details: list[str] = []
    reports: list[dict[str, Any]] = []

    if require and not ledgers:
        details.append("required obligation ledger was not found")

    for path in ledgers:
        rel = path.relative_to(repo) if path.is_relative_to(repo) else path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            details.append(f"{rel}: could not parse obligation ledger: {exc}")
            continue
        if isinstance(data.get("obligations"), list) and isinstance(data.get("source_contracts"), list):
            try:
                import obligation_ledger

                data = obligation_ledger.check_ledger(data, repo)
                obligation_ledger.write_ledger(path, data)
            except Exception as exc:
                details.append(f"{rel}: could not check obligation ledger: {exc}")
                continue

        schema = data.get("schema_version")
        verdict = data.get("verdict")
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        fail = _int_value(summary.get("fail"))
        unverified = _int_value(summary.get("unverified"))
        reports.append(
            {
                "path": str(rel),
                "schema_version": schema,
                "verdict": verdict,
                "fail": fail,
                "unverified": unverified,
            }
        )

        if schema != "ao2.obligation-ledger.v1":
            details.append(f"{rel}: schema_version must be ao2.obligation-ledger.v1")
        if verdict != "accepted":
            details.append(f"{rel}: verdict must be accepted")
        if fail != 0:
            details.append(f"{rel}: fail count must be 0, got {fail}")
        if unverified != 0:
            details.append(f"{rel}: unverified count must be 0, got {unverified}")

    return {
        "verdict": "FAIL" if details else "PASS",
        "details": details,
        "ledger_count": len(ledgers),
        "reports": reports,
    }


def _find_ao2_binary(repo: Path) -> str | None:
    """Locate the ao2 binary closure should call for AO2 verdict subsumption.

    Honors the explicit ``AO2_BINARY`` / ``AO2_BIN`` env overrides first, then
    looks for a release/debug binary inside an adjacent ``ao2`` checkout
    (the standard local layout where ao-operator and ao2 sit side by side),
    then falls back to ``shutil.which("ao2")`` for an installed binary.
    """
    for env_key in ("AO2_BINARY", "AO2_BIN"):
        override = os.environ.get(env_key)
        if override and Path(override).is_file():
            return override
    repo_resolved = repo.resolve()
    sibling = repo_resolved.parent / "ao2"
    for relative in ("target/release/ao2", "target/debug/ao2"):
        candidate = sibling / relative
        if candidate.is_file():
            return str(candidate)
    discovered = shutil.which("ao2")
    return discovered


def _check_ao2_native_evaluator_verification(payload: dict[str, Any]) -> list[str]:
    """Return a list of detail strings explaining why a verification is unsafe.

    Empty list means the verification is acceptable: the AO2 native evaluator
    decision is signed, signature-verified end-to-end, the trust boundary is
    intact, and the verifier identifies itself as the AO2-owned decision
    verifier with ao-operator in the parity-oracle role. Anything else is a
    closure-blocking detail.
    """
    details: list[str] = []
    if not isinstance(payload, dict):
        return ["AO2 verifier returned a non-object JSON value"]
    if payload.get("schema_version") != AO2_NATIVE_EVALUATOR_VERIFICATION_SCHEMA:
        details.append(
            "verification schema_version must be "
            f"{AO2_NATIVE_EVALUATOR_VERIFICATION_SCHEMA!r}, got "
            f"{payload.get('schema_version')!r}"
        )
    if payload.get("status") != "accepted":
        details.append(
            f"verification status must be 'accepted', got {payload.get('status')!r}"
        )
    if payload.get("signature_status") != "signed":
        details.append(
            f"signature_status must be 'signed', got {payload.get('signature_status')!r}"
        )
    for flag in (
        "signature_verified",
        "signature_digest_match",
        "public_key_digest_match",
        "signed_payload_digest_match",
        "decision_payload_matches_signed_payload",
        "signature_requirement_satisfied",
        "trust_boundary_ok",
    ):
        if payload.get(flag) is not True:
            details.append(f"{flag} must be true, got {payload.get(flag)!r}")
    if payload.get("ao2_decision_owner") != AO2_NATIVE_EVALUATOR_VERIFICATION_OWNER:
        details.append(
            "ao2_decision_owner must be "
            f"{AO2_NATIVE_EVALUATOR_VERIFICATION_OWNER!r}, got "
            f"{payload.get('ao2_decision_owner')!r}"
        )
    if payload.get("factory_v3_role") != AO2_NATIVE_EVALUATOR_FACTORY_V3_ROLE:
        details.append(
            "factory_v3_role must be "
            f"{AO2_NATIVE_EVALUATOR_FACTORY_V3_ROLE!r}, got "
            f"{payload.get('factory_v3_role')!r}"
        )
    return details


def _run_ao2_evaluator_decision_verifier(
    ao2_binary: str, decision_path: Path, timeout: int
) -> tuple[dict[str, Any] | None, list[str]]:
    """Subprocess-call ``ao2 factory verify-evaluator-decision --json``."""
    argv = [
        ao2_binary,
        "factory",
        "verify-evaluator-decision",
        "--decision",
        str(decision_path),
        "--json",
    ]
    try:
        completed = subprocess.run(
            argv,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, [f"ao2 binary {ao2_binary!r} could not be executed"]
    except subprocess.TimeoutExpired:
        return None, [
            f"ao2 factory verify-evaluator-decision timed out after {timeout}s"
        ]
    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "").strip()[-512:]
        return None, [
            "ao2 factory verify-evaluator-decision exited "
            f"{completed.returncode}: {stderr_tail or '<no stderr>'}"
        ]
    stdout = (completed.stdout or "").strip()
    if not stdout:
        return None, ["ao2 factory verify-evaluator-decision produced no stdout JSON"]
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, [f"ao2 factory verify-evaluator-decision returned invalid JSON: {exc}"]
    return payload, []


def _discover_ao2_native_evaluator_decisions(repo: Path) -> list[Path]:
    """Find checked-in AO2 native evaluator decision JSONs in the repo.

    Excludes ``*.signed-payload.json`` sidecars (those are the bytes the
    signature was computed over — they are not a decision file).
    """
    candidates: list[Path] = []
    for pattern in (
        "run-artifacts/**/ao2-native-evaluator-decision.json",
        "run-artifacts/**/release-ao2-native-evaluator-decision.json",
        "run-artifacts/**/*-ao2-native-evaluator-decision.json",
        "docs/evaluations/**/ao2-native-evaluator-decision.json",
        ".ao2/**/ao2-native-evaluator-decision.json",
    ):
        candidates.extend(repo.glob(pattern))
    decisions: set[Path] = set()
    for path in candidates:
        if path.name.endswith(".signed-payload.json"):
            continue
        decisions.add(path.resolve())
    return sorted(decisions)


def ao2_evaluator_decision_evidence(
    repo: Path,
    *,
    require: bool,
    ao2_binary: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Defer closure to AO2's native evaluator-decision verifier verdict.

    Phase 2 exit-gate item #4: AO2's closure verdict subsumes ao-operator's.
    When opt-in (``require=True``), discover any AO2 native evaluator
    decisions checked into the repo and reject closure unless the AO2
    verifier accepts every one of them. The verifier itself owns the
    signature, trust-boundary, and digest checks — this function only
    consumes the verifier's verdict and refuses closure on anything other
    than a fully-clean accept.

    The check is opt-in because not every repo carries an AO2 native
    evaluator decision yet; closures that pre-date AO2 native evaluation
    must keep passing unchanged. When ``require=True`` and a decision is
    present, the closure refuses to "pass" with an unsigned, missing, or
    rejected verdict, even if the rest of the closure checks succeed.
    """
    decisions = _discover_ao2_native_evaluator_decisions(repo)
    details: list[str] = []
    reports: list[dict[str, Any]] = []

    if require and not decisions:
        details.append("required AO2 native evaluator decision was not found")

    if not decisions or not require:
        return {
            "verdict": "FAIL" if details else "PASS",
            "details": details,
            "decision_count": len(decisions),
            "reports": reports,
            "ao2_binary_resolved": None,
        }

    binary = ao2_binary if ao2_binary is not None else _find_ao2_binary(repo)
    if not binary:
        details.append(
            "ao2 binary not found; closure cannot consult AO2 native evaluator "
            "verdict (set AO2_BINARY, install ao2 on PATH, or build ao2 sibling)"
        )
        return {
            "verdict": "FAIL",
            "details": details,
            "decision_count": len(decisions),
            "reports": reports,
            "ao2_binary_resolved": None,
        }

    for path in decisions:
        rel = path.relative_to(repo) if path.is_relative_to(repo) else path
        try:
            decision_data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            details.append(f"{rel}: could not parse AO2 native evaluator decision: {exc}")
            reports.append({"path": str(rel), "verdict": "FAIL"})
            continue
        decision_schema = decision_data.get("schema_version") if isinstance(decision_data, dict) else None
        if decision_schema != AO2_NATIVE_EVALUATOR_DECISION_SCHEMA:
            details.append(
                f"{rel}: schema_version must be "
                f"{AO2_NATIVE_EVALUATOR_DECISION_SCHEMA!r}, got {decision_schema!r}"
            )
            reports.append(
                {
                    "path": str(rel),
                    "decision_schema_version": decision_schema,
                    "verdict": "FAIL",
                }
            )
            continue

        verification, run_errors = _run_ao2_evaluator_decision_verifier(binary, path, timeout)
        if verification is None:
            for err in run_errors:
                details.append(f"{rel}: {err}")
            reports.append({"path": str(rel), "verdict": "FAIL"})
            continue
        verification_errors = _check_ao2_native_evaluator_verification(verification)
        verdict = "FAIL" if verification_errors else "PASS"
        reports.append(
            {
                "path": str(rel),
                "decision_schema_version": decision_schema,
                "verification_schema_version": verification.get("schema_version"),
                "verification_status": verification.get("status"),
                "signature_status": verification.get("signature_status"),
                "verdict": verdict,
            }
        )
        for err in verification_errors:
            details.append(f"{rel}: {err}")

    return {
        "verdict": "FAIL" if details else "PASS",
        "details": details,
        "decision_count": len(decisions),
        "reports": reports,
        "ao2_binary_resolved": binary,
    }


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


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
    require_obligation_ledger: bool = False,
    require_ao2_evaluator_decision: bool = False,
    ao2_binary: str | None = None,
) -> dict[str, Any]:
    commands = closure_commands(repo, include_pytest=include_pytest)
    for item in extra:
        commands.append(_portable_shell_args(item))

    if dry_run:
        return {
            "repo": str(repo),
            "verdict": "PASS",
            "commands": commands,
            "results": [],
            "errors": [],
        }

    warning_errors = [] if commands else ["no known closure commands found"]
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

    obligation_result = obligation_ledger_evidence(repo, require=require_obligation_ledger)
    if obligation_result["verdict"] == "FAIL":
        errors.extend(obligation_result["details"])

    ao2_evaluator_result = ao2_evaluator_decision_evidence(
        repo,
        require=require_ao2_evaluator_decision,
        ao2_binary=ao2_binary,
        timeout=timeout,
    )
    if ao2_evaluator_result["verdict"] == "FAIL":
        errors.extend(ao2_evaluator_result["details"])

    verdict = "FAIL" if errors else ("WARN" if warning_errors else "PASS")
    return {
        "repo": str(repo),
        "verdict": verdict,
        "commands": commands,
        "results": results,
        "errors": [*warning_errors, *errors],
        "trigger_evidence": trigger_result,
        "gate_r_evidence": gate_r_result,
        "obligation_ledger_evidence": obligation_result,
        "ao2_evaluator_decision_evidence": ao2_evaluator_result,
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
        required = run(repo, include_pytest=False, timeout=10, dry_run=False, extra=[], require_obligation_ledger=True)
        if required["verdict"] != "FAIL" or "required obligation ledger was not found" not in required["errors"]:
            print(json.dumps(required, indent=2), file=sys.stderr)
            return 1
        ao2_required = run(
            repo,
            include_pytest=False,
            timeout=10,
            dry_run=False,
            extra=[],
            require_ao2_evaluator_decision=True,
        )
        if ao2_required["verdict"] != "FAIL" or "required AO2 native evaluator decision was not found" not in ao2_required["errors"]:
            print(json.dumps(ao2_required, indent=2), file=sys.stderr)
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
        "--require-obligation-ledger",
        action="store_true",
        help="fail closure when no AO2 obligation ledger is present",
    )
    parser.add_argument(
        "--require-ao2-evaluator-decision",
        action="store_true",
        help=(
            "fail closure unless every AO2 native evaluator decision in the "
            "repo is accepted by `ao2 factory verify-evaluator-decision` "
            "(Phase 2 exit-gate #4: AO2 owns the closure verdict)"
        ),
    )
    parser.add_argument(
        "--ao2-binary",
        default=None,
        help=(
            "Override the ao2 binary path used by --require-ao2-evaluator-decision "
            "(defaults to $AO2_BINARY, then ../ao2/target/release/ao2, then $PATH)"
        ),
    )
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
        require_obligation_ledger=args.require_obligation_ledger,
        require_ao2_evaluator_decision=args.require_ao2_evaluator_decision,
        ao2_binary=args.ao2_binary,
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
