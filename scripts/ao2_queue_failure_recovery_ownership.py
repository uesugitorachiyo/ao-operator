#!/usr/bin/env python3
"""ao-operator declares AO2 owns the failure / retry / cancel lifecycle.

Phase 2 exit-gate item #5 requires that failure, retry, and cancellation
semantics are owned by AO2 (not ao-operator), with replay-clean evidence.

This script consumes evidence produced by AO2's persisted workbench queue:

- ``ao2 factory queue-submit ...`` →
  ``ao2.ao-operator-compat-workbench-queue-submit.v1``
- ``ao2 factory queue-cancel``/``queue-retry``/transition →
  ``ao2.ao-operator-compat-workbench-queue-transition.v1``

It emits a ao-operator ownership claim
(``ao-operator/ao2-queue-failure-recovery-ownership/v1``) certifying that
AO2's queue is the authority for retry/cancel decisions on the given
run, with a replay-clean transition chain folded from the supplied
evidence files.

The script enforces several refuse-to-emit safeguards. The load-bearing
one is ``--local-retry-decision``: if any local-side retry/cancel
decision file is supplied, the script refuses to emit an ownership
claim because that would mean ao-operator has retained lifecycle
ownership. Other safeguards: schema validation on submit + each
transition; run_id consistency across submit + transitions; the
queue entry's ``execution_contract.execution_owner == "ao2"``; and the
entry's ``parity_checklist_progress.ao2_persists_queue_history_cancel_retry_state``
is true.

Pure stdlib, no subprocess to the ``ao2`` binary. Callers run the AO2
queue commands themselves, capture the JSON outputs, and feed those
paths to this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/ao2-queue-failure-recovery-ownership/v1"
SUBMIT_SCHEMA = "ao2.ao-operator-compat-workbench-queue-submit.v1"
TRANSITION_SCHEMA = "ao2.ao-operator-compat-workbench-queue-transition.v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-workbench-queue"
EXPECTED_EXECUTION_OWNER = "ao2"

TRUST_BOUNDARY: dict[str, Any] = {
    "failure_lifecycle_owner": "ao2_factory_queue",
    "factory_v3_role": "defers_to_ao2_queue",
    "control_plane_role": "read_only_observer",
    "control_plane_approves_release": False,
    "mutates_ao_artifacts": False,
}


class InvalidOwnershipInputError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} did not parse to a JSON object")
    return value


def _validate_submit(submit: dict[str, Any], path: Path) -> None:
    schema = submit.get("schema_version")
    if schema != SUBMIT_SCHEMA:
        raise InvalidOwnershipInputError(
            f"submit schema must be {SUBMIT_SCHEMA!r}; got {schema!r} in {path}"
        )
    if submit.get("factory_v3_role") != EXPECTED_FACTORY_V3_ROLE:
        raise InvalidOwnershipInputError(
            f"submit factory_v3_role must be {EXPECTED_FACTORY_V3_ROLE!r}; "
            f"got {submit.get('factory_v3_role')!r} in {path}"
        )
    if submit.get("ao2_decision_owner") != EXPECTED_AO2_DECISION_OWNER:
        raise InvalidOwnershipInputError(
            f"submit ao2_decision_owner must be {EXPECTED_AO2_DECISION_OWNER!r}; "
            f"got {submit.get('ao2_decision_owner')!r} in {path}"
        )
    entry = submit.get("entry") or {}
    execution_contract = entry.get("execution_contract") or {}
    if execution_contract.get("execution_owner") != EXPECTED_EXECUTION_OWNER:
        raise InvalidOwnershipInputError(
            f"submit entry.execution_contract.execution_owner must be "
            f"{EXPECTED_EXECUTION_OWNER!r}; got "
            f"{execution_contract.get('execution_owner')!r} in {path}"
        )
    parity = entry.get("parity_checklist_progress") or {}
    if parity.get("ao2_persists_queue_history_cancel_retry_state") is not True:
        raise InvalidOwnershipInputError(
            "submit entry.parity_checklist_progress."
            "ao2_persists_queue_history_cancel_retry_state must be true "
            f"(observed {parity.get('ao2_persists_queue_history_cancel_retry_state')!r}) "
            f"in {path}"
        )


def _validate_transition(
    transition: dict[str, Any], path: Path, expected_run_id: str
) -> None:
    schema = transition.get("schema_version")
    if schema != TRANSITION_SCHEMA:
        raise InvalidOwnershipInputError(
            f"transition schema must be {TRANSITION_SCHEMA!r}; got {schema!r} in {path}"
        )
    if transition.get("factory_v3_role") != EXPECTED_FACTORY_V3_ROLE:
        raise InvalidOwnershipInputError(
            f"transition factory_v3_role must be {EXPECTED_FACTORY_V3_ROLE!r}; "
            f"got {transition.get('factory_v3_role')!r} in {path}"
        )
    if transition.get("ao2_decision_owner") != EXPECTED_AO2_DECISION_OWNER:
        raise InvalidOwnershipInputError(
            f"transition ao2_decision_owner must be {EXPECTED_AO2_DECISION_OWNER!r}; "
            f"got {transition.get('ao2_decision_owner')!r} in {path}"
        )
    run_id = transition.get("run_id")
    if run_id != expected_run_id:
        raise InvalidOwnershipInputError(
            f"run_id mismatch: submit run_id {expected_run_id!r} but transition "
            f"run_id {run_id!r} in {path}"
        )


def _build_transition_chain(
    submit: dict[str, Any], transitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    submit_entry = submit.get("entry") or {}
    for record in submit_entry.get("transition_history") or []:
        if isinstance(record, dict):
            chain.append(dict(record))
    seen = {(rec.get("at"), rec.get("status")) for rec in chain}
    for transition in transitions:
        entry = transition.get("entry") or {}
        for record in entry.get("transition_history") or []:
            if not isinstance(record, dict):
                continue
            key = (record.get("at"), record.get("status"))
            if key in seen:
                continue
            seen.add(key)
            chain.append(dict(record))
    return chain


def build_ownership(
    *,
    submit: dict[str, Any],
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    entry = submit.get("entry") or {}
    run_id = submit.get("run_id") or entry.get("run_id") or ""
    latest = transitions[-1] if transitions else None
    if latest is not None:
        latest_entry = latest.get("entry") or {}
        current_status = (
            latest_entry.get("status") or latest.get("status") or entry.get("status") or ""
        )
        attempts = int(
            latest_entry.get("attempts", entry.get("attempts", 0)) or 0
        )
    else:
        current_status = entry.get("status") or submit.get("status") or ""
        attempts = int(entry.get("attempts", 0) or 0)

    chain = _build_transition_chain(submit, transitions)
    return {
        "schema": SCHEMA,
        "status": "accepted",
        "decision": "accept_ao2_owns_retry_cancel_lifecycle",
        "run_id": run_id,
        "current_status": current_status,
        "attempts": attempts,
        "transition_chain": chain,
        "blockers": [],
        "ao2_ownership": {
            "execution_owner": EXPECTED_EXECUTION_OWNER,
            "queue_owner": EXPECTED_AO2_DECISION_OWNER,
            "retry_cancel_owner": EXPECTED_AO2_DECISION_OWNER,
            "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        },
        "evidence": {
            "submit_schema_version": SUBMIT_SCHEMA,
            "transition_count": len(transitions),
            "transition_schemas": [TRANSITION_SCHEMA for _ in transitions],
        },
        "trust_boundary": dict(TRUST_BOUNDARY),
        "next_action": (
            "AO2 queue owns the failure / retry / cancel lifecycle for this run; "
            "ao-operator must not initiate retry or cancel decisions locally"
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AO2 Queue Failure Recovery Ownership",
        "",
        f"- status: `{payload.get('status', 'missing')}`",
        f"- decision: `{payload.get('decision', 'missing')}`",
        f"- run_id: `{payload.get('run_id', 'missing')}`",
        f"- current_status: `{payload.get('current_status', 'missing')}`",
        f"- attempts: `{payload.get('attempts', 0)}`",
        f"- failure_lifecycle_owner: `{payload['trust_boundary']['failure_lifecycle_owner']}`",
        f"- factory_v3_role: `{payload['trust_boundary']['factory_v3_role']}`",
        "",
        "## Transition chain",
        "",
        "| at | from | status | reason |",
        "| --- | --- | --- | --- |",
    ]
    for record in payload.get("transition_chain", []):
        lines.append(
            f"| {record.get('at', '')} | {record.get('from', '')} | "
            f"{record.get('status', '')} | {record.get('reason', '')} |"
        )
    lines.extend(
        [
            "",
            "## AO2 ownership",
            "",
            f"- execution_owner: `{payload['ao2_ownership']['execution_owner']}`",
            f"- queue_owner: `{payload['ao2_ownership']['queue_owner']}`",
            f"- retry_cancel_owner: `{payload['ao2_ownership']['retry_cancel_owner']}`",
            f"- factory_v3_role: `{payload['ao2_ownership']['factory_v3_role']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", type=Path, required=True)
    parser.add_argument(
        "--transition",
        type=Path,
        action="append",
        default=[],
        dest="transitions",
        help="AO2 queue-transition JSON (repeatable)",
    )
    parser.add_argument(
        "--local-retry-decision",
        type=Path,
        default=None,
        help=(
            "If supplied, the script refuses to emit an ownership claim. "
            "Used to prove ao-operator did not retain lifecycle ownership."
        ),
    )
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.local_retry_decision is not None:
        print(
            "retry/cancel ownership cannot be local: AO2 owns the failure "
            "lifecycle. Remove --local-retry-decision and run AO2's queue "
            "commands instead.",
            file=sys.stderr,
        )
        return 2

    submit = _load_json(args.submit)
    try:
        _validate_submit(submit, args.submit)
    except InvalidOwnershipInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    expected_run_id = submit.get("run_id") or (submit.get("entry") or {}).get("run_id") or ""
    transitions: list[dict[str, Any]] = []
    for transition_path in args.transitions:
        transition = _load_json(transition_path)
        try:
            _validate_transition(transition, transition_path, expected_run_id)
        except InvalidOwnershipInputError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        transitions.append(transition)
    payload = build_ownership(submit=submit, transitions=transitions)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(text, encoding="utf-8")
    if args.write_md:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(render_markdown(payload), encoding="utf-8")
    if args.json:
        print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
