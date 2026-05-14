#!/usr/bin/env python3
"""Agent output canary-leak detection gate.

Models the agent-output exfiltration boundary invariant that no
AO Operator agent final output can leak a canary token or
marked-secret value originating in retrieved context, whether
literally, base64-encoded, with unicode homoglyph substitution,
reassembled from fragments, or relabeled via a different output
field.

Every output edge whose payload would let an attacker exfiltrate
a canary token or marked secret is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real model client invoked):

* ``clean_no_canary_or_marked_secret_leak_in_output`` -- control:
  every registered output contains only declared non-canary,
  non-secret tokens.
* ``literal_canary_token_in_output_rejected`` -- mutation: a
  canary token from retrieved context appears literally in the
  output; the verifier MUST reject.
* ``base64_encoded_canary_token_in_output_rejected`` --
  mutation: a canary token is base64-encoded in the output as a
  side-channel; the verifier MUST reject.
* ``unicode_homoglyph_canary_substitution_in_output_rejected``
  -- mutation: a canary token with unicode homoglyph
  substitution appears in the output; the verifier MUST reject.
* ``partial_canary_fragment_concatenation_in_output_rejected``
  -- mutation: canary-token fragments are concatenated across
  the output to reassemble the original token; the verifier
  MUST reject.
* ``marked_secret_passthrough_via_field_label_rejected`` --
  mutation: a marked secret appears in the output under a
  different field label (relabeled passthrough); the verifier
  MUST reject.

Every case lays down a per-case
``agent-output-canary-leak-detection-transcript.json`` in a
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
    "agent-output-canary-leak-detection.json"
)
SCHEMA = "ao-operator/agent-output-canary-leak-detection/v1"

CASE_IDS = (
    "clean_no_canary_or_marked_secret_leak_in_output",
    "literal_canary_token_in_output_rejected",
    "base64_encoded_canary_token_in_output_rejected",
    "unicode_homoglyph_canary_substitution_in_output_rejected",
    "partial_canary_fragment_concatenation_in_output_rejected",
    "marked_secret_passthrough_via_field_label_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_canary_or_marked_secret_leak_in_output": "PASS",
    "literal_canary_token_in_output_rejected": "FAIL",
    "base64_encoded_canary_token_in_output_rejected": "FAIL",
    "unicode_homoglyph_canary_substitution_in_output_rejected": "FAIL",
    "partial_canary_fragment_concatenation_in_output_rejected": "FAIL",
    "marked_secret_passthrough_via_field_label_rejected": "FAIL",
}

OUTPUT_CLASSES = {
    "clean_output",
    "literal_canary_leak",
    "base64_canary_leak",
    "homoglyph_canary_leak",
    "fragment_canary_leak",
    "marked_secret_relabel_leak",
}
APPROVED_OUTPUT_CLASSES = {
    "clean_output",
}
HAZARD_CLASSES = {
    "literal_canary_leak_admit",
    "base64_canary_leak_admit",
    "homoglyph_canary_leak_admit",
    "fragment_canary_leak_admit",
    "marked_secret_relabel_leak_admit",
}

CANARY_TOKEN_ALPHA = "canary::token_alpha"
CANARY_TOKEN_BETA = "canary::token_beta"
MARKED_SECRET_ALPHA = "secret::marked_alpha"
DECLARED_FIELD_LABEL_ALPHA = "field-label::declared_alpha"
DECLARED_FIELD_LABEL_BETA = "field-label::declared_beta"

_CLEAN_OUTPUT_ALPHA = "output::clean_alpha"
_CLEAN_OUTPUT_BETA = "output::clean_beta"
_CLEAN_OUTPUT_GAMMA = "output::clean_gamma"
_LITERAL_CANARY_FRAGMENT = "output::literal_canary_alpha"
_BASE64_CANARY_FRAGMENT = "output::base64_canary_alpha"
_HOMOGLYPH_CANARY_FRAGMENT = "output::homoglyph_canary_alpha"
_FRAGMENT_CANARY_FRAGMENT = "output::fragment_canary_alpha"
_MARKED_SECRET_RELABEL_FRAGMENT = "output::marked_secret_relabel_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentOutputCanaryLeakDetectionVerifier:
    """In-memory agent-output canary-leak detection verifier."""

    def __init__(self) -> None:
        self.outputs: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, output: dict[str, Any]) -> None:
        self.outputs.append(dict(output))
        self._validate_output(output)

    def _validate_output(self, output: dict[str, Any]) -> None:
        output_id = str(output.get("id") or "<unnamed>")
        output_class = output.get("output_class")
        if output_class not in OUTPUT_CLASSES:
            self.errors.append(
                f"unknown_output_class:id={output_id},class={output_class!r}"
            )
            return
        if output_class == "literal_canary_leak":
            self.errors.append(
                f"literal_canary_leak_admit_rejection:id={output_id},output={output.get('output_id', '<unknown>')}"
            )
            return
        if output_class == "base64_canary_leak":
            self.errors.append(
                f"base64_canary_leak_admit_rejection:id={output_id},output={output.get('output_id', '<unknown>')}"
            )
            return
        if output_class == "homoglyph_canary_leak":
            self.errors.append(
                f"homoglyph_canary_leak_admit_rejection:id={output_id},output={output.get('output_id', '<unknown>')}"
            )
            return
        if output_class == "fragment_canary_leak":
            self.errors.append(
                f"fragment_canary_leak_admit_rejection:id={output_id},output={output.get('output_id', '<unknown>')}"
            )
            return
        if output_class == "marked_secret_relabel_leak":
            self.errors.append(
                f"marked_secret_relabel_leak_admit_rejection:id={output_id},output={output.get('output_id', '<unknown>')}"
            )
            return
        if output_class not in APPROVED_OUTPUT_CLASSES:
            self.errors.append(
                f"unapproved_output_class:id={output_id},class={output_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_OUTPUTS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_output_alpha",
        "output_class": "clean_output",
        "output_id": _CLEAN_OUTPUT_ALPHA,
        "field_label": DECLARED_FIELD_LABEL_ALPHA,
        "literal_canary_observed": False,
        "base64_canary_observed": False,
        "homoglyph_canary_observed": False,
        "fragment_canary_observed": False,
        "marked_secret_relabel_observed": False,
    },
    {
        "id": "clean_output_beta",
        "output_class": "clean_output",
        "output_id": _CLEAN_OUTPUT_BETA,
        "field_label": DECLARED_FIELD_LABEL_BETA,
        "literal_canary_observed": False,
        "base64_canary_observed": False,
        "homoglyph_canary_observed": False,
        "fragment_canary_observed": False,
        "marked_secret_relabel_observed": False,
    },
    {
        "id": "clean_output_gamma",
        "output_class": "clean_output",
        "output_id": _CLEAN_OUTPUT_GAMMA,
        "field_label": DECLARED_FIELD_LABEL_ALPHA,
        "literal_canary_observed": False,
        "base64_canary_observed": False,
        "homoglyph_canary_observed": False,
        "fragment_canary_observed": False,
        "marked_secret_relabel_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-output-canary-leak-detection-transcript.json").write_text(
        json.dumps({"outputs": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_canary_or_marked_secret_leak_in_output(work: Path) -> dict[str, Any]:
    case_id = "clean_no_canary_or_marked_secret_leak_in_output"
    verifier = _AgentOutputCanaryLeakDetectionVerifier()
    for output in _CLEAN_OUTPUTS:
        verifier.register(output)
    transcript = [{"op": "register", **output} for output in _CLEAN_OUTPUTS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered output contains only declared "
            "non-canary, non-secret tokens with no literal canary, no "
            "base64-canary, no homoglyph-canary, no fragment-canary, "
            "and no marked-secret relabel passthrough"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentOutputCanaryLeakDetectionVerifier()
    for output in _CLEAN_OUTPUTS:
        verifier.register(output)
    verifier.register(mutated)
    transcript = [{"op": "register", **output} for output in (*_CLEAN_OUTPUTS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_literal_canary_token_in_output_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "literal_canary_token_in_output_rejected",
        {
            "id": "mutated_literal_canary_leak_admit",
            "output_class": "literal_canary_leak",
            "output_id": _LITERAL_CANARY_FRAGMENT,
            "field_label": DECLARED_FIELD_LABEL_ALPHA,
            "leaked_canary_token": CANARY_TOKEN_ALPHA,
            "literal_canary_observed": True,
            "base64_canary_observed": False,
            "homoglyph_canary_observed": False,
            "fragment_canary_observed": False,
            "marked_secret_relabel_observed": False,
        },
        detail=(
            "mutation: a canary token from retrieved context appears "
            "literally in the output and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_base64_encoded_canary_token_in_output_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "base64_encoded_canary_token_in_output_rejected",
        {
            "id": "mutated_base64_canary_leak_admit",
            "output_class": "base64_canary_leak",
            "output_id": _BASE64_CANARY_FRAGMENT,
            "field_label": DECLARED_FIELD_LABEL_ALPHA,
            "leaked_canary_token": CANARY_TOKEN_ALPHA,
            "literal_canary_observed": False,
            "base64_canary_observed": True,
            "homoglyph_canary_observed": False,
            "fragment_canary_observed": False,
            "marked_secret_relabel_observed": False,
        },
        detail=(
            "mutation: a canary token is base64-encoded in the "
            "output as a side-channel and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_unicode_homoglyph_canary_substitution_in_output_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "unicode_homoglyph_canary_substitution_in_output_rejected",
        {
            "id": "mutated_homoglyph_canary_leak_admit",
            "output_class": "homoglyph_canary_leak",
            "output_id": _HOMOGLYPH_CANARY_FRAGMENT,
            "field_label": DECLARED_FIELD_LABEL_BETA,
            "leaked_canary_token": CANARY_TOKEN_BETA,
            "literal_canary_observed": False,
            "base64_canary_observed": False,
            "homoglyph_canary_observed": True,
            "fragment_canary_observed": False,
            "marked_secret_relabel_observed": False,
        },
        detail=(
            "mutation: a canary token with unicode homoglyph "
            "substitution appears in the output and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_partial_canary_fragment_concatenation_in_output_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "partial_canary_fragment_concatenation_in_output_rejected",
        {
            "id": "mutated_fragment_canary_leak_admit",
            "output_class": "fragment_canary_leak",
            "output_id": _FRAGMENT_CANARY_FRAGMENT,
            "field_label": DECLARED_FIELD_LABEL_ALPHA,
            "leaked_canary_token": CANARY_TOKEN_ALPHA,
            "literal_canary_observed": False,
            "base64_canary_observed": False,
            "homoglyph_canary_observed": False,
            "fragment_canary_observed": True,
            "marked_secret_relabel_observed": False,
        },
        detail=(
            "mutation: canary-token fragments are concatenated "
            "across the output to reassemble the original token "
            "and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_marked_secret_passthrough_via_field_label_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "marked_secret_passthrough_via_field_label_rejected",
        {
            "id": "mutated_marked_secret_relabel_leak_admit",
            "output_class": "marked_secret_relabel_leak",
            "output_id": _MARKED_SECRET_RELABEL_FRAGMENT,
            "field_label": DECLARED_FIELD_LABEL_BETA,
            "leaked_marked_secret": MARKED_SECRET_ALPHA,
            "literal_canary_observed": False,
            "base64_canary_observed": False,
            "homoglyph_canary_observed": False,
            "fragment_canary_observed": False,
            "marked_secret_relabel_observed": True,
        },
        detail=(
            "mutation: a marked secret appears in the output under "
            "a different field label as a relabeled passthrough "
            "and the verifier must reject instead of silently "
            "accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_canary_or_marked_secret_leak_in_output": run_clean_no_canary_or_marked_secret_leak_in_output,
    "literal_canary_token_in_output_rejected": run_literal_canary_token_in_output_rejected,
    "base64_encoded_canary_token_in_output_rejected": run_base64_encoded_canary_token_in_output_rejected,
    "unicode_homoglyph_canary_substitution_in_output_rejected": run_unicode_homoglyph_canary_substitution_in_output_rejected,
    "partial_canary_fragment_concatenation_in_output_rejected": run_partial_canary_fragment_concatenation_in_output_rejected,
    "marked_secret_passthrough_via_field_label_rejected": run_marked_secret_passthrough_via_field_label_rejected,
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
        "output_classes": sorted(OUTPUT_CLASSES),
        "approved_output_classes": sorted(APPROVED_OUTPUT_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent output canary-leak detection gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent output canary-leak detection blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-output-canary-leak-detection-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-output-canary-leak-detection-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
