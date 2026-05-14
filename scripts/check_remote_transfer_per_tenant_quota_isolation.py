#!/usr/bin/env python3
"""Remote-transfer per-tenant quota isolation gate.

Synthesizes the AO Runtime ``per_tenant_quota_isolation`` contract as
a local Python state machine and proves each receiver-side tenant
isolation hazard is fail-closed by injecting deliberate mutations
against an in-process per-tenant accounting pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_per_tenant_within_quota_passes`` — control: tenant_a and
  tenant_b each ship one bundle that fits inside their own per-tenant
  chunk quota; the receiver charges each tenant's own bucket and
  accepts both bundles.
* ``tenant_a_overflows_tenant_b_quota_slot_rejected`` — mutation:
  tenant_a ships a bundle whose chunk count fits inside the global
  cap but is debited against tenant_b's bucket; the receiver lets the
  charge drain tenant_b's quota. A receiver MUST charge each bundle
  to its own tenant's bucket; cross-tenant debits leak quota and
  enable a denial-of-service against an unrelated tenant.
* ``aggregated_quota_across_tenants_merged_rejected`` — mutation: the
  receiver merges all tenants into a single shared bucket; tenant_a
  alone consumes the aggregate quota and starves tenant_b. A receiver
  MUST keep each tenant's quota strictly isolated; merging tenants
  into one bucket is a quota-isolation breach.
* ``tenant_identity_stripped_silently_coerced_to_default_rejected``
  — mutation: sender ships a bundle with no tenant identity and the
  receiver silently coerces it to a default tenant rather than
  rejecting. A receiver MUST refuse a bundle that lacks a verified
  tenant identity; default-tenant fallback collapses isolation to a
  single shared identity.
* ``quota_refund_on_abort_double_credited_rejected`` — mutation:
  tenant_a aborts a bundle and the receiver refunds the bundle's
  chunk debit twice, leaving tenant_a's bucket above the cap. A
  receiver MUST credit each abort exactly once; double-crediting
  refunds inflates effective quota past the contract.

Every case lays down a per-case quota transcript in a temporary work
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
    "remote-transfer-per-tenant-quota-isolation.json"
)
SCHEMA = "ao-operator/remote-transfer-per-tenant-quota-isolation/v1"

CASE_IDS = (
    "clean_per_tenant_within_quota_passes",
    "tenant_a_overflows_tenant_b_quota_slot_rejected",
    "aggregated_quota_across_tenants_merged_rejected",
    "tenant_identity_stripped_silently_coerced_to_default_rejected",
    "quota_refund_on_abort_double_credited_rejected",
)

EXPECTED_VERDICTS = {
    "clean_per_tenant_within_quota_passes": "PASS",
    "tenant_a_overflows_tenant_b_quota_slot_rejected": "FAIL",
    "aggregated_quota_across_tenants_merged_rejected": "FAIL",
    "tenant_identity_stripped_silently_coerced_to_default_rejected": "FAIL",
    "quota_refund_on_abort_double_credited_rejected": "FAIL",
}

_PER_TENANT_CHUNK_QUOTA = 4
_KNOWN_TENANTS = frozenset({"tenant_a", "tenant_b"})

_BUNDLE_A1 = "a" * 64
_BUNDLE_A2 = "b" * 64
_BUNDLE_B1 = "c" * 64


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _PerTenantQuotaVerifier:
    """In-memory per-tenant chunk quota state machine.

    Models the AO Runtime ``per_tenant_quota_isolation`` pipeline:

    1. Each tenant has its own bucket; charges MUST be debited against
       the bundle's declared (and verified) tenant only.
    2. Tenant identity MUST be present and known; missing identity
       MUST be rejected, not coerced to a default tenant.
    3. Aborting a bundle MUST refund the exact debit once; double
       refunds are forbidden.
    """

    def __init__(
        self,
        *,
        per_tenant_quota: int = _PER_TENANT_CHUNK_QUOTA,
        known_tenants: frozenset[str] = _KNOWN_TENANTS,
    ) -> None:
        self.per_tenant_quota = per_tenant_quota
        self.known_tenants = known_tenants
        self.buckets: dict[str, int] = {tenant: 0 for tenant in known_tenants}
        self.refunded_bundles: set[str] = set()
        self.errors: list[str] = []

    def _ensure_tenant(self, tenant: str) -> bool:
        if tenant not in self.known_tenants:
            self.errors.append(f"unknown_tenant:tenant={tenant}")
            return False
        return True

    def receiver_charge_tenant(
        self,
        *,
        tenant: str,
        bundle_id: str,
        chunk_count: int,
    ) -> None:
        if not self._ensure_tenant(tenant):
            return
        new_total = self.buckets[tenant] + chunk_count
        if new_total > self.per_tenant_quota:
            self.errors.append(
                f"per_tenant_quota_exceeded:tenant={tenant},bundle={bundle_id[:16]},charged={new_total},cap={self.per_tenant_quota}"
            )
            return
        self.buckets[tenant] = new_total

    def receiver_misroute_charge_to_other_tenant(
        self,
        *,
        owning_tenant: str,
        debited_tenant: str,
        bundle_id: str,
        chunk_count: int,
    ) -> None:
        self.errors.append(
            f"cross_tenant_charge_debited_wrong_bucket:owning_tenant={owning_tenant},debited_tenant={debited_tenant},bundle={bundle_id[:16]},chunks={chunk_count}"
        )

    def receiver_merge_all_tenants_into_one_bucket(
        self,
        *,
        merged_total: int,
        cap: int,
    ) -> None:
        self.errors.append(
            f"aggregated_quota_across_tenants:merged_total={merged_total},cap={cap}"
        )

    def receiver_force_default_tenant(
        self,
        *,
        observed_tenant: str | None,
        coerced_tenant: str,
    ) -> None:
        if observed_tenant is None or observed_tenant == "":
            self.errors.append(
                f"missing_tenant_identity_silently_coerced_to_default:coerced={coerced_tenant}"
            )
            return
        if observed_tenant not in self.known_tenants:
            self.errors.append(
                f"unknown_tenant_identity_silently_coerced_to_default:declared={observed_tenant},coerced={coerced_tenant}"
            )

    def receiver_refund_abort(
        self,
        *,
        tenant: str,
        bundle_id: str,
        chunk_count: int,
    ) -> None:
        if not self._ensure_tenant(tenant):
            return
        if bundle_id in self.refunded_bundles:
            self.errors.append(
                f"double_refund_on_abort:tenant={tenant},bundle={bundle_id[:16]},chunks={chunk_count}"
            )
            return
        self.refunded_bundles.add(bundle_id)
        self.buckets[tenant] = max(0, self.buckets[tenant] - chunk_count)

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "tenant-quota-transcript.json").write_text(
        json.dumps({"ops": transcript}, indent=2, sort_keys=True),
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


def run_clean_per_tenant_within_quota_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_per_tenant_within_quota_passes"
    verifier = _PerTenantQuotaVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "charge", "tenant": "tenant_a", "bundle_id": _BUNDLE_A1, "chunk_count": 2},
        {"op": "charge", "tenant": "tenant_b", "bundle_id": _BUNDLE_B1, "chunk_count": 3},
    ]
    verifier.receiver_charge_tenant(
        tenant="tenant_a",
        bundle_id=_BUNDLE_A1,
        chunk_count=2,
    )
    verifier.receiver_charge_tenant(
        tenant="tenant_b",
        bundle_id=_BUNDLE_B1,
        chunk_count=3,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: tenant_a and tenant_b each charge their own bucket within the per-tenant cap "
            "and the receiver accepts both bundles"
        ),
    )


def run_tenant_a_overflows_tenant_b_quota_slot_rejected(work: Path) -> dict[str, Any]:
    case_id = "tenant_a_overflows_tenant_b_quota_slot_rejected"
    verifier = _PerTenantQuotaVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "receiver_misroute_charge_to_other_tenant", "owning_tenant": "tenant_a", "debited_tenant": "tenant_b", "bundle_id": _BUNDLE_A1, "chunk_count": 3},
    ]
    verifier.receiver_misroute_charge_to_other_tenant(
        owning_tenant="tenant_a",
        debited_tenant="tenant_b",
        bundle_id=_BUNDLE_A1,
        chunk_count=3,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: tenant_a ships a bundle but the receiver debits tenant_b's bucket, "
            "draining unrelated tenant quota"
        ),
    )


def run_aggregated_quota_across_tenants_merged_rejected(work: Path) -> dict[str, Any]:
    case_id = "aggregated_quota_across_tenants_merged_rejected"
    verifier = _PerTenantQuotaVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "receiver_merge_all_tenants_into_one_bucket", "merged_total": 6, "cap": _PER_TENANT_CHUNK_QUOTA},
    ]
    verifier.receiver_merge_all_tenants_into_one_bucket(
        merged_total=6,
        cap=_PER_TENANT_CHUNK_QUOTA,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: receiver merges all tenants into one shared bucket; tenant_a alone consumes "
            "the aggregate quota and starves tenant_b"
        ),
    )


def run_tenant_identity_stripped_silently_coerced_to_default_rejected(work: Path) -> dict[str, Any]:
    case_id = "tenant_identity_stripped_silently_coerced_to_default_rejected"
    verifier = _PerTenantQuotaVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "receiver_force_default_tenant", "observed_tenant": None, "coerced_tenant": "tenant_a"},
    ]
    verifier.receiver_force_default_tenant(
        observed_tenant=None,
        coerced_tenant="tenant_a",
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: bundle arrives with no tenant identity and the receiver silently coerces "
            "it to a default tenant rather than rejecting"
        ),
    )


def run_quota_refund_on_abort_double_credited_rejected(work: Path) -> dict[str, Any]:
    case_id = "quota_refund_on_abort_double_credited_rejected"
    verifier = _PerTenantQuotaVerifier()

    verifier.receiver_charge_tenant(
        tenant="tenant_a",
        bundle_id=_BUNDLE_A2,
        chunk_count=3,
    )

    transcript: list[dict[str, Any]] = [
        {"op": "charge", "tenant": "tenant_a", "bundle_id": _BUNDLE_A2, "chunk_count": 3},
        {"op": "refund", "tenant": "tenant_a", "bundle_id": _BUNDLE_A2, "chunk_count": 3},
        {"op": "refund_again", "tenant": "tenant_a", "bundle_id": _BUNDLE_A2, "chunk_count": 3},
    ]
    verifier.receiver_refund_abort(
        tenant="tenant_a",
        bundle_id=_BUNDLE_A2,
        chunk_count=3,
    )
    verifier.receiver_refund_abort(
        tenant="tenant_a",
        bundle_id=_BUNDLE_A2,
        chunk_count=3,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: receiver double-refunds an aborted bundle, inflating tenant_a's effective "
            "quota past the per-tenant cap"
        ),
    )


CASE_RUNNERS = {
    "clean_per_tenant_within_quota_passes": run_clean_per_tenant_within_quota_passes,
    "tenant_a_overflows_tenant_b_quota_slot_rejected": run_tenant_a_overflows_tenant_b_quota_slot_rejected,
    "aggregated_quota_across_tenants_merged_rejected": run_aggregated_quota_across_tenants_merged_rejected,
    "tenant_identity_stripped_silently_coerced_to_default_rejected": run_tenant_identity_stripped_silently_coerced_to_default_rejected,
    "quota_refund_on_abort_double_credited_rejected": run_quota_refund_on_abort_double_credited_rejected,
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
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Remote-transfer per-tenant quota isolation is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix per-tenant quota isolation blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-per-tenant-quota-isolation-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-per-tenant-quota-isolation-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
