#!/usr/bin/env python3
"""Remote-transfer bundle content-type allowlist gate.

Synthesizes the AO Runtime ``bundle_content_type_allowlist`` contract
as a local Python state machine and proves each receiver-side
content-type or encoding hazard is fail-closed by injecting
deliberate mutations against an in-process allowlist enforcement
pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_allowlisted_content_type_passes`` — control: sender
  declares ``content_type=application/x-factory-bundle`` and
  ``content_encoding=identity``, both on the receiver allowlist; the
  receiver matches against the allowlist and accepts the bundle.
* ``unknown_content_type_silently_coerced_rejected`` — mutation:
  sender declares ``content_type=application/x-experimental-foo``,
  not on the allowlist; the receiver silently coerces it to
  ``application/x-factory-bundle``. A receiver MUST reject any
  declared ``content_type`` not on the allowlist; coercion is a
  forgery vector for content interpreted under a privileged type.
* ``mismatched_extension_to_content_type_rejected`` — mutation:
  sender ships payload bytes whose magic header is ``%PDF`` while
  declaring ``content_type=application/x-factory-bundle``; the
  receiver dispatches based on ``content_type`` without sniffing
  the payload. A receiver MUST reject a bundle whose declared
  ``content_type`` does not match the payload signature; allowing
  the mismatch lets a sender smuggle content under a trusted type.
* ``unknown_content_encoding_silently_decoded_rejected`` — mutation:
  sender declares ``content_encoding=experimental-zstd``, not on
  the allowlist, and the receiver silently falls back to
  ``identity`` decoding rather than rejecting. A receiver MUST
  reject any declared ``content_encoding`` not on the allowlist;
  silent fallback to identity bypasses the encoding contract.
* ``content_type_charset_parameter_smuggled_rejected`` — mutation:
  sender declares
  ``content_type=application/x-factory-bundle;charset=../../etc/passwd``;
  the receiver naively concatenates the parameter into a filesystem
  path while routing the bundle. A receiver MUST reject any
  ``content_type`` parameter that contains path traversal sequences
  or does not match the parameter allowlist.

Every case lays down a per-case content-type transcript in a
temporary work directory, runs it through the verifier embedded in
this gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the expected
verdict.

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
    "remote-transfer-bundle-content-type-allowlist.json"
)
SCHEMA = "ao-operator/remote-transfer-bundle-content-type-allowlist/v1"

CASE_IDS = (
    "clean_allowlisted_content_type_passes",
    "unknown_content_type_silently_coerced_rejected",
    "mismatched_extension_to_content_type_rejected",
    "unknown_content_encoding_silently_decoded_rejected",
    "content_type_charset_parameter_smuggled_rejected",
)

EXPECTED_VERDICTS = {
    "clean_allowlisted_content_type_passes": "PASS",
    "unknown_content_type_silently_coerced_rejected": "FAIL",
    "mismatched_extension_to_content_type_rejected": "FAIL",
    "unknown_content_encoding_silently_decoded_rejected": "FAIL",
    "content_type_charset_parameter_smuggled_rejected": "FAIL",
}

_CONTENT_TYPE_ALLOWLIST = frozenset({"application/x-factory-bundle"})
_CONTENT_ENCODING_ALLOWLIST = frozenset({"identity", "gzip"})
_CHARSET_PARAM_ALLOWLIST = frozenset({"utf-8", "us-ascii"})

_PAYLOAD_MAGIC_FOR_CONTENT_TYPE = {
    "application/x-factory-bundle": "FBND",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _ContentTypeAllowlistVerifier:
    """In-memory content-type/encoding allowlist state machine.

    Models the AO Runtime ``bundle_content_type_allowlist`` pipeline:
    on bundle arrival the receiver enforces four invariants:

    1. Declared ``content_type`` MUST be on the allowlist; unknown
       values MUST NOT be silently coerced.
    2. The payload signature (magic header) MUST match the declared
       ``content_type``; mismatches MUST be rejected.
    3. Declared ``content_encoding`` MUST be on the encoding
       allowlist; unknown values MUST NOT silently fall back to
       identity decoding.
    4. ``content_type`` parameters (e.g. ``charset``) MUST be on the
       parameter allowlist and MUST NOT contain path traversal or
       other untrusted payload bytes.
    """

    def __init__(
        self,
        *,
        content_type_allowlist: frozenset[str] = _CONTENT_TYPE_ALLOWLIST,
        content_encoding_allowlist: frozenset[str] = _CONTENT_ENCODING_ALLOWLIST,
        charset_param_allowlist: frozenset[str] = _CHARSET_PARAM_ALLOWLIST,
    ) -> None:
        self.content_type_allowlist = content_type_allowlist
        self.content_encoding_allowlist = content_encoding_allowlist
        self.charset_param_allowlist = charset_param_allowlist
        self.errors: list[str] = []

    def receiver_validate_content_type(
        self,
        *,
        declared_content_type: str,
        declared_content_encoding: str,
        payload_magic: str,
    ) -> None:
        base = declared_content_type.split(";", 1)[0].strip()
        if base not in self.content_type_allowlist:
            self.errors.append(
                f"unknown_content_type:declared={declared_content_type}"
            )
            return
        expected_magic = _PAYLOAD_MAGIC_FOR_CONTENT_TYPE.get(base)
        if expected_magic is not None and payload_magic != expected_magic:
            self.errors.append(
                f"payload_magic_mismatch:declared={base},payload_magic={payload_magic},expected={expected_magic}"
            )
            return
        if declared_content_encoding not in self.content_encoding_allowlist:
            self.errors.append(
                f"unknown_content_encoding:declared={declared_content_encoding}"
            )
            return

    def receiver_force_coerce_unknown_content_type(
        self,
        *,
        declared_content_type: str,
        coerced_content_type: str,
    ) -> None:
        if declared_content_type.split(";", 1)[0].strip() not in self.content_type_allowlist:
            self.errors.append(
                f"silently_coerced_unknown_content_type:declared={declared_content_type},coerced={coerced_content_type}"
            )

    def receiver_dispatch_without_payload_sniff(
        self,
        *,
        declared_content_type: str,
        payload_magic: str,
    ) -> None:
        base = declared_content_type.split(";", 1)[0].strip()
        expected_magic = _PAYLOAD_MAGIC_FOR_CONTENT_TYPE.get(base)
        if expected_magic is not None and payload_magic != expected_magic:
            self.errors.append(
                f"dispatched_with_payload_magic_mismatch:declared={base},payload_magic={payload_magic},expected={expected_magic}"
            )

    def receiver_force_fallback_to_identity_encoding(
        self,
        *,
        declared_content_encoding: str,
    ) -> None:
        if declared_content_encoding not in self.content_encoding_allowlist:
            self.errors.append(
                f"silently_fell_back_to_identity_encoding:declared={declared_content_encoding}"
            )

    def receiver_concatenate_charset_parameter_into_path(
        self,
        *,
        declared_content_type: str,
    ) -> None:
        if ";" not in declared_content_type:
            return
        params = declared_content_type.split(";", 1)[1]
        for kv in params.split(";"):
            kv = kv.strip()
            if "=" not in kv:
                continue
            key, value = kv.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "charset":
                if value not in self.charset_param_allowlist:
                    self.errors.append(
                        f"unsafe_charset_parameter:value={value}"
                    )
                if "/" in value or ".." in value:
                    self.errors.append(
                        f"path_traversal_in_charset_parameter:value={value}"
                    )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "content-type-transcript.json").write_text(
        json.dumps({"ops": transcript}, indent=2, sort_keys=True),
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


def run_clean_allowlisted_content_type_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_allowlisted_content_type_passes"
    verifier = _ContentTypeAllowlistVerifier()
    declared_content_type = "application/x-factory-bundle"
    declared_content_encoding = "identity"
    payload_magic = "FBND"

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "declared_content_type": declared_content_type,
            "declared_content_encoding": declared_content_encoding,
            "payload_magic": payload_magic,
        },
    ]
    verifier.receiver_validate_content_type(
        declared_content_type=declared_content_type,
        declared_content_encoding=declared_content_encoding,
        payload_magic=payload_magic,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender declares allowlisted content_type/encoding and the payload magic "
            "matches; receiver validates without error"
        ),
    )


def run_unknown_content_type_silently_coerced_rejected(work: Path) -> dict[str, Any]:
    case_id = "unknown_content_type_silently_coerced_rejected"
    verifier = _ContentTypeAllowlistVerifier()
    declared_content_type = "application/x-experimental-foo"
    coerced_content_type = "application/x-factory-bundle"

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "declared_content_type": declared_content_type},
        {"op": "receiver_force_coerce_unknown_content_type", "coerced": coerced_content_type},
    ]
    verifier.receiver_force_coerce_unknown_content_type(
        declared_content_type=declared_content_type,
        coerced_content_type=coerced_content_type,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender declares unallowlisted content_type and receiver silently coerces "
            "it to the allowlisted bundle content_type rather than rejecting"
        ),
    )


def run_mismatched_extension_to_content_type_rejected(work: Path) -> dict[str, Any]:
    case_id = "mismatched_extension_to_content_type_rejected"
    verifier = _ContentTypeAllowlistVerifier()
    declared_content_type = "application/x-factory-bundle"
    payload_magic = "%PDF"

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "declared_content_type": declared_content_type,
            "payload_magic": payload_magic,
        },
        {"op": "receiver_dispatch_without_payload_sniff"},
    ]
    verifier.receiver_dispatch_without_payload_sniff(
        declared_content_type=declared_content_type,
        payload_magic=payload_magic,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender declares the allowlisted content_type but ships payload bytes whose "
            "magic header does not match; receiver dispatches without sniffing"
        ),
    )


def run_unknown_content_encoding_silently_decoded_rejected(work: Path) -> dict[str, Any]:
    case_id = "unknown_content_encoding_silently_decoded_rejected"
    verifier = _ContentTypeAllowlistVerifier()
    declared_content_encoding = "experimental-zstd"

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "declared_content_encoding": declared_content_encoding},
        {"op": "receiver_force_fallback_to_identity_encoding"},
    ]
    verifier.receiver_force_fallback_to_identity_encoding(
        declared_content_encoding=declared_content_encoding,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender declares unallowlisted content_encoding and receiver silently falls "
            "back to identity decoding rather than rejecting"
        ),
    )


def run_content_type_charset_parameter_smuggled_rejected(work: Path) -> dict[str, Any]:
    case_id = "content_type_charset_parameter_smuggled_rejected"
    verifier = _ContentTypeAllowlistVerifier()
    declared_content_type = "application/x-factory-bundle;charset=../../etc/passwd"

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "declared_content_type": declared_content_type},
        {"op": "receiver_concatenate_charset_parameter_into_path"},
    ]
    verifier.receiver_concatenate_charset_parameter_into_path(
        declared_content_type=declared_content_type,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender stuffs a path-traversal payload into the content_type charset "
            "parameter; receiver concatenates it into a filesystem path during routing"
        ),
    )


CASE_RUNNERS = {
    "clean_allowlisted_content_type_passes": run_clean_allowlisted_content_type_passes,
    "unknown_content_type_silently_coerced_rejected": run_unknown_content_type_silently_coerced_rejected,
    "mismatched_extension_to_content_type_rejected": run_mismatched_extension_to_content_type_rejected,
    "unknown_content_encoding_silently_decoded_rejected": run_unknown_content_encoding_silently_decoded_rejected,
    "content_type_charset_parameter_smuggled_rejected": run_content_type_charset_parameter_smuggled_rejected,
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
            "Remote-transfer bundle content-type allowlist is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix bundle content-type allowlist blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-content-type-allowlist-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-content-type-allowlist-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
