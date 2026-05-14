#!/usr/bin/env python3
"""AI agent destructive-action approval gate.

Models the destructive-action approval state machine that governs
every AO Operator / AO Runtime path which can mutate or destroy
shared state (rm, git reset --hard, git push --force, git branch -D,
db drop, transfer cleanup, approval revocation, etc.).

The gate proves that a destructive action only executes when a
fresh, scoped, single-use approval token is presented at execution
time -- never on a policy declaration alone, never on a stale or
expired token, never on a token whose scope is widened at execute
time, never twice for distinct destructive ops, and never inherited
by a child process without re-confirming.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_destructive_action_with_fresh_scoped_approval_executes`` --
  control: a destructive op runs against a fresh, scope-matched,
  unconsumed token before its expiry; the verifier produces no
  errors.
* ``stale_approval_reused_after_expiry_rejected`` -- mutation: a
  destructive op presents a token whose ``expires_at`` is in the
  past relative to ``now``; the verifier MUST reject.
* ``approval_scope_widened_at_exec_silently_accepted_rejected`` --
  mutation: a destructive op presents a token issued for a narrow
  target but executes against a wider target; the verifier MUST
  reject.
* ``approval_consumed_twice_for_distinct_destructive_ops_rejected``
  -- mutation: the same token is consumed for two distinct
  destructive ops; the verifier MUST reject the second consumption.
* ``destructive_op_runs_with_policy_only_without_token_rejected`` --
  mutation: a destructive op runs against a policy declaration
  ("approval allowed") with no materialized token; the verifier
  MUST reject.
* ``parent_process_approval_inherited_by_child_without_reconfirm_rejected``
  -- mutation: a child process presents the parent's token without
  re-confirming for its own destructive op; the verifier MUST
  reject.

Every case lays down a per-case
``destructive-action-approval-transcript.json`` in a temporary work
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
    "ai-agent-destructive-action-approval.json"
)
SCHEMA = "ao-operator/ai-agent-destructive-action-approval/v1"

CASE_IDS = (
    "clean_destructive_action_with_fresh_scoped_approval_executes",
    "stale_approval_reused_after_expiry_rejected",
    "approval_scope_widened_at_exec_silently_accepted_rejected",
    "approval_consumed_twice_for_distinct_destructive_ops_rejected",
    "destructive_op_runs_with_policy_only_without_token_rejected",
    "parent_process_approval_inherited_by_child_without_reconfirm_rejected",
)

EXPECTED_VERDICTS = {
    "clean_destructive_action_with_fresh_scoped_approval_executes": "PASS",
    "stale_approval_reused_after_expiry_rejected": "FAIL",
    "approval_scope_widened_at_exec_silently_accepted_rejected": "FAIL",
    "approval_consumed_twice_for_distinct_destructive_ops_rejected": "FAIL",
    "destructive_op_runs_with_policy_only_without_token_rejected": "FAIL",
    "parent_process_approval_inherited_by_child_without_reconfirm_rejected": "FAIL",
}

_OPERATOR_ID = "operator_alpha"
_TOKEN_VALID = "approval_token_zeta"
_TOKEN_DISTINCT = "approval_token_eta"
_TOKEN_PARENT = "approval_token_parent_theta"
_OP_DESTRUCTIVE = "git_reset_hard"
_OP_DISTINCT = "git_branch_delete_force"
_TARGET_NARROW = "feature/x"
_TARGET_WIDE = "main"
_BLAST_RADIUS = "high"
_ISSUE_TIME = "2026-05-08T00:00:00+00:00"
_EXPIRY_TIME = "2026-05-08T01:00:00+00:00"
_NOW_FRESH = "2026-05-08T00:30:00+00:00"
_NOW_AFTER_EXPIRY = "2026-05-08T02:00:00+00:00"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class _DestructiveActionApprovalVerifier:
    """In-memory destructive-action approval state machine.

    Enforces:

    1. A destructive op MUST present a token registered via
       ``issue_token``; a policy declaration alone is never enough.
    2. A token MUST be presented before its ``expires_at`` (relative
       to the supplied ``now``); stale tokens are rejected.
    3. The token's ``operator_id``, ``op``, ``target``, and
       ``blast_radius`` MUST exactly match the executing op; any
       widening of scope at execute time is rejected.
    4. A token MUST be consumed at most once; a second consumption
       (even for a distinct destructive op) is rejected.
    5. A child process presenting its parent's token without
       issuing a fresh, child-scoped approval is rejected.
    """

    def __init__(self) -> None:
        self.tokens: dict[str, dict[str, Any]] = {}
        self.consumed: set[str] = set()
        self.executions: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def issue_token(
        self,
        *,
        token_id: str,
        operator_id: str,
        op: str,
        target: str,
        blast_radius: str,
        issued_at: str,
        expires_at: str,
    ) -> None:
        self.tokens[token_id] = {
            "operator_id": operator_id,
            "op": op,
            "target": target,
            "blast_radius": blast_radius,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }

    def execute_with_token(
        self,
        *,
        token_id: str,
        operator_id: str,
        op: str,
        target: str,
        blast_radius: str,
        now: str,
        parent_token_id: str | None = None,
    ) -> None:
        record = {
            "op": "execute_with_token",
            "token_id": token_id,
            "operator_id": operator_id,
            "exec_op": op,
            "target": target,
            "blast_radius": blast_radius,
            "now": now,
            "parent_token_id": parent_token_id,
        }
        self.executions.append(record)
        token = self.tokens.get(token_id)
        if token is None:
            self.errors.append(
                f"destructive_op_token_unknown:token_id={token_id},op={op}"
            )
            return
        try:
            now_ts = _parse_iso(now)
            expires_ts = _parse_iso(token["expires_at"])
            issued_ts = _parse_iso(token["issued_at"])
        except ValueError:
            self.errors.append(
                f"destructive_op_token_unparseable_time:token_id={token_id}"
            )
            return
        if now_ts >= expires_ts:
            self.errors.append(
                f"stale_approval_reused_after_expiry:token_id={token_id},now={now},expires_at={token['expires_at']}"
            )
            return
        if now_ts < issued_ts:
            self.errors.append(
                f"approval_used_before_issue:token_id={token_id},now={now},issued_at={token['issued_at']}"
            )
            return
        scope_mismatches: list[str] = []
        if token["operator_id"] != operator_id:
            scope_mismatches.append(
                f"operator_id(issued={token['operator_id']},exec={operator_id})"
            )
        if token["op"] != op:
            scope_mismatches.append(f"op(issued={token['op']},exec={op})")
        if token["target"] != target:
            scope_mismatches.append(
                f"target(issued={token['target']},exec={target})"
            )
        if token["blast_radius"] != blast_radius:
            scope_mismatches.append(
                f"blast_radius(issued={token['blast_radius']},exec={blast_radius})"
            )
        if scope_mismatches:
            self.errors.append(
                f"approval_scope_widened_at_exec:token_id={token_id},mismatches={'|'.join(scope_mismatches)}"
            )
            return
        if token_id in self.consumed:
            self.errors.append(
                f"approval_consumed_twice:token_id={token_id},exec_op={op},target={target}"
            )
            return
        if parent_token_id is not None and parent_token_id == token_id:
            self.errors.append(
                f"child_process_inherited_parent_token_without_reconfirm:parent_token_id={parent_token_id},exec_op={op}"
            )
            return
        self.consumed.add(token_id)

    def execute_policy_only(
        self,
        *,
        operator_id: str,
        op: str,
        target: str,
        blast_radius: str,
        policy_label: str,
    ) -> None:
        self.executions.append(
            {
                "op": "execute_policy_only",
                "operator_id": operator_id,
                "exec_op": op,
                "target": target,
                "blast_radius": blast_radius,
                "policy_label": policy_label,
            }
        )
        self.errors.append(
            f"policy_only_destructive_op_without_token:op={op},target={target},policy_label={policy_label}"
        )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "destructive-action-approval-transcript.json").write_text(
        json.dumps({"events": transcript}, indent=2, sort_keys=True),
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


def _issue_clean_token(verifier: _DestructiveActionApprovalVerifier) -> dict[str, Any]:
    issue = {
        "op": "issue_token",
        "token_id": _TOKEN_VALID,
        "operator_id": _OPERATOR_ID,
        "exec_op": _OP_DESTRUCTIVE,
        "target": _TARGET_NARROW,
        "blast_radius": _BLAST_RADIUS,
        "issued_at": _ISSUE_TIME,
        "expires_at": _EXPIRY_TIME,
    }
    verifier.issue_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        issued_at=_ISSUE_TIME,
        expires_at=_EXPIRY_TIME,
    )
    return issue


def run_clean_destructive_action_with_fresh_scoped_approval_executes(work: Path) -> dict[str, Any]:
    case_id = "clean_destructive_action_with_fresh_scoped_approval_executes"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = [_issue_clean_token(verifier)]

    verifier.execute_with_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_FRESH,
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: destructive op runs against a fresh, scope-matched, "
            "unconsumed approval token before its expiry"
        ),
    )


def run_stale_approval_reused_after_expiry_rejected(work: Path) -> dict[str, Any]:
    case_id = "stale_approval_reused_after_expiry_rejected"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = [_issue_clean_token(verifier)]

    verifier.execute_with_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_AFTER_EXPIRY,
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: destructive op presents a token whose expires_at is in the "
            "past relative to now and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_approval_scope_widened_at_exec_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "approval_scope_widened_at_exec_silently_accepted_rejected"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = [_issue_clean_token(verifier)]

    verifier.execute_with_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_WIDE,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_FRESH,
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: destructive op presents a token issued for a narrow target "
            "but executes against a wider target and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_approval_consumed_twice_for_distinct_destructive_ops_rejected(work: Path) -> dict[str, Any]:
    case_id = "approval_consumed_twice_for_distinct_destructive_ops_rejected"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = [_issue_clean_token(verifier)]

    verifier.execute_with_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_FRESH,
    )
    transcript.append(verifier.executions[-1])

    verifier.execute_with_token(
        token_id=_TOKEN_VALID,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_FRESH,
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: the same token is consumed for two destructive ops in a row "
            "and the verifier must reject the second consumption instead of "
            "silently accepting"
        ),
    )


def run_destructive_op_runs_with_policy_only_without_token_rejected(work: Path) -> dict[str, Any]:
    case_id = "destructive_op_runs_with_policy_only_without_token_rejected"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = []

    verifier.execute_policy_only(
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        policy_label="approval_allowed_for_operator_alpha",
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: destructive op runs against a policy declaration "
            "('approval allowed') with no materialized token and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_parent_process_approval_inherited_by_child_without_reconfirm_rejected(work: Path) -> dict[str, Any]:
    case_id = "parent_process_approval_inherited_by_child_without_reconfirm_rejected"
    verifier = _DestructiveActionApprovalVerifier()
    transcript: list[dict[str, Any]] = []

    verifier.issue_token(
        token_id=_TOKEN_PARENT,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        issued_at=_ISSUE_TIME,
        expires_at=_EXPIRY_TIME,
    )
    transcript.append(
        {
            "op": "issue_token",
            "token_id": _TOKEN_PARENT,
            "operator_id": _OPERATOR_ID,
            "exec_op": _OP_DESTRUCTIVE,
            "target": _TARGET_NARROW,
            "blast_radius": _BLAST_RADIUS,
            "issued_at": _ISSUE_TIME,
            "expires_at": _EXPIRY_TIME,
        }
    )

    verifier.execute_with_token(
        token_id=_TOKEN_PARENT,
        operator_id=_OPERATOR_ID,
        op=_OP_DESTRUCTIVE,
        target=_TARGET_NARROW,
        blast_radius=_BLAST_RADIUS,
        now=_NOW_FRESH,
        parent_token_id=_TOKEN_PARENT,
    )
    transcript.append(verifier.executions[-1])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a child process presents its parent's token without "
            "issuing a fresh, child-scoped approval and the verifier must reject "
            "instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_destructive_action_with_fresh_scoped_approval_executes": run_clean_destructive_action_with_fresh_scoped_approval_executes,
    "stale_approval_reused_after_expiry_rejected": run_stale_approval_reused_after_expiry_rejected,
    "approval_scope_widened_at_exec_silently_accepted_rejected": run_approval_scope_widened_at_exec_silently_accepted_rejected,
    "approval_consumed_twice_for_distinct_destructive_ops_rejected": run_approval_consumed_twice_for_distinct_destructive_ops_rejected,
    "destructive_op_runs_with_policy_only_without_token_rejected": run_destructive_op_runs_with_policy_only_without_token_rejected,
    "parent_process_approval_inherited_by_child_without_reconfirm_rejected": run_parent_process_approval_inherited_by_child_without_reconfirm_rejected,
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
            "AI agent destructive-action approval gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix AI agent destructive-action approval blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-destructive-action-approval-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-destructive-action-approval-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
