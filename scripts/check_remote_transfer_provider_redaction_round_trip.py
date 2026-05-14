#!/usr/bin/env python3
"""Remote-transfer provider redaction round-trip gate.

Synthesizes the AO Runtime ``provider_redaction_round_trip`` contract
as a local Python state machine and proves each redaction-layer
violation is fail-closed by injecting deliberate mutations against an
in-process redact/transmit/respond/verify pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_round_trip_passes`` — control: a request payload with two
  sensitive fields is redacted to opaque markers before transmit, the
  synthetic provider echoes only the redacted form, and the verifier
  confirms (a) every sensitive value was replaced before transmit and
  (b) the response contains no plaintext sensitive value.
* ``redaction_marker_stripped_before_transmit_rejected`` — mutation: a
  buggy serializer drops the redaction markers before transmit so the
  raw plaintext sensitive value crosses the wire. The pre-transmit
  invariant must reject.
* ``sensitive_field_leaks_past_redaction_filter_rejected`` — mutation:
  the redaction filter is given an incomplete sensitive-field list, so
  one sensitive field is transmitted in plaintext. The
  redaction-coverage invariant must reject.
* ``double_redaction_corrupts_payload_rejected`` — mutation: the
  redactor is run twice over the same payload, replacing already-opaque
  markers with a different marker. The deterministic-redaction
  invariant must reject.
* ``provider_response_leaks_redacted_value_back_rejected`` — mutation:
  the synthetic provider response contains the *plaintext* sensitive
  value that the request had redacted. The response-leak invariant
  must reject.

Every case lays down a per-case round-trip transcript in a temporary
work directory, runs it through the verifier embedded in this gate,
and records ``observed_verdict``. The gate's overall verdict is
``PASS`` only when every case lines up with the expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-provider-redaction-round-trip.json"
)
SCHEMA = "ao-operator/remote-transfer-provider-redaction-round-trip/v1"

REDACTION_MARKER_RE = re.compile(r"^\[REDACTED:[A-Za-z0-9_]+\]$")

CASE_IDS = (
    "clean_round_trip_passes",
    "redaction_marker_stripped_before_transmit_rejected",
    "sensitive_field_leaks_past_redaction_filter_rejected",
    "double_redaction_corrupts_payload_rejected",
    "provider_response_leaks_redacted_value_back_rejected",
)

EXPECTED_VERDICTS = {
    "clean_round_trip_passes": "PASS",
    "redaction_marker_stripped_before_transmit_rejected": "FAIL",
    "sensitive_field_leaks_past_redaction_filter_rejected": "FAIL",
    "double_redaction_corrupts_payload_rejected": "FAIL",
    "provider_response_leaks_redacted_value_back_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _RedactionVerifier:
    """In-memory provider-redaction round-trip state machine.

    Models the AO Runtime ``provider_redaction_round_trip`` pipeline:
    a request payload is redacted, transmitted to a synthetic
    provider, the provider returns a response, and the verifier
    enforces five distilled redaction invariants:

    1. Every value of a registered sensitive field MUST be replaced
       with a redaction marker before transmit (pre-transmit
       invariant).
    2. The redaction marker MUST match the canonical pattern
       ``[REDACTED:<token>]`` (marker-shape invariant).
    3. The transmitted payload MUST NOT contain any plaintext
       sensitive value anywhere in the serialized JSON
       (redaction-coverage invariant).
    4. Re-running the redactor over an already-redacted payload MUST
       leave it unchanged (deterministic-redaction invariant).
    5. The provider response MUST NOT contain any plaintext sensitive
       value (response-leak invariant).
    """

    def __init__(
        self,
        *,
        sensitive_fields: list[str],
        sensitive_values: dict[str, str],
    ) -> None:
        self.sensitive_fields = list(sensitive_fields)
        self.sensitive_values = dict(sensitive_values)
        self.errors: list[str] = []

    def verify(
        self,
        *,
        request: dict[str, Any],
        transmitted: dict[str, Any],
        response: dict[str, Any],
        redacted_twice: dict[str, Any] | None = None,
    ) -> None:
        for field in self.sensitive_fields:
            if field not in transmitted:
                self.errors.append(
                    f"sensitive_field_missing_from_transmit:field={field}"
                )
                continue
            transmitted_value = transmitted[field]
            if not isinstance(transmitted_value, str):
                self.errors.append(
                    f"sensitive_field_not_string_at_transmit:field={field},type={type(transmitted_value).__name__}"
                )
                continue
            if not REDACTION_MARKER_RE.match(transmitted_value):
                self.errors.append(
                    f"redaction_marker_missing_or_malformed:field={field},value={transmitted_value!r}"
                )

        transmitted_blob = json.dumps(transmitted, sort_keys=True)
        for field, raw in self.sensitive_values.items():
            if raw and raw in transmitted_blob:
                self.errors.append(
                    f"plaintext_sensitive_value_in_transmit:field={field}"
                )

        if redacted_twice is not None and redacted_twice != transmitted:
            self.errors.append(
                "double_redaction_not_idempotent:second_pass_diverged_from_first"
            )

        response_blob = json.dumps(response, sort_keys=True)
        for field, raw in self.sensitive_values.items():
            if raw and raw in response_blob:
                self.errors.append(
                    f"plaintext_sensitive_value_in_response:field={field}"
                )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _redact(
    payload: dict[str, Any],
    *,
    fields: list[str],
    token: str = "value",
) -> dict[str, Any]:
    out = dict(payload)
    for field in fields:
        if field in out:
            out[field] = f"[REDACTED:{token}_{field}]"
    return out


def _persist_case(
    work: Path,
    case_id: str,
    *,
    request: dict[str, Any],
    transmitted: dict[str, Any],
    response: dict[str, Any],
) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "round-trip-transcript.json").write_text(
        json.dumps(
            {"request": request, "transmitted": transmitted, "response": response},
            indent=2,
            sort_keys=True,
        ),
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


def run_clean_round_trip_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_round_trip_passes"
    request = {
        "prompt": "Summarize quarterly revenue.",
        "api_key": "sk-secret-aaa",
        "user_email": "alice@example.com",
    }
    sensitive_fields = ["api_key", "user_email"]
    sensitive_values = {f: request[f] for f in sensitive_fields}
    transmitted = _redact(request, fields=sensitive_fields)
    response = {
        "answer": "Q1 revenue rose 12 percent.",
        "echo_api_key": transmitted["api_key"],
        "echo_user_email": transmitted["user_email"],
    }
    _persist_case(work, case_id, request=request, transmitted=transmitted, response=response)
    verifier = _RedactionVerifier(
        sensitive_fields=sensitive_fields,
        sensitive_values=sensitive_values,
    )
    redacted_twice = _redact(transmitted, fields=sensitive_fields)
    verifier.verify(
        request=request,
        transmitted=transmitted,
        response=response,
        redacted_twice=redacted_twice,
    )
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: api_key and user_email replaced with markers before transmit; "
            "provider response echoes only redacted markers; double-redaction is idempotent"
        ),
    )


def run_redaction_marker_stripped_before_transmit_rejected(work: Path) -> dict[str, Any]:
    case_id = "redaction_marker_stripped_before_transmit_rejected"
    request = {
        "prompt": "Send invoice to user.",
        "api_key": "sk-secret-bbb",
        "user_email": "bob@example.com",
    }
    sensitive_fields = ["api_key", "user_email"]
    sensitive_values = {f: request[f] for f in sensitive_fields}
    transmitted = dict(request)
    response = {"answer": "Done.", "echo_api_key": "[REDACTED:value_api_key]"}
    _persist_case(work, case_id, request=request, transmitted=transmitted, response=response)
    verifier = _RedactionVerifier(
        sensitive_fields=sensitive_fields,
        sensitive_values=sensitive_values,
    )
    verifier.verify(request=request, transmitted=transmitted, response=response)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: serializer drops the redaction step; raw api_key and user_email cross the wire",
    )


def run_sensitive_field_leaks_past_redaction_filter_rejected(work: Path) -> dict[str, Any]:
    case_id = "sensitive_field_leaks_past_redaction_filter_rejected"
    request = {
        "prompt": "Reset password.",
        "api_key": "sk-secret-ccc",
        "user_email": "carol@example.com",
    }
    sensitive_fields = ["api_key", "user_email"]
    sensitive_values = {f: request[f] for f in sensitive_fields}
    incomplete_filter = ["api_key"]
    transmitted = _redact(request, fields=incomplete_filter)
    response = {"answer": "Reset link emailed.", "echo_api_key": transmitted["api_key"]}
    _persist_case(work, case_id, request=request, transmitted=transmitted, response=response)
    verifier = _RedactionVerifier(
        sensitive_fields=sensitive_fields,
        sensitive_values=sensitive_values,
    )
    verifier.verify(request=request, transmitted=transmitted, response=response)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: redaction filter omits user_email so plaintext email crosses the wire",
    )


def run_double_redaction_corrupts_payload_rejected(work: Path) -> dict[str, Any]:
    case_id = "double_redaction_corrupts_payload_rejected"
    request = {
        "prompt": "Generate report.",
        "api_key": "sk-secret-ddd",
        "user_email": "dan@example.com",
    }
    sensitive_fields = ["api_key", "user_email"]
    sensitive_values = {f: request[f] for f in sensitive_fields}
    transmitted = _redact(request, fields=sensitive_fields, token="value")
    redacted_twice = _redact(transmitted, fields=sensitive_fields, token="rotated")
    response = {"answer": "Report ready.", "echo_api_key": transmitted["api_key"]}
    _persist_case(work, case_id, request=request, transmitted=transmitted, response=response)
    verifier = _RedactionVerifier(
        sensitive_fields=sensitive_fields,
        sensitive_values=sensitive_values,
    )
    verifier.verify(
        request=request,
        transmitted=transmitted,
        response=response,
        redacted_twice=redacted_twice,
    )
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: redactor is non-idempotent — second pass with a rotated token diverges from first pass",
    )


def run_provider_response_leaks_redacted_value_back_rejected(work: Path) -> dict[str, Any]:
    case_id = "provider_response_leaks_redacted_value_back_rejected"
    request = {
        "prompt": "Verify account.",
        "api_key": "sk-secret-eee",
        "user_email": "eve@example.com",
    }
    sensitive_fields = ["api_key", "user_email"]
    sensitive_values = {f: request[f] for f in sensitive_fields}
    transmitted = _redact(request, fields=sensitive_fields)
    response = {
        "answer": "Account verified.",
        "echo_api_key": "sk-secret-eee",
        "echo_user_email": transmitted["user_email"],
    }
    _persist_case(work, case_id, request=request, transmitted=transmitted, response=response)
    verifier = _RedactionVerifier(
        sensitive_fields=sensitive_fields,
        sensitive_values=sensitive_values,
    )
    verifier.verify(request=request, transmitted=transmitted, response=response)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: provider response contains plaintext api_key the request had redacted",
    )


CASE_RUNNERS = {
    "clean_round_trip_passes": run_clean_round_trip_passes,
    "redaction_marker_stripped_before_transmit_rejected": run_redaction_marker_stripped_before_transmit_rejected,
    "sensitive_field_leaks_past_redaction_filter_rejected": run_sensitive_field_leaks_past_redaction_filter_rejected,
    "double_redaction_corrupts_payload_rejected": run_double_redaction_corrupts_payload_rejected,
    "provider_response_leaks_redacted_value_back_rejected": run_provider_response_leaks_redacted_value_back_rejected,
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
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Remote-transfer provider redaction round-trip is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix provider redaction round-trip blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-provider-redaction-round-trip-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-provider-redaction-round-trip-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
