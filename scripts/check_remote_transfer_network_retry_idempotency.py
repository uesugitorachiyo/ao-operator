#!/usr/bin/env python3
"""Remote-transfer network retry idempotency gate.

Synthesizes the AO Runtime ``network_retry_idempotency`` contract as a
local Python state machine and proves each resilience-layer violation
is fail-closed by injecting deliberate mutations against an in-process
send/receive_commit/ack/timeout/finalize pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_retry_round_trip_passes`` — control: two chunks are sent with
  fresh nonces, the first ack is dropped so the sender retries the
  same chunk_index with the same nonce, the receiver dedupes on nonce
  and acknowledges once, finalize commits both chunks exactly once.
* ``retry_without_nonce_dedup_rejected`` — mutation: a buggy retry
  mints a *new* nonce for a chunk that has already been transmitted,
  so the receiver cannot dedupe and the chunk is committed twice.
* ``partial_flush_on_network_drop_rejected`` — mutation: a chunk is
  sent and committed but the connection drops before ack, and the
  sender finalizes anyway, leaving the chunk uncertainly delivered
  with no resolved ack record.
* ``ack_lost_causes_double_commit_rejected`` — mutation: an ack is
  lost and the retry path commits the same nonce a second time on the
  receiver, violating commit-once-per-nonce.
* ``timeout_shorter_than_response_causes_orphan_rejected`` — mutation:
  a send is marked timed-out by the sender, but the slow receiver
  later commits anyway, producing an orphaned commit not tracked by
  the sender's resolved set.

Every case lays down a per-case retry transcript in a temporary work
directory, runs it through the verifier embedded in this gate, and
records ``observed_verdict``. The gate's overall verdict is ``PASS``
only when every case lines up with the expected verdict.

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
    "remote-transfer-network-retry-idempotency.json"
)
SCHEMA = "ao-operator/remote-transfer-network-retry-idempotency/v1"

CASE_IDS = (
    "clean_retry_round_trip_passes",
    "retry_without_nonce_dedup_rejected",
    "partial_flush_on_network_drop_rejected",
    "ack_lost_causes_double_commit_rejected",
    "timeout_shorter_than_response_causes_orphan_rejected",
)

EXPECTED_VERDICTS = {
    "clean_retry_round_trip_passes": "PASS",
    "retry_without_nonce_dedup_rejected": "FAIL",
    "partial_flush_on_network_drop_rejected": "FAIL",
    "ack_lost_causes_double_commit_rejected": "FAIL",
    "timeout_shorter_than_response_causes_orphan_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _RetryVerifier:
    """In-memory network retry idempotency state machine.

    Models the AO Runtime ``network_retry_idempotency`` pipeline:
    a sender emits chunks tagged with a per-chunk nonce, a receiver
    commits each unique nonce exactly once, acks are returned to the
    sender, the sender retries on missing acks, and the verifier
    enforces four distilled resilience invariants:

    1. A retry for a previously-sent chunk MUST reuse the original
       nonce minted for that chunk_index (nonce-dedup invariant).
    2. The receiver MUST commit each nonce exactly once even when the
       same nonce arrives twice (commit-once invariant).
    3. ``finalize`` MUST NOT be called while any sent nonce is still
       in-flight (no-partial-flush invariant).
    4. Once the sender records a timeout for a nonce, the receiver
       MUST NOT later commit that nonce (no-orphan-commit invariant).
    """

    def __init__(self) -> None:
        self.sent_nonces: dict[int, str] = {}
        self.acked_nonces: set[str] = set()
        self.committed_nonces: set[str] = set()
        self.committed_chunks: set[int] = set()
        self.timed_out_nonces: set[str] = set()
        self.in_flight_nonces: set[str] = set()
        self.errors: list[str] = []
        self.finalized = False

    def send(self, chunk_index: int, nonce: str) -> None:
        if chunk_index in self.sent_nonces:
            prior = self.sent_nonces[chunk_index]
            if prior != nonce:
                self.errors.append(
                    f"retry_minted_new_nonce:chunk_index={chunk_index},prior_nonce={prior},retry_nonce={nonce}"
                )
        else:
            self.sent_nonces[chunk_index] = nonce
        self.in_flight_nonces.add(nonce)

    def receive_commit(self, chunk_index: int, nonce: str) -> None:
        if nonce in self.timed_out_nonces:
            self.errors.append(
                f"orphan_commit_after_timeout:chunk_index={chunk_index},nonce={nonce}"
            )
            return
        if nonce in self.committed_nonces:
            self.errors.append(
                f"double_commit_for_nonce:chunk_index={chunk_index},nonce={nonce}"
            )
            return
        self.committed_nonces.add(nonce)
        self.committed_chunks.add(chunk_index)

    def ack(self, nonce: str) -> None:
        if nonce not in self.committed_nonces:
            self.errors.append(
                f"ack_without_commit:nonce={nonce}"
            )
            return
        self.acked_nonces.add(nonce)
        self.in_flight_nonces.discard(nonce)

    def timeout(self, nonce: str) -> None:
        self.timed_out_nonces.add(nonce)
        self.in_flight_nonces.discard(nonce)

    def finalize(self) -> None:
        self.finalized = True
        if self.in_flight_nonces:
            self.errors.append(
                f"finalize_with_in_flight_nonces:in_flight={sorted(self.in_flight_nonces)}"
            )
        for chunk_index, nonce in self.sent_nonces.items():
            if nonce in self.timed_out_nonces:
                continue
            if chunk_index not in self.committed_chunks:
                self.errors.append(
                    f"finalize_without_commit:chunk_index={chunk_index},nonce={nonce}"
                )
            elif nonce not in self.acked_nonces:
                self.errors.append(
                    f"finalize_without_ack:chunk_index={chunk_index},nonce={nonce}"
                )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "retry-transcript.json").write_text(
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


def run_clean_retry_round_trip_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_retry_round_trip_passes"
    verifier = _RetryVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0"})
    verifier.send(0, "n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0"})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0", "retry": True})
    verifier.send(0, "n0")
    transcript.append({"op": "receiver_dedupes_replays_ack", "nonce": "n0"})
    transcript.append({"op": "ack", "nonce": "n0"})
    verifier.ack("n0")

    transcript.append({"op": "send", "chunk_index": 1, "nonce": "n1"})
    verifier.send(1, "n1")
    transcript.append({"op": "receive_commit", "chunk_index": 1, "nonce": "n1"})
    verifier.receive_commit(1, "n1")
    transcript.append({"op": "ack", "nonce": "n1"})
    verifier.ack("n1")

    transcript.append({"op": "finalize"})
    verifier.finalize()

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: chunk 0 retried with same nonce; well-behaved receiver "
            "dedupes on the cached commit and replays the cached ack rather "
            "than committing again; chunk 1 acked normally; finalize sees no in-flight nonces"
        ),
    )


def run_retry_without_nonce_dedup_rejected(work: Path) -> dict[str, Any]:
    case_id = "retry_without_nonce_dedup_rejected"
    verifier = _RetryVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0"})
    verifier.send(0, "n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0"})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0_v2", "retry": True})
    verifier.send(0, "n0_v2")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0_v2", "retry": True})
    verifier.receive_commit(0, "n0_v2")
    transcript.append({"op": "ack", "nonce": "n0"})
    verifier.ack("n0")
    transcript.append({"op": "ack", "nonce": "n0_v2"})
    verifier.ack("n0_v2")
    transcript.append({"op": "finalize"})
    verifier.finalize()

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: retry mints a fresh nonce for chunk 0 so the receiver cannot dedupe and commits twice",
    )


def run_partial_flush_on_network_drop_rejected(work: Path) -> dict[str, Any]:
    case_id = "partial_flush_on_network_drop_rejected"
    verifier = _RetryVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0"})
    verifier.send(0, "n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0"})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "ack", "nonce": "n0"})
    verifier.ack("n0")

    transcript.append({"op": "send", "chunk_index": 1, "nonce": "n1"})
    verifier.send(1, "n1")
    transcript.append({"op": "finalize"})
    verifier.finalize()

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: chunk 1 is sent but never committed/acked before finalize, so the sender flushes a partial batch",
    )


def run_ack_lost_causes_double_commit_rejected(work: Path) -> dict[str, Any]:
    case_id = "ack_lost_causes_double_commit_rejected"
    verifier = _RetryVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0"})
    verifier.send(0, "n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0"})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0", "retry": True})
    verifier.send(0, "n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0", "retry": True})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "ack", "nonce": "n0"})
    verifier.ack("n0")
    transcript.append({"op": "finalize"})
    verifier.finalize()

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: ack lost; receiver commits the same nonce a second time on retry, violating commit-once",
    )


def run_timeout_shorter_than_response_causes_orphan_rejected(work: Path) -> dict[str, Any]:
    case_id = "timeout_shorter_than_response_causes_orphan_rejected"
    verifier = _RetryVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "send", "chunk_index": 0, "nonce": "n0"})
    verifier.send(0, "n0")
    transcript.append({"op": "timeout", "nonce": "n0"})
    verifier.timeout("n0")
    transcript.append({"op": "receive_commit", "chunk_index": 0, "nonce": "n0", "late": True})
    verifier.receive_commit(0, "n0")
    transcript.append({"op": "finalize"})
    verifier.finalize()

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender times out chunk 0; slow receiver later commits the timed-out nonce, producing an orphan",
    )


CASE_RUNNERS = {
    "clean_retry_round_trip_passes": run_clean_retry_round_trip_passes,
    "retry_without_nonce_dedup_rejected": run_retry_without_nonce_dedup_rejected,
    "partial_flush_on_network_drop_rejected": run_partial_flush_on_network_drop_rejected,
    "ack_lost_causes_double_commit_rejected": run_ack_lost_causes_double_commit_rejected,
    "timeout_shorter_than_response_causes_orphan_rejected": run_timeout_shorter_than_response_causes_orphan_rejected,
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
            "Remote-transfer network retry idempotency is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix network retry idempotency blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-network-retry-idempotency-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-network-retry-idempotency-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
