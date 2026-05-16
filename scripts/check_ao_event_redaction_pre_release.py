#!/usr/bin/env python3
"""AO event-log redaction pre-release gate.

Enforces the threat-model clause from docs/sdd/39-security-threat-model-data-flow.md:

    "AO events and role artifacts must be redacted before public release."

The existing check_public_release_security.py scans source/docs FILES for HIGH
and MEDIUM patterns (private keys, API keys, personal paths, private IPs).
The existing redact_strict_public_artifacts.py rewrites markdown bodies in
run-artifacts/ and docs/evaluations/. Neither one walks the EMBEDDED JSON
payloads inside AO runtime event logs (the ao-runtime events.jsonl format
emitted into run-artifacts/<run_id>/events.jsonl and similar locations).

Without this gate, an operator who copies an events.jsonl into a public-release
evidence pack can leak a personal path, an API key, or a private IP inside a
task.completed payload's stdout field, because the wrapper-file scan never
inspects the JSON body.

This gate walks AO event-log JSON content, extracts every string value from
the payload tree, and runs each value through the same HIGH/MEDIUM redaction
patterns used by check_public_release_security.py — plus a base64 round-trip
defense so a naive base64-encoded secret cannot slip past a string-match-only
scanner.

The gate exercises six deterministic cases against a temporary work directory
(no repo pollution, no provider dispatch, no AO, no real event log written):

* ``clean_events_log_passes`` -- control: a synthetic events.jsonl with only
  benign payloads passes the scan with zero findings.
* ``personal_path_in_stdout_rejected`` -- mutation: a task.completed payload
  whose stdout contains a /Users/ or /home/ path is fail-closed.
* ``anthropic_api_key_pattern_in_stderr_rejected`` -- mutation: a payload
  whose stderr contains an ANTHROPIC_API_KEY=sk-... marker is fail-closed.
* ``bearer_token_in_artifact_payload_rejected`` -- mutation: a task.artifact
  payload containing a "Bearer <token>" string is fail-closed.
* ``private_ipv4_in_task_metadata_rejected`` -- mutation: a payload field
  containing a 10/8, 192.168/16, or 172.16-31/12 IPv4 is fail-closed.
* ``base64_round_trip_secret_in_payload_rejected`` -- mutation: a payload
  field that decodes (base64) to a value matching a HIGH pattern is
  fail-closed.

Every case lays down a per-case events.jsonl in a temporary work directory,
runs it through the verifier, and records observed_verdict. The gate's overall
verdict is PASS only when every case lines up with the expected verdict.

The gate exposes a ``scan_events_log(path)`` helper for the SECURITY.md gate
runner and a ``scan_tree(root)`` helper that walks all events.jsonl files
under run-artifacts/ and docs/evaluations/.

The gate never invokes AO or provider CLIs and never authorizes dispatch.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "ao-event-redaction-pre-release.json"
)
SCHEMA = "ao-operator/ao-event-redaction-pre-release/v1"

# HIGH-severity patterns. Mirrors check_public_release_security.py categories
# (private_key, openai_api_key, anthropic_api_key, bearer_token).
HIGH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key_block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "openai_api_key",
        re.compile(r"OPENAI_API_KEY\s*=\s*[A-Za-z0-9_\-]{8,}"),
    ),
    (
        "anthropic_api_key",
        re.compile(r"ANTHROPIC_API_KEY\s*=\s*[A-Za-z0-9_\-]{8,}"),
    ),
    (
        "anthropic_sk_prefix_token",
        re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ),
    (
        "bearer_token",
        re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{12,}"),
    ),
)

# MEDIUM-severity patterns. Mirrors public-release scanner.
MEDIUM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "personal_path",
        re.compile(
            r"(?:/Users/[A-Za-z0-9_.\-]+|/home/[A-Za-z0-9_.\-]+|/opt/ai-workstation/[A-Za-z0-9_.\-/]+)"
        ),
    ),
    (
        "private_network_target",
        re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
        ),
    ),
    (
        "stale_context_marker",
        re.compile(r"<claude-mem-context>|FACTORY_V3_LLM_WIKI_PATH|path:llm_wiki"),
    ),
)

# Suffixes treated as AO event-log JSON. events.jsonl is the canonical format;
# events.json is used for single-run aggregated views.
EVENT_LOG_NAMES: frozenset[str] = frozenset({"events.jsonl", "events.json"})

# Self-exempt files so the gate doesn't flag its own pattern strings.
SELF_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "scripts/check_ao_event_redaction_pre_release.py",
        "tests/test_check_ao_event_redaction_pre_release.py",
    }
)

# Path segments that mark a debug-only capture tree (not release-bound).
# Files under these segments contain raw pre-redaction event payloads by
# design (e.g. failure-snapshots/<incident-id>/runs/.../events.jsonl). A
# separate redaction process handles them before they enter the public-release
# evidence pack, so scan-repo skips them. The synthetic-case self-test
# (default mode) is unaffected — it always runs in a temp directory.
DEBUG_CAPTURE_PATH_SEGMENTS: tuple[str, ...] = (
    "failure-snapshots",
    "failure_snapshots",
)

CASE_IDS = (
    "clean_events_log_passes",
    "personal_path_in_stdout_rejected",
    "anthropic_api_key_pattern_in_stderr_rejected",
    "bearer_token_in_artifact_payload_rejected",
    "private_ipv4_in_task_metadata_rejected",
    "base64_round_trip_secret_in_payload_rejected",
)

EXPECTED_VERDICTS = {
    "clean_events_log_passes": "PASS",
    "personal_path_in_stdout_rejected": "FAIL",
    "anthropic_api_key_pattern_in_stderr_rejected": "FAIL",
    "bearer_token_in_artifact_payload_rejected": "FAIL",
    "private_ipv4_in_task_metadata_rejected": "FAIL",
    "base64_round_trip_secret_in_payload_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _iter_strings(node: Any) -> Iterable[tuple[str, Any]]:
    """Walk a JSON-like tree; yield (json-pointer-ish path, string value) tuples."""

    def _walk(prefix: str, obj: Any) -> Iterable[tuple[str, Any]]:
        if isinstance(obj, dict):
            for key, value in obj.items():
                yield from _walk(f"{prefix}/{key}" if prefix else f"/{key}", value)
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                yield from _walk(f"{prefix}/{idx}" if prefix else f"/{idx}", value)
        elif isinstance(obj, str):
            yield prefix or "/", obj

    yield from _walk("", node)


def _scan_string_for_patterns(value: str) -> list[tuple[str, str]]:
    """Return list of (severity, finding_id) hits in a single string."""
    hits: list[tuple[str, str]] = []
    for name, pattern in HIGH_PATTERNS:
        if pattern.search(value):
            hits.append(("HIGH", name))
    for name, pattern in MEDIUM_PATTERNS:
        if pattern.search(value):
            hits.append(("MEDIUM", name))
    return hits


_BASE64_LIKELY = re.compile(r"^[A-Za-z0-9+/]{16,}={0,2}$")


def _attempt_base64_decode(value: str) -> str | None:
    """Return decoded string if value looks like base64 and decodes to printable text."""
    stripped = value.strip()
    if not _BASE64_LIKELY.match(stripped):
        return None
    # Length must be a multiple of 4 (base64 requirement, possibly with padding).
    if len(stripped) % 4 != 0:
        return None
    try:
        decoded = base64.b64decode(stripped, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    try:
        text = decoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    # Reject blobs whose decoded form is mostly non-printable (likely binary).
    printable = sum(1 for c in text if c.isprintable() or c in {"\n", "\t", " "})
    if not text or printable / max(len(text), 1) < 0.85:
        return None
    return text


def scan_event_payloads(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan a sequence of event dicts; return list of findings."""
    findings: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("id") or event.get("event_id") or "<unknown>")
        for json_path, value in _iter_strings(event):
            for severity, finding_id in _scan_string_for_patterns(value):
                findings.append(
                    {
                        "event_id": event_id,
                        "json_path": json_path,
                        "severity": severity,
                        "finding_id": finding_id,
                        "snippet": value[:200],
                    }
                )
            decoded = _attempt_base64_decode(value)
            if decoded is not None:
                for severity, finding_id in _scan_string_for_patterns(decoded):
                    findings.append(
                        {
                            "event_id": event_id,
                            "json_path": json_path,
                            "severity": severity,
                            "finding_id": f"base64::{finding_id}",
                            "snippet": value[:200],
                            "decoded_snippet": decoded[:200],
                        }
                    )
    return findings


