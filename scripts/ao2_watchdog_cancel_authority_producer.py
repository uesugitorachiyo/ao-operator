#!/usr/bin/env python3
"""Produce a no-active-ao2-runs attestation from an AO2 queue-list snapshot.

Phase 2 exit-gate item #5 follow-up. ``hermes_ao2_watchdog.py`` now
consults AO2 cancel authority before terminating an overdue Hermes
one-shot (see ``evaluate_ao2_cancel_authority``). To opt the live
launchd loop into ``--require-ao2-cancel-authority``, ao-operator needs
a way to materialise the attestation file deterministically from
observed AO2 state.

This producer reads an ``ao2 factory queue-list --json`` JSON
(``schema_version`` = ``ao2.ao-operator-compat-workbench-queue-list.v1``)
and emits the
``ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1`` payload
when the queue has no active entries (status in ``queued`` /
``running`` / ``cancel_requested``). Otherwise it refuses with exit 2
and prints the active entries on stderr.

The producer does NOT shell out to the ``ao2`` binary. The launchd
plist or operator captures ``ao2 factory queue-list --target ... --json``
to disk first and hands the path to this script. That keeps the
producer pure and offline-testable.

Hard refusals (exit 2):
- input path missing or unreadable JSON;
- queue-list schema is not
  ``ao2.ao-operator-compat-workbench-queue-list.v1``;
- any entry has status ``queued``, ``running``, or ``cancel_requested``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

QUEUE_LIST_SCHEMA = "ao2.ao-operator-compat-workbench-queue-list.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"

ACTIVE_STATUSES: frozenset[str] = frozenset({"queued", "running", "cancel_requested"})

DEFAULT_REASON = (
    "AO2 factory queue-list snapshot reports no active entries; the "
    "overdue Hermes one-shot has no in-flight AO2 run to cancel"
)


class ProducerError(RuntimeError):
    """Raised for any producer refusal; caller maps to exit code 2."""


def validate_queue_list_payload(
    payload: Any, *, source: str
) -> dict[str, Any]:
    """Reusable shape + schema check for an in-memory queue-list payload.

    Shared by the CLI ``--queue-list-json`` path and the dry-run script
    so both call sites refuse identical inputs identically. ``source``
    is the human-readable origin (file path, ``live:<bin>``) used in
    error messages.
    """

    if not isinstance(payload, dict):
        raise ProducerError(
            f"queue-list did not parse to a JSON object: {source}"
        )
    schema = payload.get("schema_version")
    if schema != QUEUE_LIST_SCHEMA:
        raise ProducerError(
            f"queue-list schema_version must be {QUEUE_LIST_SCHEMA!r}; "
            f"got {schema!r} in {source}"
        )
    return payload


def _load_queue_list(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProducerError(
            f"--queue-list-json input not found: {path}"
        ) from exc
    except OSError as exc:
        raise ProducerError(
            f"--queue-list-json input unreadable: {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProducerError(
            f"--queue-list-json input is not valid JSON: {path}: {exc}"
        ) from exc
    return validate_queue_list_payload(payload, source=str(path))


def _classify_entries(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    active: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").strip()
        if not status:
            status = "unknown"
        counts[status] = counts.get(status, 0) + 1
        if status in ACTIVE_STATUSES:
            active.append(
                {
                    "run_id": str(entry.get("run_id") or ""),
                    "status": status,
                }
            )
    return active, counts


def build_attestation(
    queue_list: dict[str, Any], *, reason: str, now_ms: int | None = None
) -> dict[str, Any]:
    entries_raw = queue_list.get("entries")
    if not isinstance(entries_raw, list):
        entries_raw = []
    active, status_counts = _classify_entries(entries_raw)
    if active:
        formatted = ", ".join(f"{e['run_id']}={e['status']}" for e in active)
        raise ProducerError(
            "queue-list shows active AO2 queue entries; cannot emit "
            "no-active-ao2-runs attestation: " + formatted
        )
    entry_count = queue_list.get("entry_count")
    if not isinstance(entry_count, int):
        entry_count = len(entries_raw)
    timestamp = now_ms if now_ms is not None else int(time.time() * 1000)
    return {
        "schema": ATTESTATION_SCHEMA,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "no_active_ao2_runs": True,
        "reason": reason,
        "produced_at_ms": timestamp,
        "source": {
            "schema_version": QUEUE_LIST_SCHEMA,
            "queue_path": str(queue_list.get("queue_path") or ""),
            "entry_count": int(entry_count),
            "active_entry_count": 0,
            "status_counts": status_counts,
        },
    }


def write_attestation(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_native_attestation(path: Path) -> dict[str, Any]:
    """Read a candidate AO2-native attestation file produced by
    ``ao2 factory cancel-authority`` and return its parsed payload.

    Refuses on missing input, malformed JSON, or non-object root."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProducerError(
            f"--ao2-native-attestation input not found: {path}"
        ) from exc
    except OSError as exc:
        raise ProducerError(
            f"--ao2-native-attestation input unreadable: {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProducerError(
            f"--ao2-native-attestation input is not valid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProducerError(
            f"--ao2-native-attestation input did not parse to a JSON object: {path}"
        )
    return payload


