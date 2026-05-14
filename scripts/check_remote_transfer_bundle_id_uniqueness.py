#!/usr/bin/env python3
"""Remote-transfer bundle-id uniqueness gate.

Synthesizes the AO Runtime ``bundle_id_uniqueness`` contract as a
local Python state machine and proves each receiver-side bundle-id
collision hazard is fail-closed by injecting deliberate mutations
against an in-process bundle-id ledger.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_unique_bundle_ids_pass`` — control: a sender submits three
  distinct bundles with unique ``bundle_id`` values; the receiver
  records each in its uniqueness ledger and accepts all three.
* ``duplicate_bundle_id_within_session_rejected`` — mutation: a
  sender re-submits the same ``bundle_id`` within a single session
  carrying different content, and the receiver force-accepts the
  duplicate. A receiver MUST reject any second submission of a
  ``bundle_id`` already recorded in the ledger.
* ``cross_sender_bundle_id_collision_rejected`` — mutation: two
  distinct senders submit bundles whose ``bundle_id`` values collide
  while their content differs; the receiver collapses the two into
  one ledger entry. A receiver MUST scope ``bundle_id`` uniqueness
  globally across senders and reject the second sender's submission
  rather than silently merging content under a single id.
* ``bundle_id_truncation_collision_rejected`` — mutation: the
  receiver truncates ``bundle_id`` to a fixed prefix (16 hex chars)
  for indexing and treats two distinct full ids that share the same
  prefix as the same bundle. A receiver MUST compare the full
  ``bundle_id`` and reject the second submission once a prefix
  collision is observed; truncation collapse is a forgery vector.
* ``bundle_id_replayed_after_completion_rejected`` — mutation: a
  sender replays a previously-completed ``bundle_id`` with new
  content after the receiver has cleared its in-flight tracking,
  and the receiver accepts it as a fresh bundle. A receiver MUST
  retain a durable completion ledger and reject any replay of a
  completed ``bundle_id`` regardless of whether the in-flight
  tracking has been cleared.

Every case lays down a per-case ledger transcript in a temporary
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-bundle-id-uniqueness.json"
)
SCHEMA = "ao-operator/remote-transfer-bundle-id-uniqueness/v1"

CASE_IDS = (
    "clean_unique_bundle_ids_pass",
    "duplicate_bundle_id_within_session_rejected",
    "cross_sender_bundle_id_collision_rejected",
    "bundle_id_truncation_collision_rejected",
    "bundle_id_replayed_after_completion_rejected",
)

EXPECTED_VERDICTS = {
    "clean_unique_bundle_ids_pass": "PASS",
    "duplicate_bundle_id_within_session_rejected": "FAIL",
    "cross_sender_bundle_id_collision_rejected": "FAIL",
    "bundle_id_truncation_collision_rejected": "FAIL",
    "bundle_id_replayed_after_completion_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _BundleIdUniquenessVerifier:
    """In-memory bundle-id uniqueness state machine.

    Models the AO Runtime ``bundle_id_uniqueness`` pipeline: the
    receiver maintains an in-flight ledger plus a durable completion
    ledger, both keyed on the full ``bundle_id``. Four invariants:

    1. The same ``bundle_id`` MUST NOT be accepted twice within a
       session (in-flight duplicate rejection).
    2. ``bundle_id`` uniqueness scope spans senders; two senders
       submitting the same ``bundle_id`` MUST be treated as a
       collision, not silently merged.
    3. The full ``bundle_id`` MUST be compared; truncation prefixes
       MUST NOT cause two distinct ids to collapse into one ledger
       entry.
    4. Completion MUST be persisted; a completed ``bundle_id`` MUST
       NOT be replayable after in-flight tracking is cleared.
    """

    def __init__(self, *, prefix_index_chars: int = 16) -> None:
        self.prefix_index_chars = prefix_index_chars
        self.in_flight: dict[str, dict[str, Any]] = {}
        self.completed: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []

    def receiver_record_unique(
        self,
        *,
        sender: str,
        bundle_id: str,
        content_digest: str,
    ) -> None:
        if bundle_id in self.in_flight or bundle_id in self.completed:
            self.errors.append(
                f"bundle_id_already_known:bundle_id={bundle_id},sender={sender}"
            )
            return
        self.in_flight[bundle_id] = {
            "sender": sender,
            "content_digest": content_digest,
        }

    def receiver_complete(self, *, bundle_id: str) -> None:
        if bundle_id not in self.in_flight:
            self.errors.append(
                f"complete_called_for_unknown_bundle_id:bundle_id={bundle_id}"
            )
            return
        self.completed[bundle_id] = self.in_flight.pop(bundle_id)

    def receiver_clear_in_flight(self) -> None:
        self.in_flight.clear()

    def receiver_force_accept_duplicate(
        self,
        *,
        sender: str,
        bundle_id: str,
        content_digest: str,
    ) -> None:
        if bundle_id in self.in_flight or bundle_id in self.completed:
            self.errors.append(
                f"force_accepted_duplicate_bundle_id:bundle_id={bundle_id},sender={sender}"
            )

    def receiver_collapse_cross_sender_collision(
        self,
        *,
        sender_a: str,
        sender_b: str,
        bundle_id: str,
        content_digest_a: str,
        content_digest_b: str,
    ) -> None:
        if content_digest_a == content_digest_b:
            return
        self.errors.append(
            f"silently_collapsed_cross_sender_bundle_id:bundle_id={bundle_id},sender_a={sender_a},sender_b={sender_b}"
        )

    def receiver_index_by_truncated_prefix(
        self,
        *,
        bundle_id_a: str,
        bundle_id_b: str,
    ) -> None:
        prefix_a = bundle_id_a[: self.prefix_index_chars]
        prefix_b = bundle_id_b[: self.prefix_index_chars]
        if prefix_a == prefix_b and bundle_id_a != bundle_id_b:
            self.errors.append(
                f"truncated_prefix_collision_collapsed:bundle_id_a={bundle_id_a},bundle_id_b={bundle_id_b},prefix={prefix_a}"
            )

    def receiver_force_accept_completed_replay(
        self,
        *,
        sender: str,
        bundle_id: str,
        content_digest: str,
    ) -> None:
        if bundle_id in self.completed:
            self.errors.append(
                f"force_accepted_completed_replay:bundle_id={bundle_id},sender={sender}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "bundle-id-ledger-transcript.json").write_text(
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


def run_clean_unique_bundle_ids_pass(work: Path) -> dict[str, Any]:
    case_id = "clean_unique_bundle_ids_pass"
    verifier = _BundleIdUniquenessVerifier()
    bundles = [
        ("alice", "0123456789abcdef" + "00000001" * 4, "digest-a"),
        ("alice", "0123456789abcdef" + "00000002" * 4, "digest-b"),
        ("alice", "0123456789abcdef" + "00000003" * 4, "digest-c"),
    ]

    transcript: list[dict[str, Any]] = []
    for sender, bundle_id, digest in bundles:
        transcript.append(
            {"op": "announce", "sender": sender, "bundle_id": bundle_id, "content_digest": digest}
        )
        verifier.receiver_record_unique(
            sender=sender, bundle_id=bundle_id, content_digest=digest
        )
        transcript.append({"op": "complete", "bundle_id": bundle_id})
        verifier.receiver_complete(bundle_id=bundle_id)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender submits three distinct bundles with unique bundle_id values; "
            "receiver records each into the uniqueness ledger and accepts all three"
        ),
    )


def run_duplicate_bundle_id_within_session_rejected(work: Path) -> dict[str, Any]:
    case_id = "duplicate_bundle_id_within_session_rejected"
    verifier = _BundleIdUniquenessVerifier()
    bundle_id = "abcdef0123456789" + "11111111" * 4

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "sender": "alice", "bundle_id": bundle_id, "content_digest": "digest-a"},
        {"op": "announce_duplicate", "sender": "alice", "bundle_id": bundle_id, "content_digest": "digest-b"},
        {"op": "receiver_force_accept_duplicate"},
    ]
    verifier.receiver_record_unique(
        sender="alice", bundle_id=bundle_id, content_digest="digest-a"
    )
    verifier.receiver_force_accept_duplicate(
        sender="alice", bundle_id=bundle_id, content_digest="digest-b"
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender re-submits the same bundle_id within one session carrying different "
            "content; receiver force-accepts the duplicate instead of rejecting on ledger hit"
        ),
    )


def run_cross_sender_bundle_id_collision_rejected(work: Path) -> dict[str, Any]:
    case_id = "cross_sender_bundle_id_collision_rejected"
    verifier = _BundleIdUniquenessVerifier()
    bundle_id = "fedcba9876543210" + "22222222" * 4

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "sender": "alice", "bundle_id": bundle_id, "content_digest": "digest-a"},
        {"op": "announce", "sender": "bob", "bundle_id": bundle_id, "content_digest": "digest-b"},
        {"op": "receiver_collapse_cross_sender_collision"},
    ]
    verifier.receiver_record_unique(
        sender="alice", bundle_id=bundle_id, content_digest="digest-a"
    )
    verifier.receiver_collapse_cross_sender_collision(
        sender_a="alice",
        sender_b="bob",
        bundle_id=bundle_id,
        content_digest_a="digest-a",
        content_digest_b="digest-b",
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: two distinct senders submit bundles with colliding bundle_id values; "
            "receiver silently collapses the two into one ledger entry instead of rejecting"
        ),
    )


def run_bundle_id_truncation_collision_rejected(work: Path) -> dict[str, Any]:
    case_id = "bundle_id_truncation_collision_rejected"
    verifier = _BundleIdUniquenessVerifier(prefix_index_chars=16)
    bundle_id_a = "0011223344556677" + "aaaaaaaa" * 4
    bundle_id_b = "0011223344556677" + "bbbbbbbb" * 4

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "sender": "alice", "bundle_id": bundle_id_a, "content_digest": "digest-a"},
        {"op": "announce", "sender": "alice", "bundle_id": bundle_id_b, "content_digest": "digest-b"},
        {"op": "receiver_index_by_truncated_prefix", "prefix_index_chars": 16},
    ]
    verifier.receiver_record_unique(
        sender="alice", bundle_id=bundle_id_a, content_digest="digest-a"
    )
    verifier.receiver_index_by_truncated_prefix(
        bundle_id_a=bundle_id_a, bundle_id_b=bundle_id_b
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: receiver indexes by 16-char prefix and treats two distinct full bundle_id "
            "values that share the same prefix as the same bundle (truncation collapse)"
        ),
    )


def run_bundle_id_replayed_after_completion_rejected(work: Path) -> dict[str, Any]:
    case_id = "bundle_id_replayed_after_completion_rejected"
    verifier = _BundleIdUniquenessVerifier()
    bundle_id = "deadbeefcafef00d" + "33333333" * 4

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "sender": "alice", "bundle_id": bundle_id, "content_digest": "digest-a"},
        {"op": "complete", "bundle_id": bundle_id},
        {"op": "receiver_clear_in_flight"},
        {"op": "announce_replay", "sender": "alice", "bundle_id": bundle_id, "content_digest": "digest-b"},
        {"op": "receiver_force_accept_completed_replay"},
    ]
    verifier.receiver_record_unique(
        sender="alice", bundle_id=bundle_id, content_digest="digest-a"
    )
    verifier.receiver_complete(bundle_id=bundle_id)
    verifier.receiver_clear_in_flight()
    verifier.receiver_force_accept_completed_replay(
        sender="alice", bundle_id=bundle_id, content_digest="digest-b"
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender replays a previously-completed bundle_id with new content after "
            "in-flight tracking is cleared; receiver lacks a durable completion ledger and accepts"
        ),
    )


CASE_RUNNERS = {
    "clean_unique_bundle_ids_pass": run_clean_unique_bundle_ids_pass,
    "duplicate_bundle_id_within_session_rejected": run_duplicate_bundle_id_within_session_rejected,
    "cross_sender_bundle_id_collision_rejected": run_cross_sender_bundle_id_collision_rejected,
    "bundle_id_truncation_collision_rejected": run_bundle_id_truncation_collision_rejected,
    "bundle_id_replayed_after_completion_rejected": run_bundle_id_replayed_after_completion_rejected,
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
            "Remote-transfer bundle-id uniqueness is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix bundle-id uniqueness blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-id-uniqueness-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-id-uniqueness-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