def parse_events_log(path: Path) -> list[dict[str, Any]]:
    """Parse an events.jsonl or events.json file into a list of event dicts."""
    text = path.read_text(encoding="utf-8", errors="replace")
    events: list[dict[str, Any]] = []
    if path.name == "events.jsonl":
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                events.append(
                    {
                        "id": f"<malformed-line-{line_no}>",
                        "_parse_error": str(exc),
                    }
                )
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            events.append({"id": "<malformed-json>", "_parse_error": str(exc)})
            return events
        if isinstance(payload, list):
            events.extend(payload)
        elif isinstance(payload, dict):
            inner = payload.get("events")
            if isinstance(inner, list):
                events.extend(inner)
            else:
                events.append(payload)
    return events


def scan_events_log(path: Path) -> list[dict[str, Any]]:
    """Scan a single events.jsonl / events.json file; return findings."""
    events = parse_events_log(path)
    findings = scan_event_payloads(events)
    for finding in findings:
        finding["source_path"] = path.name
    return findings


def is_debug_capture_path(rel: str) -> bool:
    parts = rel.split("/")
    return any(seg in parts for seg in DEBUG_CAPTURE_PATH_SEGMENTS)


def iter_event_logs(root: Path) -> Iterable[Path]:
    for sub in ("run-artifacts", "docs/evaluations"):
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.name in EVENT_LOG_NAMES:
                rel = relpath(root, path)
                if rel in SELF_EXEMPT_FILES:
                    continue
                if is_debug_capture_path(rel):
                    continue
                yield path


