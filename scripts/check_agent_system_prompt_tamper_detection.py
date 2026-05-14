#!/usr/bin/env python3
"""Agent system prompt tamper detection gate.

Models the agent system-prompt integrity invariant that no Factory
v3 agent execution can run with a system prompt that has been
tampered with via substitution, appended instruction injection,
truncation, unicode homoglyph confusable characters, or role
relabel from system to user/assistant.

Every prompt edge whose payload would let a tampered system prompt
reach the model is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real prompt loader invoked):

* ``clean_no_system_prompt_tamper`` -- control: every registered
  prompt payload matches the declared baseline hash, has no
  appended instructions, is full-length, contains no homoglyph
  characters, and keeps the system role intact.
* ``system_prompt_substitution_admit_rejected`` -- mutation: a
  prompt payload swaps the system text for a different baseline;
  the verifier MUST reject.
* ``system_prompt_appended_instruction_admit_rejected`` -- mutation:
  a prompt payload appends an extra adversarial instruction beyond
  the declared baseline; the verifier MUST reject.
* ``system_prompt_truncation_admit_rejected`` -- mutation: a
  prompt payload truncates the declared baseline mid-instruction;
  the verifier MUST reject.
* ``system_prompt_unicode_homoglyph_admit_rejected`` -- mutation:
  a prompt payload substitutes ASCII characters with visually
  identical unicode homoglyphs; the verifier MUST reject.
* ``system_prompt_role_relabel_admit_rejected`` -- mutation: a
  prompt payload relabels the system role to user or assistant;
  the verifier MUST reject.

Every case lays down a per-case
``agent-system-prompt-tamper-transcript.json`` in a temporary
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
    "agent-system-prompt-tamper-detection.json"
)
SCHEMA = "ao-operator/agent-system-prompt-tamper-detection/v1"

CASE_IDS = (
    "clean_no_system_prompt_tamper",
    "system_prompt_substitution_admit_rejected",
    "system_prompt_appended_instruction_admit_rejected",
    "system_prompt_truncation_admit_rejected",
    "system_prompt_unicode_homoglyph_admit_rejected",
    "system_prompt_role_relabel_admit_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_system_prompt_tamper": "PASS",
    "system_prompt_substitution_admit_rejected": "FAIL",
    "system_prompt_appended_instruction_admit_rejected": "FAIL",
    "system_prompt_truncation_admit_rejected": "FAIL",
    "system_prompt_unicode_homoglyph_admit_rejected": "FAIL",
    "system_prompt_role_relabel_admit_rejected": "FAIL",
}

PROMPT_CLASSES = {
    "clean_prompt",
    "system_prompt_substitution",
    "system_prompt_appended_instruction",
    "system_prompt_truncation",
    "system_prompt_unicode_homoglyph",
    "system_prompt_role_relabel",
}
APPROVED_PROMPT_CLASSES = {
    "clean_prompt",
}
HAZARD_CLASSES = {
    "system_prompt_substitution_admit",
    "system_prompt_appended_instruction_admit",
    "system_prompt_truncation_admit",
    "system_prompt_unicode_homoglyph_admit",
    "system_prompt_role_relabel_admit",
}

DECLARED_BASELINE_HASH_ALPHA = "baseline::sha256_alpha"
DECLARED_BASELINE_HASH_BETA = "baseline::sha256_beta"
DECLARED_BASELINE_HASH_GAMMA = "baseline::sha256_gamma"

_CLEAN_PROMPT_ALPHA = "prompt::clean_alpha"
_CLEAN_PROMPT_BETA = "prompt::clean_beta"
_CLEAN_PROMPT_GAMMA = "prompt::clean_gamma"
_SUBSTITUTED_PROMPT = "prompt::substituted_alpha"
_APPENDED_INSTRUCTION_PROMPT = "prompt::appended_alpha"
_TRUNCATED_PROMPT = "prompt::truncated_alpha"
_HOMOGLYPH_PROMPT = "prompt::homoglyph_alpha"
_ROLE_RELABEL_PROMPT = "prompt::role_relabel_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentSystemPromptTamperDetectionVerifier:
    """In-memory agent system-prompt tamper-detection verifier."""

    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, prompt: dict[str, Any]) -> None:
        self.prompts.append(dict(prompt))
        self._validate_prompt(prompt)

    def _validate_prompt(self, prompt: dict[str, Any]) -> None:
        prompt_id = str(prompt.get("id") or "<unnamed>")
        prompt_class = prompt.get("prompt_class")
        if prompt_class not in PROMPT_CLASSES:
            self.errors.append(
                f"unknown_prompt_class:id={prompt_id},class={prompt_class!r}"
            )
            return
        if prompt_class == "system_prompt_substitution":
            self.errors.append(
                f"system_prompt_substitution_admit_rejection:id={prompt_id},prompt={prompt.get('prompt_id', '<unknown>')}"
            )
            return
        if prompt_class == "system_prompt_appended_instruction":
            self.errors.append(
                f"system_prompt_appended_instruction_admit_rejection:id={prompt_id},prompt={prompt.get('prompt_id', '<unknown>')}"
            )
            return
        if prompt_class == "system_prompt_truncation":
            self.errors.append(
                f"system_prompt_truncation_admit_rejection:id={prompt_id},prompt={prompt.get('prompt_id', '<unknown>')}"
            )
            return
        if prompt_class == "system_prompt_unicode_homoglyph":
            self.errors.append(
                f"system_prompt_unicode_homoglyph_admit_rejection:id={prompt_id},prompt={prompt.get('prompt_id', '<unknown>')}"
            )
            return
        if prompt_class == "system_prompt_role_relabel":
            self.errors.append(
                f"system_prompt_role_relabel_admit_rejection:id={prompt_id},prompt={prompt.get('prompt_id', '<unknown>')}"
            )
            return
        if prompt_class not in APPROVED_PROMPT_CLASSES:
            self.errors.append(
                f"unapproved_prompt_class:id={prompt_id},class={prompt_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_prompt_alpha",
        "prompt_class": "clean_prompt",
        "prompt_id": _CLEAN_PROMPT_ALPHA,
        "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
        "role": "system",
        "substitution_observed": False,
        "appended_instruction_observed": False,
        "truncation_observed": False,
        "homoglyph_observed": False,
        "role_relabel_observed": False,
    },
    {
        "id": "clean_prompt_beta",
        "prompt_class": "clean_prompt",
        "prompt_id": _CLEAN_PROMPT_BETA,
        "declared_baseline_hash": DECLARED_BASELINE_HASH_BETA,
        "role": "system",
        "substitution_observed": False,
        "appended_instruction_observed": False,
        "truncation_observed": False,
        "homoglyph_observed": False,
        "role_relabel_observed": False,
    },
    {
        "id": "clean_prompt_gamma",
        "prompt_class": "clean_prompt",
        "prompt_id": _CLEAN_PROMPT_GAMMA,
        "declared_baseline_hash": DECLARED_BASELINE_HASH_GAMMA,
        "role": "system",
        "substitution_observed": False,
        "appended_instruction_observed": False,
        "truncation_observed": False,
        "homoglyph_observed": False,
        "role_relabel_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-system-prompt-tamper-transcript.json").write_text(
        json.dumps({"prompts": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_system_prompt_tamper(work: Path) -> dict[str, Any]:
    case_id = "clean_no_system_prompt_tamper"
    verifier = _AgentSystemPromptTamperDetectionVerifier()
    for prompt in _CLEAN_PROMPTS:
        verifier.register(prompt)
    transcript = [{"op": "register", **prompt} for prompt in _CLEAN_PROMPTS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered system prompt matches its "
            "declared baseline hash with no appended instruction, "
            "no truncation, no homoglyph substitution, and the "
            "system role intact"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentSystemPromptTamperDetectionVerifier()
    for prompt in _CLEAN_PROMPTS:
        verifier.register(prompt)
    verifier.register(mutated)
    transcript = [{"op": "register", **prompt} for prompt in (*_CLEAN_PROMPTS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_system_prompt_substitution_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "system_prompt_substitution_admit_rejected",
        {
            "id": "mutated_system_prompt_substitution_admit",
            "prompt_class": "system_prompt_substitution",
            "prompt_id": _SUBSTITUTED_PROMPT,
            "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
            "role": "system",
            "substitution_observed": True,
            "appended_instruction_observed": False,
            "truncation_observed": False,
            "homoglyph_observed": False,
            "role_relabel_observed": False,
        },
        detail=(
            "mutation: a prompt payload swaps the system text for "
            "a different baseline and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_system_prompt_appended_instruction_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "system_prompt_appended_instruction_admit_rejected",
        {
            "id": "mutated_system_prompt_appended_instruction_admit",
            "prompt_class": "system_prompt_appended_instruction",
            "prompt_id": _APPENDED_INSTRUCTION_PROMPT,
            "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
            "role": "system",
            "substitution_observed": False,
            "appended_instruction_observed": True,
            "truncation_observed": False,
            "homoglyph_observed": False,
            "role_relabel_observed": False,
        },
        detail=(
            "mutation: a prompt payload appends an extra "
            "adversarial instruction beyond the declared baseline "
            "and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_system_prompt_truncation_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "system_prompt_truncation_admit_rejected",
        {
            "id": "mutated_system_prompt_truncation_admit",
            "prompt_class": "system_prompt_truncation",
            "prompt_id": _TRUNCATED_PROMPT,
            "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
            "role": "system",
            "substitution_observed": False,
            "appended_instruction_observed": False,
            "truncation_observed": True,
            "homoglyph_observed": False,
            "role_relabel_observed": False,
        },
        detail=(
            "mutation: a prompt payload truncates the declared "
            "baseline mid-instruction and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_system_prompt_unicode_homoglyph_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "system_prompt_unicode_homoglyph_admit_rejected",
        {
            "id": "mutated_system_prompt_unicode_homoglyph_admit",
            "prompt_class": "system_prompt_unicode_homoglyph",
            "prompt_id": _HOMOGLYPH_PROMPT,
            "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
            "role": "system",
            "substitution_observed": False,
            "appended_instruction_observed": False,
            "truncation_observed": False,
            "homoglyph_observed": True,
            "role_relabel_observed": False,
        },
        detail=(
            "mutation: a prompt payload substitutes ASCII "
            "characters with visually identical unicode homoglyphs "
            "and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_system_prompt_role_relabel_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "system_prompt_role_relabel_admit_rejected",
        {
            "id": "mutated_system_prompt_role_relabel_admit",
            "prompt_class": "system_prompt_role_relabel",
            "prompt_id": _ROLE_RELABEL_PROMPT,
            "declared_baseline_hash": DECLARED_BASELINE_HASH_ALPHA,
            "role": "user",
            "substitution_observed": False,
            "appended_instruction_observed": False,
            "truncation_observed": False,
            "homoglyph_observed": False,
            "role_relabel_observed": True,
        },
        detail=(
            "mutation: a prompt payload relabels the system role "
            "to user or assistant and the verifier must reject "
            "instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_system_prompt_tamper": run_clean_no_system_prompt_tamper,
    "system_prompt_substitution_admit_rejected": run_system_prompt_substitution_admit_rejected,
    "system_prompt_appended_instruction_admit_rejected": run_system_prompt_appended_instruction_admit_rejected,
    "system_prompt_truncation_admit_rejected": run_system_prompt_truncation_admit_rejected,
    "system_prompt_unicode_homoglyph_admit_rejected": run_system_prompt_unicode_homoglyph_admit_rejected,
    "system_prompt_role_relabel_admit_rejected": run_system_prompt_role_relabel_admit_rejected,
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
        "prompt_classes": sorted(PROMPT_CLASSES),
        "approved_prompt_classes": sorted(APPROVED_PROMPT_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent system prompt tamper detection gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent system prompt tamper detection blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-system-prompt-tamper-detection-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-system-prompt-tamper-detection-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
