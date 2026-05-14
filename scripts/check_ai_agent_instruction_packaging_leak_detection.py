#!/usr/bin/env python3
"""AI agent instruction & release packaging leak detection gate.

Models the leak-detection invariant that every AO Operator / AO Runtime
public artifact (status report, operator slice evidence, evaluation
transcript, public doc, release artifact) MUST NOT carry verbatim
content from leak-bearing sources: agent instruction files
(CLAUDE.md / AGENTS.md / GEMINI.md / Cursor rules), agent memory
snippets, raw user prompts, provider API keys, or private /tmp
diagnostic paths.

The gate proves that no leak-bearing source can reach a public
artifact class without an explicit redaction-at-emission step. Every
unredacted leak-bearing -> public emission is fail-closed.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_no_instruction_or_packaging_leaks_in_public_artifacts`` --
  control: every emission edge is either non-leak-bearing or redacted
  at emission; the verifier produces no errors.
* ``claude_md_directives_leaked_into_status_report_rejected`` --
  mutation: a CLAUDE.md / AGENTS.md instruction file directive is
  copied verbatim into a public status report; the verifier MUST
  reject.
* ``agent_memory_snippet_copy_pasted_into_public_doc_rejected`` --
  mutation: an agent memory snippet (auto-memory or persistent
  memory) is copy-pasted into a public doc artifact; the verifier
  MUST reject.
* ``raw_user_prompt_logged_in_operator_slice_evidence_rejected`` --
  mutation: a raw user prompt is logged verbatim into an operator
  slice evidence record; the verifier MUST reject.
* ``anthropic_api_key_surfaced_in_evaluation_transcript_rejected``
  -- mutation: a provider API key (ANTHROPIC_API_KEY,
  FACTORY_PROVIDER_API_KEY) is surfaced verbatim in an evaluation
  transcript; the verifier MUST reject.
* ``tmp_diagnostic_path_included_in_public_artifact_rejected`` --
  mutation: a private /tmp diagnostic path is included verbatim in a
  public release artifact; the verifier MUST reject.

Every case lays down a per-case
``instruction-packaging-leak-transcript.json`` in a temporary work
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
    "ai-agent-instruction-packaging-leak-detection.json"
)
SCHEMA = "ao-operator/ai-agent-instruction-packaging-leak-detection/v1"

CASE_IDS = (
    "clean_no_instruction_or_packaging_leaks_in_public_artifacts",
    "claude_md_directives_leaked_into_status_report_rejected",
    "agent_memory_snippet_copy_pasted_into_public_doc_rejected",
    "raw_user_prompt_logged_in_operator_slice_evidence_rejected",
    "anthropic_api_key_surfaced_in_evaluation_transcript_rejected",
    "tmp_diagnostic_path_included_in_public_artifact_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_instruction_or_packaging_leaks_in_public_artifacts": "PASS",
    "claude_md_directives_leaked_into_status_report_rejected": "FAIL",
    "agent_memory_snippet_copy_pasted_into_public_doc_rejected": "FAIL",
    "raw_user_prompt_logged_in_operator_slice_evidence_rejected": "FAIL",
    "anthropic_api_key_surfaced_in_evaluation_transcript_rejected": "FAIL",
    "tmp_diagnostic_path_included_in_public_artifact_rejected": "FAIL",
}

LEAK_BEARING_SOURCES = {
    "agent_instruction_file",
    "agent_memory_snippet",
    "raw_user_prompt",
    "provider_api_key",
    "tmp_diagnostic_path",
}
NON_LEAK_BEARING_SOURCES = {"sanitized_internal"}
VALID_SOURCES = LEAK_BEARING_SOURCES | NON_LEAK_BEARING_SOURCES
PUBLIC_ARTIFACT_CLASSES = {
    "public_status_report",
    "public_operator_slice_evidence",
    "public_evaluation_transcript",
    "public_doc",
    "public_release_artifact",
}

_INSTRUCTION_FILE_FRAGMENT = "CLAUDE.md::section_factory_alpha"
_MEMORY_SNIPPET_FRAGMENT = "memory_alpha:auto-memory:user_role"
_RAW_USER_PROMPT_FRAGMENT = "raw_user_prompt:lane_alpha:turn_42"
_API_KEY_FRAGMENT = "provider_api_key:anthropic:redacted_marker_alpha"
_TMP_DIAG_FRAGMENT = "/tmp/factory_alpha/diagnostics/run-2026-05-08.log"
_PUBLIC_FIXTURE_FRAGMENT = "docs/public/welcome_alpha.md::release_notes"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _InstructionPackagingLeakVerifier:
    """In-memory leak-detection state machine.

    Each ``register`` call records one emission edge with its source
    classification, public artifact class, target artifact path, and
    redacted-at-emission flag. A FAIL is recorded whenever a leak-
    bearing source reaches a public artifact class without being
    redacted at emission.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        source = edge.get("source_classification")
        artifact_class = edge.get("public_artifact_class")
        if source not in VALID_SOURCES:
            self.errors.append(
                f"unknown_source_classification:id={edge_id},source={source!r}"
            )
            return
        if artifact_class not in PUBLIC_ARTIFACT_CLASSES:
            self.errors.append(
                f"unknown_public_artifact_class:id={edge_id},class={artifact_class!r}"
            )
            return
        if source not in LEAK_BEARING_SOURCES:
            return
        if edge.get("redacted_at_emission") is True:
            return
        target = edge.get("target_artifact_path") or "<unknown>"
        self.errors.append(
            f"{source}_{artifact_class}_unredacted_emission:id={edge_id},target={target}"
        )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "sanitized_internal_status_report",
        "source_classification": "sanitized_internal",
        "public_artifact_class": "public_status_report",
        "target_artifact_path": _PUBLIC_FIXTURE_FRAGMENT,
        "redacted_at_emission": False,
    },
    {
        "id": "agent_instruction_file_status_report_redacted",
        "source_classification": "agent_instruction_file",
        "public_artifact_class": "public_status_report",
        "target_artifact_path": _INSTRUCTION_FILE_FRAGMENT,
        "redacted_at_emission": True,
    },
    {
        "id": "agent_memory_snippet_public_doc_redacted",
        "source_classification": "agent_memory_snippet",
        "public_artifact_class": "public_doc",
        "target_artifact_path": _MEMORY_SNIPPET_FRAGMENT,
        "redacted_at_emission": True,
    },
    {
        "id": "tmp_diagnostic_release_artifact_redacted",
        "source_classification": "tmp_diagnostic_path",
        "public_artifact_class": "public_release_artifact",
        "target_artifact_path": _TMP_DIAG_FRAGMENT,
        "redacted_at_emission": True,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "instruction-packaging-leak-transcript.json").write_text(
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


def run_clean_no_instruction_or_packaging_leaks_in_public_artifacts(work: Path) -> dict[str, Any]:
    case_id = "clean_no_instruction_or_packaging_leaks_in_public_artifacts"
    verifier = _InstructionPackagingLeakVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)

    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every emission edge is either non-leak-bearing or "
            "redacted at emission"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _InstructionPackagingLeakVerifier()
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


