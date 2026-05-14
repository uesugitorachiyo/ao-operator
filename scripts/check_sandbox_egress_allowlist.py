#!/usr/bin/env python3
"""Sandbox egress allowlist gate.

Models the sandbox egress allowlist invariant that no AO Operator
agent sandbox egress attempt can reach a host that is not on the
operator allowlist and that no IP-literal bypass, no
DNS-rebind bypass, no proxy-chain bypass, and no raw-socket
bypass can be admitted as a side-channel around the allowlist.

Every egress edge whose target host, IP literal, DNS resolution,
proxy chain, or raw-socket state would let the sandbox escape
the operator allowlist is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real network connection or sandbox runtime invoked):

* ``clean_no_unallowlisted_or_bypassed_egress_attempts`` --
  control: every registered egress targets a host on the
  operator allowlist with no IP-literal bypass, no DNS-rebind
  bypass, no proxy-chain bypass, and no raw-socket bypass.
* ``unallowlisted_host_egress_admitted_rejected`` -- mutation:
  an egress targets a host that is not on the operator
  allowlist; the verifier MUST reject.
* ``ip_literal_bypass_admits_unallowlisted_target_rejected`` --
  mutation: an egress uses a literal IP address to bypass
  hostname-based allowlist checking and reach an unallowlisted
  target; the verifier MUST reject.
* ``dns_rebind_bypass_admits_unallowlisted_target_rejected`` --
  mutation: an egress relies on inconsistent DNS resolution
  between the allowlist check and the actual connection to
  bypass the allowlist; the verifier MUST reject.
* ``proxy_chain_bypass_admits_unallowlisted_target_rejected`` --
  mutation: an egress is routed through a proxy chain that
  conceals an unallowlisted target host from the allowlist
  check; the verifier MUST reject.
* ``raw_socket_bypass_admits_unallowlisted_target_rejected`` --
  mutation: an egress opens a raw socket to an unallowlisted
  target, bypassing the higher-layer allowlist check; the
  verifier MUST reject.

Every case lays down a per-case
``sandbox-egress-allowlist-transcript.json`` in a temporary
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
    "sandbox-egress-allowlist.json"
)
SCHEMA = "ao-operator/sandbox-egress-allowlist/v1"

CASE_IDS = (
    "clean_no_unallowlisted_or_bypassed_egress_attempts",
    "unallowlisted_host_egress_admitted_rejected",
    "ip_literal_bypass_admits_unallowlisted_target_rejected",
    "dns_rebind_bypass_admits_unallowlisted_target_rejected",
    "proxy_chain_bypass_admits_unallowlisted_target_rejected",
    "raw_socket_bypass_admits_unallowlisted_target_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_unallowlisted_or_bypassed_egress_attempts": "PASS",
    "unallowlisted_host_egress_admitted_rejected": "FAIL",
    "ip_literal_bypass_admits_unallowlisted_target_rejected": "FAIL",
    "dns_rebind_bypass_admits_unallowlisted_target_rejected": "FAIL",
    "proxy_chain_bypass_admits_unallowlisted_target_rejected": "FAIL",
    "raw_socket_bypass_admits_unallowlisted_target_rejected": "FAIL",
}

EGRESS_CLASSES = {
    "allowlisted_egress",
    "unallowlisted_host_egress",
    "ip_literal_bypass",
    "dns_rebind_bypass",
    "proxy_chain_bypass",
    "raw_socket_bypass",
}
APPROVED_EGRESS_CLASSES = {
    "allowlisted_egress",
}
HAZARD_CLASSES = {
    "unallowlisted_host_egress_admit",
    "ip_literal_bypass_admit",
    "dns_rebind_bypass_admit",
    "proxy_chain_bypass_admit",
    "raw_socket_bypass_admit",
}

OPERATOR_HOST_ALPHA = "host::operator_alpha"
OPERATOR_HOST_BETA = "host::operator_beta"
OPERATOR_HOST_GAMMA = "host::operator_gamma"
UNALLOWLISTED_HOST = "host::unallowlisted_alpha"

_ALLOWLISTED_EGRESS_ALPHA = "egress::allowlisted_alpha"
_ALLOWLISTED_EGRESS_BETA = "egress::allowlisted_beta"
_ALLOWLISTED_EGRESS_GAMMA = "egress::allowlisted_gamma"
_UNALLOWLISTED_HOST_FRAGMENT = "egress::unallowlisted_host_alpha"
_IP_LITERAL_BYPASS_FRAGMENT = "egress::ip_literal_bypass_alpha"
_DNS_REBIND_BYPASS_FRAGMENT = "egress::dns_rebind_bypass_alpha"
_PROXY_CHAIN_BYPASS_FRAGMENT = "egress::proxy_chain_bypass_alpha"
_RAW_SOCKET_BYPASS_FRAGMENT = "egress::raw_socket_bypass_alpha"

_IP_LITERAL_ALPHA = "ip::literal_alpha"
_PROXY_CHAIN_ALPHA = "proxy::chain_alpha"
_RAW_SOCKET_ALPHA = "socket::raw_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _SandboxEgressAllowlistVerifier:
    """In-memory sandbox egress allowlist verifier."""

    def __init__(self) -> None:
        self.egresses: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, egress: dict[str, Any]) -> None:
        self.egresses.append(dict(egress))
        self._validate_egress(egress)

    def _validate_egress(self, egress: dict[str, Any]) -> None:
        egress_id = str(egress.get("id") or "<unnamed>")
        egress_class = egress.get("egress_class")
        if egress_class not in EGRESS_CLASSES:
            self.errors.append(
                f"unknown_egress_class:id={egress_id},class={egress_class!r}"
            )
            return
        if egress_class == "unallowlisted_host_egress":
            self.errors.append(
                f"unallowlisted_host_egress_admit_rejection:id={egress_id},egress={egress.get('egress_id', '<unknown>')}"
            )
            return
        if egress_class == "ip_literal_bypass":
            self.errors.append(
                f"ip_literal_bypass_admit_rejection:id={egress_id},egress={egress.get('egress_id', '<unknown>')}"
            )
            return
        if egress_class == "dns_rebind_bypass":
            self.errors.append(
                f"dns_rebind_bypass_admit_rejection:id={egress_id},egress={egress.get('egress_id', '<unknown>')}"
            )
            return
        if egress_class == "proxy_chain_bypass":
            self.errors.append(
                f"proxy_chain_bypass_admit_rejection:id={egress_id},egress={egress.get('egress_id', '<unknown>')}"
            )
            return
        if egress_class == "raw_socket_bypass":
            self.errors.append(
                f"raw_socket_bypass_admit_rejection:id={egress_id},egress={egress.get('egress_id', '<unknown>')}"
            )
            return
        if egress_class not in APPROVED_EGRESS_CLASSES:
            self.errors.append(
                f"unapproved_egress_class:id={egress_id},class={egress_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EGRESSES: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_allowlisted_egress_alpha",
        "egress_class": "allowlisted_egress",
        "egress_id": _ALLOWLISTED_EGRESS_ALPHA,
        "target_host": OPERATOR_HOST_ALPHA,
        "target_ip_literal": "",
        "dns_resolution_consistent": True,
        "proxy_chain_observed": False,
        "raw_socket_observed": False,
        "target_in_allowlist": True,
    },
    {
        "id": "clean_allowlisted_egress_beta",
        "egress_class": "allowlisted_egress",
        "egress_id": _ALLOWLISTED_EGRESS_BETA,
        "target_host": OPERATOR_HOST_BETA,
        "target_ip_literal": "",
        "dns_resolution_consistent": True,
        "proxy_chain_observed": False,
        "raw_socket_observed": False,
        "target_in_allowlist": True,
    },
    {
        "id": "clean_allowlisted_egress_gamma",
        "egress_class": "allowlisted_egress",
        "egress_id": _ALLOWLISTED_EGRESS_GAMMA,
        "target_host": OPERATOR_HOST_GAMMA,
        "target_ip_literal": "",
        "dns_resolution_consistent": True,
        "proxy_chain_observed": False,
        "raw_socket_observed": False,
        "target_in_allowlist": True,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "sandbox-egress-allowlist-transcript.json").write_text(
        json.dumps({"egresses": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_unallowlisted_or_bypassed_egress_attempts(work: Path) -> dict[str, Any]:
    case_id = "clean_no_unallowlisted_or_bypassed_egress_attempts"
    verifier = _SandboxEgressAllowlistVerifier()
    for egress in _CLEAN_EGRESSES:
        verifier.register(egress)
    transcript = [{"op": "register", **egress} for egress in _CLEAN_EGRESSES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered egress targets a host on the "
            "operator allowlist with no IP-literal bypass, no "
            "DNS-rebind bypass, no proxy-chain bypass, and no "
            "raw-socket bypass"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _SandboxEgressAllowlistVerifier()
    for egress in _CLEAN_EGRESSES:
        verifier.register(egress)
    verifier.register(mutated)
    transcript = [{"op": "register", **egress} for egress in (*_CLEAN_EGRESSES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_unallowlisted_host_egress_admitted_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "unallowlisted_host_egress_admitted_rejected",
        {
            "id": "mutated_unallowlisted_host_egress_admit",
            "egress_class": "unallowlisted_host_egress",
            "egress_id": _UNALLOWLISTED_HOST_FRAGMENT,
            "target_host": UNALLOWLISTED_HOST,
            "target_ip_literal": "",
            "dns_resolution_consistent": True,
            "proxy_chain_observed": False,
            "raw_socket_observed": False,
            "target_in_allowlist": False,
        },
        detail=(
            "mutation: an egress targets a host that is not on the "
            "operator allowlist and the verifier must reject instead "
            "of silently accepting"
        ),
    )


def run_ip_literal_bypass_admits_unallowlisted_target_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "ip_literal_bypass_admits_unallowlisted_target_rejected",
        {
            "id": "mutated_ip_literal_bypass_admit",
            "egress_class": "ip_literal_bypass",
            "egress_id": _IP_LITERAL_BYPASS_FRAGMENT,
            "target_host": "",
            "target_ip_literal": _IP_LITERAL_ALPHA,
            "dns_resolution_consistent": True,
            "proxy_chain_observed": False,
            "raw_socket_observed": False,
            "target_in_allowlist": False,
        },
        detail=(
            "mutation: an egress uses a literal IP address to bypass "
            "hostname-based allowlist checking and reach an "
            "unallowlisted target and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_dns_rebind_bypass_admits_unallowlisted_target_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "dns_rebind_bypass_admits_unallowlisted_target_rejected",
        {
            "id": "mutated_dns_rebind_bypass_admit",
            "egress_class": "dns_rebind_bypass",
            "egress_id": _DNS_REBIND_BYPASS_FRAGMENT,
            "target_host": OPERATOR_HOST_ALPHA,
            "target_ip_literal": "",
            "dns_resolution_consistent": False,
            "proxy_chain_observed": False,
            "raw_socket_observed": False,
            "target_in_allowlist": False,
        },
        detail=(
            "mutation: an egress relies on inconsistent DNS "
            "resolution between the allowlist check and the actual "
            "connection to bypass the allowlist and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_proxy_chain_bypass_admits_unallowlisted_target_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "proxy_chain_bypass_admits_unallowlisted_target_rejected",
        {
            "id": "mutated_proxy_chain_bypass_admit",
            "egress_class": "proxy_chain_bypass",
            "egress_id": _PROXY_CHAIN_BYPASS_FRAGMENT,
            "target_host": _PROXY_CHAIN_ALPHA,
            "target_ip_literal": "",
            "dns_resolution_consistent": True,
            "proxy_chain_observed": True,
            "raw_socket_observed": False,
            "target_in_allowlist": False,
        },
        detail=(
            "mutation: an egress is routed through a proxy chain "
            "that conceals an unallowlisted target host from the "
            "allowlist check and the verifier must reject instead "
            "of silently accepting"
        ),
    )


def run_raw_socket_bypass_admits_unallowlisted_target_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "raw_socket_bypass_admits_unallowlisted_target_rejected",
        {
            "id": "mutated_raw_socket_bypass_admit",
            "egress_class": "raw_socket_bypass",
            "egress_id": _RAW_SOCKET_BYPASS_FRAGMENT,
            "target_host": "",
            "target_ip_literal": _RAW_SOCKET_ALPHA,
            "dns_resolution_consistent": True,
            "proxy_chain_observed": False,
            "raw_socket_observed": True,
            "target_in_allowlist": False,
        },
        detail=(
            "mutation: an egress opens a raw socket to an "
            "unallowlisted target, bypassing the higher-layer "
            "allowlist check and the verifier must reject instead "
            "of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_unallowlisted_or_bypassed_egress_attempts": run_clean_no_unallowlisted_or_bypassed_egress_attempts,
    "unallowlisted_host_egress_admitted_rejected": run_unallowlisted_host_egress_admitted_rejected,
    "ip_literal_bypass_admits_unallowlisted_target_rejected": run_ip_literal_bypass_admits_unallowlisted_target_rejected,
    "dns_rebind_bypass_admits_unallowlisted_target_rejected": run_dns_rebind_bypass_admits_unallowlisted_target_rejected,
    "proxy_chain_bypass_admits_unallowlisted_target_rejected": run_proxy_chain_bypass_admits_unallowlisted_target_rejected,
    "raw_socket_bypass_admits_unallowlisted_target_rejected": run_raw_socket_bypass_admits_unallowlisted_target_rejected,
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
        "egress_classes": sorted(EGRESS_CLASSES),
        "approved_egress_classes": sorted(APPROVED_EGRESS_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Sandbox egress allowlist gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Sandbox egress allowlist blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-sandbox-egress-allowlist-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-sandbox-egress-allowlist-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
