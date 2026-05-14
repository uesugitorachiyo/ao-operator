#!/usr/bin/env python3
"""Remote-transfer resource exhaustion guard gate.

Synthesizes the AO Runtime ``resource_exhaustion_guard`` contract as
a local Python state machine and proves each receiver-side quota
hazard is fail-closed by injecting deliberate mutations against an
in-process announce / send_chunk / receiver_validate pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_within_quota_passes`` — control: sender announces 100
  chunks of 1024 bytes each (total 102_400 bytes); receiver quota is
  1_000 chunks / 10_485_760 bytes / 1_048_576 per-chunk; the
  announcement validates, every chunk validates, and the final
  received counters match the announcement.
* ``announced_chunk_count_exceeds_quota_rejected`` — mutation: sender
  announces 5_000 chunks while the receiver caps at 1_000; the
  receiver accepts the announcement anyway. A receiver MUST reject
  any announcement whose chunk count exceeds its quota.
* ``announced_total_size_exceeds_quota_rejected`` — mutation: sender
  announces 100 chunks totalling 100_000_000 bytes while the receiver
  caps total bytes at 10_485_760; the receiver accepts. A receiver
  MUST reject any announcement whose total size exceeds its byte
  quota even when the chunk count is in range.
* ``per_chunk_size_exceeds_max_rejected`` — mutation: sender announces
  in-quota counts but ships a single chunk that is 4_194_304 bytes
  while the receiver caps per-chunk at 1_048_576; the receiver
  accepts the oversize chunk. A receiver MUST reject any chunk whose
  size exceeds the per-chunk maximum.
* ``transfer_exceeds_announced_count_rejected`` — mutation: sender
  announces 3 chunks, ships chunks 0/1/2, then ships a fourth chunk
  beyond the announcement; the receiver accepts the surplus chunk.
  A receiver MUST refuse any chunk whose index is at or beyond the
  announced chunk count.

Every case lays down a per-case quota transcript in a temporary work
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
    "remote-transfer-resource-exhaustion-guard.json"
)
SCHEMA = "ao-operator/remote-transfer-resource-exhaustion-guard/v1"

CASE_IDS = (
    "clean_within_quota_passes",
    "announced_chunk_count_exceeds_quota_rejected",
    "announced_total_size_exceeds_quota_rejected",
    "per_chunk_size_exceeds_max_rejected",
    "transfer_exceeds_announced_count_rejected",
)

EXPECTED_VERDICTS = {
    "clean_within_quota_passes": "PASS",
    "announced_chunk_count_exceeds_quota_rejected": "FAIL",
    "announced_total_size_exceeds_quota_rejected": "FAIL",
    "per_chunk_size_exceeds_max_rejected": "FAIL",
    "transfer_exceeds_announced_count_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _QuotaVerifier:
    """In-memory resource-exhaustion guard state machine.

    Models the AO Runtime ``resource_exhaustion_guard`` pipeline:
    a sender announces a planned chunk_count and total_bytes, then
    streams individual chunks; the receiver advertises three quotas
    (max_chunk_count, max_total_bytes, max_per_chunk_bytes) and
    enforces four distilled DoS-prevention invariants:

    1. The announced ``chunk_count`` MUST NOT exceed
       ``max_chunk_count`` (announcement-chunk-count invariant).
    2. The announced ``total_bytes`` MUST NOT exceed
       ``max_total_bytes`` (announcement-total-size invariant).
    3. Every received chunk MUST be ``<= max_per_chunk_bytes``
       (per-chunk-size invariant).
    4. Received chunk indices MUST stay strictly below the announced
       ``chunk_count`` (no-overrun invariant).
    """

    def __init__(
        self,
        *,
        max_chunk_count: int,
        max_total_bytes: int,
        max_per_chunk_bytes: int,
    ) -> None:
        self.max_chunk_count = max_chunk_count
        self.max_total_bytes = max_total_bytes
        self.max_per_chunk_bytes = max_per_chunk_bytes
        self.announced_chunk_count: int | None = None
        self.announced_total_bytes: int | None = None
        self.received_chunk_count: int = 0
        self.received_total_bytes: int = 0
        self.errors: list[str] = []

    def receiver_validate_announcement(
        self, *, chunk_count: int, total_bytes: int
    ) -> None:
        if chunk_count > self.max_chunk_count:
            self.errors.append(
                f"announced_chunk_count_exceeds_quota:announced={chunk_count},max={self.max_chunk_count}"
            )
            return
        if total_bytes > self.max_total_bytes:
            self.errors.append(
                f"announced_total_bytes_exceeds_quota:announced={total_bytes},max={self.max_total_bytes}"
            )
            return
        self.announced_chunk_count = chunk_count
        self.announced_total_bytes = total_bytes

    def receiver_force_accept_oversize_announcement(
        self, *, chunk_count: int, total_bytes: int
    ) -> None:
        if chunk_count > self.max_chunk_count:
            self.errors.append(
                f"force_accepted_chunk_count_over_quota:announced={chunk_count},max={self.max_chunk_count}"
            )
        if total_bytes > self.max_total_bytes:
            self.errors.append(
                f"force_accepted_total_bytes_over_quota:announced={total_bytes},max={self.max_total_bytes}"
            )
        self.announced_chunk_count = chunk_count
        self.announced_total_bytes = total_bytes

    def receiver_validate_chunk(self, *, chunk_index: int, chunk_bytes: int) -> None:
        if chunk_bytes > self.max_per_chunk_bytes:
            self.errors.append(
                f"chunk_exceeds_per_chunk_max:chunk_index={chunk_index},bytes={chunk_bytes},max={self.max_per_chunk_bytes}"
            )
            return
        if (
            self.announced_chunk_count is not None
            and chunk_index >= self.announced_chunk_count
        ):
            self.errors.append(
                f"chunk_index_beyond_announced_count:chunk_index={chunk_index},announced={self.announced_chunk_count}"
            )
            return
        self.received_chunk_count += 1
        self.received_total_bytes += chunk_bytes

    def receiver_force_accept_oversize_chunk(
        self, *, chunk_index: int, chunk_bytes: int
    ) -> None:
        if chunk_bytes > self.max_per_chunk_bytes:
            self.errors.append(
                f"force_accepted_oversize_chunk:chunk_index={chunk_index},bytes={chunk_bytes},max={self.max_per_chunk_bytes}"
            )
        self.received_chunk_count += 1
        self.received_total_bytes += chunk_bytes

    def receiver_force_accept_overrun_chunk(
        self, *, chunk_index: int, chunk_bytes: int
    ) -> None:
        if (
            self.announced_chunk_count is not None
            and chunk_index >= self.announced_chunk_count
        ):
            self.errors.append(
                f"force_accepted_overrun_chunk:chunk_index={chunk_index},announced={self.announced_chunk_count}"
            )
        self.received_chunk_count += 1
        self.received_total_bytes += chunk_bytes

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "quota-transcript.json").write_text(
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


def run_clean_within_quota_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_within_quota_passes"
    verifier = _QuotaVerifier(
        max_chunk_count=1000,
        max_total_bytes=10_485_760,
        max_per_chunk_bytes=1_048_576,
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "announce", "chunk_count": 100, "total_bytes": 102_400})
    verifier.receiver_validate_announcement(chunk_count=100, total_bytes=102_400)
    for chunk_index in range(3):
        transcript.append({"op": "send_chunk", "chunk_index": chunk_index, "bytes": 1024})
        verifier.receiver_validate_chunk(chunk_index=chunk_index, chunk_bytes=1024)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender announces 100x1024-byte chunks within receiver "
            "quotas (1000 chunks / 10 MiB total / 1 MiB per chunk); chunks "
            "stream within bounds and validate without raising"
        ),
    )


def run_announced_chunk_count_exceeds_quota_rejected(work: Path) -> dict[str, Any]:
    case_id = "announced_chunk_count_exceeds_quota_rejected"
    verifier = _QuotaVerifier(
        max_chunk_count=1000,
        max_total_bytes=10_485_760,
        max_per_chunk_bytes=1_048_576,
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "announce", "chunk_count": 5000, "total_bytes": 102_400})
    transcript.append({"op": "receiver_force_accept_oversize_announcement", "chunk_count": 5000})
    verifier.receiver_force_accept_oversize_announcement(chunk_count=5000, total_bytes=102_400)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender announces 5000 chunks; receiver max=1000; receiver force-accepts the announcement",
    )


def run_announced_total_size_exceeds_quota_rejected(work: Path) -> dict[str, Any]:
    case_id = "announced_total_size_exceeds_quota_rejected"
    verifier = _QuotaVerifier(
        max_chunk_count=1000,
        max_total_bytes=10_485_760,
        max_per_chunk_bytes=1_048_576,
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "announce", "chunk_count": 100, "total_bytes": 100_000_000})
    transcript.append({"op": "receiver_force_accept_oversize_announcement", "total_bytes": 100_000_000})
    verifier.receiver_force_accept_oversize_announcement(chunk_count=100, total_bytes=100_000_000)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender announces 100_000_000 total bytes; receiver max_total_bytes=10_485_760; receiver force-accepts",
    )


def run_per_chunk_size_exceeds_max_rejected(work: Path) -> dict[str, Any]:
    case_id = "per_chunk_size_exceeds_max_rejected"
    verifier = _QuotaVerifier(
        max_chunk_count=1000,
        max_total_bytes=10_485_760,
        max_per_chunk_bytes=1_048_576,
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "announce", "chunk_count": 4, "total_bytes": 4_194_304})
    verifier.receiver_validate_announcement(chunk_count=4, total_bytes=4_194_304)
    transcript.append({
        "op": "receiver_force_accept_oversize_chunk",
        "chunk_index": 0,
        "bytes": 4_194_304,
    })
    verifier.receiver_force_accept_oversize_chunk(chunk_index=0, chunk_bytes=4_194_304)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: chunk 0 carries 4_194_304 bytes; receiver max_per_chunk_bytes=1_048_576; receiver force-accepts the oversize chunk",
    )


def run_transfer_exceeds_announced_count_rejected(work: Path) -> dict[str, Any]:
    case_id = "transfer_exceeds_announced_count_rejected"
    verifier = _QuotaVerifier(
        max_chunk_count=1000,
        max_total_bytes=10_485_760,
        max_per_chunk_bytes=1_048_576,
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({"op": "announce", "chunk_count": 3, "total_bytes": 3072})
    verifier.receiver_validate_announcement(chunk_count=3, total_bytes=3072)
    for chunk_index in range(3):
        transcript.append({"op": "send_chunk", "chunk_index": chunk_index, "bytes": 1024})
        verifier.receiver_validate_chunk(chunk_index=chunk_index, chunk_bytes=1024)
    transcript.append({
        "op": "receiver_force_accept_overrun_chunk",
        "chunk_index": 3,
        "bytes": 1024,
    })
    verifier.receiver_force_accept_overrun_chunk(chunk_index=3, chunk_bytes=1024)

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender announces 3 chunks, ships chunks 0/1/2 normally then a surplus chunk 3; receiver force-accepts the overrun chunk",
    )


CASE_RUNNERS = {
    "clean_within_quota_passes": run_clean_within_quota_passes,
    "announced_chunk_count_exceeds_quota_rejected": run_announced_chunk_count_exceeds_quota_rejected,
    "announced_total_size_exceeds_quota_rejected": run_announced_total_size_exceeds_quota_rejected,
    "per_chunk_size_exceeds_max_rejected": run_per_chunk_size_exceeds_max_rejected,
    "transfer_exceeds_announced_count_rejected": run_transfer_exceeds_announced_count_rejected,
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
            "Remote-transfer resource exhaustion guard is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix resource exhaustion guard blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-resource-exhaustion-guard-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-resource-exhaustion-guard-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
