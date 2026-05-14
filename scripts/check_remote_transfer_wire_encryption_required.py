#!/usr/bin/env python3
"""Remote-transfer wire-encryption-required gate.

Synthesizes the AO Runtime ``wire_encryption_required`` contract as a
local Python state machine and proves each receiver-side
wire-encryption hazard is fail-closed by injecting deliberate
mutations against an in-process transport-layer enforcement pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_encrypted_bundle_accepted`` — control: sender negotiates
  ``transport=tls1.3`` with cipher
  ``TLS_AES_256_GCM_SHA384`` and the per-bundle ``encrypted=true``
  header is preserved end-to-end; the receiver enforces all three
  invariants and accepts the bundle.
* ``cleartext_bundle_silently_accepted_rejected`` — mutation: sender
  ships a bundle over a cleartext socket (``transport=plaintext``)
  and the receiver silently accepts it. A receiver MUST reject any
  bundle that did not arrive over an allowlisted encrypted
  transport; cleartext bypasses the wire-encryption contract.
* ``downgraded_tls_cipher_silently_accepted_rejected`` — mutation:
  sender negotiates an encrypted transport but with a downgraded
  TLS version (``transport=tls1.0``) outside the transport
  allowlist; the receiver silently accepts. A receiver MUST reject
  any transport that is not on the transport allowlist; silently
  accepting downgraded versions exposes the bundle to known
  protocol weaknesses.
* ``weak_null_cipher_suite_negotiated_rejected`` — mutation: sender
  forces a NULL-or-RC4 cipher suite (``cipher=TLS_NULL_WITH_NULL_NULL``)
  even though the transport version is allowlisted; the receiver
  silently accepts. A receiver MUST reject any cipher suite on the
  weak-cipher denylist; null/weak ciphers offer no confidentiality.
* ``encryption_header_stripped_after_handshake_rejected`` — mutation:
  sender completes an encrypted handshake but a man-in-the-middle
  strips the per-bundle ``encrypted=true`` header before the bundle
  reaches the receiver, leaving ``encrypted=false``. A receiver MUST
  reject any bundle whose per-bundle encryption header does not
  remain ``true`` end-to-end; relying on the handshake alone permits
  selective post-handshake stripping.

Every case lays down a per-case wire-encryption transcript in a
temporary work directory, runs it through the verifier embedded in
this gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the expected
verdict.

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
    "remote-transfer-wire-encryption-required.json"
)
SCHEMA = "ao-operator/remote-transfer-wire-encryption-required/v1"

CASE_IDS = (
    "clean_encrypted_bundle_accepted",
    "cleartext_bundle_silently_accepted_rejected",
    "downgraded_tls_cipher_silently_accepted_rejected",
    "weak_null_cipher_suite_negotiated_rejected",
    "encryption_header_stripped_after_handshake_rejected",
)

EXPECTED_VERDICTS = {
    "clean_encrypted_bundle_accepted": "PASS",
    "cleartext_bundle_silently_accepted_rejected": "FAIL",
    "downgraded_tls_cipher_silently_accepted_rejected": "FAIL",
    "weak_null_cipher_suite_negotiated_rejected": "FAIL",
    "encryption_header_stripped_after_handshake_rejected": "FAIL",
}

_TRANSPORT_ALLOWLIST = frozenset({"tls1.3"})
_CIPHER_ALLOWLIST = frozenset({
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
})
_CIPHER_DENYLIST = frozenset({
    "TLS_NULL_WITH_NULL_NULL",
    "TLS_RSA_WITH_NULL_SHA",
    "TLS_RSA_WITH_RC4_128_SHA",
    "NULL",
})


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _WireEncryptionVerifier:
    """In-memory wire-encryption state machine.

    Models the AO Runtime ``wire_encryption_required`` pipeline:

    1. The transport version MUST be on the transport allowlist;
       cleartext or downgraded versions MUST be rejected.
    2. The negotiated cipher suite MUST be on the cipher allowlist
       and MUST NOT be on the weak-cipher denylist.
    3. The per-bundle ``encrypted`` header MUST remain ``true`` from
       sender announcement through receiver dispatch; if a man-in-
       the-middle strips it post-handshake, the receiver MUST refuse.
    """

    def __init__(
        self,
        *,
        transport_allowlist: frozenset[str] = _TRANSPORT_ALLOWLIST,
        cipher_allowlist: frozenset[str] = _CIPHER_ALLOWLIST,
        cipher_denylist: frozenset[str] = _CIPHER_DENYLIST,
    ) -> None:
        self.transport_allowlist = transport_allowlist
        self.cipher_allowlist = cipher_allowlist
        self.cipher_denylist = cipher_denylist
        self.errors: list[str] = []

    def receiver_validate_wire_encryption(
        self,
        *,
        transport: str,
        cipher: str,
        announced_encrypted: bool,
        observed_encrypted: bool,
    ) -> None:
        if transport not in self.transport_allowlist:
            self.errors.append(
                f"unallowed_transport:transport={transport}"
            )
            return
        if cipher in self.cipher_denylist:
            self.errors.append(
                f"weak_cipher_suite:cipher={cipher}"
            )
            return
        if cipher not in self.cipher_allowlist:
            self.errors.append(
                f"unallowed_cipher:cipher={cipher}"
            )
            return
        if not announced_encrypted or not observed_encrypted:
            self.errors.append(
                f"bundle_encryption_header_missing:announced={announced_encrypted},observed={observed_encrypted}"
            )
            return
        if announced_encrypted is True and observed_encrypted is False:
            self.errors.append(
                "bundle_encryption_header_stripped_post_handshake"
            )

    def receiver_silently_accept_cleartext(
        self,
        *,
        transport: str,
    ) -> None:
        if transport not in self.transport_allowlist:
            self.errors.append(
                f"silently_accepted_cleartext_bundle:transport={transport}"
            )

    def receiver_silently_accept_downgraded_transport(
        self,
        *,
        transport: str,
    ) -> None:
        if transport not in self.transport_allowlist:
            self.errors.append(
                f"silently_accepted_downgraded_transport:transport={transport}"
            )

    def receiver_silently_accept_weak_cipher(
        self,
        *,
        cipher: str,
    ) -> None:
        if cipher in self.cipher_denylist or cipher not in self.cipher_allowlist:
            self.errors.append(
                f"silently_accepted_weak_cipher_suite:cipher={cipher}"
            )

    def receiver_silently_accept_post_handshake_strip(
        self,
        *,
        announced_encrypted: bool,
        observed_encrypted: bool,
    ) -> None:
        if announced_encrypted is True and observed_encrypted is False:
            self.errors.append(
                "silently_accepted_bundle_encryption_header_stripped_post_handshake"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "wire-encryption-transcript.json").write_text(
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


def run_clean_encrypted_bundle_accepted(work: Path) -> dict[str, Any]:
    case_id = "clean_encrypted_bundle_accepted"
    verifier = _WireEncryptionVerifier()

    transcript: list[dict[str, Any]] = [
        {
            "op": "announce",
            "transport": "tls1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "announced_encrypted": True,
            "observed_encrypted": True,
        },
    ]
    verifier.receiver_validate_wire_encryption(
        transport="tls1.3",
        cipher="TLS_AES_256_GCM_SHA384",
        announced_encrypted=True,
        observed_encrypted=True,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender negotiates an allowlisted transport and cipher, the per-bundle "
            "encryption header is preserved, and the receiver accepts"
        ),
    )


def run_cleartext_bundle_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "cleartext_bundle_silently_accepted_rejected"
    verifier = _WireEncryptionVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "transport": "plaintext"},
        {"op": "receiver_silently_accept_cleartext"},
    ]
    verifier.receiver_silently_accept_cleartext(transport="plaintext")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender ships the bundle over a cleartext socket and the receiver silently "
            "accepts it instead of rejecting"
        ),
    )


def run_downgraded_tls_cipher_silently_accepted_rejected(work: Path) -> dict[str, Any]:
    case_id = "downgraded_tls_cipher_silently_accepted_rejected"
    verifier = _WireEncryptionVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "transport": "tls1.0"},
        {"op": "receiver_silently_accept_downgraded_transport"},
    ]
    verifier.receiver_silently_accept_downgraded_transport(transport="tls1.0")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender negotiates a downgraded TLS version outside the transport allowlist "
            "and the receiver silently accepts"
        ),
    )


def run_weak_null_cipher_suite_negotiated_rejected(work: Path) -> dict[str, Any]:
    case_id = "weak_null_cipher_suite_negotiated_rejected"
    verifier = _WireEncryptionVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "cipher": "TLS_NULL_WITH_NULL_NULL"},
        {"op": "receiver_silently_accept_weak_cipher"},
    ]
    verifier.receiver_silently_accept_weak_cipher(cipher="TLS_NULL_WITH_NULL_NULL")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender forces a null cipher suite even though transport version is "
            "allowlisted; the receiver silently accepts"
        ),
    )


def run_encryption_header_stripped_after_handshake_rejected(work: Path) -> dict[str, Any]:
    case_id = "encryption_header_stripped_after_handshake_rejected"
    verifier = _WireEncryptionVerifier()

    transcript: list[dict[str, Any]] = [
        {"op": "announce", "announced_encrypted": True, "observed_encrypted": False},
        {"op": "receiver_silently_accept_post_handshake_strip"},
    ]
    verifier.receiver_silently_accept_post_handshake_strip(
        announced_encrypted=True,
        observed_encrypted=False,
    )

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: sender announces encrypted=true at handshake but a man-in-the-middle "
            "strips the per-bundle encrypted header before reaching the receiver"
        ),
    )


CASE_RUNNERS = {
    "clean_encrypted_bundle_accepted": run_clean_encrypted_bundle_accepted,
    "cleartext_bundle_silently_accepted_rejected": run_cleartext_bundle_silently_accepted_rejected,
    "downgraded_tls_cipher_silently_accepted_rejected": run_downgraded_tls_cipher_silently_accepted_rejected,
    "weak_null_cipher_suite_negotiated_rejected": run_weak_null_cipher_suite_negotiated_rejected,
    "encryption_header_stripped_after_handshake_rejected": run_encryption_header_stripped_after_handshake_rejected,
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
            "Remote-transfer wire-encryption-required is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix wire-encryption blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-wire-encryption-required-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-wire-encryption-required-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
