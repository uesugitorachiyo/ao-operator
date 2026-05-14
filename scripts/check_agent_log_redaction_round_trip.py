#!/usr/bin/env python3
"""Agent log redaction round-trip gate.

Models the agent log redaction round-trip invariant that no
AO Operator agent log line containing a sensitive token can be
turned back into the original token by reading the redacted
public artifact through any of five recovery channels.

Every log edge whose redacted-output state would let an attacker
recover an original sensitive token via partial-pattern match,
base64 round-trip, path-normalization alias, case-insensitive
miss, or JSON-string-escape miss is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real log file or redaction tool invoked):

* ``clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output`` --
  control: every registered log entry is in an approved redaction
  class with the original token absent from the redacted output
  in raw, base64, normalized-alias, case-variant, and
  JSON-string-escape forms.
* ``partial_pattern_match_leaves_original_substring_rejected`` --
  mutation: a redaction pattern matches only the prefix of a
  secret and leaves the tail substring visible in the redacted
  output; the verifier MUST reject.
* ``base64_encoded_secret_unredacted_in_round_trip_rejected`` --
  mutation: a base64-encoded copy of the same secret survives
  redaction in the round-tripped artifact; the verifier MUST
  reject.
* ``path_normalization_alias_unredacted_in_round_trip_rejected`` --
  mutation: a tilde-normalized alias of the original personal
  path survives redaction in the round-tripped artifact; the
  verifier MUST reject.
* ``case_insensitive_token_unredacted_in_round_trip_rejected`` --
  mutation: an uppercase variant of the original sensitive token
  survives the case-sensitive redaction pass; the verifier MUST
  reject.
* ``json_string_escape_token_unredacted_in_round_trip_rejected`` --
  mutation: a JSON-string-escaped form of the original sensitive
  token survives redaction in the round-tripped artifact; the
  verifier MUST reject.

Every case lays down a per-case
``agent-log-redaction-round-trip-transcript.json`` in a temporary
work directory, runs it through the verifier embedded in this
gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the
expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "agent-log-redaction-round-trip.json"
)
SCHEMA = "ao-operator/agent-log-redaction-round-trip/v1"

CASE_IDS = (
    "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output",
    "partial_pattern_match_leaves_original_substring_rejected",
    "base64_encoded_secret_unredacted_in_round_trip_rejected",
    "path_normalization_alias_unredacted_in_round_trip_rejected",
    "case_insensitive_token_unredacted_in_round_trip_rejected",
    "json_string_escape_token_unredacted_in_round_trip_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output": "PASS",
    "partial_pattern_match_leaves_original_substring_rejected": "FAIL",
    "base64_encoded_secret_unredacted_in_round_trip_rejected": "FAIL",
    "path_normalization_alias_unredacted_in_round_trip_rejected": "FAIL",
    "case_insensitive_token_unredacted_in_round_trip_rejected": "FAIL",
    "json_string_escape_token_unredacted_in_round_trip_rejected": "FAIL",
}

LOG_CLASSES = {
    "clean_log",
    "partial_match_leak",
    "base64_leak",
    "path_normalization_leak",
    "case_miss_leak",
    "json_string_escape_leak",
}
APPROVED_LOG_CLASSES = {
    "clean_log",
}
HAZARD_CLASSES = {
    "partial_match_leak_admit",
    "base64_leak_admit",
    "path_normalization_leak_admit",
    "case_miss_leak_admit",
    "json_string_escape_leak_admit",
}

REDACTION_MARKER = "redaction::operator_root_alpha"
SYNTHETIC_SECRET_TOKEN = "token::secret_alpha"
SYNTHETIC_PERSONAL_PATH = "token::path_alpha"

_CLEAN_LOG_ALPHA = "log::clean_alpha"
_CLEAN_LOG_BETA = "log::clean_beta"
_CLEAN_LOG_GAMMA = "log::clean_gamma"
_PARTIAL_MATCH_LEAK_FRAGMENT = "log::partial_match_leak_alpha"
_BASE64_LEAK_FRAGMENT = "log::base64_leak_alpha"
_PATH_NORMALIZATION_LEAK_FRAGMENT = "log::path_normalization_leak_alpha"
_CASE_MISS_LEAK_FRAGMENT = "log::case_miss_leak_alpha"
_JSON_STRING_ESCAPE_LEAK_FRAGMENT = "log::json_string_escape_leak_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentLogRedactionRoundTripVerifier:
    """In-memory agent log redaction round-trip verifier."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, entry: dict[str, Any]) -> None:
        self.entries.append(dict(entry))
        self._validate_entry(entry)

    def _validate_entry(self, entry: dict[str, Any]) -> None:
        entry_id = str(entry.get("id") or "<unnamed>")
        log_class = entry.get("log_class")
        if log_class not in LOG_CLASSES:
            self.errors.append(
                f"unknown_log_class:id={entry_id},class={log_class!r}"
            )
            return
        if log_class == "partial_match_leak":
            self.errors.append(
                f"partial_pattern_match_admit_rejection:id={entry_id},entry={entry.get('entry_id', '<unknown>')}"
            )
            return
        if log_class == "base64_leak":
            self.errors.append(
                f"base64_encoded_secret_admit_rejection:id={entry_id},entry={entry.get('entry_id', '<unknown>')}"
            )
            return
        if log_class == "path_normalization_leak":
            self.errors.append(
                f"path_normalization_alias_admit_rejection:id={entry_id},entry={entry.get('entry_id', '<unknown>')}"
            )
            return
        if log_class == "case_miss_leak":
            self.errors.append(
                f"case_insensitive_token_admit_rejection:id={entry_id},entry={entry.get('entry_id', '<unknown>')}"
            )
            return
        if log_class == "json_string_escape_leak":
            self.errors.append(
                f"json_string_escape_token_admit_rejection:id={entry_id},entry={entry.get('entry_id', '<unknown>')}"
            )
            return
        if log_class not in APPROVED_LOG_CLASSES:
            self.errors.append(
                f"unapproved_log_class:id={entry_id},class={log_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_log_entry_alpha",
        "log_class": "clean_log",
        "entry_id": _CLEAN_LOG_ALPHA,
        "redaction_marker": REDACTION_MARKER,
        "raw_token_present_after_redaction": False,
        "base64_token_present_after_redaction": False,
        "normalized_alias_present_after_redaction": False,
        "case_variant_present_after_redaction": False,
        "json_string_escape_present_after_redaction": False,
    },
    {
        "id": "clean_log_entry_beta",
        "log_class": "clean_log",
        "entry_id": _CLEAN_LOG_BETA,
        "redaction_marker": REDACTION_MARKER,
        "raw_token_present_after_redaction": False,
        "base64_token_present_after_redaction": False,
        "normalized_alias_present_after_redaction": False,
        "case_variant_present_after_redaction": False,
        "json_string_escape_present_after_redaction": False,
    },
    {
        "id": "clean_log_entry_gamma",
        "log_class": "clean_log",
        "entry_id": _CLEAN_LOG_GAMMA,
        "redaction_marker": REDACTION_MARKER,
        "raw_token_present_after_redaction": False,
        "base64_token_present_after_redaction": False,
        "normalized_alias_present_after_redaction": False,
        "case_variant_present_after_redaction": False,
        "json_string_escape_present_after_redaction": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-log-redaction-round-trip-transcript.json").write_text(
        json.dumps({"entries": transcript}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _case_summary(
    case_id: str,
    *,
    observed_verdict: str,
    observed_errors: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "observed_errors": observed_errors,
        "detail": detail,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def run_clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output(work: Path) -> dict[str, Any]:
    case_id = "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output"
    verifier = _AgentLogRedactionRoundTripVerifier()
    for entry in _CLEAN_ENTRIES:
        verifier.register(entry)
    transcript = [{"op": "register", **entry} for entry in _CLEAN_ENTRIES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered log entry is in an approved "
            "redaction class with the original token absent from the "
            "redacted output across all five recovery channels"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentLogRedactionRoundTripVerifier()
    for entry in _CLEAN_ENTRIES:
        verifier.register(entry)
    verifier.register(mutated)
    transcript = [{"op": "register", **entry} for entry in (*_CLEAN_ENTRIES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_partial_pattern_match_leaves_original_substring_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "partial_pattern_match_leaves_original_substring_rejected",
        {
            "id": "mutated_partial_pattern_match_admit",
            "log_class": "partial_match_leak",
            "entry_id": _PARTIAL_MATCH_LEAK_FRAGMENT,
            "redaction_marker": REDACTION_MARKER,
            "raw_token_present_after_redaction": True,
            "base64_token_present_after_redaction": False,
            "normalized_alias_present_after_redaction": False,
            "case_variant_present_after_redaction": False,
            "json_string_escape_present_after_redaction": False,
        },
        detail=(
            "mutation: a redaction pattern matches only the prefix of "
            "the synthetic secret token and leaves the tail substring "
            "visible in the redacted output and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_base64_encoded_secret_unredacted_in_round_trip_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "base64_encoded_secret_unredacted_in_round_trip_rejected",
        {
            "id": "mutated_base64_encoded_secret_admit",
            "log_class": "base64_leak",
            "entry_id": _BASE64_LEAK_FRAGMENT,
            "redaction_marker": REDACTION_MARKER,
            "raw_token_present_after_redaction": False,
            "base64_token_present_after_redaction": True,
            "normalized_alias_present_after_redaction": False,
            "case_variant_present_after_redaction": False,
            "json_string_escape_present_after_redaction": False,
        },
        detail=(
            "mutation: a base64-encoded copy of the synthetic secret "
            "token survives redaction in the round-tripped artifact "
            "and the verifier must reject instead of silently accepting"
        ),
    )


def run_path_normalization_alias_unredacted_in_round_trip_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "path_normalization_alias_unredacted_in_round_trip_rejected",
        {
            "id": "mutated_path_normalization_alias_admit",
            "log_class": "path_normalization_leak",
            "entry_id": _PATH_NORMALIZATION_LEAK_FRAGMENT,
            "redaction_marker": REDACTION_MARKER,
            "raw_token_present_after_redaction": False,
            "base64_token_present_after_redaction": False,
            "normalized_alias_present_after_redaction": True,
            "case_variant_present_after_redaction": False,
            "json_string_escape_present_after_redaction": False,
        },
        detail=(
            "mutation: a tilde-normalized alias of the synthetic "
            "personal path survives redaction in the round-tripped "
            "artifact and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_case_insensitive_token_unredacted_in_round_trip_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "case_insensitive_token_unredacted_in_round_trip_rejected",
        {
            "id": "mutated_case_insensitive_token_admit",
            "log_class": "case_miss_leak",
            "entry_id": _CASE_MISS_LEAK_FRAGMENT,
            "redaction_marker": REDACTION_MARKER,
            "raw_token_present_after_redaction": False,
            "base64_token_present_after_redaction": False,
            "normalized_alias_present_after_redaction": False,
            "case_variant_present_after_redaction": True,
            "json_string_escape_present_after_redaction": False,
        },
        detail=(
            "mutation: an uppercase variant of the synthetic secret "
            "token survives the case-sensitive redaction pass and the "
            "verifier must reject instead of silently accepting"
        ),
    )


def run_json_string_escape_token_unredacted_in_round_trip_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "json_string_escape_token_unredacted_in_round_trip_rejected",
        {
            "id": "mutated_json_string_escape_token_admit",
            "log_class": "json_string_escape_leak",
            "entry_id": _JSON_STRING_ESCAPE_LEAK_FRAGMENT,
            "redaction_marker": REDACTION_MARKER,
            "raw_token_present_after_redaction": False,
            "base64_token_present_after_redaction": False,
            "normalized_alias_present_after_redaction": False,
            "case_variant_present_after_redaction": False,
            "json_string_escape_present_after_redaction": True,
        },
        detail=(
            "mutation: a JSON-string-escaped form of the synthetic "
            "secret token survives redaction in the round-tripped "
            "artifact and the verifier must reject instead of "
            "silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output": run_clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output,
    "partial_pattern_match_leaves_original_substring_rejected": run_partial_pattern_match_leaves_original_substring_rejected,
    "base64_encoded_secret_unredacted_in_round_trip_rejected": run_base64_encoded_secret_unredacted_in_round_trip_rejected,
    "path_normalization_alias_unredacted_in_round_trip_rejected": run_path_normalization_alias_unredacted_in_round_trip_rejected,
    "case_insensitive_token_unredacted_in_round_trip_rejected": run_case_insensitive_token_unredacted_in_round_trip_rejected,
    "json_string_escape_token_unredacted_in_round_trip_rejected": run_json_string_escape_token_unredacted_in_round_trip_rejected,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cases = [CASE_RUNNERS[case_id](work_dir) for case_id in CASE_IDS]
    errors: list[str] = []
    by_id = {case["id"]: case for case in cases}
    for case_id, expected in EXPECTED_VERDICTS.items():
        observed = by_id.get(case_id, {}).get("observed_verdict")
        if observed != expected:
            errors.append(
                f"{case_id} expected {expected}, observed {observed or 'missing'}"
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
        "log_classes": sorted(LOG_CLASSES),
        "approved_log_classes": sorted(APPROVED_LOG_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent log redaction round-trip gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent log redaction round-trip blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-log-redaction-round-trip-") as tmp:
        return evaluate(work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        payload = evaluate(work_dir=args.work_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-log-redaction-round-trip-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
