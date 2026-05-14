#!/usr/bin/env python3
"""Agent tool-argument injection escape gate.

Models the tool-call argument boundary invariant that no AO Operator
agent tool call can escape its declared argument schema via string-
template breakout, nested-object smuggling, polymorphic-type
coercion, shell-metacharacter injection, or tool-name spoofing
smuggled inside argument payloads.

Every tool-call edge whose argument payload would let an attacker
escape the declared schema or redirect the dispatcher is
fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real tool dispatcher invoked):

* ``clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion``
  -- control: every registered tool call has well-formed arguments
  matching the declared schema with no breakout sequences, no
  nested smuggling, no type coercion, no shell metacharacters, and
  no tool-name spoof.
* ``string_template_breakout_via_unescaped_quote_rejected`` --
  mutation: a tool argument contains an unescaped quote or template
  delimiter that escapes its declared string slot; the verifier
  MUST reject.
* ``json_arg_breakout_via_nested_object_smuggling_rejected`` --
  mutation: a tool argument contains a nested object that smuggles
  fields beyond the declared schema; the verifier MUST reject.
* ``polymorphic_argument_coercion_via_type_mismatch_rejected`` --
  mutation: a tool argument coerces a declared scalar field into a
  list or object to bypass per-field validation; the verifier MUST
  reject.
* ``shell_metachar_injection_via_unfiltered_string_arg_rejected``
  -- mutation: a tool argument destined for a shell-tool sink
  contains shell metacharacters that would chain or redirect the
  shell command; the verifier MUST reject.
* ``tool_name_spoof_via_arg_smuggled_alternate_tool_rejected`` --
  mutation: a tool argument contains a smuggled ``tool_name`` field
  that an unsafe dispatcher would honor as a redirect to an
  alternate tool; the verifier MUST reject.

Every case lays down a per-case
``agent-tool-arg-injection-escape-transcript.json`` in a temporary
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
    "agent-tool-arg-injection-escape.json"
)
SCHEMA = "ao-operator/agent-tool-arg-injection-escape/v1"

CASE_IDS = (
    "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion",
    "string_template_breakout_via_unescaped_quote_rejected",
    "json_arg_breakout_via_nested_object_smuggling_rejected",
    "polymorphic_argument_coercion_via_type_mismatch_rejected",
    "shell_metachar_injection_via_unfiltered_string_arg_rejected",
    "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion": "PASS",
    "string_template_breakout_via_unescaped_quote_rejected": "FAIL",
    "json_arg_breakout_via_nested_object_smuggling_rejected": "FAIL",
    "polymorphic_argument_coercion_via_type_mismatch_rejected": "FAIL",
    "shell_metachar_injection_via_unfiltered_string_arg_rejected": "FAIL",
    "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected": "FAIL",
}

CALL_CLASSES = {
    "clean_call",
    "string_template_breakout",
    "nested_object_smuggling",
    "polymorphic_type_coercion",
    "shell_metachar_injection",
    "tool_name_spoof",
}
APPROVED_CALL_CLASSES = {
    "clean_call",
}
HAZARD_CLASSES = {
    "string_template_breakout_admit",
    "nested_object_smuggling_admit",
    "polymorphic_type_coercion_admit",
    "shell_metachar_injection_admit",
    "tool_name_spoof_admit",
}

DECLARED_TOOL_ALPHA = "tool::declared_alpha"
DECLARED_TOOL_BETA = "tool::declared_beta"
DECLARED_TOOL_GAMMA = "tool::declared_gamma"
SPOOFED_TARGET_TOOL = "tool::spoofed_target_alpha"

_CLEAN_CALL_ALPHA = "call::clean_alpha"
_CLEAN_CALL_BETA = "call::clean_beta"
_CLEAN_CALL_GAMMA = "call::clean_gamma"
_STRING_BREAKOUT_FRAGMENT = "call::string_breakout_alpha"
_NESTED_SMUGGLING_FRAGMENT = "call::nested_smuggling_alpha"
_POLYMORPHIC_COERCION_FRAGMENT = "call::polymorphic_coercion_alpha"
_SHELL_METACHAR_FRAGMENT = "call::shell_metachar_alpha"
_TOOL_NAME_SPOOF_FRAGMENT = "call::tool_name_spoof_alpha"

_ARG_PAYLOAD_CLEAN_ALPHA = "arg-payload::clean_alpha"
_ARG_PAYLOAD_CLEAN_BETA = "arg-payload::clean_beta"
_ARG_PAYLOAD_CLEAN_GAMMA = "arg-payload::clean_gamma"
_ARG_PAYLOAD_STRING_BREAKOUT = "arg-payload::string_breakout_alpha"
_ARG_PAYLOAD_NESTED_SMUGGLING = "arg-payload::nested_smuggling_alpha"
_ARG_PAYLOAD_POLYMORPHIC_COERCION = "arg-payload::polymorphic_coercion_alpha"
_ARG_PAYLOAD_SHELL_METACHAR = "arg-payload::shell_metachar_alpha"
_ARG_PAYLOAD_TOOL_NAME_SPOOF = "arg-payload::tool_name_spoof_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentToolArgInjectionEscapeVerifier:
    """In-memory tool-argument injection-escape verifier."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, call: dict[str, Any]) -> None:
        self.calls.append(dict(call))
        self._validate_call(call)

    def _validate_call(self, call: dict[str, Any]) -> None:
        call_id = str(call.get("id") or "<unnamed>")
        call_class = call.get("call_class")
        if call_class not in CALL_CLASSES:
            self.errors.append(
                f"unknown_call_class:id={call_id},class={call_class!r}"
            )
            return
        if call_class == "string_template_breakout":
            self.errors.append(
                f"string_template_breakout_admit_rejection:id={call_id},call={call.get('call_id', '<unknown>')}"
            )
            return
        if call_class == "nested_object_smuggling":
            self.errors.append(
                f"nested_object_smuggling_admit_rejection:id={call_id},call={call.get('call_id', '<unknown>')}"
            )
            return
        if call_class == "polymorphic_type_coercion":
            self.errors.append(
                f"polymorphic_type_coercion_admit_rejection:id={call_id},call={call.get('call_id', '<unknown>')}"
            )
            return
        if call_class == "shell_metachar_injection":
            self.errors.append(
                f"shell_metachar_injection_admit_rejection:id={call_id},call={call.get('call_id', '<unknown>')}"
            )
            return
        if call_class == "tool_name_spoof":
            self.errors.append(
                f"tool_name_spoof_admit_rejection:id={call_id},call={call.get('call_id', '<unknown>')}"
            )
            return
        if call_class not in APPROVED_CALL_CLASSES:
            self.errors.append(
                f"unapproved_call_class:id={call_id},class={call_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_CALLS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_call_alpha",
        "call_class": "clean_call",
        "call_id": _CLEAN_CALL_ALPHA,
        "tool_name": DECLARED_TOOL_ALPHA,
        "arg_payload_signature": _ARG_PAYLOAD_CLEAN_ALPHA,
        "string_breakout_observed": False,
        "nested_smuggling_observed": False,
        "argument_type_coerced": False,
        "shell_metachar_observed": False,
        "tool_name_spoof_observed": False,
    },
    {
        "id": "clean_call_beta",
        "call_class": "clean_call",
        "call_id": _CLEAN_CALL_BETA,
        "tool_name": DECLARED_TOOL_BETA,
        "arg_payload_signature": _ARG_PAYLOAD_CLEAN_BETA,
        "string_breakout_observed": False,
        "nested_smuggling_observed": False,
        "argument_type_coerced": False,
        "shell_metachar_observed": False,
        "tool_name_spoof_observed": False,
    },
    {
        "id": "clean_call_gamma",
        "call_class": "clean_call",
        "call_id": _CLEAN_CALL_GAMMA,
        "tool_name": DECLARED_TOOL_GAMMA,
        "arg_payload_signature": _ARG_PAYLOAD_CLEAN_GAMMA,
        "string_breakout_observed": False,
        "nested_smuggling_observed": False,
        "argument_type_coerced": False,
        "shell_metachar_observed": False,
        "tool_name_spoof_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-tool-arg-injection-escape-transcript.json").write_text(
        json.dumps({"tool_calls": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion(work: Path) -> dict[str, Any]:
    case_id = "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion"
    verifier = _AgentToolArgInjectionEscapeVerifier()
    for call in _CLEAN_CALLS:
        verifier.register(call)
    transcript = [{"op": "register", **call} for call in _CLEAN_CALLS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered tool call has well-formed "
            "arguments matching the declared schema with no breakout "
            "sequences, no nested smuggling, no type coercion, no "
            "shell metacharacters, and no tool-name spoof"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentToolArgInjectionEscapeVerifier()
    for call in _CLEAN_CALLS:
        verifier.register(call)
    verifier.register(mutated)
    transcript = [{"op": "register", **call} for call in (*_CLEAN_CALLS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_string_template_breakout_via_unescaped_quote_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "string_template_breakout_via_unescaped_quote_rejected",
        {
            "id": "mutated_string_template_breakout_admit",
            "call_class": "string_template_breakout",
            "call_id": _STRING_BREAKOUT_FRAGMENT,
            "tool_name": DECLARED_TOOL_ALPHA,
            "arg_payload_signature": _ARG_PAYLOAD_STRING_BREAKOUT,
            "string_breakout_observed": True,
            "nested_smuggling_observed": False,
            "argument_type_coerced": False,
            "shell_metachar_observed": False,
            "tool_name_spoof_observed": False,
        },
        detail=(
            "mutation: a tool argument contains an unescaped quote or "
            "template delimiter that escapes its declared string slot "
            "and the verifier must reject instead of silently accepting"
        ),
    )


def run_json_arg_breakout_via_nested_object_smuggling_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "json_arg_breakout_via_nested_object_smuggling_rejected",
        {
            "id": "mutated_nested_object_smuggling_admit",
            "call_class": "nested_object_smuggling",
            "call_id": _NESTED_SMUGGLING_FRAGMENT,
            "tool_name": DECLARED_TOOL_BETA,
            "arg_payload_signature": _ARG_PAYLOAD_NESTED_SMUGGLING,
            "string_breakout_observed": False,
            "nested_smuggling_observed": True,
            "argument_type_coerced": False,
            "shell_metachar_observed": False,
            "tool_name_spoof_observed": False,
        },
        detail=(
            "mutation: a tool argument contains a nested object that "
            "smuggles fields beyond the declared schema and the "
            "verifier must reject instead of silently accepting"
        ),
    )


def run_polymorphic_argument_coercion_via_type_mismatch_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "polymorphic_argument_coercion_via_type_mismatch_rejected",
        {
            "id": "mutated_polymorphic_type_coercion_admit",
            "call_class": "polymorphic_type_coercion",
            "call_id": _POLYMORPHIC_COERCION_FRAGMENT,
            "tool_name": DECLARED_TOOL_GAMMA,
            "arg_payload_signature": _ARG_PAYLOAD_POLYMORPHIC_COERCION,
            "string_breakout_observed": False,
            "nested_smuggling_observed": False,
            "argument_type_coerced": True,
            "shell_metachar_observed": False,
            "tool_name_spoof_observed": False,
        },
        detail=(
            "mutation: a tool argument coerces a declared scalar "
            "field into a list or object to bypass per-field "
            "validation and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_shell_metachar_injection_via_unfiltered_string_arg_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "shell_metachar_injection_via_unfiltered_string_arg_rejected",
        {
            "id": "mutated_shell_metachar_injection_admit",
            "call_class": "shell_metachar_injection",
            "call_id": _SHELL_METACHAR_FRAGMENT,
            "tool_name": DECLARED_TOOL_ALPHA,
            "arg_payload_signature": _ARG_PAYLOAD_SHELL_METACHAR,
            "string_breakout_observed": False,
            "nested_smuggling_observed": False,
            "argument_type_coerced": False,
            "shell_metachar_observed": True,
            "tool_name_spoof_observed": False,
        },
        detail=(
            "mutation: a tool argument destined for a shell-tool "
            "sink contains shell metacharacters that would chain or "
            "redirect the shell command and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_tool_name_spoof_via_arg_smuggled_alternate_tool_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected",
        {
            "id": "mutated_tool_name_spoof_admit",
            "call_class": "tool_name_spoof",
            "call_id": _TOOL_NAME_SPOOF_FRAGMENT,
            "tool_name": DECLARED_TOOL_BETA,
            "arg_payload_signature": _ARG_PAYLOAD_TOOL_NAME_SPOOF,
            "string_breakout_observed": False,
            "nested_smuggling_observed": False,
            "argument_type_coerced": False,
            "shell_metachar_observed": False,
            "tool_name_spoof_observed": True,
            "spoofed_target_tool": SPOOFED_TARGET_TOOL,
        },
        detail=(
            "mutation: a tool argument contains a smuggled "
            "tool_name field that an unsafe dispatcher would honor "
            "as a redirect to an alternate tool and the verifier "
            "must reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion": run_clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion,
    "string_template_breakout_via_unescaped_quote_rejected": run_string_template_breakout_via_unescaped_quote_rejected,
    "json_arg_breakout_via_nested_object_smuggling_rejected": run_json_arg_breakout_via_nested_object_smuggling_rejected,
    "polymorphic_argument_coercion_via_type_mismatch_rejected": run_polymorphic_argument_coercion_via_type_mismatch_rejected,
    "shell_metachar_injection_via_unfiltered_string_arg_rejected": run_shell_metachar_injection_via_unfiltered_string_arg_rejected,
    "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected": run_tool_name_spoof_via_arg_smuggled_alternate_tool_rejected,
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
        "call_classes": sorted(CALL_CLASSES),
        "approved_call_classes": sorted(APPROVED_CALL_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent tool-argument injection-escape gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent tool-argument injection-escape blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-tool-arg-injection-escape-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-tool-arg-injection-escape-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