def scan_tree(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    for path in iter_event_logs(root):
        for finding in scan_events_log(path):
            finding["path"] = relpath(root, path)
            findings.append(finding)
    return findings


def _write_events_log(case_dir: Path, events: list[dict[str, Any]]) -> Path:
    log_path = case_dir / "events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n"
    log_path.write_text(body, encoding="utf-8")
    return log_path


def _run_case(
    work: Path,
    case_id: str,
    events: list[dict[str, Any]],
    expected_finding_ids: tuple[str, ...],
    detail: str,
) -> dict[str, Any]:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    log_path = _write_events_log(case_dir, events)
    findings = scan_events_log(log_path)
    expected = set(expected_finding_ids)
    actual = {f["finding_id"] for f in findings}
    matches_expectation = actual == expected
    observed = "PASS" if not findings else "FAIL"
    transcript = case_dir / "ao-event-redaction-transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "event_count": len(events),
                "findings": findings,
                "expected_finding_ids": sorted(expected),
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
        "expected_finding_ids": sorted(expected),
        "matches_expectation": matches_expectation,
        "transcript": transcript.name,
    }


def _event(event_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event_id,
        "timestamp": "2026-05-16T00:00:00Z",
        "runId": "synthetic-run-001",
        "kind": kind,
        "payload": payload,
    }


def run_clean_events_log_passes(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "clean_events_log_passes",
        [
            _event(
                "ev-1",
                "run.started",
                {"name": "redaction-control", "tasks": 1},
            ),
            _event(
                "ev-2",
                "task.completed",
                {
                    "exit_code": 0,
                    "stdout": "hello",
                    "stderr": "",
                    "status": "succeeded",
                },
            ),
            _event(
                "ev-3",
                "run.completed",
                {"status": "completed", "tasks_run": 1},
            ),
        ],
        expected_finding_ids=(),
        detail=(
            "control: a synthetic events.jsonl with only benign payloads "
            "passes the scan with zero findings"
        ),
    )


def run_personal_path_in_stdout_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "personal_path_in_stdout_rejected",
        [
            _event(
                "ev-leak-path",
                "task.completed",
                {
                    "exit_code": 0,
                    "stdout": "wrote bundle to /home/operator-alpha/staging/out.tar",
                    "stderr": "",
                    "status": "succeeded",
                },
            ),
        ],
        expected_finding_ids=("personal_path",),
        detail=(
            "mutation: a task.completed payload whose stdout contains a "
            "/home/<user> personal path is fail-closed"
        ),
    )


def run_anthropic_api_key_pattern_in_stderr_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "anthropic_api_key_pattern_in_stderr_rejected",
        [
            _event(
                "ev-leak-key",
                "task.completed",
                {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "error: ANTHROPIC_API_KEY=sk-ant-placeholder-redaction-target rejected",
                    "status": "failed",
                },
            ),
        ],
        expected_finding_ids=("anthropic_api_key", "anthropic_sk_prefix_token"),
        detail=(
            "mutation: a payload whose stderr contains an "
            "ANTHROPIC_API_KEY=sk-... marker is fail-closed"
        ),
    )


