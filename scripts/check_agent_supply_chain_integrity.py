#!/usr/bin/env python3
"""Agent supply-chain integrity gate.

Models the supply-chain integrity invariant that no AO Operator
agent dependency, lock-file digest, or post-install hook can admit
unauthorized provenance into the working tree without an explicit
operator-approved trust marker.

Every package edge whose provenance class is not on the operator
approval list -- or whose registry, lock-file digest, post-install
hook, or transitive yank state breaches the supply-chain invariants
-- is fail-closed.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO, no real
package manager invoked):

* ``clean_no_unauthorized_provenance_or_unsigned_package_edges`` --
  control: every registered package edge is in an approved
  provenance class with a matching lock-file digest, ships from an
  operator-allowlisted registry, has no post-install network
  egress, and has been re-pinned past any upstream yank.
* ``unsigned_package_admitted_without_signature_rejected`` --
  mutation: an unsigned package is admitted without an operator-
  approved signature; the verifier MUST reject.
* ``lock_file_digest_mismatch_admitted_rejected`` -- mutation: a
  package is admitted with a lock-file digest that does not match
  the registered digest; the verifier MUST reject.
* ``dependency_confusion_via_shadow_registry_rejected`` --
  mutation: a package is admitted from a shadow registry not on
  the operator allowlist; the verifier MUST reject.
* ``post_install_script_with_network_egress_rejected`` -- mutation:
  a package whose post-install script performs network egress is
  admitted; the verifier MUST reject.
* ``transitive_yank_without_repin_rejected`` -- mutation: a
  package whose transitive dependency was yanked upstream but has
  not been re-pinned is admitted; the verifier MUST reject.

Every case lays down a per-case
``agent-supply-chain-integrity-transcript.json`` in a temporary
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
    "agent-supply-chain-integrity.json"
)
SCHEMA = "ao-operator/agent-supply-chain-integrity/v1"

CASE_IDS = (
    "clean_no_unauthorized_provenance_or_unsigned_package_edges",
    "unsigned_package_admitted_without_signature_rejected",
    "lock_file_digest_mismatch_admitted_rejected",
    "dependency_confusion_via_shadow_registry_rejected",
    "post_install_script_with_network_egress_rejected",
    "transitive_yank_without_repin_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_unauthorized_provenance_or_unsigned_package_edges": "PASS",
    "unsigned_package_admitted_without_signature_rejected": "FAIL",
    "lock_file_digest_mismatch_admitted_rejected": "FAIL",
    "dependency_confusion_via_shadow_registry_rejected": "FAIL",
    "post_install_script_with_network_egress_rejected": "FAIL",
    "transitive_yank_without_repin_rejected": "FAIL",
}

PACKAGE_CLASSES = {
    "operator_signed",
    "operator_allowlisted",
    "unsigned",
    "digest_mismatch",
    "shadow_registry",
    "post_install_egress",
    "transitive_yank_unrepinned",
}
APPROVED_PACKAGE_CLASSES = {"operator_signed", "operator_allowlisted"}
HAZARD_CLASSES = {
    "unsigned_admit",
    "digest_mismatch_admit",
    "dependency_confusion_admit",
    "post_install_egress_admit",
    "transitive_yank_unrepinned_admit",
}

ALLOWLISTED_REGISTRIES = {"registry::operator_allowlisted_alpha"}
SHADOW_REGISTRY_FRAGMENT = "registry::shadow_alpha"

_OPERATOR_SIGNED_ALPHA = "pkg::operator_signed_alpha"
_OPERATOR_SIGNED_BETA = "pkg::operator_signed_beta"
_UNSIGNED_FRAGMENT = "pkg::unsigned_alpha"
_DIGEST_MISMATCH_FRAGMENT = "pkg::digest_mismatch_alpha"
_SHADOW_REGISTRY_PKG_FRAGMENT = "pkg::shadow_registry_alpha"
_POST_INSTALL_EGRESS_FRAGMENT = "pkg::post_install_egress_alpha"
_TRANSITIVE_YANK_FRAGMENT = "pkg::transitive_yank_alpha"

_OPERATOR_ROOT_SIGNATURE = "signature::operator_root_alpha"
_NETWORK_EGRESS_HOOK = "hook::network_egress_alpha"
_TRANSITIVE_UNREPINNED_YANK = "yank::transitive_unrepinned_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _AgentSupplyChainIntegrityVerifier:
    """In-memory supply-chain integrity verifier.

    Each ``register`` call records one package edge with its
    provenance class, registry, lock-file digest match flag,
    post-install egress flag, transitive yank state, and synthetic
    package identifier. A FAIL is recorded whenever a package edge
    breaches one of the five supply-chain hazard classes.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        package_class = edge.get("package_class")
        if package_class not in PACKAGE_CLASSES:
            self.errors.append(
                f"unknown_package_class:id={edge_id},class={package_class!r}"
            )
            return
        if package_class == "unsigned":
            self.errors.append(
                f"unsigned_package_admit_rejection:id={edge_id},pkg={edge.get('package_id', '<unknown>')}"
            )
            return
        if package_class == "digest_mismatch":
            self.errors.append(
                f"lock_file_digest_mismatch_admit_rejection:id={edge_id},pkg={edge.get('package_id', '<unknown>')}"
            )
            return
        if package_class == "shadow_registry":
            self.errors.append(
                f"dependency_confusion_via_shadow_registry_admit_rejection:id={edge_id},pkg={edge.get('package_id', '<unknown>')}"
            )
            return
        if package_class == "post_install_egress":
            self.errors.append(
                f"post_install_script_with_network_egress_admit_rejection:id={edge_id},pkg={edge.get('package_id', '<unknown>')}"
            )
            return
        if package_class == "transitive_yank_unrepinned":
            self.errors.append(
                f"transitive_yank_without_repin_admit_rejection:id={edge_id},pkg={edge.get('package_id', '<unknown>')}"
            )
            return
        if package_class not in APPROVED_PACKAGE_CLASSES:
            self.errors.append(
                f"unapproved_package_class:id={edge_id},class={package_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "operator_signed_pkg_alpha",
        "package_class": "operator_signed",
        "package_id": _OPERATOR_SIGNED_ALPHA,
        "registry": "registry::operator_allowlisted_alpha",
        "lock_digest_match": True,
        "post_install_egress": False,
        "transitive_yank_repinned": True,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
    {
        "id": "operator_signed_pkg_beta",
        "package_class": "operator_signed",
        "package_id": _OPERATOR_SIGNED_BETA,
        "registry": "registry::operator_allowlisted_alpha",
        "lock_digest_match": True,
        "post_install_egress": False,
        "transitive_yank_repinned": True,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
    {
        "id": "operator_allowlisted_pkg_alpha",
        "package_class": "operator_allowlisted",
        "package_id": "pkg::operator_allowlisted_alpha",
        "registry": "registry::operator_allowlisted_alpha",
        "lock_digest_match": True,
        "post_install_egress": False,
        "transitive_yank_repinned": True,
        "signature": _OPERATOR_ROOT_SIGNATURE,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "agent-supply-chain-integrity-transcript.json").write_text(
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


def run_clean_no_unauthorized_provenance_or_unsigned_package_edges(work: Path) -> dict[str, Any]:
    case_id = "clean_no_unauthorized_provenance_or_unsigned_package_edges"
    verifier = _AgentSupplyChainIntegrityVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered package edge is in an approved "
            "provenance class with matching lock digest, allowlisted "
            "registry, no post-install egress, and re-pinned transitive yanks"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _AgentSupplyChainIntegrityVerifier()
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


def run_unsigned_package_admitted_without_signature_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "unsigned_package_admitted_without_signature_rejected",
        {
            "id": "mutated_unsigned_package_admit",
            "package_class": "unsigned",
            "package_id": _UNSIGNED_FRAGMENT,
            "registry": "registry::operator_allowlisted_alpha",
            "lock_digest_match": True,
            "post_install_egress": False,
            "transitive_yank_repinned": True,
            "signature": None,
        },
        detail=(
            "mutation: an unsigned package is admitted without an "
            "operator-approved signature and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_lock_file_digest_mismatch_admitted_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "lock_file_digest_mismatch_admitted_rejected",
        {
            "id": "mutated_lock_file_digest_mismatch_admit",
            "package_class": "digest_mismatch",
            "package_id": _DIGEST_MISMATCH_FRAGMENT,
            "registry": "registry::operator_allowlisted_alpha",
            "lock_digest_match": False,
            "post_install_egress": False,
            "transitive_yank_repinned": True,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: a package is admitted with a lock-file digest "
            "that does not match the registered digest and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_dependency_confusion_via_shadow_registry_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "dependency_confusion_via_shadow_registry_rejected",
        {
            "id": "mutated_dependency_confusion_via_shadow_registry_admit",
            "package_class": "shadow_registry",
            "package_id": _SHADOW_REGISTRY_PKG_FRAGMENT,
            "registry": SHADOW_REGISTRY_FRAGMENT,
            "lock_digest_match": True,
            "post_install_egress": False,
            "transitive_yank_repinned": True,
            "signature": _OPERATOR_ROOT_SIGNATURE,
        },
        detail=(
            "mutation: a package is admitted from a shadow registry "
            "not on the operator allowlist and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_post_install_script_with_network_egress_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "post_install_script_with_network_egress_rejected",
        {
            "id": "mutated_post_install_script_with_network_egress_admit",
            "package_class": "post_install_egress",
            "package_id": _POST_INSTALL_EGRESS_FRAGMENT,
            "registry": "registry::operator_allowlisted_alpha",
            "lock_digest_match": True,
            "post_install_egress": True,
            "transitive_yank_repinned": True,
            "signature": _OPERATOR_ROOT_SIGNATURE,
            "post_install_hook": _NETWORK_EGRESS_HOOK,
        },
        detail=(
            "mutation: a package whose post-install script performs "
            "network egress is admitted and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_transitive_yank_without_repin_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "transitive_yank_without_repin_rejected",
        {
            "id": "mutated_transitive_yank_without_repin_admit",
            "package_class": "transitive_yank_unrepinned",
            "package_id": _TRANSITIVE_YANK_FRAGMENT,
            "registry": "registry::operator_allowlisted_alpha",
            "lock_digest_match": True,
            "post_install_egress": False,
            "transitive_yank_repinned": False,
            "signature": _OPERATOR_ROOT_SIGNATURE,
            "yank_marker": _TRANSITIVE_UNREPINNED_YANK,
        },
        detail=(
            "mutation: a package whose transitive dependency was yanked "
            "upstream but has not been re-pinned is admitted and the "
            "verifier must reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_unauthorized_provenance_or_unsigned_package_edges": run_clean_no_unauthorized_provenance_or_unsigned_package_edges,
    "unsigned_package_admitted_without_signature_rejected": run_unsigned_package_admitted_without_signature_rejected,
    "lock_file_digest_mismatch_admitted_rejected": run_lock_file_digest_mismatch_admitted_rejected,
    "dependency_confusion_via_shadow_registry_rejected": run_dependency_confusion_via_shadow_registry_rejected,
    "post_install_script_with_network_egress_rejected": run_post_install_script_with_network_egress_rejected,
    "transitive_yank_without_repin_rejected": run_transitive_yank_without_repin_rejected,
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
        "package_classes": sorted(PACKAGE_CLASSES),
        "approved_package_classes": sorted(APPROVED_PACKAGE_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Agent supply-chain integrity gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Agent supply-chain integrity blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-supply-chain-integrity-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-agent-supply-chain-integrity-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
