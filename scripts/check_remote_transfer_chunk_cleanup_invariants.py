#!/usr/bin/env python3
"""Remote-transfer chunk-cleanup invariants gate.

Synthesizes the AO Runtime ``chunked_upload`` cleanup contract (Phase
2b/3 evidence ``chunked-upload-validation-20260506T233808Z.md``) as a
local Python state machine and proves that each cleanup invariant is
fail-closed by injecting deliberate mutations.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_upload_commit_passes`` — control: an upload that completes
  cleanly leaves the stage dir empty after finalize.
* ``orphaned_chunk_after_abort_detected`` — mutation: an aborted upload
  leaves a chunk file on disk; the invariant must reject it.
* ``missing_finalize_detected`` — mutation: chunks uploaded but
  ``CommitWorkspaceUpload`` never called; the invariant must reject it
  because the partial stage would never be reaped.
* ``stale_partial_stage_dir_detected`` — mutation: a leftover
  partial-stage marker from a prior aborted upload is still present
  when a new upload begins.
* ``double_commit_rejected`` — mutation: ``CommitWorkspaceUpload``
  invoked twice for the same upload id; idempotency violation.
* ``retry_index_drift_detected`` — mutation: the failed-chunk index
  reported to the client differs from the actual failed chunk; retry
  pointer drift.

Every case lays down an on-disk staging tree under the work directory,
populates an in-memory session record, and runs the invariant validator
embedded in this gate. The case-level ``observed_verdict`` is then
compared against the expected verdict; the gate's overall verdict is
``PASS`` only when every case lines up.

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
    "remote-transfer-chunk-cleanup-invariants.json"
)
SCHEMA = "ao-operator/remote-transfer-chunk-cleanup-invariants/v1"

CASE_IDS = (
    "clean_upload_commit_passes",
    "orphaned_chunk_after_abort_detected",
    "missing_finalize_detected",
    "stale_partial_stage_dir_detected",
    "double_commit_rejected",
    "retry_index_drift_detected",
)

EXPECTED_VERDICTS = {
    "clean_upload_commit_passes": "PASS",
    "orphaned_chunk_after_abort_detected": "FAIL",
    "missing_finalize_detected": "FAIL",
    "stale_partial_stage_dir_detected": "FAIL",
    "double_commit_rejected": "FAIL",
    "retry_index_drift_detected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _stage_dir(work: Path, case_id: str) -> Path:
    stage = work / case_id
    stage.mkdir(parents=True, exist_ok=True)
    return stage


def _chunk_path(stage: Path, upload_id: str, index: int) -> Path:
    return stage / f"{upload_id}-chunk-{index:04d}.bin"


def _partial_marker(stage: Path, upload_id: str) -> Path:
    return stage / f"partial-stage-{upload_id}.marker"


def _validate(session: dict[str, Any], stage: Path) -> tuple[str, list[str]]:
    """Return (verdict, errors) for a chunk-upload session against its stage dir.

    The validator enforces six invariants distilled from the AO Runtime
    chunked_upload Phase 2b/3 evidence: no orphaned chunk after abort,
    finalize required after successful chunks, single-commit, no stale
    partial-stage markers from prior uploads, retry index must match the
    failed chunk, and a successful finalize must leave the stage clean.
    """
    errors: list[str] = []
    upload_id = session["upload_id"]
    aborted = bool(session["aborted"])
    finalize_count = int(session["finalize_count"])
    chunks_uploaded = list(session["chunks_uploaded"])
    last_failed = session.get("last_failed_chunk_index")
    expected_failed = session.get("expected_failed_chunk_index")

    if not stage.exists():
        return ("FAIL", ["stage_dir_missing"])

    chunk_files = sorted(p.name for p in stage.iterdir() if p.is_file() and p.name.startswith(f"{upload_id}-chunk-"))
    foreign_markers = sorted(
        p.name
        for p in stage.iterdir()
        if p.is_file()
        and p.name.startswith("partial-stage-")
        and not p.name.startswith(f"partial-stage-{upload_id}.")
    )

    if aborted and chunk_files:
        errors.append(f"orphaned_chunks_after_abort:{chunk_files}")

    if not aborted and chunks_uploaded and finalize_count == 0:
        errors.append("missing_finalize_after_successful_chunks")

    if finalize_count > 1:
        errors.append(f"double_commit:finalize_count={finalize_count}")

    if foreign_markers:
        errors.append(f"stale_partial_stage_dir:{foreign_markers}")

    if last_failed is not None and expected_failed is not None and last_failed != expected_failed:
        errors.append(
            f"retry_index_drift:reported={last_failed},expected={expected_failed}"
        )

    if finalize_count == 1 and not aborted and not errors:
        leftover = sorted(p.name for p in stage.iterdir())
        if leftover:
            errors.append(f"unclean_stage_after_finalize:{leftover}")

    return ("PASS" if not errors else "FAIL", errors)


def _case_summary(
    case_id: str,
    *,
    observed_verdict: str,
    chunk_count: int,
    aborted: bool,
    finalize_count: int,
    observed_errors: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "chunk_count": chunk_count,
        "aborted": aborted,
        "finalize_count": finalize_count,
        "observed_errors": observed_errors,
        "detail": detail,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def run_clean_upload_commit_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_upload_commit_passes"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-001"
    chunk_count = 3
    for i in range(chunk_count):
        _chunk_path(stage, upload_id, i).write_bytes(b"chunk-" + bytes([i]))
    for i in range(chunk_count):
        _chunk_path(stage, upload_id, i).unlink()
    session = {
        "upload_id": upload_id,
        "aborted": False,
        "finalize_count": 1,
        "chunks_uploaded": list(range(chunk_count)),
        "last_failed_chunk_index": None,
        "expected_failed_chunk_index": None,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=chunk_count,
        aborted=False,
        finalize_count=1,
        observed_errors=errors,
        detail="control: full-cycle commit reaps all chunks",
    )


def run_orphaned_chunk_after_abort_detected(work: Path) -> dict[str, Any]:
    case_id = "orphaned_chunk_after_abort_detected"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-002"
    chunk_count = 3
    for i in range(chunk_count):
        _chunk_path(stage, upload_id, i).write_bytes(b"chunk")
    _chunk_path(stage, upload_id, 0).unlink()
    _chunk_path(stage, upload_id, 1).unlink()
    session = {
        "upload_id": upload_id,
        "aborted": True,
        "finalize_count": 0,
        "chunks_uploaded": [0, 1, 2],
        "last_failed_chunk_index": None,
        "expected_failed_chunk_index": None,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=chunk_count,
        aborted=True,
        finalize_count=0,
        observed_errors=errors,
        detail="mutation: chunk-2 leaks past abort and is detected",
    )


def run_missing_finalize_detected(work: Path) -> dict[str, Any]:
    case_id = "missing_finalize_detected"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-003"
    chunk_count = 2
    session = {
        "upload_id": upload_id,
        "aborted": False,
        "finalize_count": 0,
        "chunks_uploaded": [0, 1],
        "last_failed_chunk_index": None,
        "expected_failed_chunk_index": None,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=chunk_count,
        aborted=False,
        finalize_count=0,
        observed_errors=errors,
        detail="mutation: chunks accepted but CommitWorkspaceUpload never invoked",
    )


def run_stale_partial_stage_dir_detected(work: Path) -> dict[str, Any]:
    case_id = "stale_partial_stage_dir_detected"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-004"
    _partial_marker(stage, "upload-stale-prior").write_text("orphaned", encoding="utf-8")
    session = {
        "upload_id": upload_id,
        "aborted": False,
        "finalize_count": 1,
        "chunks_uploaded": [0],
        "last_failed_chunk_index": None,
        "expected_failed_chunk_index": None,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=1,
        aborted=False,
        finalize_count=1,
        observed_errors=errors,
        detail="mutation: leftover partial-stage marker from prior aborted upload",
    )


def run_double_commit_rejected(work: Path) -> dict[str, Any]:
    case_id = "double_commit_rejected"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-005"
    session = {
        "upload_id": upload_id,
        "aborted": False,
        "finalize_count": 2,
        "chunks_uploaded": [0, 1],
        "last_failed_chunk_index": None,
        "expected_failed_chunk_index": None,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=2,
        aborted=False,
        finalize_count=2,
        observed_errors=errors,
        detail="mutation: same upload id committed twice; idempotency violation",
    )


def run_retry_index_drift_detected(work: Path) -> dict[str, Any]:
    case_id = "retry_index_drift_detected"
    stage = _stage_dir(work, case_id)
    upload_id = "upload-006"
    session = {
        "upload_id": upload_id,
        "aborted": True,
        "finalize_count": 0,
        "chunks_uploaded": [0, 1],
        "last_failed_chunk_index": 0,
        "expected_failed_chunk_index": 2,
    }
    verdict, errors = _validate(session, stage)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=3,
        aborted=True,
        finalize_count=0,
        observed_errors=errors,
        detail="mutation: chunk-2 hash mismatch but retry index reports chunk-0",
    )


CASE_RUNNERS = {
    "clean_upload_commit_passes": run_clean_upload_commit_passes,
    "orphaned_chunk_after_abort_detected": run_orphaned_chunk_after_abort_detected,
    "missing_finalize_detected": run_missing_finalize_detected,
    "stale_partial_stage_dir_detected": run_stale_partial_stage_dir_detected,
    "double_commit_rejected": run_double_commit_rejected,
    "retry_index_drift_detected": run_retry_index_drift_detected,
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
            "Remote-transfer chunk-cleanup invariants are locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix chunk-cleanup invariant blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-chunk-cleanup-invariants-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-chunk-cleanup-invariants-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
