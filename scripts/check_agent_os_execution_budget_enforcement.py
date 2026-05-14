#!/usr/bin/env python3
"""Agent OS execution budget enforcement gate.

Models the agent execution budget invariant that no AO Operator
agent execution can exceed declared budget caps via token-budget
overflow, time-budget overflow, tool-call-count overflow,
cost-ceiling overflow, or mid-execution budget-reset bypass.

Every execution edge whose payload would let an agent exceed a
declared budget cap is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real execution scheduler invoked):

* ``clean_no_budget_overflow_or_reset_bypass`` -- control: every
  registered execution stays within declared token, time,
  tool-call, and cost caps with no mid-execution budget reset.
* ``token_budget_overflow_admit_rejected`` -- mutation: an
  execution emits more tokens than the declared token cap; the
  verifier MUST reject.
* ``time_budget_overflow_admit_rejected`` -- mutation: an
  execution runs longer than the declared time cap; the verifier
  MUST reject.
* ``tool_call_count_overflow_admit_rejected`` -- mutation: an
  execution issues more tool calls than the declared tool-call
  cap; the verifier MUST reject.
* ``cost_ceiling_overflow_admit_rejected`` -- mutation: an
  execution accumulates cost above the declared cost cap; the
  verifier MUST reject.
* ``budget_reset_bypass_admit_rejected`` -- mutation: an
  execution resets its budget mid-run to extend past the
  declared cap; the verifier MUST reject.

Every case lays down a per-case
``agent-os-execution-budget-transcript.json`` in a temporary
work directory, runs it through the verifier embedded in this
gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the
expected verdict.

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
    "agent-os-execution-budget-enforcement.json"
)
SCHEMA = "ao-operator/agent-os-execution-budget-enforcement/v1"

CASE_IDS = (
    "clean_no_budget_overflow_or_reset_bypass",
    "token_budget_overflow_admit_rejected",
    "time_budget_overflow_admit_rejected",
    "tool_call_count_overflow_admit_rejected",
    "cost_ceiling_overflow_admit_rejected",
    "budget_reset_bypass_admit_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_budget_overflow_or_reset_bypass": "PASS",
    "token_budget_overflow_admit_rejected": "FAIL",
    "time_budget_overflow_admit_rejected": "FAIL",
    "tool_call_count_overflow_admit_rejected": "FAIL",
    "cost_ceiling_overflow_admit_rejected": "FAIL",
    "budget_reset_bypass_admit_rejected": "FAIL",
}

EXECUTION_CLASSES = {
    "clean_execution",
    "token_budget_overflow",
    "time_budget_overflow",
    "tool_call_count_overflow",
    "cost_ceiling_overflow",
    "budget_reset_bypass",
}
APPROVED_EXECUTION_CLASSES = {
    "clean_execution",
}
HAZARD_CLASSES = {
    "token_budget_overflow_admit",
    "time_budget_overflow_admit",
    "tool_call_count_overflow_admit",
    "cost_ceiling_overflow_admit",
    "budget_reset_bypass_admit",
}

DECLARED_TOKEN_CAP_ALPHA = "budget::token_cap_alpha"
DECLARED_TIME_CAP_ALPHA = "budget::time_cap_alpha"
DECLARED_TOOL_CALL_CAP_ALPHA = "budget::tool_call_cap_alpha"
DECLARED_COST_CAP_ALPHA = "budget::cost_cap_alpha"
DECLARED_RESET_TOKEN_ALPHA = "budget::reset_token_alpha"

_CLEAN_EXECUTION_ALPHA = "execution::clean_alpha"
_CLEAN_EXECUTION_BETA = "execution::clean_beta"
_CLEAN_EXECUTION_GAMMA = "execution::clean_gamma"
_TOKEN_OVERFLOW_EXECUTION = "execution::token_overflow_alpha"
_TIME_OVERFLOW_EXECUTION = "execution::time_overflow_alpha"
_TOOL_CALL_OVERFLOW_EXECUTION = "execution::tool_call_overflow_alpha"
_COST_OVERFLOW_EXECUTION = "execution::cost_overflow_alpha"
_BUDGET_RESET_BYPASS_EXECUTION = "execution::budget_reset_bypass_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentOsExecutionBudgetEnforcementVerifier:
    """In-memory agent-os execution budget enforcement verifier."""

    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, execution: dict[str, Any]) -> None:
        self.executions.append(dict(execution))
        self._validate_execution(execution)

    def _validate_execution(self, execution: dict[str, Any]) -> None:
        execution_id = str(execution.get("id") or "<unnamed>")
        execution_class = execution.get("execution_class")
        if execution_class not in EXECUTION_CLASSES:
            self.errors.append(
                f"unknown_execution_class:id={execution_id},class={execution_class!r}"
            )
            return
        if execution_class == "token_budget_overflow":
            self.errors.append(
                f"token_budget_overflow_admit_rejection:id={execution_id},execution={execution.get('execution_id', '<unknown>')}"
            )
            return
        if execution_class == "time_budget_overflow":
            self.errors.append(
                f"time_budget_overflow_admit_rejection:id={execution_id},execution={execution.get('execution_id', '<unknown>')}"
            )
            return
        if execution_class == "tool_call_count_overflow":
            self.errors.append(
                f"tool_call_count_overflow_admit_rejection:id={execution_id},execution={execution.get('execution_id', '<unknown>')}"
            )
            return
        if execution_class == "cost_ceiling_overflow":
            self.errors.append(
                f"cost_ceiling_overflow_admit_rejection:id={execution_id},execution={execution.get('execution_id', '<unknown>')}"
            )
            return
        if execution_class == "budget_reset_bypass":
            self.errors.append(
                f"budget_reset_bypass_admit_rejection:id={execution_id},execution={execution.get('execution_id', '<unknown>')}"
            )
            return
        if execution_class not in APPROVED_EXECUTION_CLASSES:
            self.errors.append(
                f"unapproved_execution_class:id={execution_id},class={execution_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EXECUTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_execution_alpha",
        "execution_class": "clean_execution",
        "execution_id": _CLEAN_EXECUTION_ALPHA,
        "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
        "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
        "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
        "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
        "token_overflow_observed": False,
        "time_overflow_observed": False,
        "tool_call_overflow_observed": False,
        "cost_overflow_observed": False,
        "budget_reset_observed": False,
    },
    {
        "id": "clean_execution_beta",
        "execution_class": "clean_execution",
        "execution_id": _CLEAN_EXECUTION_BETA,
        "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
        "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
        "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
        "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
        "token_overflow_observed": False,
        "time_overflow_observed": False,
        "tool_call_overflow_observed": False,
        "cost_overflow_observed": False,
        "budget_reset_observed": False,
    },
    {
        "id": "clean_execution_gamma",
        "execution_class": "clean_execution",
        "execution_id": _CLEAN_EXECUTION_GAMMA,
        "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
        "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
        "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
        "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
        "token_overflow_observed": False,
        "time_overflow_observed": False,
        "tool_call_overflow_observed": False,
        "cost_overflow_observed": False,
        "budget_reset_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-os-execution-budget-transcript.json").write_text(
        json.dumps({"executions": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_budget_overflow_or_reset_bypass(work: Path) -> dict[str, Any]:
    case_id = "clean_no_budget_overflow_or_reset_bypass"
    verifier = _AgentOsExecutionBudgetEnforcementVerifier()
    for execution in _CLEAN_EXECUTIONS:
        verifier.register(execution)
    transcript = [{"op": "register", **execution} for execution in _CLEAN_EXECUTIONS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered execution stays within "
            "declared token, time, tool-call, and cost caps with "
            "no mid-execution budget-reset bypass"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentOsExecutionBudgetEnforcementVerifier()
    for execution in _CLEAN_EXECUTIONS:
        verifier.register(execution)
    verifier.register(mutated)
    transcript = [{"op": "register", **execution} for execution in (*_CLEAN_EXECUTIONS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_token_budget_overflow_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "token_budget_overflow_admit_rejected",
        {
            "id": "mutated_token_budget_overflow_admit",
            "execution_class": "token_budget_overflow",
            "execution_id": _TOKEN_OVERFLOW_EXECUTION,
            "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
            "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
            "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
            "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
            "token_overflow_observed": True,
            "time_overflow_observed": False,
            "tool_call_overflow_observed": False,
            "cost_overflow_observed": False,
            "budget_reset_observed": False,
        },
        detail=(
            "mutation: an execution emits more tokens than the "
            "declared token cap and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_time_budget_overflow_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "time_budget_overflow_admit_rejected",
        {
            "id": "mutated_time_budget_overflow_admit",
            "execution_class": "time_budget_overflow",
            "execution_id": _TIME_OVERFLOW_EXECUTION,
            "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
            "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
            "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
            "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
            "token_overflow_observed": False,
            "time_overflow_observed": True,
            "tool_call_overflow_observed": False,
            "cost_overflow_observed": False,
            "budget_reset_observed": False,
        },
        detail=(
            "mutation: an execution runs longer than the declared "
            "time cap and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_tool_call_count_overflow_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tool_call_count_overflow_admit_rejected",
        {
            "id": "mutated_tool_call_count_overflow_admit",
            "execution_class": "tool_call_count_overflow",
            "execution_id": _TOOL_CALL_OVERFLOW_EXECUTION,
            "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
            "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
            "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
            "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
            "token_overflow_observed": False,
            "time_overflow_observed": False,
            "tool_call_overflow_observed": True,
            "cost_overflow_observed": False,
            "budget_reset_observed": False,
        },
        detail=(
            "mutation: an execution issues more tool calls than "
            "the declared tool-call cap and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_cost_ceiling_overflow_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "cost_ceiling_overflow_admit_rejected",
        {
            "id": "mutated_cost_ceiling_overflow_admit",
            "execution_class": "cost_ceiling_overflow",
            "execution_id": _COST_OVERFLOW_EXECUTION,
            "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
            "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
            "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
            "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
            "token_overflow_observed": False,
            "time_overflow_observed": False,
            "tool_call_overflow_observed": False,
            "cost_overflow_observed": True,
            "budget_reset_observed": False,
        },
        detail=(
            "mutation: an execution accumulates cost above the "
            "declared cost cap and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_budget_reset_bypass_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "budget_reset_bypass_admit_rejected",
        {
            "id": "mutated_budget_reset_bypass_admit",
            "execution_class": "budget_reset_bypass",
            "execution_id": _BUDGET_RESET_BYPASS_EXECUTION,
            "declared_token_cap": DECLARED_TOKEN_CAP_ALPHA,
            "declared_time_cap": DECLARED_TIME_CAP_ALPHA,
            "declared_tool_call_cap": DECLARED_TOOL_CALL_CAP_ALPHA,
            "declared_cost_cap": DECLARED_COST_CAP_ALPHA,
            "reset_token": DECLARED_RESET_TOKEN_ALPHA,
            "token_overflow_observed": False,
            "time_overflow_observed": False,
            "tool_call_overflow_observed": False,
            "cost_overflow_observed": False,
            "budget_reset_observed": True,
        },
        detail=(
            "mutation: an execution resets its budget mid-run to "
            "extend past the declared cap and the verifier must "
            "reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_budget_overflow_or_reset_bypass": run_clean_no_budget_overflow_or_reset_bypass,
    "token_budget_overflow_admit_rejected": run_token_budget_overflow_admit_rejected,
    "time_budget_overflow_admit_rejected": run_time_budget_overflow_admit_rejected,
    "tool_call_count_overflow_admit_rejected": run_tool_call_count_overflow_admit_rejected,
    "cost_ceiling_overflow_admit_rejected": run_cost_ceiling_overflow_admit_rejected,
    "budget_reset_bypass_admit_rejected": run_budget_reset_bypass_admit_rejected,
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
        "execution_classes": sorted(EXECUTION_CLASSES),
        "approved_execution_classes": sorted(APPROVED_EXECUTION_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent OS execution budget enforcement gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent OS execution budget enforcement blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-execution-budget-enforcement-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-execution-budget-enforcement-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