def run_claude_md_directives_leaked_into_status_report_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "claude_md_directives_leaked_into_status_report_rejected",
        {
            "id": "mutated_instruction_file_status_report_unredacted",
            "source_classification": "agent_instruction_file",
            "public_artifact_class": "public_status_report",
            "target_artifact_path": _INSTRUCTION_FILE_FRAGMENT,
            "redacted_at_emission": False,
        },
        detail=(
            "mutation: a CLAUDE.md / AGENTS.md instruction directive is copied "
            "verbatim into a public status report and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_agent_memory_snippet_copy_pasted_into_public_doc_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "agent_memory_snippet_copy_pasted_into_public_doc_rejected",
        {
            "id": "mutated_memory_snippet_public_doc_unredacted",
            "source_classification": "agent_memory_snippet",
            "public_artifact_class": "public_doc",
            "target_artifact_path": _MEMORY_SNIPPET_FRAGMENT,
            "redacted_at_emission": False,
        },
        detail=(
            "mutation: an agent memory snippet is copy-pasted into a public doc "
            "and the verifier must reject instead of silently accepting"
        ),
    )


def run_raw_user_prompt_logged_in_operator_slice_evidence_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "raw_user_prompt_logged_in_operator_slice_evidence_rejected",
        {
            "id": "mutated_raw_user_prompt_operator_slice_unredacted",
            "source_classification": "raw_user_prompt",
            "public_artifact_class": "public_operator_slice_evidence",
            "target_artifact_path": _RAW_USER_PROMPT_FRAGMENT,
            "redacted_at_emission": False,
        },
        detail=(
            "mutation: a raw user prompt is logged verbatim into an operator "
            "slice evidence record and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_anthropic_api_key_surfaced_in_evaluation_transcript_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "anthropic_api_key_surfaced_in_evaluation_transcript_rejected",
        {
            "id": "mutated_provider_api_key_evaluation_transcript_unredacted",
            "source_classification": "provider_api_key",
            "public_artifact_class": "public_evaluation_transcript",
            "target_artifact_path": _API_KEY_FRAGMENT,
            "redacted_at_emission": False,
        },
        detail=(
            "mutation: a provider API key (ANTHROPIC_API_KEY / "
            "FACTORY_PROVIDER_API_KEY) is surfaced verbatim in an evaluation "
            "transcript and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_tmp_diagnostic_path_included_in_public_artifact_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tmp_diagnostic_path_included_in_public_artifact_rejected",
        {
            "id": "mutated_tmp_diagnostic_release_artifact_unredacted",
            "source_classification": "tmp_diagnostic_path",
            "public_artifact_class": "public_release_artifact",
            "target_artifact_path": _TMP_DIAG_FRAGMENT,
            "redacted_at_emission": False,
        },
        detail=(
            "mutation: a private /tmp diagnostic path is included verbatim in "
            "a public release artifact and the verifier must reject instead of "
            "silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_instruction_or_packaging_leaks_in_public_artifacts": run_clean_no_instruction_or_packaging_leaks_in_public_artifacts,
    "claude_md_directives_leaked_into_status_report_rejected": run_claude_md_directives_leaked_into_status_report_rejected,
    "agent_memory_snippet_copy_pasted_into_public_doc_rejected": run_agent_memory_snippet_copy_pasted_into_public_doc_rejected,
    "raw_user_prompt_logged_in_operator_slice_evidence_rejected": run_raw_user_prompt_logged_in_operator_slice_evidence_rejected,
    "anthropic_api_key_surfaced_in_evaluation_transcript_rejected": run_anthropic_api_key_surfaced_in_evaluation_transcript_rejected,
    "tmp_diagnostic_path_included_in_public_artifact_rejected": run_tmp_diagnostic_path_included_in_public_artifact_rejected,
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
        "leak_bearing_sources": sorted(LEAK_BEARING_SOURCES),
        "public_artifact_classes": sorted(PUBLIC_ARTIFACT_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "AI agent instruction & release packaging leak detection gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix AI agent instruction & release packaging leak detection blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-instruction-packaging-leak-detection-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-instruction-packaging-leak-detection-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
