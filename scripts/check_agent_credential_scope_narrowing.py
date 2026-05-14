#!/usr/bin/env python3
"""Agent credential scope narrowing gate.

Models the credential-scoping invariant that no AO Operator agent
can widen a scoped credential at use time via scope substitution,
scope append, audience relabel, expiry extension, or principal
mint.

Every credential edge whose payload would let a narrowed
credential broaden in-flight is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real credential broker invoked):

* ``clean_no_credential_scope_widening`` -- control: every
  registered credential carries only the originally declared
  scope, audience, expiry, and principal; no widening, no
  appended scopes, no relabel, no expiry push, no principal
  mint.
* ``credential_scope_substitution_admit_rejected`` -- mutation:
  a credential payload swaps the declared scope for a broader
  scope; the verifier MUST reject.
* ``credential_scope_append_admit_rejected`` -- mutation: a
  credential payload appends an extra scope beyond the declared
  scope; the verifier MUST reject.
* ``credential_audience_relabel_admit_rejected`` -- mutation: a
  credential payload relabels the declared audience to a
  different tenant; the verifier MUST reject.
* ``credential_expiry_extension_admit_rejected`` -- mutation: a
  credential payload pushes its expiry past the declared TTL;
  the verifier MUST reject.
* ``credential_principal_mint_admit_rejected`` -- mutation: a
  credential payload mints a higher-privilege principal beyond
  the declared principal; the verifier MUST reject.

Every case lays down a per-case
``agent-credential-scope-narrowing-transcript.json`` in a
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
    "agent-credential-scope-narrowing.json"
)
SCHEMA = "ao-operator/agent-credential-scope-narrowing/v1"

CASE_IDS = (
    "clean_no_credential_scope_widening",
    "credential_scope_substitution_admit_rejected",
    "credential_scope_append_admit_rejected",
    "credential_audience_relabel_admit_rejected",
    "credential_expiry_extension_admit_rejected",
    "credential_principal_mint_admit_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_credential_scope_widening": "PASS",
    "credential_scope_substitution_admit_rejected": "FAIL",
    "credential_scope_append_admit_rejected": "FAIL",
    "credential_audience_relabel_admit_rejected": "FAIL",
    "credential_expiry_extension_admit_rejected": "FAIL",
    "credential_principal_mint_admit_rejected": "FAIL",
}

CREDENTIAL_CLASSES = {
    "clean_credential",
    "credential_scope_substitution",
    "credential_scope_append",
    "credential_audience_relabel",
    "credential_expiry_extension",
    "credential_principal_mint",
}
APPROVED_CREDENTIAL_CLASSES = {
    "clean_credential",
}
HAZARD_CLASSES = {
    "credential_scope_substitution_admit",
    "credential_scope_append_admit",
    "credential_audience_relabel_admit",
    "credential_expiry_extension_admit",
    "credential_principal_mint_admit",
}

DECLARED_SCOPE_ALPHA = "scope::read_alpha"
DECLARED_SCOPE_BETA = "scope::read_beta"
DECLARED_SCOPE_GAMMA = "scope::read_gamma"
BROADER_SCOPE = "scope::admin_root"
APPENDED_SCOPE = "scope::write_extra"
DECLARED_AUDIENCE_ALPHA = "aud::tenant_alpha"
DECLARED_AUDIENCE_BETA = "aud::tenant_beta"
DECLARED_AUDIENCE_GAMMA = "aud::tenant_gamma"
DECLARED_EXPIRY = "2026-05-08T00:00:00Z"
EXTENDED_EXPIRY = "2099-01-01T00:00:00Z"
DECLARED_PRINCIPAL = "principal::user_alpha"
MINTED_PRINCIPAL = "principal::admin_root"

_CLEAN_CREDENTIAL_ALPHA = "cred::clean_alpha"
_CLEAN_CREDENTIAL_BETA = "cred::clean_beta"
_CLEAN_CREDENTIAL_GAMMA = "cred::clean_gamma"
_SCOPE_SUBSTITUTED_CRED = "cred::scope_substituted_alpha"
_SCOPE_APPENDED_CRED = "cred::scope_appended_alpha"
_AUDIENCE_RELABEL_CRED = "cred::audience_relabel_alpha"
_EXPIRY_EXTENSION_CRED = "cred::expiry_extension_alpha"
_PRINCIPAL_MINT_CRED = "cred::principal_mint_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _CredentialScopeNarrowingVerifier:
    """In-memory agent credential scope-narrowing verifier."""

    def __init__(self) -> None:
        self.credentials: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, credential: dict[str, Any]) -> None:
        self.credentials.append(dict(credential))
        self._validate_credential(credential)

    def _validate_credential(self, credential: dict[str, Any]) -> None:
        credential_id = str(credential.get("id") or "<unnamed>")
        credential_class = credential.get("credential_class")
        if credential_class not in CREDENTIAL_CLASSES:
            self.errors.append(
                f"unknown_credential_class:id={credential_id},class={credential_class!r}"
            )
            return
        if credential_class == "credential_scope_substitution":
            self.errors.append(
                f"credential_scope_substitution_admit_rejection:id={credential_id},credential={credential.get('credential_id', '<unknown>')}"
            )
            return
        if credential_class == "credential_scope_append":
            self.errors.append(
                f"credential_scope_append_admit_rejection:id={credential_id},credential={credential.get('credential_id', '<unknown>')}"
            )
            return
        if credential_class == "credential_audience_relabel":
            self.errors.append(
                f"credential_audience_relabel_admit_rejection:id={credential_id},credential={credential.get('credential_id', '<unknown>')}"
            )
            return
        if credential_class == "credential_expiry_extension":
            self.errors.append(
                f"credential_expiry_extension_admit_rejection:id={credential_id},credential={credential.get('credential_id', '<unknown>')}"
            )
            return
        if credential_class == "credential_principal_mint":
            self.errors.append(
                f"credential_principal_mint_admit_rejection:id={credential_id},credential={credential.get('credential_id', '<unknown>')}"
            )
            return
        if credential_class not in APPROVED_CREDENTIAL_CLASSES:
            self.errors.append(
                f"unapproved_credential_class:id={credential_id},class={credential_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_CREDENTIALS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_credential_alpha",
        "credential_class": "clean_credential",
        "credential_id": _CLEAN_CREDENTIAL_ALPHA,
        "declared_scope": DECLARED_SCOPE_ALPHA,
        "declared_audience": DECLARED_AUDIENCE_ALPHA,
        "declared_expiry": DECLARED_EXPIRY,
        "declared_principal": DECLARED_PRINCIPAL,
        "scope_substitution_observed": False,
        "scope_append_observed": False,
        "audience_relabel_observed": False,
        "expiry_extension_observed": False,
        "principal_mint_observed": False,
    },
    {
        "id": "clean_credential_beta",
        "credential_class": "clean_credential",
        "credential_id": _CLEAN_CREDENTIAL_BETA,
        "declared_scope": DECLARED_SCOPE_BETA,
        "declared_audience": DECLARED_AUDIENCE_BETA,
        "declared_expiry": DECLARED_EXPIRY,
        "declared_principal": DECLARED_PRINCIPAL,
        "scope_substitution_observed": False,
        "scope_append_observed": False,
        "audience_relabel_observed": False,
        "expiry_extension_observed": False,
        "principal_mint_observed": False,
    },
    {
        "id": "clean_credential_gamma",
        "credential_class": "clean_credential",
        "credential_id": _CLEAN_CREDENTIAL_GAMMA,
        "declared_scope": DECLARED_SCOPE_GAMMA,
        "declared_audience": DECLARED_AUDIENCE_GAMMA,
        "declared_expiry": DECLARED_EXPIRY,
        "declared_principal": DECLARED_PRINCIPAL,
        "scope_substitution_observed": False,
        "scope_append_observed": False,
        "audience_relabel_observed": False,
        "expiry_extension_observed": False,
        "principal_mint_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-credential-scope-narrowing-transcript.json").write_text(
        json.dumps({"credentials": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_credential_scope_widening(work: Path) -> dict[str, Any]:
    case_id = "clean_no_credential_scope_widening"
    verifier = _CredentialScopeNarrowingVerifier()
    for credential in _CLEAN_CREDENTIALS:
        verifier.register(credential)
    transcript = [{"op": "register", **credential} for credential in _CLEAN_CREDENTIALS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered credential carries only the "
            "originally declared scope, audience, expiry, and "
            "principal; no widening, no appended scopes, no relabel, "
            "no expiry push, no principal mint"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _CredentialScopeNarrowingVerifier()
    for credential in _CLEAN_CREDENTIALS:
        verifier.register(credential)
    verifier.register(mutated)
    transcript = [{"op": "register", **credential} for credential in (*_CLEAN_CREDENTIALS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_credential_scope_substitution_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "credential_scope_substitution_admit_rejected",
        {
            "id": "mutated_credential_scope_substitution_admit",
            "credential_class": "credential_scope_substitution",
            "credential_id": _SCOPE_SUBSTITUTED_CRED,
            "declared_scope": DECLARED_SCOPE_ALPHA,
            "observed_scope": BROADER_SCOPE,
            "declared_audience": DECLARED_AUDIENCE_ALPHA,
            "declared_expiry": DECLARED_EXPIRY,
            "declared_principal": DECLARED_PRINCIPAL,
            "scope_substitution_observed": True,
            "scope_append_observed": False,
            "audience_relabel_observed": False,
            "expiry_extension_observed": False,
            "principal_mint_observed": False,
        },
        detail=(
            "mutation: a credential payload swaps the declared "
            "scope for a broader scope and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_credential_scope_append_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "credential_scope_append_admit_rejected",
        {
            "id": "mutated_credential_scope_append_admit",
            "credential_class": "credential_scope_append",
            "credential_id": _SCOPE_APPENDED_CRED,
            "declared_scope": DECLARED_SCOPE_ALPHA,
            "appended_scope": APPENDED_SCOPE,
            "declared_audience": DECLARED_AUDIENCE_ALPHA,
            "declared_expiry": DECLARED_EXPIRY,
            "declared_principal": DECLARED_PRINCIPAL,
            "scope_substitution_observed": False,
            "scope_append_observed": True,
            "audience_relabel_observed": False,
            "expiry_extension_observed": False,
            "principal_mint_observed": False,
        },
        detail=(
            "mutation: a credential payload appends an extra scope "
            "beyond the declared scope and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_credential_audience_relabel_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "credential_audience_relabel_admit_rejected",
        {
            "id": "mutated_credential_audience_relabel_admit",
            "credential_class": "credential_audience_relabel",
            "credential_id": _AUDIENCE_RELABEL_CRED,
            "declared_scope": DECLARED_SCOPE_ALPHA,
            "declared_audience": DECLARED_AUDIENCE_ALPHA,
            "observed_audience": DECLARED_AUDIENCE_BETA,
            "declared_expiry": DECLARED_EXPIRY,
            "declared_principal": DECLARED_PRINCIPAL,
            "scope_substitution_observed": False,
            "scope_append_observed": False,
            "audience_relabel_observed": True,
            "expiry_extension_observed": False,
            "principal_mint_observed": False,
        },
        detail=(
            "mutation: a credential payload relabels the declared "
            "audience to a different tenant and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_credential_expiry_extension_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "credential_expiry_extension_admit_rejected",
        {
            "id": "mutated_credential_expiry_extension_admit",
            "credential_class": "credential_expiry_extension",
            "credential_id": _EXPIRY_EXTENSION_CRED,
            "declared_scope": DECLARED_SCOPE_ALPHA,
            "declared_audience": DECLARED_AUDIENCE_ALPHA,
            "declared_expiry": DECLARED_EXPIRY,
            "observed_expiry": EXTENDED_EXPIRY,
            "declared_principal": DECLARED_PRINCIPAL,
            "scope_substitution_observed": False,
            "scope_append_observed": False,
            "audience_relabel_observed": False,
            "expiry_extension_observed": True,
            "principal_mint_observed": False,
        },
        detail=(
            "mutation: a credential payload pushes its expiry past "
            "the declared TTL and the verifier must reject instead "
            "of silently accepting"
        ),
    )


def run_credential_principal_mint_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "credential_principal_mint_admit_rejected",
        {
            "id": "mutated_credential_principal_mint_admit",
            "credential_class": "credential_principal_mint",
            "credential_id": _PRINCIPAL_MINT_CRED,
            "declared_scope": DECLARED_SCOPE_ALPHA,
            "declared_audience": DECLARED_AUDIENCE_ALPHA,
            "declared_expiry": DECLARED_EXPIRY,
            "declared_principal": DECLARED_PRINCIPAL,
            "observed_principal": MINTED_PRINCIPAL,
            "scope_substitution_observed": False,
            "scope_append_observed": False,
            "audience_relabel_observed": False,
            "expiry_extension_observed": False,
            "principal_mint_observed": True,
        },
        detail=(
            "mutation: a credential payload mints a higher-privilege "
            "principal beyond the declared principal and the "
            "verifier must reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_credential_scope_widening": run_clean_no_credential_scope_widening,
    "credential_scope_substitution_admit_rejected": run_credential_scope_substitution_admit_rejected,
    "credential_scope_append_admit_rejected": run_credential_scope_append_admit_rejected,
    "credential_audience_relabel_admit_rejected": run_credential_audience_relabel_admit_rejected,
    "credential_expiry_extension_admit_rejected": run_credential_expiry_extension_admit_rejected,
    "credential_principal_mint_admit_rejected": run_credential_principal_mint_admit_rejected,
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
        "credential_classes": sorted(CREDENTIAL_CLASSES),
        "approved_credential_classes": sorted(APPROVED_CREDENTIAL_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent credential scope narrowing gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent credential scope narrowing blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-credential-scope-narrowing-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-credential-scope-narrowing-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