def validate_native_attestation(payload: dict[str, Any], path: Path) -> None:
    """Validate that ``payload`` is a canonical AO2-native attestation.

    Reuses the same fields the live watchdog validator
    (``ao2_watchdog_cancel_ownership._validate_attestation``) already
    requires for top-level keys, then layers on the ``source`` sub-object
    contract the AO2-native producer is responsible for. Raises
    :class:`ProducerError` so the caller can map to exit code 2."""

    schema = payload.get("schema")
    if schema != ATTESTATION_SCHEMA:
        raise ProducerError(
            f"--ao2-native-attestation schema must be {ATTESTATION_SCHEMA!r}; "
            f"got {schema!r} in {path}"
        )
    role = payload.get("factory_v3_role")
    if role != EXPECTED_FACTORY_V3_ROLE:
        raise ProducerError(
            f"--ao2-native-attestation factory_v3_role must be "
            f"{EXPECTED_FACTORY_V3_ROLE!r}; got {role!r} in {path}"
        )
    if payload.get("no_active_ao2_runs") is not True:
        raise ProducerError(
            "--ao2-native-attestation no_active_ao2_runs must be true; "
            f"got {payload.get('no_active_ao2_runs')!r} in {path}"
        )
    produced_at = payload.get("produced_at_ms")
    if not isinstance(produced_at, int) or produced_at <= 0:
        raise ProducerError(
            "--ao2-native-attestation produced_at_ms must be a positive "
            f"integer (millis); got {produced_at!r} in {path}"
        )
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ProducerError(
            "--ao2-native-attestation source must be an object; "
            f"got {type(source).__name__} in {path}"
        )
    src_schema = source.get("schema_version")
    if src_schema != QUEUE_LIST_SCHEMA:
        raise ProducerError(
            f"--ao2-native-attestation source.schema_version must be "
            f"{QUEUE_LIST_SCHEMA!r}; got {src_schema!r} in {path}"
        )
    active = source.get("active_entry_count")
    if active != 0:
        raise ProducerError(
            "--ao2-native-attestation source.active_entry_count must be 0; "
            f"got {active!r} in {path}"
        )
    if not isinstance(source.get("entry_count"), int):
        raise ProducerError(
            "--ao2-native-attestation source.entry_count must be an "
            f"integer in {path}"
        )
    if not isinstance(source.get("status_counts"), dict):
        raise ProducerError(
            "--ao2-native-attestation source.status_counts must be an "
            f"object in {path}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit a ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1 "
            "payload either by deriving it from an AO2 queue-list snapshot "
            "(--queue-list-json) or by passing through a pre-signed "
            "AO2-native attestation (--ao2-native-attestation). Phase 2 "
            "exit-gate item #5: AO2 is the canonical producer; ao-operator "
            "may run in pure observer mode when AO2 is the upstream."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--queue-list-json",
        type=Path,
        default=None,
        help=(
            "Path to an ao2.ao-operator-compat-workbench-queue-list.v1 JSON "
            "produced by `ao2 factory queue-list --json`. Derives the "
            "attestation locally."
        ),
    )
    source_group.add_argument(
        "--ao2-native-attestation",
        type=Path,
        default=None,
        help=(
            "Path to an AO2-native attestation produced by `ao2 factory "
            "cancel-authority`. Validates and re-emits verbatim so "
            "ao-operator becomes a pure observer of AO2's canonical "
            "receipt."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the attestation JSON.",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help=(
            "Operator reason recorded in the attestation. Only used when "
            "deriving from --queue-list-json; ignored in passthrough mode."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.ao2_native_attestation is not None:
            payload = _load_native_attestation(args.ao2_native_attestation)
            validate_native_attestation(payload, args.ao2_native_attestation)
            mode = "passthrough_ao2_native"
        else:
            queue_list = _load_queue_list(args.queue_list_json)
            payload = build_attestation(queue_list, reason=args.reason)
            mode = "derive_from_queue_list"
    except ProducerError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_attestation(payload, args.out)
    print(
        json.dumps(
            {"attestation_path": str(args.out), "mode": mode}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
