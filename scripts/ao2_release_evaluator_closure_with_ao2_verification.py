#!/usr/bin/env python3
"""Release-evaluator closure that consults the AO2 native verifier verdict.

Phase 2 exit-gate item #4 requires that evaluator/closer evidence from
AO Operator can be represented as AO2 obligations or evidence-pack
attachments, and that AO2 owns the closure verdict instead of
ao-operator self-reporting acceptance.

This script combines two inputs:

- the ao-operator release evaluator decision produced by
  ``scripts/ao2_release_evaluator_decision.py``
  (``schema: ao-operator/ao2-release-evaluator-decision/v1``);
- the AO2 native verifier output produced by
  ``ao2 factory verify-evaluator-decision --decision <native> --json``
  (``schema_version: ao2.ao-operator-compat-native-evaluator-verification.v1``).

It emits a closure decision that ACCEPTS the release closure only when
both the ao-operator evaluator decision and the AO2 native verification
are accepted. If AO2 rejects (status, signature_status, trust_boundary,
or factory_v3_role mismatch), the closure is refused regardless of
ao-operator's local verdict.

The script does not invoke the ``ao2`` binary itself: it consumes
already-produced verifier JSON so it remains pure stdlib and the test
suite does not depend on a built ao2 binary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/ao2-release-evaluator-closure-with-ao2-verification/v1"
FACTORY_DECISION_SCHEMA = "ao-operator/ao2-release-evaluator-decision/v1"
AO2_VERIFICATION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-verification.v1"
AO2_VERIFICATION_FACTORY_V3_ROLE = "parity_oracle_only"
AO2_VERIFICATION_DECISION_OWNER = "ao2-native-evaluator-decision-verifier"
# When the AO2 native verifier has not been wired through release-line nightly
# yet, the verification helper writes a JSON with status=missing_inputs. The
# closer must NOT accept the release closure in that state — but it should also
# emit a clean "blocked" signal rather than a false "rejected" so operators can
# distinguish "AO2 said no" from "AO2 hasn't been asked yet".
AO2_VERIFICATION_MISSING_INPUTS_STATUS = "missing_inputs"
CLOSURE_STATUS_BLOCKED = "blocked"
CLOSURE_DECISION_BLOCKED = "blocked_awaiting_ao2_verification"

TRUST_BOUNDARY: dict[str, Any] = {
    "frontend": "Hermes front end / queue / memory surface",
    "governed_backend": "ao-operator / AO Operator compat closer",
    "trusted_execution": "ao2 signed evidence boundary",
    "closure_decision_owner": "ao2_native_evaluator_decision_verifier",
    "factory_v3_role": "compat_closer_consumes_ao2_verdict",
    "control_plane_role": "read_only_observer",
    "mutates_ao_artifacts": False,
    "control_plane_approves_release": False,
}


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


class InvalidClosureInputError(RuntimeError):
    """Raised when one of the supplied closure inputs does not match the expected schema."""


def _validate_factory_decision(decision: dict[str, Any], path: Path) -> None:
    schema = decision.get("schema")
    if schema != FACTORY_DECISION_SCHEMA:
        raise InvalidClosureInputError(
            f"factory-decision schema must be {FACTORY_DECISION_SCHEMA!r}; "
            f"got {schema!r} in {path}"
        )


def _validate_ao2_verification(verification: dict[str, Any], path: Path) -> None:
    schema = verification.get("schema_version")
    if schema != AO2_VERIFICATION_SCHEMA:
        raise InvalidClosureInputError(
            f"ao2 verification schema must be {AO2_VERIFICATION_SCHEMA!r}; "
            f"got {schema!r} in {path}"
        )
    factory_v3_role = verification.get("factory_v3_role")
    if factory_v3_role != AO2_VERIFICATION_FACTORY_V3_ROLE:
        raise InvalidClosureInputError(
            f"ao2 verification factory_v3_role must be "
            f"{AO2_VERIFICATION_FACTORY_V3_ROLE!r}; got {factory_v3_role!r} in {path}"
        )


def _build_blocked_closure(
    *,
    factory_decision: dict[str, Any],
    factory_decision_path: Path,
    ao2_verification: dict[str, Any],
    ao2_verification_path: Path,
) -> dict[str, Any]:
    factory_status = _as_str(factory_decision.get("status"))
    factory_decision_str = _as_str(factory_decision.get("decision"))
    factory_blockers_raw = factory_decision.get("blockers") or []
    factory_blockers: list[str] = [str(b) for b in factory_blockers_raw]

    missing_raw = ao2_verification.get("missing") or []
    missing: list[str] = [str(m) for m in missing_raw if isinstance(m, (str, int))]
    blockers = [
        "ao2_native_evaluator_verification_missing_inputs: "
        "AO2 native verifier has not produced an evaluator-decision "
        "verification artifact yet; release closure cannot be issued "
        "until AO2 owns the verdict",
    ]
    for item in missing:
        blockers.append(f"ao2_verification_missing_input: {item}")

    return {
        "schema": SCHEMA,
        "status": CLOSURE_STATUS_BLOCKED,
        "decision": CLOSURE_DECISION_BLOCKED,
        "release": (
            factory_decision.get("release")
            if isinstance(factory_decision.get("release"), dict)
            else {}
        ),
        "factory_v3_decision": {
            "status": factory_status,
            "decision": factory_decision_str,
            "blockers": factory_blockers,
        },
        "ao2_verification": {
            "status": _as_str(ao2_verification.get("status")),
            "missing": missing,
            "factory_v3_role": _as_str(ao2_verification.get("factory_v3_role")),
            "ao2_decision_owner": _as_str(ao2_verification.get("ao2_decision_owner")),
            "control_plane_role": _as_str(ao2_verification.get("control_plane_role")),
        },
        "blockers": blockers,
        "evidence": {
            "factory_v3_decision_path": str(factory_decision_path),
            "ao2_verification_path": str(ao2_verification_path),
        },
        "trust_boundary": dict(TRUST_BOUNDARY),
        "next_action": (
            "produce an AO2 native evaluator decision and a corresponding "
            "ao2 factory verify-evaluator-decision artifact, then re-run the "
            "closer; AO2 owns the closure verdict"
        ),
    }


def _as_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _as_str(value: Any, default: str = "missing") -> str:
    return value if isinstance(value, str) and value else default


def build_closure(
    *,
    factory_decision: dict[str, Any],
    factory_decision_path: Path,
    ao2_verification: dict[str, Any],
    ao2_verification_path: Path,
) -> dict[str, Any]:
    if (
        _as_str(ao2_verification.get("status"))
        == AO2_VERIFICATION_MISSING_INPUTS_STATUS
    ):
        return _build_blocked_closure(
            factory_decision=factory_decision,
            factory_decision_path=factory_decision_path,
            ao2_verification=ao2_verification,
            ao2_verification_path=ao2_verification_path,
        )

    factory_status = _as_str(factory_decision.get("status"))
    factory_decision_str = _as_str(factory_decision.get("decision"))
    factory_blockers_raw = factory_decision.get("blockers") or []
    factory_blockers: list[str] = [str(b) for b in factory_blockers_raw]

    ao2_status = _as_str(ao2_verification.get("status"))
    ao2_signature_status = _as_str(ao2_verification.get("signature_status"))
    ao2_signature_verified = _as_bool(ao2_verification.get("signature_verified"))
    ao2_signature_requirement_satisfied = _as_bool(
        ao2_verification.get("signature_requirement_satisfied")
    )
    ao2_trust_boundary_ok = _as_bool(ao2_verification.get("trust_boundary_ok"))
    ao2_verdict = ao2_verification.get("verdict") or {}
    if not isinstance(ao2_verdict, dict):
        ao2_verdict = {}

    blockers: list[str] = []

    if factory_status != "accepted":
        blockers.append(
            f"factory_v3_decision_status: expected accepted, observed {factory_status}"
        )
    for blocker in factory_blockers:
        blockers.append(f"factory_v3_blocker: {blocker}")

    if ao2_status != "accepted":
        blockers.append(
            f"ao2_verification_status: expected accepted, observed {ao2_status}"
        )
    if ao2_signature_status != "signed":
        blockers.append(
            f"ao2_verification_signature_status: expected signed, observed {ao2_signature_status}"
        )
    if not ao2_signature_verified:
        blockers.append(
            "ao2_verification_signature_verified: expected True, observed False"
        )
    if not ao2_signature_requirement_satisfied:
        blockers.append(
            "ao2_verification_signature_requirement_satisfied: expected True, observed False"
        )
    if not ao2_trust_boundary_ok:
        blockers.append(
            "ao2_verification_trust_boundary_ok: expected True, observed False"
        )

    accepted = not blockers
    decision = "accept_release_closure" if accepted else "reject_release_closure"

    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "decision": decision,
        "release": factory_decision.get("release") if isinstance(factory_decision.get("release"), dict) else {},
        "factory_v3_decision": {
            "status": factory_status,
            "decision": factory_decision_str,
            "blockers": factory_blockers,
        },
        "ao2_verification": {
            "status": ao2_status,
            "signature_status": ao2_signature_status,
            "signature_verified": ao2_signature_verified,
            "signature_requirement_satisfied": ao2_signature_requirement_satisfied,
            "trust_boundary_ok": ao2_trust_boundary_ok,
            "verdict": ao2_verdict,
            "factory_v3_role": _as_str(ao2_verification.get("factory_v3_role")),
            "ao2_decision_owner": _as_str(ao2_verification.get("ao2_decision_owner")),
            "control_plane_role": _as_str(ao2_verification.get("control_plane_role")),
        },
        "blockers": blockers,
        "evidence": {
            "factory_v3_decision_path": str(factory_decision_path),
            "ao2_verification_path": str(ao2_verification_path),
        },
        "trust_boundary": dict(TRUST_BOUNDARY),
        "next_action": (
            "release closure is accepted; ao2 native verifier confirmed signed evaluator decision"
            if accepted
            else "resolve blockers before release closure; ao2 owns the closure verdict"
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release") or {}
    if not isinstance(release, dict):
        release = {}
    factory = payload.get("factory_v3_decision") or {}
    ao2 = payload.get("ao2_verification") or {}
    lines = [
        "# AO2 Release Evaluator Closure (with AO2 verification)",
        "",
        f"- status: `{payload.get('status', 'missing')}`",
        f"- decision: `{payload.get('decision', 'missing')}`",
        f"- release_tag: `{release.get('release_tag', 'missing')}`",
        f"- closure_decision_owner: `{payload['trust_boundary']['closure_decision_owner']}`",
        f"- factory_v3_role: `{payload['trust_boundary']['factory_v3_role']}`",
        f"- control_plane_approves_release: `{payload['trust_boundary']['control_plane_approves_release']}`",
        "",
        "## factory_v3_decision",
        "",
        f"- status: `{factory.get('status', 'missing')}`",
        f"- decision: `{factory.get('decision', 'missing')}`",
    ]
    factory_blockers = factory.get("blockers") or []
    if factory_blockers:
        lines.append("- blockers:")
        for b in factory_blockers:
            lines.append(f"  - {b}")
    else:
        lines.append("- blockers: none")

    lines.extend(
        [
            "",
            "## ao2_verification",
            "",
            f"- status: `{ao2.get('status', 'missing')}`",
            f"- signature_status: `{ao2.get('signature_status', 'missing')}`",
            f"- signature_verified: `{ao2.get('signature_verified', False)}`",
            f"- signature_requirement_satisfied: `{ao2.get('signature_requirement_satisfied', False)}`",
            f"- trust_boundary_ok: `{ao2.get('trust_boundary_ok', False)}`",
            f"- factory_v3_role: `{ao2.get('factory_v3_role', 'missing')}`",
            f"- ao2_decision_owner: `{ao2.get('ao2_decision_owner', 'missing')}`",
            f"- control_plane_role: `{ao2.get('control_plane_role', 'missing')}`",
        ]
    )

    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")

    evidence = payload.get("evidence", {})
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- factory_v3_decision_path: `{evidence.get('factory_v3_decision_path', 'missing')}`",
            f"- ao2_verification_path: `{evidence.get('ao2_verification_path', 'missing')}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-decision", type=Path, required=True)
    parser.add_argument("--ao2-verification", type=Path, required=True)
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    factory_decision = _load_json(args.factory_decision)
    ao2_verification = _load_json(args.ao2_verification)
    try:
        _validate_factory_decision(factory_decision, args.factory_decision)
        _validate_ao2_verification(ao2_verification, args.ao2_verification)
    except InvalidClosureInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = build_closure(
        factory_decision=factory_decision,
        factory_decision_path=args.factory_decision,
        ao2_verification=ao2_verification,
        ao2_verification_path=args.ao2_verification,
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
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
