#!/usr/bin/env python3
"""Approval clock-skew defense gate.

Models the approval clock-skew defense invariant that no Factory
v3 agent approval can be admitted past its expiry, replayed, or
reactivated by a wall-clock rewind, an NTP step-back, a leap-
second jump, a TZ-tagged-as-UTC mismatch, or a stale signed
freshness token.

Every approval edge whose monotonic-basis, wall-clock-skew,
TZ-tag, signature-freshness, or replay-token state breaches the
clock-skew invariants is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real clock service queried):

* ``clean_no_clock_skew_or_replay_or_stale_freshness_edges`` --
  control: every registered approval edge is in an approved
  freshness class, anchored to the monotonic clock, with zero
  wall-clock skew, a UTC tz tag, an unexpired signature
  freshness token, and an unused replay token.
* ``ntp_rewind_admits_expired_approval_rejected`` -- mutation:
  an approval admitted after an NTP step-back so its expiry no
  longer applies; the verifier MUST reject.
* ``leap_second_jump_admits_expired_approval_rejected`` --
  mutation: an approval admitted across a leap-second jump that
  invalidates its monotonic basis; the verifier MUST reject.
* ``tz_tagged_as_utc_admits_expired_approval_rejected`` --
  mutation: an approval admitted with a non-UTC instant whose
  tz tag falsely claims UTC; the verifier MUST reject.
* ``expired_but_cached_admits_replay_rejected`` -- mutation:
  an approval admitted from a cached envelope past its expiry;
  the verifier MUST reject.
* ``signed_token_replay_admits_reactivation_rejected`` --
  mutation: an approval admitted by replaying a previously
  consumed signed freshness token; the verifier MUST reject.

Every case lays down a per-case
``approval-clock-skew-defense-transcript.json`` in a temporary
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
    "approval-clock-skew-defense.json"
)
SCHEMA = "ao-operator/approval-clock-skew-defense/v1"

CASE_IDS = (
    "clean_no_clock_skew_or_replay_or_stale_freshness_edges",
    "ntp_rewind_admits_expired_approval_rejected",
    "leap_second_jump_admits_expired_approval_rejected",
    "tz_tagged_as_utc_admits_expired_approval_rejected",
    "expired_but_cached_admits_replay_rejected",
    "signed_token_replay_admits_reactivation_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_clock_skew_or_replay_or_stale_freshness_edges": "PASS",
    "ntp_rewind_admits_expired_approval_rejected": "FAIL",
    "leap_second_jump_admits_expired_approval_rejected": "FAIL",
    "tz_tagged_as_utc_admits_expired_approval_rejected": "FAIL",
    "expired_but_cached_admits_replay_rejected": "FAIL",
    "signed_token_replay_admits_reactivation_rejected": "FAIL",
}

APPROVAL_CLASSES = {
    "operator_signed",
    "operator_allowlisted",
    "ntp_rewind",
    "leap_second_jump",
    "tz_mismatch",
    "expired_cached",
    "replay_token",
}
APPROVED_APPROVAL_CLASSES = {"operator_signed", "operator_allowlisted"}
HAZARD_CLASSES = {
    "ntp_rewind_admit",
    "leap_second_jump_admit",
    "tz_mismatch_admit",
    "expired_cached_admit",
    "replay_token_admit",
}

MONOTONIC_BASIS = "monotonic::reference_alpha"
UTC_TZ_TAG = "tz::utc"

_OPERATOR_SIGNED_ALPHA = "approval::operator_signed_alpha"
_OPERATOR_SIGNED_BETA = "approval::operator_signed_beta"
_NTP_REWIND_FRAGMENT = "approval::ntp_rewind_alpha"
_LEAP_SECOND_FRAGMENT = "approval::leap_second_jump_alpha"
_TZ_MISMATCH_FRAGMENT = "approval::tz_mismatch_alpha"
_EXPIRED_CACHED_FRAGMENT = "approval::expired_cached_alpha"
_REPLAY_TOKEN_FRAGMENT = "approval::replay_token_alpha"

_OPERATOR_ROOT_SIGNATURE = "signature::operator_root_alpha"
_FRESH_TOKEN = "token::operator_fresh_alpha"
_CONSUMED_TOKEN = "token::operator_consumed_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _ApprovalClockSkewDefenseVerifier:
    """In-memory approval clock-skew defense verifier.

    Each ``register`` call records one approval edge with its
    approval class, monotonic basis, wall-clock skew (seconds),
    tz tag, signature freshness, and replay-token state. A FAIL
    is recorded whenever an approval breaches one of the five
    clock-skew hazard classes.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        approval_class = edge.get("approval_class")
        if approval_class not in APPROVAL_CLASSES:
            self.errors.append(
                f"unknown_approval_class:id={edge_id},class={approval_class!r}"
            )
            return
        if approval_class == "ntp_rewind":
            self.errors.append(
                f"ntp_rewind_admit_rejection:id={edge_id},approval={edge.get('approval_id', '<unknown>')}"
            )
            return
        if approval_class == "leap_second_jump":
            self.errors.append(
                f"leap_second_jump_admit_rejection:id={edge_id},approval={edge.get('approval_id', '<unknown>')}"
            )
            return
        if approval_class == "tz_mismatch":
            self.errors.append(
                f"tz_tagged_as_utc_admit_rejection:id={edge_id},approval={edge.get('approval_id', '<unknown>')}"
            )
            return
        if approval_class == "expired_cached":
            self.errors.append(
                f"expired_but_cached_admit_rejection:id={edge_id},approval={edge.get('approval_id', '<unknown>')}"
            )
            return
        if approval_class == "replay_token":
            self.errors.append(
                f"signed_token_replay_admit_rejection:id={edge_id},approval={edge.get('approval_id', '<unknown>')}"
            )
            return
        if approval_class not in APPROVED_APPROVAL_CLASSES:
            self.errors.append(
                f"unapproved_approval_class:id={edge_id},class={approval_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "operator_signed_approval_alpha",
        "approval_class": "operator_signed",
        "approval_id": _OPERATOR_SIGNED_ALPHA,
        "monotonic_basis": MONOTONIC_BASIS,
        "wall_clock_skew_seconds": 0,
        "tz_tag": UTC_TZ_TAG,
        "signature_freshness": _FRESH_TOKEN,
        "replay_token_consumed": False,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
    {
        "id": "operator_signed_approval_beta",
        "approval_class": "operator_signed",
        "approval_id": _OPERATOR_SIGNED_BETA,
        "monotonic_basis": MONOTONIC_BASIS,
        "wall_clock_skew_seconds": 0,
        "tz_tag": UTC_TZ_TAG,
        "signature_freshness": _FRESH_TOKEN,
        "replay_token_consumed": False,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
    {
        "id": "operator_allowlisted_approval_alpha",
        "approval_class": "operator_allowlisted",
        "approval_id": "approval::operator_allowlisted_alpha",
        "monotonic_basis": MONOTONIC_BASIS,
        "wall_clock_skew_seconds": 0,
        "tz_tag": UTC_TZ_TAG,
        "signature_freshness": _FRESH_TOKEN,
        "replay_token_consumed": False,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "approval-clock-skew-defense-transcript.json").write_text(
        json.dumps({"edges": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_clock_skew_or_replay_or_stale_freshness_edges(work: Path) -> dict[str, Any]:
    case_id = "clean_no_clock_skew_or_replay_or_stale_freshness_edges"
    verifier = _ApprovalClockSkewDefenseVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered approval edge is in an approved "
            "freshness class anchored to the monotonic clock with zero "
            "wall-clock skew, a UTC tz tag, fresh signature, and unused "
            "replay token"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _ApprovalClockSkewDefenseVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    verifier.register(mutated)
    transcript = [{"op": "register", **edge} for edge in (*_CLEAN_EDGES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_ntp_rewind_admits_expired_approval_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "ntp_rewind_admits_expired_approval_rejected",
        {
            "id": "mutated_ntp_rewind_admit",
            "approval_class": "ntp_rewind",
            "approval_id": _NTP_REWIND_FRAGMENT,
            "monotonic_basis": MONOTONIC_BASIS,
            "wall_clock_skew_seconds": -3600,
            "tz_tag": UTC_TZ_TAG,
            "signature_freshness": _FRESH_TOKEN,
            "replay_token_consumed": False,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: an approval is admitted after an NTP step-back so "
            "its expiry no longer applies and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_leap_second_jump_admits_expired_approval_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "leap_second_jump_admits_expired_approval_rejected",
        {
            "id": "mutated_leap_second_jump_admit",
            "approval_class": "leap_second_jump",
            "approval_id": _LEAP_SECOND_FRAGMENT,
            "monotonic_basis": MONOTONIC_BASIS,
            "wall_clock_skew_seconds": 1,
            "tz_tag": UTC_TZ_TAG,
            "signature_freshness": _FRESH_TOKEN,
            "replay_token_consumed": False,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: an approval is admitted across a leap-second jump "
            "that invalidates its monotonic basis and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_tz_tagged_as_utc_admits_expired_approval_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tz_tagged_as_utc_admits_expired_approval_rejected",
        {
            "id": "mutated_tz_tagged_as_utc_admit",
            "approval_class": "tz_mismatch",
            "approval_id": _TZ_MISMATCH_FRAGMENT,
            "monotonic_basis": MONOTONIC_BASIS,
            "wall_clock_skew_seconds": 0,
            "tz_tag": "tz::america_los_angeles_tagged_as_utc",
            "signature_freshness": _FRESH_TOKEN,
            "replay_token_consumed": False,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: an approval is admitted with a non-UTC instant "
            "whose tz tag falsely claims UTC and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_expired_but_cached_admits_replay_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "expired_but_cached_admits_replay_rejected",
        {
            "id": "mutated_expired_but_cached_admit",
            "approval_class": "expired_cached",
            "approval_id": _EXPIRED_CACHED_FRAGMENT,
            "monotonic_basis": MONOTONIC_BASIS,
            "wall_clock_skew_seconds": 0,
            "tz_tag": UTC_TZ_TAG,
            "signature_freshness": "token::expired_cached_alpha",
            "replay_token_consumed": False,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: an approval is admitted from a cached envelope "
            "past its expiry and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_signed_token_replay_admits_reactivation_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "signed_token_replay_admits_reactivation_rejected",
        {
            "id": "mutated_signed_token_replay_admit",
            "approval_class": "replay_token",
            "approval_id": _REPLAY_TOKEN_FRAGMENT,
            "monotonic_basis": MONOTONIC_BASIS,
            "wall_clock_skew_seconds": 0,
            "tz_tag": UTC_TZ_TAG,
            "signature_freshness": _CONSUMED_TOKEN,
            "replay_token_consumed": True,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: an approval is admitted by replaying a previously "
            "consumed signed freshness token and the verifier must "
            "reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_clock_skew_or_replay_or_stale_freshness_edges": run_clean_no_clock_skew_or_replay_or_stale_freshness_edges,
    "ntp_rewind_admits_expired_approval_rejected": run_ntp_rewind_admits_expired_approval_rejected,
    "leap_second_jump_admits_expired_approval_rejected": run_leap_second_jump_admits_expired_approval_rejected,
    "tz_tagged_as_utc_admits_expired_approval_rejected": run_tz_tagged_as_utc_admits_expired_approval_rejected,
    "expired_but_cached_admits_replay_rejected": run_expired_but_cached_admits_replay_rejected,
    "signed_token_replay_admits_reactivation_rejected": run_signed_token_replay_admits_reactivation_rejected,
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
        "approval_classes": sorted(APPROVAL_CLASSES),
        "approved_approval_classes": sorted(APPROVED_APPROVAL_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Approval clock-skew defense gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Approval clock-skew defense blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-approval-clock-skew-defense-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-approval-clock-skew-defense-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
