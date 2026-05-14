#!/usr/bin/env python3
"""Remote-transfer concurrent transfer collision gate.

Synthesizes the AO Runtime ``concurrent_transfer_collision`` contract
as a local Python state machine and proves each multi-writer
collision hazard is fail-closed by injecting deliberate mutations
against an in-process lock / write_chunk / finalize / release_lock /
lock_expire pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_serialized_concurrent_transfers_passes`` — control: writer
  A acquires the bundle lock, writes its chunks, finalizes, and
  releases; writer B then takes the lock and writes its own chunks.
  Lock ownership is honored end-to-end and finalize occurs exactly
  once per writer turn.
* ``parallel_transfers_no_lock_corrupts_state_rejected`` — mutation:
  both writers skip lock acquisition and interleave writes against
  the same bundle, producing a chunk register with mixed authorship.
* ``simultaneous_finalize_double_completes_bundle_rejected`` —
  mutation: writer A holds the lock and finalizes; writer B
  finalizes the same bundle as well, racing two completion writes.
* ``lost_writer_overwrites_winner_bundle_rejected`` — mutation:
  writer A wins the lock; writer B writes a chunk to the same bundle
  without checking the current lock holder, overwriting the winner.
* ``stale_lock_holder_resumes_after_handoff_rejected`` — mutation:
  writer A's lock expires (lock_expire), writer B takes the lock and
  writes; writer A then returns and continues writing as if it still
  owned the bundle.

Every case lays down a per-case collision transcript in a temporary
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
    "remote-transfer-concurrent-transfer-collision.json"
)
SCHEMA = "ao-operator/remote-transfer-concurrent-transfer-collision/v1"

CASE_IDS = (
    "clean_serialized_concurrent_transfers_passes",
    "parallel_transfers_no_lock_corrupts_state_rejected",
    "simultaneous_finalize_double_completes_bundle_rejected",
    "lost_writer_overwrites_winner_bundle_rejected",
    "stale_lock_holder_resumes_after_handoff_rejected",
)

EXPECTED_VERDICTS = {
    "clean_serialized_concurrent_transfers_passes": "PASS",
    "parallel_transfers_no_lock_corrupts_state_rejected": "FAIL",
    "simultaneous_finalize_double_completes_bundle_rejected": "FAIL",
    "lost_writer_overwrites_winner_bundle_rejected": "FAIL",
    "stale_lock_holder_resumes_after_handoff_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _CollisionVerifier:
    """In-memory concurrent-transfer collision state machine.

    Models the AO Runtime ``concurrent_transfer_collision`` pipeline:
    multiple writers attempt to upload chunks to the same bundle_id,
    serialized through a per-bundle lock, terminated by finalize, and
    the verifier enforces five distilled concurrency invariants:

    1. ``write_chunk`` requires the calling writer to be the current
       lock holder (lock-required-for-write invariant).
    2. ``finalize`` requires the calling writer to be the current
       lock holder (lock-required-for-finalize invariant).
    3. A chunk_index in a given bundle MUST NOT be overwritten by a
       different writer than the one that first wrote it
       (no-overwrite invariant).
    4. ``finalize`` MUST be called at most once per bundle until the
       bundle is reset (finalize-once invariant).
    5. After ``lock_expire`` (or release_lock) for writer X, X MUST
       NOT continue to write or finalize without re-acquiring the
       lock (no-stale-lock-holder invariant).
    """

    def __init__(self) -> None:
        self.lock_holder: str | None = None
        self.expired_writers: set[str] = set()
        self.chunk_owner: dict[int, str] = {}
        self.finalized_writers: set[str] = set()
        self.bundle_finalized: bool = False
        self.errors: list[str] = []

    def acquire_lock(self, writer_id: str) -> None:
        if self.lock_holder is not None and self.lock_holder != writer_id:
            self.errors.append(
                f"acquire_lock_while_held:requested_by={writer_id},current_holder={self.lock_holder}"
            )
            return
        self.lock_holder = writer_id
        self.expired_writers.discard(writer_id)

    def write_chunk(self, writer_id: str, chunk_index: int) -> None:
        if writer_id in self.expired_writers and self.lock_holder != writer_id:
            self.errors.append(
                f"stale_lock_holder_write:writer={writer_id},chunk_index={chunk_index},current_holder={self.lock_holder}"
            )
            return
        if self.lock_holder != writer_id:
            self.errors.append(
                f"write_without_lock:writer={writer_id},chunk_index={chunk_index},current_holder={self.lock_holder}"
            )
            return
        prior_owner = self.chunk_owner.get(chunk_index)
        if prior_owner is not None and prior_owner != writer_id:
            self.errors.append(
                f"chunk_overwrite_by_other_writer:chunk_index={chunk_index},prior_owner={prior_owner},new_writer={writer_id}"
            )
            return
        self.chunk_owner[chunk_index] = writer_id

    def finalize(self, writer_id: str) -> None:
        if writer_id in self.expired_writers and self.lock_holder != writer_id:
            self.errors.append(
                f"stale_lock_holder_finalize:writer={writer_id},current_holder={self.lock_holder}"
            )
            return
        if self.lock_holder != writer_id:
            self.errors.append(
                f"finalize_without_lock:writer={writer_id},current_holder={self.lock_holder}"
            )
            return
        if self.bundle_finalized:
            self.errors.append(
                f"double_finalize:writer={writer_id}"
            )
            return
        self.bundle_finalized = True
        self.finalized_writers.add(writer_id)

    def release_lock(self, writer_id: str) -> None:
        if self.lock_holder != writer_id:
            self.errors.append(
                f"release_without_holding:writer={writer_id},current_holder={self.lock_holder}"
            )
            return
        self.lock_holder = None
        self.bundle_finalized = False
        self.chunk_owner.clear()

    def lock_expire(self, writer_id: str) -> None:
        if self.lock_holder == writer_id:
            self.lock_holder = None
        self.expired_writers.add(writer_id)

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "collision-transcript.json").write_text(
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


def run_clean_serialized_concurrent_transfers_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_serialized_concurrent_transfers_passes"
    verifier = _CollisionVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "acquire_lock", "writer_id": "A"})
    verifier.acquire_lock("A")
    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 0})
    verifier.write_chunk("A", 0)
    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 1})
    verifier.write_chunk("A", 1)
    transcript.append({"op": "finalize", "writer_id": "A"})
    verifier.finalize("A")
    transcript.append({"op": "release_lock", "writer_id": "A"})
    verifier.release_lock("A")

    transcript.append({"op": "acquire_lock", "writer_id": "B"})
    verifier.acquire_lock("B")
    transcript.append({"op": "write_chunk", "writer_id": "B", "chunk_index": 0})
    verifier.write_chunk("B", 0)
    transcript.append({"op": "write_chunk", "writer_id": "B", "chunk_index": 1})
    verifier.write_chunk("B", 1)
    transcript.append({"op": "finalize", "writer_id": "B"})
    verifier.finalize("B")
    transcript.append({"op": "release_lock", "writer_id": "B"})
    verifier.release_lock("B")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: writer A acquires lock, writes/finalizes/releases; "
            "writer B then acquires the same bundle lock and serially performs "
            "its own write/finalize/release; no overwrite, no double finalize"
        ),
    )


def run_parallel_transfers_no_lock_corrupts_state_rejected(work: Path) -> dict[str, Any]:
    case_id = "parallel_transfers_no_lock_corrupts_state_rejected"
    verifier = _CollisionVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 0, "no_lock": True})
    verifier.write_chunk("A", 0)
    transcript.append({"op": "write_chunk", "writer_id": "B", "chunk_index": 1, "no_lock": True})
    verifier.write_chunk("B", 1)
    transcript.append({"op": "finalize", "writer_id": "A", "no_lock": True})
    verifier.finalize("A")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: both writers skip lock acquisition and write/finalize against the same bundle in parallel",
    )


def run_simultaneous_finalize_double_completes_bundle_rejected(work: Path) -> dict[str, Any]:
    case_id = "simultaneous_finalize_double_completes_bundle_rejected"
    verifier = _CollisionVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "acquire_lock", "writer_id": "A"})
    verifier.acquire_lock("A")
    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 0})
    verifier.write_chunk("A", 0)
    transcript.append({"op": "finalize", "writer_id": "A"})
    verifier.finalize("A")
    transcript.append({"op": "finalize_race", "writer_id": "B"})
    verifier.finalize("B")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: writer A finalizes; writer B finalizes the same bundle without holding the lock, racing completion",
    )


def run_lost_writer_overwrites_winner_bundle_rejected(work: Path) -> dict[str, Any]:
    case_id = "lost_writer_overwrites_winner_bundle_rejected"
    verifier = _CollisionVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "acquire_lock", "writer_id": "A"})
    verifier.acquire_lock("A")
    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 0})
    verifier.write_chunk("A", 0)
    transcript.append({"op": "write_chunk_unlocked", "writer_id": "B", "chunk_index": 0})
    verifier.write_chunk("B", 0)
    transcript.append({"op": "finalize", "writer_id": "A"})
    verifier.finalize("A")
    transcript.append({"op": "release_lock", "writer_id": "A"})
    verifier.release_lock("A")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: writer B writes the same chunk_index without checking the lock holder, overwriting writer A",
    )


def run_stale_lock_holder_resumes_after_handoff_rejected(work: Path) -> dict[str, Any]:
    case_id = "stale_lock_holder_resumes_after_handoff_rejected"
    verifier = _CollisionVerifier()
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "acquire_lock", "writer_id": "A"})
    verifier.acquire_lock("A")
    transcript.append({"op": "write_chunk", "writer_id": "A", "chunk_index": 0})
    verifier.write_chunk("A", 0)
    transcript.append({"op": "lock_expire", "writer_id": "A"})
    verifier.lock_expire("A")
    transcript.append({"op": "acquire_lock", "writer_id": "B"})
    verifier.acquire_lock("B")
    transcript.append({"op": "write_chunk", "writer_id": "B", "chunk_index": 1})
    verifier.write_chunk("B", 1)
    transcript.append({"op": "stale_resume_write", "writer_id": "A", "chunk_index": 2})
    verifier.write_chunk("A", 2)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: writer A's lock expires; writer B takes over; writer A returns and writes as if it still held the lock",
    )


CASE_RUNNERS = {
    "clean_serialized_concurrent_transfers_passes": run_clean_serialized_concurrent_transfers_passes,
    "parallel_transfers_no_lock_corrupts_state_rejected": run_parallel_transfers_no_lock_corrupts_state_rejected,
    "simultaneous_finalize_double_completes_bundle_rejected": run_simultaneous_finalize_double_completes_bundle_rejected,
    "lost_writer_overwrites_winner_bundle_rejected": run_lost_writer_overwrites_winner_bundle_rejected,
    "stale_lock_holder_resumes_after_handoff_rejected": run_stale_lock_holder_resumes_after_handoff_rejected,
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
            "Remote-transfer concurrent transfer collision is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix concurrent transfer collision blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-concurrent-transfer-collision-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-concurrent-transfer-collision-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