def run_bearer_token_in_artifact_payload_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "bearer_token_in_artifact_payload_rejected",
        [
            _event(
                "ev-leak-bearer",
                "task.artifact",
                {
                    "kind": "log",
                    "mime": "text/plain",
                    "name": "request-headers.txt",
                    "preview": "Authorization: Bearer abcdef0123456789placeholder",
                },
            ),
        ],
        expected_finding_ids=("bearer_token",),
        detail=(
            "mutation: a task.artifact payload containing a 'Bearer <token>' "
            "string is fail-closed"
        ),
    )


def run_private_ipv4_in_task_metadata_rejected(work: Path) -> dict[str, Any]:
    return _run_case(
        work,
        "private_ipv4_in_task_metadata_rejected",
        [
            _event(
                "ev-leak-ip",
                "task.started",
                {
                    "host": "10.0.42.17",
                    "kind": "Shell",
                },
            ),
        ],
        expected_finding_ids=("private_network_target",),
        detail=(
            "mutation: a payload field containing a 10/8 RFC1918 IPv4 "
            "address is fail-closed"
        ),
    )


def run_base64_round_trip_secret_in_payload_rejected(work: Path) -> dict[str, Any]:
    # Encode an obvious HIGH-pattern marker as base64. The plain string is
    # absent from the payload — only the base64 form is.
    plaintext_secret = "ANTHROPIC_API_KEY=sk-ant-placeholder-redaction-target"
    encoded = base64.b64encode(plaintext_secret.encode("utf-8")).decode("ascii")
    return _run_case(
        work,
        "base64_round_trip_secret_in_payload_rejected",
        [
            _event(
                "ev-leak-b64",
                "task.completed",
                {
                    "exit_code": 0,
                    "stdout": encoded,
                    "stderr": "",
                    "status": "succeeded",
                },
            ),
        ],
        expected_finding_ids=(
            "base64::anthropic_api_key",
            "base64::anthropic_sk_prefix_token",
        ),
        detail=(
            "mutation: a payload field whose base64-decoded form matches a "
            "HIGH pattern is fail-closed; a naive string-only scanner would "
            "miss it"
        ),
    )


CASE_RUNNERS = {
    "clean_events_log_passes": run_clean_events_log_passes,
    "personal_path_in_stdout_rejected": run_personal_path_in_stdout_rejected,
    "anthropic_api_key_pattern_in_stderr_rejected": run_anthropic_api_key_pattern_in_stderr_rejected,
    "bearer_token_in_artifact_payload_rejected": run_bearer_token_in_artifact_payload_rejected,
    "private_ipv4_in_task_metadata_rejected": run_private_ipv4_in_task_metadata_rejected,
    "base64_round_trip_secret_in_payload_rejected": run_base64_round_trip_secret_in_payload_rejected,
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
        # Expected finding-id set must be a subset of actual; we tolerate the
        # scanner finding *more* than expected (e.g. a key value also matches
        # the sk-ant prefix), but never *fewer*.
        actual_ids = {f["finding_id"] for f in case.get("findings", [])}
        missing = set(case.get("expected_finding_ids", [])) - actual_ids
        if missing:
            errors.append(
                f"{case_id} expected finding ids missing: {sorted(missing)}"
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
        "high_pattern_ids": [name for name, _ in HIGH_PATTERNS],
        "medium_pattern_ids": [name for name, _ in MEDIUM_PATTERNS],
        "event_log_names": sorted(EVENT_LOG_NAMES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "AO event-log redaction pre-release gate is locked fail-closed; "
            "proceed with public-release artifact redaction verification."
            if overall_pass
            else "Fix AO event-log redaction blockers before approving a "
            "public release."
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
        "high_pattern_ids": [name for name, _ in HIGH_PATTERNS],
        "medium_pattern_ids": [name for name, _ in MEDIUM_PATTERNS],
        "event_log_names": sorted(EVENT_LOG_NAMES),
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
        prefix="ao-operator-ao-event-redaction-"
    ) as tmp:
        return evaluate(work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate AO event-log redaction before public release"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument(
        "--scan-repo",
        action="store_true",
        help="Run a production scan of --root for unredacted AO events.jsonl payloads",
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
                prefix="ao-operator-ao-event-redaction-"
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
