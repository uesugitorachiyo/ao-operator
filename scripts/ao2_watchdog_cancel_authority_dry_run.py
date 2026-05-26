#!/usr/bin/env python3
"""End-to-end dry-run of the AO2 watchdog cancel-authority producer ↔ consumer
round trip without touching the live launchd loop.

Phase 2 exit-gate item #5 follow-up. The producer
(``scripts/ao2_watchdog_cancel_authority_producer.py``) emits a
``ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1`` from an
``ao2 factory queue-list --json`` snapshot, and the live watchdog
(``scripts/hermes_ao2_watchdog.py``) consumes that attestation via
``evaluate_ao2_cancel_authority`` when ``--require-ao2-cancel-authority``
is in effect. The launchd-tick wiring that flips the live loop into
require-mode is deferred per
``[[feedback_ao_claude_hooks_brick_operator_session]]``.

This dry-run is the safe-by-construction pre-flight: it captures (or
loads) a queue-list snapshot against an *isolated* target, runs the
producer in-process, feeds the result back through
``evaluate_ao2_cancel_authority`` with a synthetic active PID, and
writes a single ``dry-run-evidence.json`` artifact whose schema is
``ao-operator/ao2-watchdog-cancel-authority-dry-run/v1``. The live
launchd loop is never invoked or modified.

Two input modes (mutually exclusive, exactly one required):

- ``--queue-list-json PATH`` — consume a pre-captured snapshot. Offline,
  hermetic; the path of choice for tests and replay.
- ``--ao2-bin PATH`` — capture live by invoking
  ``ao2 factory queue-list --target <fresh-tmp> --json``. The target
  is always a freshly-created tempdir managed by this script so the
  invocation can never collide with the live ``ao2-control-plane``
  data dir.

Exit codes:

- ``0`` — round trip emitted evidence (whatever the outcome).
- ``2`` — ``--strict`` was set and the watchdog did not return
  ``accept_ao2_owns_watchdog_cancel`` (either the producer refused
  because of an active queue entry, or the watchdog rejected the
  attestation).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ao2_watchdog_cancel_authority_producer as _producer  # noqa: E402
import ao2_watchdog_cancel_ownership as _cancel_ownership  # noqa: E402
import hermes_ao2_watchdog as _watchdog  # noqa: E402

DRY_RUN_SCHEMA = "ao-operator/ao2-watchdog-cancel-authority-dry-run/v1"
QUEUE_LIST_SCHEMA = _producer.QUEUE_LIST_SCHEMA
ATTESTATION_SCHEMA = _producer.ATTESTATION_SCHEMA
ACTIVE_STATUSES: frozenset[str] = _producer.ACTIVE_STATUSES

DEFAULT_REASON = (
    "AO2 watchdog cancel-authority dry-run round-trip: producer-emitted "
    "no-active-AO2-runs attestation accepted by hermes_ao2_watchdog "
    "evaluate_ao2_cancel_authority under --require-ao2-cancel-authority"
)
DEFAULT_ACTIVE_PID = 1


class LiveCaptureError(RuntimeError):
    """Raised when the live ``ao2 factory queue-list`` capture fails."""


def capture_queue_list_live(ao2_bin: Path) -> tuple[dict[str, Any], str]:
    """Invoke ``ao2 factory queue-list --target <fresh-tmp> --json``.

    Returns the parsed JSON plus a source label suitable for the
    evidence record. The target is always a freshly-created tempdir
    that is cleaned up before this function returns, so the invocation
    can never collide with the operator's ``ao2-control-plane`` data
    dir or the live ao2 workbench queue.
    """

    if not ao2_bin.exists():
        raise LiveCaptureError(f"--ao2-bin not found: {ao2_bin}")
    with tempfile.TemporaryDirectory(prefix="ao2-watchdog-dry-run-target-") as tmp:
        target = Path(tmp)
        try:
            result = subprocess.run(
                [
                    str(ao2_bin),
                    "factory",
                    "queue-list",
                    "--target",
                    str(target),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
        except OSError as exc:
            raise LiveCaptureError(
                f"--ao2-bin {ao2_bin} could not be executed: {exc}"
            ) from exc
        if result.returncode != 0:
            raise LiveCaptureError(
                f"ao2 factory queue-list exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LiveCaptureError(
                f"ao2 factory queue-list did not emit valid JSON: {exc}"
            ) from exc
    if not isinstance(payload, dict):
        raise LiveCaptureError(
            "ao2 factory queue-list JSON did not parse to an object"
        )
    return payload, f"live:{ao2_bin}"


def load_queue_list_from_file(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(
            f"--queue-list-json did not parse to a JSON object: {path}"
        )
    return payload, f"file:{path}"


def _count_active_entries(queue_list: dict[str, Any]) -> int:
    active = 0
    entries = queue_list.get("entries")
    if not isinstance(entries, list):
        return 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").strip()
        if status in ACTIVE_STATUSES:
            active += 1
    return active


def evaluate_round_trip(
    attestation_path: Path, *, active_pid: int
) -> dict[str, Any]:
    """Feed ``attestation_path`` through ``hermes_ao2_watchdog``'s authority
    evaluator under ``--require-ao2-cancel-authority`` semantics.

    Returns the raw ``evaluate_ao2_cancel_authority`` dict.
    """

    args = Namespace(
        ao2_cancel_transitions=[],
        no_active_ao2_runs_attestation=attestation_path,
        require_ao2_cancel_authority=True,
    )
    return _watchdog.evaluate_ao2_cancel_authority(args, active_pid=active_pid)


def run_dry_run(
    *,
    queue_list_payload: dict[str, Any],
    out_dir: Path,
    active_pid: int,
    reason: str,
    queue_list_source_label: str,
) -> dict[str, Any]:
    """Pure orchestration: write all artifacts and return the evidence dict.

    Never reads from or writes to the live watchdog runtime directory;
    the caller is expected to pass an isolated ``out_dir``.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    queue_list_path = out_dir / "queue-list.json"
    queue_list_path.write_text(
        json.dumps(queue_list_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    queue_list_summary = {
        "source": queue_list_source_label,
        "snapshot_path": str(queue_list_path),
        "schema_version": queue_list_payload.get("schema_version"),
        "entry_count": queue_list_payload.get("entry_count"),
        "active_entry_count": _count_active_entries(queue_list_payload),
    }
    base_evidence = {
        "schema": DRY_RUN_SCHEMA,
        "active_pid": active_pid,
        "queue_list": queue_list_summary,
        "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
        "ao2_ownership": {
            "cancel_owner": _cancel_ownership.EXPECTED_AO2_DECISION_OWNER,
            "retry_owner": _cancel_ownership.EXPECTED_AO2_DECISION_OWNER,
            "factory_v3_role": _cancel_ownership.EXPECTED_FACTORY_V3_ROLE,
        },
    }

    try:
        _producer.validate_queue_list_payload(
            queue_list_payload, source=queue_list_source_label
        )
        attestation_payload = _producer.build_attestation(
            queue_list_payload, reason=reason
        )
    except _producer.ProducerError as exc:
        evidence = {
            **base_evidence,
            "outcome": "producer_refused",
            "producer": {
                "refused": True,
                "error": str(exc),
            },
            "attestation": None,
            "watchdog_decision": None,
        }
        _write_evidence(out_dir, evidence)
        return evidence

    attestation_path = out_dir / "no-active-ao2-runs-attestation.json"
    _producer.write_attestation(attestation_payload, attestation_path)

    decision = evaluate_round_trip(attestation_path, active_pid=active_pid)
    accepted = decision.get("decision") == "accept_ao2_owns_watchdog_cancel"
    outcome = (
        "accept_ao2_owns_watchdog_cancel" if accepted else "watchdog_refused"
    )
    authority = decision.get("authority") or {}
    claim = authority.get("claim") if isinstance(authority, dict) else None
    evidence = {
        **base_evidence,
        "outcome": outcome,
        "producer": {
            "refused": False,
            "attestation_path": str(attestation_path),
            "attestation_schema": attestation_payload["schema"],
            "produced_at_ms": attestation_payload["produced_at_ms"],
        },
        "attestation": {
            "path": str(attestation_path),
            "schema": attestation_payload["schema"],
            "factory_v3_role": attestation_payload["factory_v3_role"],
            "no_active_ao2_runs": attestation_payload["no_active_ao2_runs"],
        },
        "watchdog_decision": {
            "decision": decision.get("decision"),
            "mode": decision.get("mode"),
            "claim_status": (
                claim.get("status") if isinstance(claim, dict) else None
            ),
            "claim_blockers": (
                list(claim.get("blockers") or [])
                if isinstance(claim, dict)
                else []
            ),
            "no_active_ao2_runs_attestation_provided": (
                claim.get("no_active_ao2_runs_attestation_provided")
                if isinstance(claim, dict)
                else None
            ),
        },
    }
    _write_evidence(out_dir, evidence)
    return evidence


def _write_evidence(out_dir: Path, evidence: dict[str, Any]) -> Path:
    path = out_dir / "dry-run-evidence.json"
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run the AO2 watchdog cancel-authority producer ↔ consumer "
            "round trip without touching the live launchd loop. Writes "
            "dry-run-evidence.json under --out-dir."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--queue-list-json",
        type=Path,
        default=None,
        help=(
            "Path to a pre-captured ao2 factory queue-list JSON. Hermetic; "
            "preferred for tests and replay."
        ),
    )
    source_group.add_argument(
        "--ao2-bin",
        type=Path,
        default=None,
        help=(
            "Path to the ao2 binary. Invokes `ao2 factory queue-list "
            "--target <fresh-tmp> --json` against an isolated tempdir "
            "(never the operator's data dir)."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help=(
            "Directory under which to write queue-list.json, "
            "no-active-ao2-runs-attestation.json, and dry-run-evidence.json. "
            "Should be an isolated path, never the live watchdog-runtime."
        ),
    )
    parser.add_argument(
        "--active-pid",
        type=int,
        default=DEFAULT_ACTIVE_PID,
        help=(
            "Synthetic active PID fed to evaluate_ao2_cancel_authority. "
            "No process with this PID is signalled or inspected; the value "
            "is only used inside build_ownership to assert the no-active "
            "attestation covers the recorded terminated_pid."
        ),
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help=(
            "Operator reason recorded on the attestation. Defaults to a "
            "dry-run-specific string so on-disk attestations never look "
            "like a live-loop receipt."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit 2 if the watchdog did not return "
            "accept_ao2_owns_watchdog_cancel."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.queue_list_json is not None:
            queue_list_payload, source = load_queue_list_from_file(
                args.queue_list_json
            )
        else:
            queue_list_payload, source = capture_queue_list_live(args.ao2_bin)
    except (LiveCaptureError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    evidence = run_dry_run(
        queue_list_payload=queue_list_payload,
        out_dir=args.out_dir,
        active_pid=args.active_pid,
        reason=args.reason,
        queue_list_source_label=source,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if args.strict and evidence["outcome"] != "accept_ao2_owns_watchdog_cancel":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
