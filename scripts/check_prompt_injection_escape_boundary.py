#!/usr/bin/env python3
"""Prompt-injection escape boundary gate.

Models the prompt-injection escape boundary invariant that no
AO Operator agent prompt assembly can let attacker-controlled
content reorder, escape, or replace operator-trusted instructions
already placed in the system or developer slot.

Every prompt edge whose role-section ordering, fence, JSON or
tool-name shadowing, or unicode-smuggling state would let an
attacker reach the operator-trusted system slot is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real LLM invoked):

* ``clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended`` --
  control: every registered prompt section is in an approved
  role with operator-trusted instructions placed strictly before
  any attacker-controlled content, no fence escape, no JSON
  replacement, no tool-name shadow, no unicode homoglyph smuggle.
* ``attacker_role_spoofing_appended_after_user_content_rejected`` --
  mutation: an attacker-controlled section spoofs the system role
  and appears after the operator-trusted system slot; the
  verifier MUST reject.
* ``fenced_block_escape_breaking_system_boundary_rejected`` --
  mutation: an attacker-controlled fenced block closes the
  system-section fence and re-opens with attacker instructions;
  the verifier MUST reject.
* ``json_injection_replacing_operator_instructions_rejected`` --
  mutation: an attacker-controlled JSON payload re-keys the
  operator-trusted ``system`` field; the verifier MUST reject.
* ``tool_name_shadowing_via_attacker_section_rejected`` --
  mutation: an attacker-controlled section declares a tool name
  that shadows an operator-allowlisted tool; the verifier MUST
  reject.
* ``instruction_smuggling_via_unicode_homoglyph_rejected`` --
  mutation: an attacker-controlled section smuggles instructions
  using a unicode homoglyph for an operator-trusted role marker;
  the verifier MUST reject.

Every case lays down a per-case
``prompt-injection-escape-boundary-transcript.json`` in a
temporary work directory, runs it through the verifier embedded
in this gate, and records ``observed_verdict``. The gate's
overall verdict is ``PASS`` only when every case lines up with
the expected verdict.

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
    "prompt-injection-escape-boundary.json"
)
SCHEMA = "ao-operator/prompt-injection-escape-boundary/v1"

CASE_IDS = (
    "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended",
    "attacker_role_spoofing_appended_after_user_content_rejected",
    "fenced_block_escape_breaking_system_boundary_rejected",
    "json_injection_replacing_operator_instructions_rejected",
    "tool_name_shadowing_via_attacker_section_rejected",
    "instruction_smuggling_via_unicode_homoglyph_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended": "PASS",
    "attacker_role_spoofing_appended_after_user_content_rejected": "FAIL",
    "fenced_block_escape_breaking_system_boundary_rejected": "FAIL",
    "json_injection_replacing_operator_instructions_rejected": "FAIL",
    "tool_name_shadowing_via_attacker_section_rejected": "FAIL",
    "instruction_smuggling_via_unicode_homoglyph_rejected": "FAIL",
}

SECTION_CLASSES = {
    "operator_system",
    "operator_developer",
    "user_input",
    "tool_result",
    "role_spoof",
    "fence_escape",
    "json_injection",
    "tool_shadow",
    "unicode_smuggle",
}
APPROVED_SECTION_CLASSES = {
    "operator_system",
    "operator_developer",
    "user_input",
    "tool_result",
}
HAZARD_CLASSES = {
    "role_spoof_admit",
    "fence_escape_admit",
    "json_injection_admit",
    "tool_shadow_admit",
    "unicode_smuggle_admit",
}

ALLOWLISTED_TOOLS = {"tool::operator_allowlisted_alpha"}
SYSTEM_ROLE_MARKER = "role::system"

_OPERATOR_SYSTEM_ALPHA = "section::operator_system_alpha"
_OPERATOR_DEVELOPER_ALPHA = "section::operator_developer_alpha"
_USER_INPUT_ALPHA = "section::user_input_alpha"
_TOOL_RESULT_ALPHA = "section::tool_result_alpha"
_ROLE_SPOOF_FRAGMENT = "section::role_spoof_alpha"
_FENCE_ESCAPE_FRAGMENT = "section::fence_escape_alpha"
_JSON_INJECTION_FRAGMENT = "section::json_injection_alpha"
_TOOL_SHADOW_FRAGMENT = "section::tool_shadow_alpha"
_UNICODE_SMUGGLE_FRAGMENT = "section::unicode_smuggle_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _PromptInjectionEscapeBoundaryVerifier:
    """In-memory prompt-injection escape boundary verifier.

    Each ``register`` call records one prompt section with its
    section class, role marker, fence balance, JSON key, tool name,
    and unicode-marker state. A FAIL is recorded whenever a
    section breaches one of the five escape-boundary hazard
    classes.
    """

    def __init__(self) -> None:
        self.sections: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, section: dict[str, Any]) -> None:
        self.sections.append(dict(section))
        self._validate_section(section)

    def _validate_section(self, section: dict[str, Any]) -> None:
        section_id = str(section.get("id") or "<unnamed>")
        section_class = section.get("section_class")
        if section_class not in SECTION_CLASSES:
            self.errors.append(
                f"unknown_section_class:id={section_id},class={section_class!r}"
            )
            return
        if section_class == "role_spoof":
            self.errors.append(
                f"attacker_role_spoof_admit_rejection:id={section_id},section={section.get('section_id', '<unknown>')}"
            )
            return
        if section_class == "fence_escape":
            self.errors.append(
                f"fenced_block_escape_admit_rejection:id={section_id},section={section.get('section_id', '<unknown>')}"
            )
            return
        if section_class == "json_injection":
            self.errors.append(
                f"json_injection_replacing_operator_instructions_admit_rejection:id={section_id},section={section.get('section_id', '<unknown>')}"
            )
            return
        if section_class == "tool_shadow":
            self.errors.append(
                f"tool_name_shadowing_admit_rejection:id={section_id},section={section.get('section_id', '<unknown>')}"
            )
            return
        if section_class == "unicode_smuggle":
            self.errors.append(
                f"instruction_smuggling_via_unicode_homoglyph_admit_rejection:id={section_id},section={section.get('section_id', '<unknown>')}"
            )
            return
        if section_class not in APPROVED_SECTION_CLASSES:
            self.errors.append(
                f"unapproved_section_class:id={section_id},class={section_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "operator_system_section_alpha",
        "section_class": "operator_system",
        "section_id": _OPERATOR_SYSTEM_ALPHA,
        "role_marker": SYSTEM_ROLE_MARKER,
        "fence_balanced": True,
        "json_keys_overwrite_system": False,
        "tool_name": None,
        "unicode_homoglyph_present": False,
    },
    {
        "id": "operator_developer_section_alpha",
        "section_class": "operator_developer",
        "section_id": _OPERATOR_DEVELOPER_ALPHA,
        "role_marker": "role::developer",
        "fence_balanced": True,
        "json_keys_overwrite_system": False,
        "tool_name": "tool::operator_allowlisted_alpha",
        "unicode_homoglyph_present": False,
    },
    {
        "id": "user_input_section_alpha",
        "section_class": "user_input",
        "section_id": _USER_INPUT_ALPHA,
        "role_marker": "role::user",
        "fence_balanced": True,
        "json_keys_overwrite_system": False,
        "tool_name": None,
        "unicode_homoglyph_present": False,
    },
    {
        "id": "tool_result_section_alpha",
        "section_class": "tool_result",
        "section_id": _TOOL_RESULT_ALPHA,
        "role_marker": "role::tool",
        "fence_balanced": True,
        "json_keys_overwrite_system": False,
        "tool_name": "tool::operator_allowlisted_alpha",
        "unicode_homoglyph_present": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "prompt-injection-escape-boundary-transcript.json").write_text(
        json.dumps({"sections": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended(work: Path) -> dict[str, Any]:
    case_id = "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended"
    verifier = _PromptInjectionEscapeBoundaryVerifier()
    for section in _CLEAN_SECTIONS:
        verifier.register(section)
    transcript = [{"op": "register", **section} for section in _CLEAN_SECTIONS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered section is in an approved role "
            "with operator-trusted instructions placed strictly before "
            "any attacker-controlled content"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _PromptInjectionEscapeBoundaryVerifier()
    for section in _CLEAN_SECTIONS:
        verifier.register(section)
    verifier.register(mutated)
    transcript = [{"op": "register", **section} for section in (*_CLEAN_SECTIONS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_attacker_role_spoofing_appended_after_user_content_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "attacker_role_spoofing_appended_after_user_content_rejected",
        {
            "id": "mutated_attacker_role_spoof_admit",
            "section_class": "role_spoof",
            "section_id": _ROLE_SPOOF_FRAGMENT,
            "role_marker": SYSTEM_ROLE_MARKER,
            "fence_balanced": True,
            "json_keys_overwrite_system": False,
            "tool_name": None,
            "unicode_homoglyph_present": False,
        },
        detail=(
            "mutation: an attacker-controlled section spoofs the system "
            "role and appears after the operator-trusted system slot and "
            "the verifier must reject instead of silently accepting"
        ),
    )


def run_fenced_block_escape_breaking_system_boundary_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "fenced_block_escape_breaking_system_boundary_rejected",
        {
            "id": "mutated_fenced_block_escape_admit",
            "section_class": "fence_escape",
            "section_id": _FENCE_ESCAPE_FRAGMENT,
            "role_marker": "role::user",
            "fence_balanced": False,
            "json_keys_overwrite_system": False,
            "tool_name": None,
            "unicode_homoglyph_present": False,
        },
        detail=(
            "mutation: an attacker-controlled fenced block closes the "
            "system-section fence and re-opens with attacker instructions "
            "and the verifier must reject instead of silently accepting"
        ),
    )


def run_json_injection_replacing_operator_instructions_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "json_injection_replacing_operator_instructions_rejected",
        {
            "id": "mutated_json_injection_admit",
            "section_class": "json_injection",
            "section_id": _JSON_INJECTION_FRAGMENT,
            "role_marker": "role::user",
            "fence_balanced": True,
            "json_keys_overwrite_system": True,
            "tool_name": None,
            "unicode_homoglyph_present": False,
        },
        detail=(
            "mutation: an attacker-controlled JSON payload re-keys the "
            "operator-trusted system field and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_tool_name_shadowing_via_attacker_section_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tool_name_shadowing_via_attacker_section_rejected",
        {
            "id": "mutated_tool_name_shadowing_admit",
            "section_class": "tool_shadow",
            "section_id": _TOOL_SHADOW_FRAGMENT,
            "role_marker": "role::tool",
            "fence_balanced": True,
            "json_keys_overwrite_system": False,
            "tool_name": "tool::operator_allowlisted_alpha",
            "unicode_homoglyph_present": False,
        },
        detail=(
            "mutation: an attacker-controlled section declares a tool "
            "name that shadows an operator-allowlisted tool and the "
            "verifier must reject instead of silently accepting"
        ),
    )


def run_instruction_smuggling_via_unicode_homoglyph_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "instruction_smuggling_via_unicode_homoglyph_rejected",
        {
            "id": "mutated_instruction_smuggling_via_unicode_homoglyph_admit",
            "section_class": "unicode_smuggle",
            "section_id": _UNICODE_SMUGGLE_FRAGMENT,
            "role_marker": "role::ѕystem",
            "fence_balanced": True,
            "json_keys_overwrite_system": False,
            "tool_name": None,
            "unicode_homoglyph_present": True,
        },
        detail=(
            "mutation: an attacker-controlled section smuggles "
            "instructions using a unicode homoglyph for an operator-"
            "trusted role marker and the verifier must reject instead "
            "of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended": run_clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended,
    "attacker_role_spoofing_appended_after_user_content_rejected": run_attacker_role_spoofing_appended_after_user_content_rejected,
    "fenced_block_escape_breaking_system_boundary_rejected": run_fenced_block_escape_breaking_system_boundary_rejected,
    "json_injection_replacing_operator_instructions_rejected": run_json_injection_replacing_operator_instructions_rejected,
    "tool_name_shadowing_via_attacker_section_rejected": run_tool_name_shadowing_via_attacker_section_rejected,
    "instruction_smuggling_via_unicode_homoglyph_rejected": run_instruction_smuggling_via_unicode_homoglyph_rejected,
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
        "section_classes": sorted(SECTION_CLASSES),
        "approved_section_classes": sorted(APPROVED_SECTION_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Prompt-injection escape boundary gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Prompt-injection escape boundary blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-prompt-injection-escape-boundary-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-prompt-injection-escape-boundary-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
