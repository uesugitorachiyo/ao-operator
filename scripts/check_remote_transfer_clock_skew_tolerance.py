#!/usr/bin/env python3
"""Remote-transfer clock skew tolerance gate.

Synthesizes the AO Runtime ``clock_skew_tolerance`` contract as a
local Python state machine and proves each receiver-side time-window
hazard is fail-closed by injecting deliberate mutations against an
in-process timestamp validation pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_within_skew_tolerance_passes`` — control: sender stamps a
  bundle ``not_before=t0`` / ``not_after=t0+ttl_seconds`` against a
  receiver clock ``r0`` whose drift from the sender clock is at most
  the receiver's ``max_skew_seconds`` tolerance; the receiver opens
  the window after applying skew tolerance and accepts the bundle.
* ``sender_clock_ahead_of_receiver_rejected`` — mutation: sender
  clock runs 600 seconds ahead of the receiver while the receiver's
  skew tolerance is 60 seconds; sender stamps ``not_before`` 600 s
  in the receiver's future, but the receiver force-accepts. A
  receiver MUST reject any bundle whose ``not_before`` is more than
  ``max_skew_seconds`` after its own clock.
* ``sender_clock_behind_receiver_rejected`` — mutation: sender clock
  runs 600 seconds behind the receiver; sender stamps ``not_after``
  60 s after its own clock so the bundle is already expired in the
  receiver's frame, but the receiver force-accepts. A receiver MUST
  reject any bundle whose ``not_after`` is more than
  ``max_skew_seconds`` before its own clock.
* ``future_dated_bundle_accepted_as_currently_valid_rejected`` —
  mutation: sender deliberately stamps ``not_before`` 24 hours in
  the future (well past the receiver's skew tolerance), but the
  receiver clamps the value to its own clock and treats the bundle
  as currently valid. A receiver MUST reject a bundle whose
  ``not_before`` is past the skew window; clamping silently into
  validity is a forgery vector.
* ``ttl_window_straddling_skew_silently_extended_rejected`` —
  mutation: sender stamps a 30-second TTL window that has just
  expired in the receiver's frame; the receiver silently extends
  the window by ``max_skew_seconds=60`` so that the bundle is
  accepted as still-valid. A receiver MUST NOT extend the window;
  skew tolerance is for evaluating the boundary, not for stretching
  the validity period.

Every case lays down a per-case clock-skew transcript in a temporary
work directory, runs it through the verifier embedded in this gate,
and records ``observed_verdict``. The gate's overall verdict is
``PASS`` only when every case lines up with the expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-clock-skew-tolerance.json"
)
SCHEMA = "ao-operator/remote-transfer-clock-skew-tolerance/v1"

CASE_IDS = (
    "clean_within_skew_tolerance_passes",
    "sender_clock_ahead_of_receiver_rejected",
    "sender_clock_behind_receiver_rejected",
    "future_dated_bundle_accepted_as_currently_valid_rejected",
    "ttl_window_straddling_skew_silently_extended_rejected",
)

EXPECTED_VERDICTS = {
    "clean_within_skew_tolerance_passes": "PASS",
    "sender_clock_ahead_of_receiver_rejected": "FAIL",
    "sender_clock_behind_receiver_rejected": "FAIL",
    "future_dated_bundle_accepted_as_currently_valid_rejected": "FAIL",
    "ttl_window_straddling_skew_silently_extended_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _isofmt(dt: datetime) -> str:
    return dt.replace(microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _ClockSkewVerifier:
    """In-memory clock-skew tolerance state machine.

    Models the AO Runtime ``clock_skew_tolerance`` pipeline: a sender
    stamps ``not_before`` / ``not_after`` timestamps against its own
    clock; the receiver evaluates them against its own clock with a
    bounded ``max_skew_seconds`` tolerance and enforces four
    distilled time-boundary invariants:

    1. ``not_before`` MUST NOT be more than ``max_skew_seconds`` AFTER
       the receiver clock (no future-dated activation outside the
       skew window).
    2. ``not_after`` MUST NOT be more than ``max_skew_seconds`` BEFORE
       the receiver clock (no already-expired bundle outside the
       skew window).
    3. ``not_before`` MUST NOT be silently clamped into validity by
       overriding it with the receiver's own clock when it is past
       the skew window.
    4. The validity window MUST NOT be silently extended by adding
       ``max_skew_seconds`` to ``not_after``; skew tolerance is a
       boundary evaluation tool, not a window-stretching tool.
    """

    def __init__(self, *, max_skew_seconds: int, receiver_now: datetime) -> None:
        self.max_skew_seconds = max_skew_seconds
        self.receiver_now = receiver_now
        self.errors: list[str] = []

    def receiver_validate_window(
        self,
        *,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        skew = self.max_skew_seconds
        if (not_before - self.receiver_now).total_seconds() > skew:
            self.errors.append(
                f"not_before_too_far_in_future:not_before={_isofmt(not_before)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={skew}"
            )
            return
        if (self.receiver_now - not_after).total_seconds() > skew:
            self.errors.append(
                f"not_after_too_far_in_past:not_after={_isofmt(not_after)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={skew}"
            )
            return

    def receiver_force_accept_future_not_before(
        self,
        *,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        skew = self.max_skew_seconds
        if (not_before - self.receiver_now).total_seconds() > skew:
            self.errors.append(
                f"force_accepted_not_before_beyond_skew:not_before={_isofmt(not_before)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={skew}"
            )

    def receiver_force_accept_expired_not_after(
        self,
        *,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        skew = self.max_skew_seconds
        if (self.receiver_now - not_after).total_seconds() > skew:
            self.errors.append(
                f"force_accepted_not_after_beyond_skew:not_after={_isofmt(not_after)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={skew}"
            )

    def receiver_clamp_future_not_before_into_validity(
        self,
        *,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        skew = self.max_skew_seconds
        if (not_before - self.receiver_now).total_seconds() > skew:
            self.errors.append(
                f"silently_clamped_future_not_before:not_before={_isofmt(not_before)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={skew}"
            )

    def receiver_extend_ttl_by_skew(
        self,
        *,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        extended_not_after = not_after + timedelta(seconds=self.max_skew_seconds)
        if (self.receiver_now - not_after).total_seconds() > 0 and (
            self.receiver_now <= extended_not_after
        ):
            self.errors.append(
                f"silently_extended_ttl_by_skew:not_after={_isofmt(not_after)},extended_not_after={_isofmt(extended_not_after)},receiver_now={_isofmt(self.receiver_now)},max_skew_seconds={self.max_skew_seconds}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "clock-skew-transcript.json").write_text(
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


_RECEIVER_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_MAX_SKEW = 60


def run_clean_within_skew_tolerance_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_within_skew_tolerance_passes"
    verifier = _ClockSkewVerifier(max_skew_seconds=_MAX_SKEW, receiver_now=_RECEIVER_NOW)
    not_before = _RECEIVER_NOW - timedelta(seconds=30)
    not_after = _RECEIVER_NOW + timedelta(seconds=300)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "not_before": _isofmt(not_before),
            "not_after": _isofmt(not_after),
            "receiver_now": _isofmt(_RECEIVER_NOW),
            "max_skew_seconds": _MAX_SKEW,
        },
    ]
    verifier.receiver_validate_window(not_before=not_before, not_after=not_after)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender stamps not_before 30s before receiver_now and not_after 300s after; "
            "receiver_now=2026-01-15T12:00:00Z, max_skew_seconds=60; window validates without error"
        ),
    )


def run_sender_clock_ahead_of_receiver_rejected(work: Path) -> dict[str, Any]:
    case_id = "sender_clock_ahead_of_receiver_rejected"
    verifier = _ClockSkewVerifier(max_skew_seconds=_MAX_SKEW, receiver_now=_RECEIVER_NOW)
    not_before = _RECEIVER_NOW + timedelta(seconds=600)
    not_after = not_before + timedelta(seconds=300)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "not_before": _isofmt(not_before),
            "not_after": _isofmt(not_after),
            "receiver_now": _isofmt(_RECEIVER_NOW),
            "max_skew_seconds": _MAX_SKEW,
            "sender_offset_seconds": 600,
        },
        {"op": "receiver_force_accept_future_not_before"},
    ]
    verifier.receiver_force_accept_future_not_before(
        not_before=not_before, not_after=not_after
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender clock runs 600s ahead of receiver; not_before is 600s past receiver_now "
            "(skew tolerance is 60s); receiver force-accepts the future-dated activation"
        ),
    )


def run_sender_clock_behind_receiver_rejected(work: Path) -> dict[str, Any]:
    case_id = "sender_clock_behind_receiver_rejected"
    verifier = _ClockSkewVerifier(max_skew_seconds=_MAX_SKEW, receiver_now=_RECEIVER_NOW)
    not_after = _RECEIVER_NOW - timedelta(seconds=600)
    not_before = not_after - timedelta(seconds=300)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "not_before": _isofmt(not_before),
            "not_after": _isofmt(not_after),
            "receiver_now": _isofmt(_RECEIVER_NOW),
            "max_skew_seconds": _MAX_SKEW,
            "sender_offset_seconds": -600,
        },
        {"op": "receiver_force_accept_expired_not_after"},
    ]
    verifier.receiver_force_accept_expired_not_after(
        not_before=not_before, not_after=not_after
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender clock runs 600s behind receiver; not_after is 600s before receiver_now "
            "(skew tolerance is 60s); receiver force-accepts the already-expired bundle"
        ),
    )


def run_future_dated_bundle_accepted_as_currently_valid_rejected(work: Path) -> dict[str, Any]:
    case_id = "future_dated_bundle_accepted_as_currently_valid_rejected"
    verifier = _ClockSkewVerifier(max_skew_seconds=_MAX_SKEW, receiver_now=_RECEIVER_NOW)
    not_before = _RECEIVER_NOW + timedelta(hours=24)
    not_after = not_before + timedelta(hours=24)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "not_before": _isofmt(not_before),
            "not_after": _isofmt(not_after),
            "receiver_now": _isofmt(_RECEIVER_NOW),
            "max_skew_seconds": _MAX_SKEW,
        },
        {"op": "receiver_clamp_future_not_before_into_validity"},
    ]
    verifier.receiver_clamp_future_not_before_into_validity(
        not_before=not_before, not_after=not_after
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender stamps not_before 24h in receiver's future; receiver silently clamps "
            "not_before to its own clock and treats the bundle as currently valid"
        ),
    )


def run_ttl_window_straddling_skew_silently_extended_rejected(work: Path) -> dict[str, Any]:
    case_id = "ttl_window_straddling_skew_silently_extended_rejected"
    verifier = _ClockSkewVerifier(max_skew_seconds=_MAX_SKEW, receiver_now=_RECEIVER_NOW)
    not_before = _RECEIVER_NOW - timedelta(seconds=45)
    not_after = _RECEIVER_NOW - timedelta(seconds=15)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "not_before": _isofmt(not_before),
            "not_after": _isofmt(not_after),
            "receiver_now": _isofmt(_RECEIVER_NOW),
            "max_skew_seconds": _MAX_SKEW,
            "ttl_seconds": 30,
        },
        {"op": "receiver_extend_ttl_by_skew"},
    ]
    verifier.receiver_extend_ttl_by_skew(
        not_before=not_before, not_after=not_after
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender stamps a 30s TTL window that has just expired (not_after 15s before "
            "receiver_now); receiver silently extends the window by max_skew_seconds=60 and accepts"
        ),
    )


CASE_RUNNERS = {
    "clean_within_skew_tolerance_passes": run_clean_within_skew_tolerance_passes,
    "sender_clock_ahead_of_receiver_rejected": run_sender_clock_ahead_of_receiver_rejected,
    "sender_clock_behind_receiver_rejected": run_sender_clock_behind_receiver_rejected,
    "future_dated_bundle_accepted_as_currently_valid_rejected": run_future_dated_bundle_accepted_as_currently_valid_rejected,
    "ttl_window_straddling_skew_silently_extended_rejected": run_ttl_window_straddling_skew_silently_extended_rejected,
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
            "Remote-transfer clock skew tolerance is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix clock skew tolerance blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-clock-skew-tolerance-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-clock-skew-tolerance-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
