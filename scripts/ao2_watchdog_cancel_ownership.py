#!/usr/bin/env python3
"""ao-operator declares AO2 owns watchdog cancel / termination semantics.

Phase 2 exit-gate item #5 (AO2-FACTORY-MIGRATION-ROADMAP.md) requires that
failure / retry / cancel decisions are owned by AO2 (not ao-operator) with
replay-clean evidence. ``hermes_ao2_watchdog.py`` retains one destructive
local surface: when an overdue lock is recovered, the watchdog calls
``terminate_process(active_pid)`` to SIGTERM the prior Hermes one-shot
process. From Phase 2's perspective that termination must be governed by
an AO2 cancel transition — ao-operator is otherwise asserting unilateral
cancel authority.

This script emits an ownership-claim artifact that certifies, for a given
watchdog status JSON, one of:

1. The watchdog did not terminate any process this run (``action !=
   "recovered_overdue_hermes_oneshot"`` and ``terminated_pid`` is absent),
   so no AO2 cancel evidence is required.
2. The watchdog did terminate a process AND every terminated pid is
   covered by at least one AO2 queue-cancel transition
   (``ao2.ao-operator-compat-workbench-queue-transition.v1`` with
   ``status == "cancelled"``), so AO2's cancel decision authorised the
   local termination after the fact.
3. The watchdog terminated a process but the operator supplied
   ``--no-active-ao2-runs-attestation <path>`` pointing to an attestation
   JSON certifying that the terminated process was a stuck Hermes
   one-shot with no in-flight AO2 run to cancel (and therefore no AO2
   cancel evidence is producible). The attestation must itself be signed
   by ``parity_oracle_only``.

Hard refusals (return code 2):
- ``--local-cancel-decision`` is supplied: this proves ao-operator
  retained cancel authority; the script never emits an accepting
  ownership claim in that case.
- Watchdog status schema is not ``ao-operator/hermes-ao2-watchdog/v1``.
- Watchdog terminated a pid but neither AO2 cancel transitions nor a
  ``--no-active-ao2-runs-attestation`` was supplied.
- Any supplied transition is not schema
  ``ao2.ao-operator-compat-workbench-queue-transition.v1`` /
  ``factory_v3_role != parity_oracle_only`` / ``ao2_decision_owner !=
  ao2-workbench-queue`` / ``status != cancelled``.

Pure stdlib, no subprocess; callers run the AO2 queue commands and pass
the captured JSON outputs in.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/ao2-watchdog-cancel-ownership/v1"
WATCHDOG_SCHEMA = "ao-operator/hermes-ao2-watchdog/v1"
TRANSITION_SCHEMA = "ao2.ao-operator-compat-workbench-queue-transition.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"

EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-workbench-queue"
TERMINATING_WATCHDOG_ACTION = "recovered_overdue_hermes_oneshot"

TRUST_BOUNDARY: dict[str, Any] = {
    "cancel_authority": "ao2_factory_queue",
    "watchdog_role": "executor_of_ao2_cancel_decision_or_unauthorized",
    "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
    "control_plane_role": "read_only_observer",
    "control_plane_approves_cancel": False,
    "mutates_ao_artifacts": False,
}


class InvalidCancelOwnershipInputError(RuntimeError):
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


def _validate_watchdog(payload: dict[str, Any], path: Path) -> None:
    schema = payload.get("schema")
    if schema != WATCHDOG_SCHEMA:
        raise InvalidCancelOwnershipInputError(
            f"watchdog status schema must be {WATCHDOG_SCHEMA!r}; got {schema!r} in {path}"
        )


def _validate_transition(payload: dict[str, Any], path: Path) -> None:
    schema = payload.get("schema_version")
    if schema != TRANSITION_SCHEMA:
        raise InvalidCancelOwnershipInputError(
            f"transition schema must be {TRANSITION_SCHEMA!r}; got {schema!r} in {path}"
        )
    if payload.get("factory_v3_role") != EXPECTED_FACTORY_V3_ROLE:
        raise InvalidCancelOwnershipInputError(
            f"transition factory_v3_role must be {EXPECTED_FACTORY_V3_ROLE!r}; "
            f"got {payload.get('factory_v3_role')!r} in {path}"
        )
    if payload.get("ao2_decision_owner") != EXPECTED_AO2_DECISION_OWNER:
        raise InvalidCancelOwnershipInputError(
            f"transition ao2_decision_owner must be {EXPECTED_AO2_DECISION_OWNER!r}; "
            f"got {payload.get('ao2_decision_owner')!r} in {path}"
        )
    entry = payload.get("entry") or {}
    status = entry.get("status") or payload.get("status")
    if status != "cancelled":
        raise InvalidCancelOwnershipInputError(
            f"transition must record status 'cancelled'; got {status!r} in {path}"
        )


def _validate_attestation(payload: dict[str, Any], path: Path) -> None:
    schema = payload.get("schema")
    if schema != ATTESTATION_SCHEMA:
        raise InvalidCancelOwnershipInputError(
            f"attestation schema must be {ATTESTATION_SCHEMA!r}; got {schema!r} in {path}"
        )
    if payload.get("factory_v3_role") != EXPECTED_FACTORY_V3_ROLE:
        raise InvalidCancelOwnershipInputError(
            f"attestation factory_v3_role must be {EXPECTED_FACTORY_V3_ROLE!r}; "
            f"got {payload.get('factory_v3_role')!r} in {path}"
        )
    if payload.get("no_active_ao2_runs") is not True:
        raise InvalidCancelOwnershipInputError(
            "attestation no_active_ao2_runs must be true "
            f"(observed {payload.get('no_active_ao2_runs')!r}) in {path}"
        )


def _terminated_pids(watchdog: dict[str, Any]) -> list[int]:
    pids: list[int] = []
    primary = watchdog.get("terminated_pid")
    if isinstance(primary, int):
        pids.append(primary)
    extra = watchdog.get("terminated_pids")
    if isinstance(extra, list):
        for value in extra:
            if isinstance(value, int) and value not in pids:
                pids.append(value)
    return pids


def _transition_covers_pid(transition: dict[str, Any], pid: int) -> bool:
    entry = transition.get("entry") or {}
    for key in ("terminated_pid", "killed_pid", "pid"):
        if entry.get(key) == pid or transition.get(key) == pid:
            return True
    for record in entry.get("transition_history") or []:
        if isinstance(record, dict) and record.get("terminated_pid") == pid:
            return True
    return False


def build_ownership(
    *,
    watchdog: dict[str, Any],
    transitions: list[dict[str, Any]],
    attestation: dict[str, Any] | None,
) -> dict[str, Any]:
    action = watchdog.get("action")
    pids = _terminated_pids(watchdog)
    terminated_a_process = action == TERMINATING_WATCHDOG_ACTION or bool(pids)

    blockers: list[str] = []
    pid_coverage: list[dict[str, Any]] = []
    if terminated_a_process:
        for pid in pids:
            covering = [
                idx
                for idx, transition in enumerate(transitions)
                if _transition_covers_pid(transition, pid)
            ]
            pid_coverage.append(
                {
                    "terminated_pid": pid,
                    "covered_by_transition_indexes": covering,
                    "covered": bool(covering) or attestation is not None,
                }
            )
        if not transitions and attestation is None:
            blockers.append(
                "watchdog terminated a process but no AO2 cancel transitions "
                "and no --no-active-ao2-runs-attestation were supplied"
            )
        elif transitions and not pids and attestation is None:
            blockers.append(
                "watchdog action indicates termination but no terminated_pid "
                "is recorded; cannot map to AO2 cancel evidence"
            )
        elif pids and attestation is None:
            uncovered = [entry["terminated_pid"] for entry in pid_coverage if not entry["covered"]]
            if uncovered:
                blockers.append(
                    "terminated_pids missing AO2 cancel transition coverage: "
                    f"{uncovered}"
                )

    accepted = not blockers
    status = "accepted" if accepted else "blocked"
    decision = (
        "accept_ao2_owns_watchdog_cancel"
        if accepted
        else "reject_factory_v3_retained_cancel_authority"
    )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "decision": decision,
        "watchdog_action": action,
        "watchdog_terminated_a_process": terminated_a_process,
        "terminated_pids": pids,
        "pid_coverage": pid_coverage,
        "transition_count": len(transitions),
        "transition_schemas": [TRANSITION_SCHEMA for _ in transitions],
        "no_active_ao2_runs_attestation_provided": attestation is not None,
        "blockers": blockers,
        "ao2_ownership": {
            "cancel_owner": EXPECTED_AO2_DECISION_OWNER,
            "retry_owner": EXPECTED_AO2_DECISION_OWNER,
            "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        },
        "trust_boundary": dict(TRUST_BOUNDARY),
        "next_action": (
            "AO2 queue owns watchdog cancel decisions; ao-operator must "
            "either consume an AO2 cancel transition before terminating a "
            "Hermes one-shot or supply a parity-oracle attestation that "
            "no AO2 run is in flight"
        ),
    }
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AO2 Watchdog Cancel Ownership",
        "",
        f"- status: `{payload.get('status', 'missing')}`",
        f"- decision: `{payload.get('decision', 'missing')}`",
        f"- watchdog_action: `{payload.get('watchdog_action', 'missing')}`",
        f"- watchdog_terminated_a_process: `{payload.get('watchdog_terminated_a_process')}`",
        f"- terminated_pids: `{payload.get('terminated_pids', [])}`",
        f"- transition_count: `{payload.get('transition_count', 0)}`",
        f"- no_active_ao2_runs_attestation_provided: "
        f"`{payload.get('no_active_ao2_runs_attestation_provided')}`",
        f"- cancel_authority: `{payload['trust_boundary']['cancel_authority']}`",
        f"- factory_v3_role: `{payload['trust_boundary']['factory_v3_role']}`",
        "",
        "## PID coverage",
        "",
        "| terminated_pid | covered_by_transition_indexes | covered |",
        "| --- | --- | --- |",
    ]
    for entry in payload.get("pid_coverage", []):
        lines.append(
            f"| {entry.get('terminated_pid', '')} | "
            f"{entry.get('covered_by_transition_indexes', [])} | "
            f"{entry.get('covered', False)} |"
        )
    blockers = payload.get("blockers") or []
    lines.extend(["", "## Blockers", ""])
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## AO2 ownership",
            "",
            f"- cancel_owner: `{payload['ao2_ownership']['cancel_owner']}`",
            f"- retry_owner: `{payload['ao2_ownership']['retry_owner']}`",
            f"- factory_v3_role: `{payload['ao2_ownership']['factory_v3_role']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchdog-status", type=Path, required=True)
    parser.add_argument(
        "--transition",
        type=Path,
        action="append",
        default=[],
        dest="transitions",
        help="AO2 queue-cancel transition JSON (repeatable)",
    )
    parser.add_argument(
        "--no-active-ao2-runs-attestation",
        type=Path,
        default=None,
        dest="attestation",
        help=(
            "Parity-oracle attestation JSON certifying the terminated Hermes "
            "one-shot had no in-flight AO2 run to cancel"
        ),
    )
    parser.add_argument(
        "--local-cancel-decision",
        type=Path,
        default=None,
        help=(
            "If supplied, the script refuses to emit an ownership claim. "
            "Used to prove ao-operator did not retain cancel authority."
        ),
    )
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.local_cancel_decision is not None:
        print(
            "cancel ownership cannot be local: AO2 owns watchdog cancel "
            "decisions. Remove --local-cancel-decision and consume an AO2 "
            "queue-cancel transition (or supply "
            "--no-active-ao2-runs-attestation) instead.",
            file=sys.stderr,
        )
        return 2

    watchdog = _load_json(args.watchdog_status)
    try:
        _validate_watchdog(watchdog, args.watchdog_status)
    except InvalidCancelOwnershipInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    transitions: list[dict[str, Any]] = []
    for transition_path in args.transitions:
        transition = _load_json(transition_path)
        try:
            _validate_transition(transition, transition_path)
        except InvalidCancelOwnershipInputError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        transitions.append(transition)

    attestation: dict[str, Any] | None = None
    if args.attestation is not None:
        attestation = _load_json(args.attestation)
        try:
            _validate_attestation(attestation, args.attestation)
        except InvalidCancelOwnershipInputError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    payload = build_ownership(
        watchdog=watchdog, transitions=transitions, attestation=attestation
    )
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(text, encoding="utf-8")
    if args.write_md:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(render_markdown(payload), encoding="utf-8")
    if args.json:
        print(text, end="")
    return 0 if payload.get("status") == "accepted" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
