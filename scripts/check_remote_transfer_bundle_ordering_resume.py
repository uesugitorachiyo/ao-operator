#!/usr/bin/env python3
"""Remote-transfer bundle ordering & resume gate.

Synthesizes the AO Runtime ``streaming_bundle_delivery`` ordering and
resume contract as a local Python state machine and proves each
streaming/resume violation is fail-closed by injecting deliberate
mutations against an in-process delivery verifier.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_ordered_delivery_passes`` — control: all chunks delivered in
  strict ascending order, cursor advances exactly once per chunk,
  high-water reaches ``total_chunks`` at finalize.
* ``out_of_order_chunk_rejected`` — mutation: chunk 1 is delivered
  after chunk 2; the cursor invariant must reject the early arrival.
* ``partial_resume_drops_middle_chunk_rejected`` — mutation: after
  chunks 0,1,2 a resume reconnects with cursor=3 but the next chunk
  delivered is index 4. The gap invariant must reject.
* ``resume_cursor_lies_about_high_water_rejected`` — mutation: a
  resume request claims ``cursor=3`` but the delivered ledger only
  confirms 0,1. The high-water invariant must reject the forward
  lie.
* ``duplicate_chunk_delivery_rejected`` — mutation: chunk 1 is
  delivered twice in a row; the cursor invariant must reject the
  second presentation.

Every case lays down a per-case delivery transcript in a temporary
work directory, runs it through the verifier embedded in this gate,
and records ``observed_verdict``. The gate's overall verdict is
``PASS`` only when every case lines up with the expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-bundle-ordering-resume.json"
)
SCHEMA = "ao-operator/remote-transfer-bundle-ordering-resume/v1"

CASE_IDS = (
    "clean_ordered_delivery_passes",
    "out_of_order_chunk_rejected",
    "partial_resume_drops_middle_chunk_rejected",
    "resume_cursor_lies_about_high_water_rejected",
    "duplicate_chunk_delivery_rejected",
)

EXPECTED_VERDICTS = {
    "clean_ordered_delivery_passes": "PASS",
    "out_of_order_chunk_rejected": "FAIL",
    "partial_resume_drops_middle_chunk_rejected": "FAIL",
    "resume_cursor_lies_about_high_water_rejected": "FAIL",
    "duplicate_chunk_delivery_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class _DeliveryVerifier:
    """In-memory streaming-delivery state machine.

    Models the AO Runtime ``streaming_bundle_delivery`` cursor: the
    receiver tracks the next expected chunk index and a ledger of
    confirmed deliveries. Any out-of-order chunk, gap, duplicate, or
    forward-lying resume cursor is rejected fail-closed.
    """

    def __init__(self, *, total_chunks: int) -> None:
        self.total_chunks = total_chunks
        self.delivered: dict[int, str] = {}
        self.cursor = 0
        self.errors: list[str] = []

    def deliver(self, *, index: int, payload: bytes) -> None:
        if index != self.cursor:
            self.errors.append(
                f"out_of_order_chunk:expected={self.cursor},received={index}"
            )
            return
        if index in self.delivered:
            self.errors.append(f"duplicate_chunk:index={index}")
            return
        self.delivered[index] = _digest(payload)
        self.cursor = index + 1

    def resume(self, *, claimed_cursor: int) -> None:
        confirmed_high_water = (max(self.delivered) + 1) if self.delivered else 0
        if claimed_cursor > confirmed_high_water:
            self.errors.append(
                f"resume_cursor_exceeds_confirmed_high_water:claimed={claimed_cursor},confirmed={confirmed_high_water}"
            )
            return
        self.cursor = claimed_cursor

    def finalize(self) -> None:
        if self.cursor != self.total_chunks:
            self.errors.append(
                f"finalize_before_all_chunks_delivered:cursor={self.cursor},total={self.total_chunks}"
            )
        for i in range(self.total_chunks):
            if i not in self.delivered:
                self.errors.append(f"missing_chunk_at_finalize:index={i}")

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "delivery-transcript.json").write_text(
        json.dumps(transcript, indent=2), encoding="utf-8"
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


def _replay(verifier: _DeliveryVerifier, transcript: list[dict[str, Any]]) -> None:
    for op in transcript:
        kind = op["op"]
        if kind == "deliver":
            verifier.deliver(index=op["index"], payload=op["payload"].encode("utf-8"))
        elif kind == "resume":
            verifier.resume(claimed_cursor=op["claimed_cursor"])
        elif kind == "finalize":
            verifier.finalize()


def run_clean_ordered_delivery_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_ordered_delivery_passes"
    transcript = [
        {"op": "deliver", "index": 0, "payload": "chunk-zero"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "deliver", "index": 2, "payload": "chunk-two"},
        {"op": "deliver", "index": 3, "payload": "chunk-three"},
        {"op": "finalize"},
    ]
    _persist_case(work, case_id, transcript)
    verifier = _DeliveryVerifier(total_chunks=4)
    _replay(verifier, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="control: 4 chunks delivered in strict ascending order; finalize at high-water=4",
    )


def run_out_of_order_chunk_rejected(work: Path) -> dict[str, Any]:
    case_id = "out_of_order_chunk_rejected"
    transcript = [
        {"op": "deliver", "index": 0, "payload": "chunk-zero"},
        {"op": "deliver", "index": 2, "payload": "chunk-two"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "deliver", "index": 3, "payload": "chunk-three"},
        {"op": "finalize"},
    ]
    _persist_case(work, case_id, transcript)
    verifier = _DeliveryVerifier(total_chunks=4)
    _replay(verifier, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: chunk-2 arrives before chunk-1; cursor invariant rejects",
    )


def run_partial_resume_drops_middle_chunk_rejected(work: Path) -> dict[str, Any]:
    case_id = "partial_resume_drops_middle_chunk_rejected"
    transcript = [
        {"op": "deliver", "index": 0, "payload": "chunk-zero"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "deliver", "index": 2, "payload": "chunk-two"},
        {"op": "resume", "claimed_cursor": 3},
        {"op": "deliver", "index": 4, "payload": "chunk-four"},
        {"op": "finalize"},
    ]
    _persist_case(work, case_id, transcript)
    verifier = _DeliveryVerifier(total_chunks=5)
    _replay(verifier, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: resume at cursor=3 then deliver index=4 — chunk-3 dropped; gap invariant rejects",
    )


def run_resume_cursor_lies_about_high_water_rejected(work: Path) -> dict[str, Any]:
    case_id = "resume_cursor_lies_about_high_water_rejected"
    transcript = [
        {"op": "deliver", "index": 0, "payload": "chunk-zero"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "resume", "claimed_cursor": 3},
        {"op": "deliver", "index": 3, "payload": "chunk-three"},
        {"op": "finalize"},
    ]
    _persist_case(work, case_id, transcript)
    verifier = _DeliveryVerifier(total_chunks=4)
    _replay(verifier, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: resume claims cursor=3 with confirmed high-water=2; high-water invariant rejects",
    )


def run_duplicate_chunk_delivery_rejected(work: Path) -> dict[str, Any]:
    case_id = "duplicate_chunk_delivery_rejected"
    transcript = [
        {"op": "deliver", "index": 0, "payload": "chunk-zero"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "deliver", "index": 1, "payload": "chunk-one"},
        {"op": "deliver", "index": 2, "payload": "chunk-two"},
        {"op": "deliver", "index": 3, "payload": "chunk-three"},
        {"op": "finalize"},
    ]
    _persist_case(work, case_id, transcript)
    verifier = _DeliveryVerifier(total_chunks=4)
    _replay(verifier, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: chunk-1 redelivered after cursor advanced to 2; cursor invariant rejects",
    )


CASE_RUNNERS = {
    "clean_ordered_delivery_passes": run_clean_ordered_delivery_passes,
    "out_of_order_chunk_rejected": run_out_of_order_chunk_rejected,
    "partial_resume_drops_middle_chunk_rejected": run_partial_resume_drops_middle_chunk_rejected,
    "resume_cursor_lies_about_high_water_rejected": run_resume_cursor_lies_about_high_water_rejected,
    "duplicate_chunk_delivery_rejected": run_duplicate_chunk_delivery_rejected,
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
            "Remote-transfer bundle ordering & resume modes are locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix bundle ordering/resume invariant blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-ordering-resume-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-ordering-resume-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
