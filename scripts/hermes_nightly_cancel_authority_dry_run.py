#!/usr/bin/env python3
"""Nightly cadence wrapper around the AO2 watchdog cancel-authority dry-run.

The Phase 2 exit-gate #5 cancel-authority dry-run script
(``scripts/ao2_watchdog_cancel_authority_dry_run.py``) verifies that the
producer ↔ consumer round trip still accepts a freshly-built
no-active-AO2-runs attestation against the live ``ao2`` binary. This
wrapper runs that dry-run on a weekly cadence from the Hermes nightly
loop, against an isolated tempdir, and writes one artifact recording
the outcome (or the reason it was skipped) to ``--out-path``.

The wrapper never touches the live launchd loop, never reads or writes
the watchdog runtime directory directly (the dry-run uses a fresh
tempdir that is cleaned up before returning), and emits a single
JSON file at ``--out-path`` whose schema is
``ao-operator/hermes-nightly-cancel-authority-dry-run/v1``.

Status values:

- ``executed`` — cadence hit and the round trip ran. ``dry_run_evidence``
  holds the full ``ao-operator/ao2-watchdog-cancel-authority-dry-run/v1``
  evidence dict. ``accepted`` is true iff the watchdog returned
  ``accept_ao2_owns_watchdog_cancel``.
- ``skipped`` — cadence not hit (``mode=off`` or weekday mismatch in
  ``mode=auto``). ``skip_reason`` records why.
- ``binary_missing`` — ``--ao2-bin`` does not exist on disk.
- ``capture_failed`` — the live ``ao2 factory queue-list`` invocation
  failed (binary present but unusable).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ao2_watchdog_cancel_authority_dry_run as _dry_run  # noqa: E402

SCHEMA = "ao-operator/hermes-nightly-cancel-authority-dry-run/v1"
DRY_RUN_SCHEMA = _dry_run.DRY_RUN_SCHEMA
MODES: tuple[str, ...] = ("auto", "force", "off")
DEFAULT_MODE = "auto"
DEFAULT_WEEKDAY = 1  # ISO Monday
DEFAULT_ACTIVE_PID = 4242
DEFAULT_REASON = (
    "hermes-nightly-cancel-authority-dry-run "
    "(weekly cadence; never invokes the live launchd loop)"
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _write(path: Path, artifact: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_step(
    *,
    ao2_bin: Path,
    out_path: Path,
    active_pid: int = DEFAULT_ACTIVE_PID,
    reason: str = DEFAULT_REASON,
    mode: str = DEFAULT_MODE,
    weekday: int = DEFAULT_WEEKDAY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate cadence, run the dry-run when scheduled, write a single
    artifact to ``out_path``, and return the artifact dict.

    The actual cancel-authority round trip runs against a freshly-created
    tempdir; ``out_path`` only receives the summarised cadence artifact.
    """

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    weekday = int(weekday)
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday must be 1..7 (ISO); got {weekday}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    moment = now or _now_utc()
    observed = moment.isoweekday()

    base: dict[str, Any] = {
        "schema": SCHEMA,
        "dry_run_schema": DRY_RUN_SCHEMA,
        "mode": mode,
        "weekday_configured": weekday,
        "weekday_observed": observed,
        "now_iso": moment.isoformat(),
        "now_ms": int(moment.timestamp() * 1000),
        "active_pid": int(active_pid),
        "reason": reason,
        "ao2_bin": str(ao2_bin),
        "ao2_bin_exists": ao2_bin.exists(),
        "out_path": str(out_path),
        "dry_run_evidence": None,
        "outcome": None,
        "accepted": None,
        "skip_reason": None,
        "blockers": [],
    }

    if mode == "off":
        artifact = {**base, "status": "skipped", "skip_reason": "mode_off"}
        _write(out_path, artifact)
        return artifact

    if mode == "auto" and observed != weekday:
        artifact = {
            **base,
            "status": "skipped",
            "skip_reason": f"not_scheduled_weekday_iso{weekday}",
        }
        _write(out_path, artifact)
        return artifact

    if not ao2_bin.exists():
        artifact = {
            **base,
            "status": "binary_missing",
            "skip_reason": "ao2_bin_not_found",
            "blockers": [f"ao2_bin_not_found:{ao2_bin}"],
        }
        _write(out_path, artifact)
        return artifact

    with tempfile.TemporaryDirectory(
        prefix="hermes-nightly-cancel-authority-"
    ) as tmp:
        tmp_dir = Path(tmp)
        try:
            payload, source = _dry_run.capture_queue_list_live(ao2_bin)
        except _dry_run.LiveCaptureError as exc:
            artifact = {
                **base,
                "status": "capture_failed",
                "skip_reason": "ao2_queue_list_capture_failed",
                "blockers": [str(exc)],
            }
            _write(out_path, artifact)
            return artifact

        evidence = _dry_run.run_dry_run(
            queue_list_payload=payload,
            out_dir=tmp_dir,
            active_pid=int(active_pid),
            reason=reason,
            queue_list_source_label=source,
        )

    outcome = evidence.get("outcome")
    accepted = outcome == "accept_ao2_owns_watchdog_cancel"
    artifact = {
        **base,
        "status": "executed",
        "outcome": outcome,
        "accepted": accepted,
        "dry_run_evidence": evidence,
        "blockers": [] if accepted else [f"watchdog_outcome:{outcome}"],
    }
    _write(out_path, artifact)
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Nightly cadence wrapper around the cancel-authority dry-run. "
            "Runs the producer ↔ consumer round trip against a fresh "
            f"tempdir on a configured weekday and writes a single {SCHEMA} "
            "JSON artifact."
        )
    )
    parser.add_argument(
        "--ao2-bin",
        type=Path,
        required=True,
        help="Path to the ao2 release binary.",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        required=True,
        help="Destination JSON path for the nightly artifact.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default=DEFAULT_MODE,
        help=(
            "auto (default): run only on --weekday; "
            "force: always run when --ao2-bin is present; "
            "off: never run."
        ),
    )
    parser.add_argument(
        "--weekday",
        type=int,
        default=DEFAULT_WEEKDAY,
        help="ISO weekday 1..7 (Mon=1) on which to run when mode=auto.",
    )
    parser.add_argument(
        "--active-pid",
        type=int,
        default=DEFAULT_ACTIVE_PID,
        help="Synthetic active PID passed through to the dry-run script.",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help="Operator reason recorded on the dry-run attestation.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit 2 if status is capture_failed/binary_missing, or "
            "executed-but-not-accepted. The skipped status never trips "
            "--strict because skipping is the expected behaviour on "
            "non-cadence days."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact = run_step(
        ao2_bin=args.ao2_bin,
        out_path=args.out_path,
        active_pid=args.active_pid,
        reason=args.reason,
        mode=args.mode,
        weekday=args.weekday,
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    if args.strict:
        status = artifact["status"]
        if status in ("binary_missing", "capture_failed"):
            return 2
        if status == "executed" and not artifact["accepted"]:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
