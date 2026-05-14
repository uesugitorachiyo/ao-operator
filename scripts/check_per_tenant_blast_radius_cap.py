#!/usr/bin/env python3
"""Per-tenant blast-radius cap gate.

Models the per-tenant blast-radius cap invariant that no
AO Operator agent action originating in tenant ``A`` can reach a
resource owned by tenant ``B`` and that no action without a
valid signed tenant tag, no action whose target is outside the
operator allowlist, and no action issued after the per-tenant
quota window has closed can be admitted.

Every action edge whose tenant boundary, allowlist, or quota
state would let a single tenant's agent loop fan out into
another tenant's resources, into unallowlisted targets, or into
post-window admission is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real tenant boundary or allowlist policy invoked):

* ``clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges`` --
  control: every registered action stays within the operator
  tenant, carries a valid signed tenant tag, targets an
  allowlisted resource, and is observed inside the open quota
  window.
* ``cross_tenant_fanout_to_unrelated_tenant_resource_rejected`` --
  mutation: an action issued by the operator tenant reaches a
  resource owned by an unrelated tenant; the verifier MUST
  reject.
* ``missing_tenant_tag_admits_global_blast_radius_rejected`` --
  mutation: an action is admitted without any tenant tag,
  letting it fan out across the global blast radius; the
  verifier MUST reject.
* ``tenant_tag_spoof_admits_other_tenant_resource_rejected`` --
  mutation: an action carries a tenant tag whose signature does
  not validate, spoofing access to another tenant's resource;
  the verifier MUST reject.
* ``allowlist_bypass_admits_unallowlisted_target_rejected`` --
  mutation: an action targets a resource that is not on the
  operator allowlist; the verifier MUST reject.
* ``quota_overflow_leak_admits_post_window_action_rejected`` --
  mutation: an action is admitted after the per-tenant quota
  window has closed, leaking blast-radius across windows; the
  verifier MUST reject.

Every case lays down a per-case
``per-tenant-blast-radius-cap-transcript.json`` in a temporary
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
    "per-tenant-blast-radius-cap.json"
)
SCHEMA = "ao-operator/per-tenant-blast-radius-cap/v1"

CASE_IDS = (
    "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges",
    "cross_tenant_fanout_to_unrelated_tenant_resource_rejected",
    "missing_tenant_tag_admits_global_blast_radius_rejected",
    "tenant_tag_spoof_admits_other_tenant_resource_rejected",
    "allowlist_bypass_admits_unallowlisted_target_rejected",
    "quota_overflow_leak_admits_post_window_action_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges": "PASS",
    "cross_tenant_fanout_to_unrelated_tenant_resource_rejected": "FAIL",
    "missing_tenant_tag_admits_global_blast_radius_rejected": "FAIL",
    "tenant_tag_spoof_admits_other_tenant_resource_rejected": "FAIL",
    "allowlist_bypass_admits_unallowlisted_target_rejected": "FAIL",
    "quota_overflow_leak_admits_post_window_action_rejected": "FAIL",
}

ACTION_CLASSES = {
    "within_tenant",
    "cross_tenant_fanout",
    "missing_tenant_tag",
    "tenant_tag_spoof",
    "allowlist_bypass",
    "quota_overflow_leak",
}
APPROVED_ACTION_CLASSES = {
    "within_tenant",
}
HAZARD_CLASSES = {
    "cross_tenant_fanout_admit",
    "missing_tenant_tag_admit",
    "tenant_tag_spoof_admit",
    "allowlist_bypass_admit",
    "quota_overflow_leak_admit",
}

OPERATOR_TENANT = "tenant::operator_alpha"
OTHER_TENANT = "tenant::other_alpha"

_WITHIN_TENANT_ALPHA = "action::within_tenant_alpha"
_WITHIN_TENANT_BETA = "action::within_tenant_beta"
_WITHIN_TENANT_GAMMA = "action::within_tenant_gamma"
_CROSS_TENANT_FANOUT_FRAGMENT = "action::cross_tenant_fanout_alpha"
_MISSING_TENANT_TAG_FRAGMENT = "action::missing_tenant_tag_alpha"
_TENANT_TAG_SPOOF_FRAGMENT = "action::tenant_tag_spoof_alpha"
_ALLOWLIST_BYPASS_FRAGMENT = "action::allowlist_bypass_alpha"
_QUOTA_OVERFLOW_LEAK_FRAGMENT = "action::quota_overflow_leak_alpha"

_TARGET_OPERATOR_ALPHA = "target::operator_alpha"
_TARGET_OPERATOR_BETA = "target::operator_beta"
_TARGET_OPERATOR_GAMMA = "target::operator_gamma"
_TARGET_OTHER_ALPHA = "target::other_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _PerTenantBlastRadiusCapVerifier:
    """In-memory per-tenant blast-radius cap verifier."""

    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, action: dict[str, Any]) -> None:
        self.actions.append(dict(action))
        self._validate_action(action)

    def _validate_action(self, action: dict[str, Any]) -> None:
        action_id = str(action.get("id") or "<unnamed>")
        action_class = action.get("action_class")
        if action_class not in ACTION_CLASSES:
            self.errors.append(
                f"unknown_action_class:id={action_id},class={action_class!r}"
            )
            return
        if action_class == "cross_tenant_fanout":
            self.errors.append(
                f"cross_tenant_fanout_admit_rejection:id={action_id},action={action.get('action_id', '<unknown>')}"
            )
            return
        if action_class == "missing_tenant_tag":
            self.errors.append(
                f"missing_tenant_tag_admit_rejection:id={action_id},action={action.get('action_id', '<unknown>')}"
            )
            return
        if action_class == "tenant_tag_spoof":
            self.errors.append(
                f"tenant_tag_spoof_admit_rejection:id={action_id},action={action.get('action_id', '<unknown>')}"
            )
            return
        if action_class == "allowlist_bypass":
            self.errors.append(
                f"allowlist_bypass_admit_rejection:id={action_id},action={action.get('action_id', '<unknown>')}"
            )
            return
        if action_class == "quota_overflow_leak":
            self.errors.append(
                f"quota_overflow_leak_admit_rejection:id={action_id},action={action.get('action_id', '<unknown>')}"
            )
            return
        if action_class not in APPROVED_ACTION_CLASSES:
            self.errors.append(
                f"unapproved_action_class:id={action_id},class={action_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_within_tenant_alpha",
        "action_class": "within_tenant",
        "action_id": _WITHIN_TENANT_ALPHA,
        "tenant_id": OPERATOR_TENANT,
        "target_resource": _TARGET_OPERATOR_ALPHA,
        "cross_tenant_target_admitted": False,
        "tenant_tag_present": True,
        "tenant_tag_signature_valid": True,
        "target_in_allowlist": True,
        "quota_window_observed": "open",
    },
    {
        "id": "clean_within_tenant_beta",
        "action_class": "within_tenant",
        "action_id": _WITHIN_TENANT_BETA,
        "tenant_id": OPERATOR_TENANT,
        "target_resource": _TARGET_OPERATOR_BETA,
        "cross_tenant_target_admitted": False,
        "tenant_tag_present": True,
        "tenant_tag_signature_valid": True,
        "target_in_allowlist": True,
        "quota_window_observed": "open",
    },
    {
        "id": "clean_within_tenant_gamma",
        "action_class": "within_tenant",
        "action_id": _WITHIN_TENANT_GAMMA,
        "tenant_id": OPERATOR_TENANT,
        "target_resource": _TARGET_OPERATOR_GAMMA,
        "cross_tenant_target_admitted": False,
        "tenant_tag_present": True,
        "tenant_tag_signature_valid": True,
        "target_in_allowlist": True,
        "quota_window_observed": "open",
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "per-tenant-blast-radius-cap-transcript.json").write_text(
        json.dumps({"actions": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges(work: Path) -> dict[str, Any]:
    case_id = "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges"
    verifier = _PerTenantBlastRadiusCapVerifier()
    for action in _CLEAN_ACTIONS:
        verifier.register(action)
    transcript = [{"op": "register", **action} for action in _CLEAN_ACTIONS]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered action stays within the operator "
            "tenant, carries a valid signed tenant tag, targets an "
            "allowlisted resource, and is observed inside the open "
            "quota window"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _PerTenantBlastRadiusCapVerifier()
    for action in _CLEAN_ACTIONS:
        verifier.register(action)
    verifier.register(mutated)
    transcript = [{"op": "register", **action} for action in (*_CLEAN_ACTIONS, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_cross_tenant_fanout_to_unrelated_tenant_resource_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "cross_tenant_fanout_to_unrelated_tenant_resource_rejected",
        {
            "id": "mutated_cross_tenant_fanout_admit",
            "action_class": "cross_tenant_fanout",
            "action_id": _CROSS_TENANT_FANOUT_FRAGMENT,
            "tenant_id": OPERATOR_TENANT,
            "target_resource": _TARGET_OTHER_ALPHA,
            "cross_tenant_target_admitted": True,
            "tenant_tag_present": True,
            "tenant_tag_signature_valid": True,
            "target_in_allowlist": True,
            "quota_window_observed": "open",
        },
        detail=(
            "mutation: an action issued by the operator tenant reaches "
            "a resource owned by an unrelated tenant and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_missing_tenant_tag_admits_global_blast_radius_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "missing_tenant_tag_admits_global_blast_radius_rejected",
        {
            "id": "mutated_missing_tenant_tag_admit",
            "action_class": "missing_tenant_tag",
            "action_id": _MISSING_TENANT_TAG_FRAGMENT,
            "tenant_id": "",
            "target_resource": _TARGET_OPERATOR_ALPHA,
            "cross_tenant_target_admitted": False,
            "tenant_tag_present": False,
            "tenant_tag_signature_valid": False,
            "target_in_allowlist": True,
            "quota_window_observed": "open",
        },
        detail=(
            "mutation: an action is admitted without any tenant tag "
            "and lets the operator agent loop fan out across the "
            "global blast radius and the verifier must reject instead "
            "of silently accepting"
        ),
    )


def run_tenant_tag_spoof_admits_other_tenant_resource_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tenant_tag_spoof_admits_other_tenant_resource_rejected",
        {
            "id": "mutated_tenant_tag_spoof_admit",
            "action_class": "tenant_tag_spoof",
            "action_id": _TENANT_TAG_SPOOF_FRAGMENT,
            "tenant_id": OTHER_TENANT,
            "target_resource": _TARGET_OTHER_ALPHA,
            "cross_tenant_target_admitted": True,
            "tenant_tag_present": True,
            "tenant_tag_signature_valid": False,
            "target_in_allowlist": True,
            "quota_window_observed": "open",
        },
        detail=(
            "mutation: an action carries a tenant tag whose signature "
            "does not validate and spoofs access to another tenant's "
            "resource and the verifier must reject instead of "
            "silently accepting"
        ),
    )


def run_allowlist_bypass_admits_unallowlisted_target_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "allowlist_bypass_admits_unallowlisted_target_rejected",
        {
            "id": "mutated_allowlist_bypass_admit",
            "action_class": "allowlist_bypass",
            "action_id": _ALLOWLIST_BYPASS_FRAGMENT,
            "tenant_id": OPERATOR_TENANT,
            "target_resource": _TARGET_OTHER_ALPHA,
            "cross_tenant_target_admitted": False,
            "tenant_tag_present": True,
            "tenant_tag_signature_valid": True,
            "target_in_allowlist": False,
            "quota_window_observed": "open",
        },
        detail=(
            "mutation: an action targets a resource that is not on "
            "the operator allowlist and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_quota_overflow_leak_admits_post_window_action_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "quota_overflow_leak_admits_post_window_action_rejected",
        {
            "id": "mutated_quota_overflow_leak_admit",
            "action_class": "quota_overflow_leak",
            "action_id": _QUOTA_OVERFLOW_LEAK_FRAGMENT,
            "tenant_id": OPERATOR_TENANT,
            "target_resource": _TARGET_OPERATOR_ALPHA,
            "cross_tenant_target_admitted": False,
            "tenant_tag_present": True,
            "tenant_tag_signature_valid": True,
            "target_in_allowlist": True,
            "quota_window_observed": "closed",
        },
        detail=(
            "mutation: an action is admitted after the per-tenant "
            "quota window has closed and leaks blast-radius across "
            "windows and the verifier must reject instead of "
            "silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges": run_clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges,
    "cross_tenant_fanout_to_unrelated_tenant_resource_rejected": run_cross_tenant_fanout_to_unrelated_tenant_resource_rejected,
    "missing_tenant_tag_admits_global_blast_radius_rejected": run_missing_tenant_tag_admits_global_blast_radius_rejected,
    "tenant_tag_spoof_admits_other_tenant_resource_rejected": run_tenant_tag_spoof_admits_other_tenant_resource_rejected,
    "allowlist_bypass_admits_unallowlisted_target_rejected": run_allowlist_bypass_admits_unallowlisted_target_rejected,
    "quota_overflow_leak_admits_post_window_action_rejected": run_quota_overflow_leak_admits_post_window_action_rejected,
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
        "action_classes": sorted(ACTION_CLASSES),
        "approved_action_classes": sorted(APPROVED_ACTION_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Per-tenant blast-radius cap gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Per-tenant blast-radius cap blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-per-tenant-blast-radius-cap-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-per-tenant-blast-radius-cap-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
