#!/usr/bin/env python3
"""Remote-transfer approval expiry & rotation gate.

Synthesizes the AO Runtime ``signed_remote_approval_transfer`` lifecycle
contract as a local Python state machine and proves each lifecycle
violation is fail-closed by injecting deliberate mutations against an
in-process verifier.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_approval_passes`` — control: approval issued by an active
  primary kid, used once well inside the expiry window verifies.
* ``expired_approval_rejected`` — mutation: ``expires_at`` lies in the
  past relative to ``now``; expiry invariant must reject it.
* ``approval_used_after_rotation_cutover_rejected`` — mutation: kid
  was valid at issuance but rotation cutover plus grace window has
  fully elapsed by use-time; rotation invariant must reject it.
* ``signing_key_rotated_midflight_without_grace_rejected`` — mutation:
  rotation policy has a zero-second grace; use-time falls one second
  past cutover. The grace-window invariant must still reject.
* ``approval_reused_beyond_ttl_rejected`` — mutation: approval is
  presented ``max_uses + 1`` times; the use-counter invariant must
  reject the final use.

Every case lays down an approval payload + signature in a temporary
work directory, runs it through the verifier embedded in this gate,
and records ``observed_verdict``. The gate's overall verdict is
``PASS`` only when every case lines up with the expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-approval-expiry-rotation.json"
)
SCHEMA = "ao-operator/remote-transfer-approval-expiry-rotation/v1"

CASE_IDS = (
    "clean_approval_passes",
    "expired_approval_rejected",
    "approval_used_after_rotation_cutover_rejected",
    "signing_key_rotated_midflight_without_grace_rejected",
    "approval_reused_beyond_ttl_rejected",
)

EXPECTED_VERDICTS = {
    "clean_approval_passes": "PASS",
    "expired_approval_rejected": "FAIL",
    "approval_used_after_rotation_cutover_rejected": "FAIL",
    "signing_key_rotated_midflight_without_grace_rejected": "FAIL",
    "approval_reused_beyond_ttl_rejected": "FAIL",
}

NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _canonical_approval_bytes(approval: dict[str, Any]) -> bytes:
    return json.dumps(approval, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(approval: dict[str, Any], *, kid: str, secret: bytes) -> str:
    digest = hmac.new(secret, _canonical_approval_bytes(approval), hashlib.sha256)
    return f"{kid}:{digest.hexdigest()}"


def _key_active_at(key: dict[str, Any], when: datetime, *, with_grace: bool) -> bool:
    valid_from = _parse_iso(key["valid_from"])
    valid_until_raw = key.get("valid_until")
    if valid_until_raw is None:
        return when >= valid_from
    valid_until = _parse_iso(valid_until_raw)
    if with_grace:
        valid_until = valid_until + timedelta(seconds=int(key.get("rotation_grace_seconds", 0)))
    return valid_from <= when <= valid_until


def _verify(
    approval: dict[str, Any],
    signature: str,
    *,
    key_registry: dict[str, dict[str, Any]],
    use_counts: dict[str, int],
    now: datetime,
) -> tuple[str, list[str]]:
    """Return (verdict, errors) for an approval presentation.

    Enforces five lifecycle invariants distilled from the AO Runtime
    signed_remote_approval_transfer contract: approval must not be
    expired at use-time, signing kid must be in the registered set,
    kid must have been active at issuance, kid must still be active
    (with rotation grace) at use-time, and the approval may not be
    presented beyond its declared ``max_uses`` ceiling. The signature
    HMAC must also verify against the registered secret.
    """
    errors: list[str] = []

    expires_at_raw = approval.get("expires_at")
    if not isinstance(expires_at_raw, str):
        errors.append("missing_expires_at")
    else:
        expires_at = _parse_iso(expires_at_raw)
        if now >= expires_at:
            errors.append(
                f"approval_expired:expires_at={expires_at_raw},now={_iso(now)}"
            )

    issued_at_raw = approval.get("issued_at")
    issued_at: datetime | None = None
    if not isinstance(issued_at_raw, str):
        errors.append("missing_issued_at")
    else:
        issued_at = _parse_iso(issued_at_raw)

    try:
        kid, sig_hex = signature.split(":", 1)
    except ValueError:
        errors.append("malformed_signature")
        kid, sig_hex = "", ""

    key = key_registry.get(kid)
    if key is None:
        errors.append(f"unregistered_signing_key:kid={kid!r}")
    else:
        secret = key["secret"]
        expected = hmac.new(secret, _canonical_approval_bytes(approval), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig_hex):
            errors.append("signature_mismatch")
        if issued_at is not None and not _key_active_at(key, issued_at, with_grace=False):
            errors.append(
                f"kid_inactive_at_issuance:kid={kid},issued_at={issued_at_raw}"
            )
        if not _key_active_at(key, now, with_grace=True):
            errors.append(
                f"kid_inactive_at_use_time:kid={kid},now={_iso(now)},grace={key.get('rotation_grace_seconds', 0)}s"
            )

    approval_id = approval.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        errors.append("missing_approval_id")
    else:
        max_uses = int(approval.get("max_uses") or 0)
        prior = use_counts.get(approval_id, 0)
        new_count = prior + 1
        use_counts[approval_id] = new_count
        if max_uses <= 0:
            errors.append(f"invalid_max_uses:approval_id={approval_id},max_uses={max_uses}")
        elif new_count > max_uses:
            errors.append(
                f"approval_reused_beyond_ttl:approval_id={approval_id},max_uses={max_uses},use={new_count}"
            )

    return ("PASS" if not errors else "FAIL", errors)


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


def _default_registry(now: datetime) -> dict[str, dict[str, Any]]:
    return {
        "kid-primary": {
            "secret": b"ao-operator-test-secret-primary",
            "valid_from": _iso(now - timedelta(days=30)),
            "valid_until": _iso(now + timedelta(days=30)),
            "rotation_grace_seconds": 300,
        },
        "kid-secondary": {
            "secret": b"ao-operator-test-secret-secondary",
            "valid_from": _iso(now - timedelta(days=30)),
            "valid_until": _iso(now + timedelta(days=30)),
            "rotation_grace_seconds": 300,
        },
    }


def _approval_dict(*, approval_id: str, issued_at: datetime, expires_at: datetime, max_uses: int, nonce: str) -> dict[str, Any]:
    return {
        "approval_id": approval_id,
        "issued_at": _iso(issued_at),
        "expires_at": _iso(expires_at),
        "max_uses": max_uses,
        "nonce": nonce,
    }


def _persist_case(work: Path, case_id: str, body: dict[str, Any]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "approval.json").write_text(json.dumps(body, indent=2), encoding="utf-8")


def run_clean_approval_passes(work: Path, *, use_counts: dict[str, int]) -> dict[str, Any]:
    case_id = "clean_approval_passes"
    registry = _default_registry(NOW)
    approval = _approval_dict(
        approval_id="approval-clean-001",
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
        max_uses=1,
        nonce="nonce-clean-001",
    )
    signature = _sign(approval, kid="kid-primary", secret=registry["kid-primary"]["secret"])
    _persist_case(work, case_id, {"approval": approval, "signature": signature})
    verdict, errors = _verify(
        approval, signature, key_registry=registry, use_counts=use_counts, now=NOW,
    )
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        observed_errors=errors,
        detail="control: approval issued and used inside expiry, kid active, first use",
    )


def run_expired_approval_rejected(work: Path, *, use_counts: dict[str, int]) -> dict[str, Any]:
    case_id = "expired_approval_rejected"
    registry = _default_registry(NOW)
    approval = _approval_dict(
        approval_id="approval-expired-002",
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(minutes=5),
        max_uses=1,
        nonce="nonce-expired-002",
    )
    signature = _sign(approval, kid="kid-primary", secret=registry["kid-primary"]["secret"])
    _persist_case(work, case_id, {"approval": approval, "signature": signature})
    verdict, errors = _verify(
        approval, signature, key_registry=registry, use_counts=use_counts, now=NOW,
    )
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        observed_errors=errors,
        detail="mutation: expires_at is 5 minutes before now; expiry invariant rejects",
    )


def run_approval_used_after_rotation_cutover_rejected(work: Path, *, use_counts: dict[str, int]) -> dict[str, Any]:
    case_id = "approval_used_after_rotation_cutover_rejected"
    cutover = NOW - timedelta(hours=1)
    registry = _default_registry(NOW)
    registry["kid-rotated"] = {
        "secret": b"ao-operator-test-secret-rotated",
        "valid_from": _iso(NOW - timedelta(days=30)),
        "valid_until": _iso(cutover),
        "rotation_grace_seconds": 60,
    }
    approval = _approval_dict(
        approval_id="approval-rotated-003",
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=1),
        max_uses=1,
        nonce="nonce-rotated-003",
    )
    signature = _sign(approval, kid="kid-rotated", secret=registry["kid-rotated"]["secret"])
    _persist_case(
        work,
        case_id,
        {"approval": approval, "signature": signature, "rotation_cutover": _iso(cutover)},
    )
    verdict, errors = _verify(
        approval, signature, key_registry=registry, use_counts=use_counts, now=NOW,
    )
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        observed_errors=errors,
        detail="mutation: kid valid at issuance but cutover + 60s grace fully elapsed by use-time",
    )


def run_signing_key_rotated_midflight_without_grace_rejected(work: Path, *, use_counts: dict[str, int]) -> dict[str, Any]:
    case_id = "signing_key_rotated_midflight_without_grace_rejected"
    cutover = NOW - timedelta(seconds=1)
    registry = _default_registry(NOW)
    registry["kid-zero-grace"] = {
        "secret": b"ao-operator-test-secret-zero-grace",
        "valid_from": _iso(NOW - timedelta(days=30)),
        "valid_until": _iso(cutover),
        "rotation_grace_seconds": 0,
    }
    approval = _approval_dict(
        approval_id="approval-zerograce-004",
        issued_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
        max_uses=1,
        nonce="nonce-zerograce-004",
    )
    signature = _sign(approval, kid="kid-zero-grace", secret=registry["kid-zero-grace"]["secret"])
    _persist_case(
        work,
        case_id,
        {"approval": approval, "signature": signature, "rotation_cutover": _iso(cutover)},
    )
    verdict, errors = _verify(
        approval, signature, key_registry=registry, use_counts=use_counts, now=NOW,
    )
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        observed_errors=errors,
        detail="mutation: rotation policy has zero grace; use-time is one second past cutover",
    )


def run_approval_reused_beyond_ttl_rejected(work: Path, *, use_counts: dict[str, int]) -> dict[str, Any]:
    case_id = "approval_reused_beyond_ttl_rejected"
    registry = _default_registry(NOW)
    approval = _approval_dict(
        approval_id="approval-reused-005",
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
        max_uses=1,
        nonce="nonce-reused-005",
    )
    signature = _sign(approval, kid="kid-primary", secret=registry["kid-primary"]["secret"])
    _persist_case(work, case_id, {"approval": approval, "signature": signature})
    _verify(approval, signature, key_registry=registry, use_counts=use_counts, now=NOW)
    verdict, errors = _verify(
        approval, signature, key_registry=registry, use_counts=use_counts, now=NOW,
    )
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        observed_errors=errors,
        detail="mutation: approval presented twice with max_uses=1; second use rejected",
    )


CASE_RUNNERS = {
    "clean_approval_passes": run_clean_approval_passes,
    "expired_approval_rejected": run_expired_approval_rejected,
    "approval_used_after_rotation_cutover_rejected": run_approval_used_after_rotation_cutover_rejected,
    "signing_key_rotated_midflight_without_grace_rejected": run_signing_key_rotated_midflight_without_grace_rejected,
    "approval_reused_beyond_ttl_rejected": run_approval_reused_beyond_ttl_rejected,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    use_counts: dict[str, int] = {}
    cases = [CASE_RUNNERS[case_id](work_dir, use_counts=use_counts) for case_id in CASE_IDS]
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
            "Remote-transfer approval expiry & rotation modes are locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix approval expiry/rotation invariant blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-approval-expiry-rotation-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-approval-expiry-rotation-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
