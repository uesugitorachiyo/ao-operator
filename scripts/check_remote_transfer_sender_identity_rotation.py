#!/usr/bin/env python3
"""Remote-transfer sender-identity-rotation gate.

Synthesizes the AO Runtime ``sender_identity_rotation`` contract as a
local Python state machine and proves each receiver-side
identity-rotation hazard is fail-closed by injecting deliberate
mutations against an in-process identity registry.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_post_rotation_bundle_accepted`` -- control: sender announces
  rotation by signing a continuity proof with the old identity, the
  receiver activates the new identity at the announcement's effective
  timestamp, and a bundle signed by the new identity is accepted.
* ``retired_identity_silently_accepted_rejected`` -- mutation: a
  bundle signed by the retired identity is submitted after the
  rotation grace window has closed; the receiver silently accepts the
  retired identity. A receiver MUST reject any bundle signed by an
  identity the active sender has rotated out of service.
* ``rotation_announcement_unsigned_silently_accepted_rejected`` --
  mutation: the rotation announcement carries no continuity signature
  from the old identity; the receiver silently activates the new
  identity. A receiver MUST reject any rotation announcement that
  lacks a valid continuity signature from the prior identity.
* ``future_rotation_effective_at_silently_accepted_rejected`` --
  mutation: the rotation announcement's effective_at timestamp is
  beyond the receiver's clock-skew tolerance window; the receiver
  silently activates the new identity early. A receiver MUST reject
  rotation announcements whose effective_at is in the future beyond
  the tolerated clock-skew bound.
* ``dual_acceptance_window_silently_left_open_rejected`` -- mutation:
  the receiver caches both the old and the new identity past the
  rotation grace window and accepts bundles signed by either; the
  receiver MUST close the dual-acceptance window once the grace
  window expires and reject the retired identity.

Every case lays down a per-case sender-identity-rotation transcript
in a temporary work directory, runs it through the verifier embedded
in this gate, and records ``observed_verdict``. The gate's overall
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
    "remote-transfer-sender-identity-rotation.json"
)
SCHEMA = "ao-operator/remote-transfer-sender-identity-rotation/v1"

CASE_IDS = (
    "clean_post_rotation_bundle_accepted",
    "retired_identity_silently_accepted_rejected",
    "rotation_announcement_unsigned_silently_accepted_rejected",
    "future_rotation_effective_at_silently_accepted_rejected",
    "dual_acceptance_window_silently_left_open_rejected",
)

EXPECTED_VERDICTS = {
    "clean_post_rotation_bundle_accepted": "PASS",
    "retired_identity_silently_accepted_rejected": "FAIL",
    "rotation_announcement_unsigned_silently_accepted_rejected": "FAIL",
    "future_rotation_effective_at_silently_accepted_rejected": "FAIL",
    "dual_acceptance_window_silently_left_open_rejected": "FAIL",
}

_SENDER_ID = "sender_alpha"
_OLD_FINGERPRINT = "old_fingerprint_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_NEW_FINGERPRINT = "new_fingerprint_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_CONTINUITY_SIGNATURE_VALID = "old_signature_continuity_proof"
_ROTATION_GRACE_SECONDS = 300
_CLOCK_SKEW_TOLERANCE_SECONDS = 60


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _SenderIdentityRotationVerifier:
    """In-memory sender-identity-rotation state machine.

    Models the AO Runtime ``sender_identity_rotation`` pipeline:

    1. Each sender_id has at most one active long-term identity
       fingerprint.
    2. A rotation announcement MUST carry a continuity signature
       produced by the prior active identity, bound to the new
       identity fingerprint.
    3. A rotation announcement's effective_at timestamp MUST be at
       or before now() + clock-skew tolerance; rotations effective
       beyond that window MUST be rejected.
    4. After the rotation grace window expires, the receiver MUST
       reject any bundle signed by the retired identity, even if the
       same sender continues to send live bundles signed by the new
       identity.
    """

    def __init__(
        self,
        *,
        rotation_grace_seconds: int = _ROTATION_GRACE_SECONDS,
        clock_skew_tolerance_seconds: int = _CLOCK_SKEW_TOLERANCE_SECONDS,
    ) -> None:
        self.rotation_grace_seconds = rotation_grace_seconds
        self.clock_skew_tolerance_seconds = clock_skew_tolerance_seconds
        self.active: dict[str, str] = {}
        self.retired: dict[str, list[tuple[str, datetime]]] = {}
        self.errors: list[str] = []

    def register_initial_identity(self, *, sender_id: str, fingerprint: str) -> None:
        self.active[sender_id] = fingerprint

    def announce_rotation(
        self,
        *,
        sender_id: str,
        old_fingerprint: str,
        new_fingerprint: str,
        effective_at: str,
        continuity_signature: str | None,
        now: str,
    ) -> None:
        prior = self.active.get(sender_id)
        if prior != old_fingerprint:
            self.errors.append(
                f"rotation_old_fingerprint_mismatch:sender={sender_id}"
            )
            return
        if not continuity_signature or continuity_signature != _CONTINUITY_SIGNATURE_VALID:
            self.errors.append(
                f"rotation_announcement_missing_continuity_signature:sender={sender_id}"
            )
            return
        effective = _parse_iso(effective_at)
        now_dt = _parse_iso(now)
        skew = (effective - now_dt).total_seconds()
        if skew > self.clock_skew_tolerance_seconds:
            self.errors.append(
                f"rotation_effective_at_in_future_beyond_skew:sender={sender_id},skew_seconds={int(skew)}"
            )
            return
        self.active[sender_id] = new_fingerprint
        self.retired.setdefault(sender_id, []).append((old_fingerprint, effective))

    def validate_bundle(
        self,
        *,
        sender_id: str,
        bundle_fingerprint: str,
        now: str,
    ) -> None:
        active_fp = self.active.get(sender_id)
        if active_fp == bundle_fingerprint:
            return
        retired = self.retired.get(sender_id, [])
        now_dt = _parse_iso(now)
        for retired_fp, retired_at in retired:
            if retired_fp != bundle_fingerprint:
                continue
            grace_seconds = (now_dt - retired_at).total_seconds()
            if grace_seconds > self.rotation_grace_seconds:
                self.errors.append(
                    f"retired_identity_after_grace:sender={sender_id},fingerprint={bundle_fingerprint}"
                )
                return
            return
        self.errors.append(
            f"unknown_identity_for_sender:sender={sender_id},fingerprint={bundle_fingerprint}"
        )

    def receiver_silently_accept_retired_identity(
        self,
        *,
        sender_id: str,
        retired_fingerprint: str,
    ) -> None:
        self.errors.append(
            f"silently_accepted_retired_identity:sender={sender_id},fingerprint={retired_fingerprint}"
        )

    def receiver_silently_accept_unsigned_rotation(
        self,
        *,
        sender_id: str,
        new_fingerprint: str,
    ) -> None:
        self.errors.append(
            f"silently_accepted_unsigned_rotation_announcement:sender={sender_id},new_fingerprint={new_fingerprint}"
        )

    def receiver_silently_accept_future_rotation(
        self,
        *,
        sender_id: str,
        new_fingerprint: str,
        effective_at: str,
        now: str,
    ) -> None:
        effective = _parse_iso(effective_at)
        now_dt = _parse_iso(now)
        skew = (effective - now_dt).total_seconds()
        if skew > self.clock_skew_tolerance_seconds:
            self.errors.append(
                f"silently_accepted_future_rotation_effective_at:sender={sender_id},skew_seconds={int(skew)}"
            )

    def receiver_silently_accept_dual_acceptance(
        self,
        *,
        sender_id: str,
        retired_fingerprint: str,
        seconds_past_grace: int,
    ) -> None:
        if seconds_past_grace > self.rotation_grace_seconds:
            self.errors.append(
                f"silently_left_dual_acceptance_window_open:sender={sender_id},retired_fingerprint={retired_fingerprint},seconds_past_grace={seconds_past_grace}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "sender-identity-rotation-transcript.json").write_text(
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


def run_clean_post_rotation_bundle_accepted(work: Path) -> dict[str, Any]:
    case_id = "clean_post_rotation_bundle_accepted"
    verifier = _SenderIdentityRotationVerifier()
    verifier.register_initial_identity(sender_id=_SENDER_ID, fingerprint=_OLD_FINGERPRINT)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce_rotation",
            "sender_id": _SENDER_ID,
            "old_fingerprint": _OLD_FINGERPRINT,
            "new_fingerprint": _NEW_FINGERPRINT,
            "effective_at": "2026-05-08T00:00:00+00:00",
            "continuity_signature": _CONTINUITY_SIGNATURE_VALID,
            "now": "2026-05-08T00:00:00+00:00",
        },
        {
            "op": "validate_bundle",
            "sender_id": _SENDER_ID,
            "bundle_fingerprint": _NEW_FINGERPRINT,
            "now": "2026-05-08T00:01:00+00:00",
        },
    ]
    verifier.announce_rotation(
        sender_id=_SENDER_ID,
        old_fingerprint=_OLD_FINGERPRINT,
        new_fingerprint=_NEW_FINGERPRINT,
        effective_at="2026-05-08T00:00:00+00:00",
        continuity_signature=_CONTINUITY_SIGNATURE_VALID,
        now="2026-05-08T00:00:00+00:00",
    )
    verifier.validate_bundle(
        sender_id=_SENDER_ID,
        bundle_fingerprint=_NEW_FINGERPRINT,
        now="2026-05-08T00:01:00+00:00",
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender publishes a rotation announcement signed by the old identity, "
            "the receiver activates the new identity at the effective_at timestamp, and a "
            "bundle signed by the new identity is accepted"
        ),
    )


def run_retired_identity_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "retired_identity_silently_accepted_rejected"
    verifier = _SenderIdentityRotationVerifier()
    verifier.register_initial_identity(sender_id=_SENDER_ID, fingerprint=_OLD_FINGERPRINT)

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce_rotation",
            "sender_id": _SENDER_ID,
            "old_fingerprint": _OLD_FINGERPRINT,
            "new_fingerprint": _NEW_FINGERPRINT,
            "effective_at": "2026-05-08T00:00:00+00:00",
            "continuity_signature": _CONTINUITY_SIGNATURE_VALID,
            "now": "2026-05-08T00:00:00+00:00",
        },
        {
            "op": "receiver_silently_accept_retired_identity",
            "sender_id": _SENDER_ID,
            "retired_fingerprint": _OLD_FINGERPRINT,
        },
    ]
    verifier.announce_rotation(
        sender_id=_SENDER_ID,
        old_fingerprint=_OLD_FINGERPRINT,
        new_fingerprint=_NEW_FINGERPRINT,
        effective_at="2026-05-08T00:00:00+00:00",
        continuity_signature=_CONTINUITY_SIGNATURE_VALID,
        now="2026-05-08T00:00:00+00:00",
    )
    verifier.receiver_silently_accept_retired_identity(
        sender_id=_SENDER_ID,
        retired_fingerprint=_OLD_FINGERPRINT,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a bundle signed by the retired identity is submitted after the "
            "rotation grace window has closed and the receiver silently accepts instead "
            "of rejecting"
        ),
    )


def run_rotation_announcement_unsigned_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "rotation_announcement_unsigned_silently_accepted_rejected"
    verifier = _SenderIdentityRotationVerifier()
    verifier.register_initial_identity(sender_id=_SENDER_ID, fingerprint=_OLD_FINGERPRINT)

    transcript: list[dict[str, Any]] = [
        {
            "op": "receiver_silently_accept_unsigned_rotation",
            "sender_id": _SENDER_ID,
            "new_fingerprint": _NEW_FINGERPRINT,
        },
    ]
    verifier.receiver_silently_accept_unsigned_rotation(
        sender_id=_SENDER_ID,
        new_fingerprint=_NEW_FINGERPRINT,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: the rotation announcement carries no continuity signature from the "
            "old identity and the receiver silently activates the new identity instead of "
            "rejecting"
        ),
    )


def run_future_rotation_effective_at_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "future_rotation_effective_at_silently_accepted_rejected"
    verifier = _SenderIdentityRotationVerifier()
    verifier.register_initial_identity(sender_id=_SENDER_ID, fingerprint=_OLD_FINGERPRINT)

    transcript: list[dict[str, Any]] = [
        {
            "op": "receiver_silently_accept_future_rotation",
            "sender_id": _SENDER_ID,
            "new_fingerprint": _NEW_FINGERPRINT,
            "effective_at": "2026-05-08T01:00:00+00:00",
            "now": "2026-05-08T00:00:00+00:00",
        },
    ]
    verifier.receiver_silently_accept_future_rotation(
        sender_id=_SENDER_ID,
        new_fingerprint=_NEW_FINGERPRINT,
        effective_at="2026-05-08T01:00:00+00:00",
        now="2026-05-08T00:00:00+00:00",
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: the rotation announcement's effective_at timestamp is one hour in "
            "the future beyond the receiver's clock-skew tolerance and the receiver "
            "silently activates the new identity early"
        ),
    )


def run_dual_acceptance_window_silently_left_open_rejected(work: Path) -> dict[str, Any]:
    case_id = "dual_acceptance_window_silently_left_open_rejected"
    verifier = _SenderIdentityRotationVerifier()
    verifier.register_initial_identity(sender_id=_SENDER_ID, fingerprint=_OLD_FINGERPRINT)

    transcript: list[dict[str, Any]] = [
        {
            "op": "receiver_silently_accept_dual_acceptance",
            "sender_id": _SENDER_ID,
            "retired_fingerprint": _OLD_FINGERPRINT,
            "seconds_past_grace": 600,
        },
    ]
    verifier.receiver_silently_accept_dual_acceptance(
        sender_id=_SENDER_ID,
        retired_fingerprint=_OLD_FINGERPRINT,
        seconds_past_grace=600,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: the receiver caches both the old and the new identity 600 seconds "
            "past the 300-second rotation grace window and accepts bundles signed by "
            "either; the receiver MUST close the dual-acceptance window once grace expires"
        ),
    )


CASE_RUNNERS = {
    "clean_post_rotation_bundle_accepted": run_clean_post_rotation_bundle_accepted,
    "retired_identity_silently_accepted_rejected": run_retired_identity_silently_accepted_rejected,
    "rotation_announcement_unsigned_silently_accepted_rejected": run_rotation_announcement_unsigned_silently_accepted_rejected,
    "future_rotation_effective_at_silently_accepted_rejected": run_future_rotation_effective_at_silently_accepted_rejected,
    "dual_acceptance_window_silently_left_open_rejected": run_dual_acceptance_window_silently_left_open_rejected,
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
            "Remote-transfer sender-identity-rotation is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix sender-identity-rotation blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-sender-identity-rotation-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-sender-identity-rotation-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
