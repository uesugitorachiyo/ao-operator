#!/usr/bin/env python3
"""DeepSec diff-review advisory SAST gate.

Models the diff-review SAST invariant that no agent-generated diff
can introduce a tainted dataflow edge from an untrusted-input
source (user prompt, tool result, web fetch body, retrieved
content, agent-controlled path) to a dangerous sink (shell exec,
filesystem write outside the workspace, network egress, eval/exec,
dynamic import) without an explicit operator-approved sanitization
step.

Every untrusted -> dangerous-sink edge without a registered
sanitizer is fail-closed.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO, no real
SAST scanner invoked):

* ``clean_no_untrusted_to_dangerous_sink_edges`` -- control: every
  registered taint edge is either non-untrusted or carries an
  explicit operator-approved sanitizer; the verifier produces no
  errors.
* ``untrusted_input_flows_into_shell_command_rejected`` --
  mutation: an untrusted input flows into a shell-exec sink
  without sanitization; the verifier MUST reject.
* ``untrusted_input_flows_into_fs_write_outside_workspace_rejected``
  -- mutation: an untrusted input flows into a fs-write-outside-
  workspace sink without sanitization; the verifier MUST reject.
* ``untrusted_input_flows_into_network_egress_rejected`` --
  mutation: an untrusted input flows into a network-egress sink
  without sanitization; the verifier MUST reject.
* ``eval_or_exec_on_retrieved_content_rejected`` -- mutation: an
  untrusted retrieved-content payload flows into eval/exec without
  sanitization; the verifier MUST reject.
* ``dynamic_import_from_agent_controlled_path_rejected`` --
  mutation: an untrusted agent-controlled path flows into a
  dynamic-import sink without sanitization; the verifier MUST
  reject.

Every case lays down a per-case
``deepsec-diff-review-advisory-transcript.json`` in a temporary
work directory, runs it through the verifier embedded in this gate,
and records ``observed_verdict``. The gate's overall verdict is
``PASS`` only when every case lines up with the expected verdict.

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
    "deepsec-diff-review-advisory-sast.json"
)
SCHEMA = "ao-operator/deepsec-diff-review-advisory-sast/v1"

CASE_IDS = (
    "clean_no_untrusted_to_dangerous_sink_edges",
    "untrusted_input_flows_into_shell_command_rejected",
    "untrusted_input_flows_into_fs_write_outside_workspace_rejected",
    "untrusted_input_flows_into_network_egress_rejected",
    "eval_or_exec_on_retrieved_content_rejected",
    "dynamic_import_from_agent_controlled_path_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_untrusted_to_dangerous_sink_edges": "PASS",
    "untrusted_input_flows_into_shell_command_rejected": "FAIL",
    "untrusted_input_flows_into_fs_write_outside_workspace_rejected": "FAIL",
    "untrusted_input_flows_into_network_egress_rejected": "FAIL",
    "eval_or_exec_on_retrieved_content_rejected": "FAIL",
    "dynamic_import_from_agent_controlled_path_rejected": "FAIL",
}

UNTRUSTED_INPUT_SOURCES = {
    "user_prompt",
    "tool_result",
    "web_fetch_body",
    "retrieved_content",
    "agent_controlled_path",
}
NON_UNTRUSTED_SOURCES = {"sanitized_internal"}
VALID_SOURCES = UNTRUSTED_INPUT_SOURCES | NON_UNTRUSTED_SOURCES
DANGEROUS_SINKS = {
    "shell_exec",
    "fs_write_outside_workspace",
    "network_egress",
    "eval_exec",
    "dynamic_import",
}

_USER_PROMPT_FRAGMENT = "untrusted::user_prompt_alpha"
_TOOL_RESULT_FRAGMENT = "untrusted::tool_result_alpha"
_WEB_FETCH_FRAGMENT = "untrusted::web_fetch_alpha"
_RETRIEVED_FRAGMENT = "untrusted::retrieved_content_alpha"
_AGENT_PATH_FRAGMENT = "untrusted::agent_controlled_path_alpha"

_SHELL_EXEC_FRAGMENT = "sink::shell_exec_alpha"
_FS_WRITE_FRAGMENT = "sink::fs_write_outside_workspace_alpha"
_NETWORK_EGRESS_FRAGMENT = "sink::network_egress_alpha"
_EVAL_EXEC_FRAGMENT = "sink::eval_exec_alpha"
_DYNAMIC_IMPORT_FRAGMENT = "sink::dynamic_import_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _DeepSecDiffReviewSastVerifier:
    """In-memory diff-review SAST dataflow verifier.

    Each ``register`` call records one taint edge with its
    untrusted-input source, dangerous sink, sanitizer-applied flag,
    and synthetic diff path. A FAIL is recorded whenever an edge
    from an untrusted source reaches a dangerous sink without a
    registered sanitizer.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        source = edge.get("untrusted_input_source")
        sink = edge.get("dangerous_sink")
        if source not in VALID_SOURCES:
            self.errors.append(
                f"unknown_untrusted_input_source:id={edge_id},source={source!r}"
            )
            return
        if sink not in DANGEROUS_SINKS:
            self.errors.append(
                f"unknown_dangerous_sink:id={edge_id},sink={sink!r}"
            )
            return
        if source not in UNTRUSTED_INPUT_SOURCES:
            return
        if edge.get("sanitizer_applied") is True:
            return
        diff_path = edge.get("diff_path") or "<unknown>"
        self.errors.append(
            f"untrusted_to_{sink}_unsanitized_edge_rejection:id={edge_id},diff={diff_path}"
        )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "sanitized_internal_shell",
        "untrusted_input_source": "sanitized_internal",
        "dangerous_sink": "shell_exec",
        "sanitizer_applied": False,
        "diff_path": "diff::sanitized_internal_alpha",
    },
    {
        "id": "user_prompt_to_shell_with_sanitizer",
        "untrusted_input_source": "user_prompt",
        "dangerous_sink": "shell_exec",
        "sanitizer_applied": True,
        "diff_path": _USER_PROMPT_FRAGMENT,
    },
    {
        "id": "tool_result_to_fs_write_with_sanitizer",
        "untrusted_input_source": "tool_result",
        "dangerous_sink": "fs_write_outside_workspace",
        "sanitizer_applied": True,
        "diff_path": _TOOL_RESULT_FRAGMENT,
    },
    {
        "id": "web_fetch_to_network_egress_with_sanitizer",
        "untrusted_input_source": "web_fetch_body",
        "dangerous_sink": "network_egress",
        "sanitizer_applied": True,
        "diff_path": _WEB_FETCH_FRAGMENT,
    },
    {
        "id": "retrieved_content_to_eval_with_sanitizer",
        "untrusted_input_source": "retrieved_content",
        "dangerous_sink": "eval_exec",
        "sanitizer_applied": True,
        "diff_path": _RETRIEVED_FRAGMENT,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "deepsec-diff-review-advisory-transcript.json").write_text(
        json.dumps({"edges": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_untrusted_to_dangerous_sink_edges(work: Path) -> dict[str, Any]:
    case_id = "clean_no_untrusted_to_dangerous_sink_edges"
    verifier = _DeepSecDiffReviewSastVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered taint edge is either non-untrusted "
            "or carries an explicit operator-approved sanitizer"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _DeepSecDiffReviewSastVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    verifier.register(mutated)
    transcript = [{"op": "register", **edge} for edge in (*_CLEAN_EDGES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_untrusted_input_flows_into_shell_command_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "untrusted_input_flows_into_shell_command_rejected",
        {
            "id": "mutated_user_prompt_to_shell_unsanitized",
            "untrusted_input_source": "user_prompt",
            "dangerous_sink": "shell_exec",
            "sanitizer_applied": False,
            "diff_path": _SHELL_EXEC_FRAGMENT,
        },
        detail=(
            "mutation: an untrusted user prompt flows directly into a shell "
            "command without sanitization and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_untrusted_input_flows_into_fs_write_outside_workspace_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "untrusted_input_flows_into_fs_write_outside_workspace_rejected",
        {
            "id": "mutated_tool_result_to_fs_write_outside_workspace_unsanitized",
            "untrusted_input_source": "tool_result",
            "dangerous_sink": "fs_write_outside_workspace",
            "sanitizer_applied": False,
            "diff_path": _FS_WRITE_FRAGMENT,
        },
        detail=(
            "mutation: an untrusted tool result flows directly into a "
            "filesystem write outside the workspace without sanitization "
            "and the verifier must reject instead of silently accepting"
        ),
    )


def run_untrusted_input_flows_into_network_egress_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "untrusted_input_flows_into_network_egress_rejected",
        {
            "id": "mutated_web_fetch_to_network_egress_unsanitized",
            "untrusted_input_source": "web_fetch_body",
            "dangerous_sink": "network_egress",
            "sanitizer_applied": False,
            "diff_path": _NETWORK_EGRESS_FRAGMENT,
        },
        detail=(
            "mutation: an untrusted web-fetch body flows directly into "
            "network egress without sanitization and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_eval_or_exec_on_retrieved_content_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "eval_or_exec_on_retrieved_content_rejected",
        {
            "id": "mutated_retrieved_content_to_eval_exec_unsanitized",
            "untrusted_input_source": "retrieved_content",
            "dangerous_sink": "eval_exec",
            "sanitizer_applied": False,
            "diff_path": _EVAL_EXEC_FRAGMENT,
        },
        detail=(
            "mutation: an untrusted retrieved-content payload flows into "
            "eval/exec without sanitization and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_dynamic_import_from_agent_controlled_path_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "dynamic_import_from_agent_controlled_path_rejected",
        {
            "id": "mutated_agent_controlled_path_to_dynamic_import_unsanitized",
            "untrusted_input_source": "agent_controlled_path",
            "dangerous_sink": "dynamic_import",
            "sanitizer_applied": False,
            "diff_path": _DYNAMIC_IMPORT_FRAGMENT,
        },
        detail=(
            "mutation: an untrusted agent-controlled path flows into a "
            "dynamic import without sanitization and the verifier must "
            "reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_untrusted_to_dangerous_sink_edges": run_clean_no_untrusted_to_dangerous_sink_edges,
    "untrusted_input_flows_into_shell_command_rejected": run_untrusted_input_flows_into_shell_command_rejected,
    "untrusted_input_flows_into_fs_write_outside_workspace_rejected": run_untrusted_input_flows_into_fs_write_outside_workspace_rejected,
    "untrusted_input_flows_into_network_egress_rejected": run_untrusted_input_flows_into_network_egress_rejected,
    "eval_or_exec_on_retrieved_content_rejected": run_eval_or_exec_on_retrieved_content_rejected,
    "dynamic_import_from_agent_controlled_path_rejected": run_dynamic_import_from_agent_controlled_path_rejected,
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
        "untrusted_input_sources": sorted(UNTRUSTED_INPUT_SOURCES),
        "dangerous_sinks": sorted(DANGEROUS_SINKS),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "DeepSec diff-review advisory SAST gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix DeepSec diff-review advisory SAST blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-deepsec-diff-review-advisory-sast-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-deepsec-diff-review-advisory-sast-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
