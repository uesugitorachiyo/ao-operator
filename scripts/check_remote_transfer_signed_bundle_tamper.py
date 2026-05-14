#!/usr/bin/env python3
"""Remote-transfer signed-bundle tamper gate.

Synthesizes the AO Runtime ``signed_bundle_transfer`` integrity contract
as a local Python state machine and proves that each tamper mode is
fail-closed by injecting deliberate mutations against an in-process
verifier.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_signed_bundle_passes`` — control: a well-formed, freshly
  signed bundle with a registered key id and unseen nonce verifies.
* ``truncated_bundle_rejected`` — mutation: chunk payload is shorter
  than the declared length; size invariant must reject it.
* ``swapped_chunk_rejected`` — mutation: chunk[1] payload is swapped
  with chunk[2]; per-chunk digest invariant must reject it.
* ``wrong_signing_key_rejected`` — mutation: bundle signed with an
  unregistered key id; signing-identity invariant must reject it.
* ``replayed_bundle_rejected`` — mutation: bundle nonce already present
  in the seen-nonces set; replay invariant must reject it.
* ``manifest_digest_mismatch_rejected`` — mutation: manifest declares
  chunk[0] digest X but the actual bytes hash to Y; declared-digest
  invariant must reject it.

Every case lays down an on-disk bundle under the work directory,
populates the manifest + signature in memory, and runs the verifier
embedded in this gate. Each case's ``observed_verdict`` is then
compared against the expected verdict; the gate's overall verdict is
``PASS`` only when every case lines up.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "remote-transfer-signed-bundle-tamper.json"
)
SCHEMA = "ao-operator/remote-transfer-signed-bundle-tamper/v1"

CASE_IDS = (
    "clean_signed_bundle_passes",
    "truncated_bundle_rejected",
    "swapped_chunk_rejected",
    "wrong_signing_key_rejected",
    "replayed_bundle_rejected",
    "manifest_digest_mismatch_rejected",
)

EXPECTED_VERDICTS = {
    "clean_signed_bundle_passes": "PASS",
    "truncated_bundle_rejected": "FAIL",
    "swapped_chunk_rejected": "FAIL",
    "wrong_signing_key_rejected": "FAIL",
    "replayed_bundle_rejected": "FAIL",
    "manifest_digest_mismatch_rejected": "FAIL",
}


REGISTERED_KEYS = {
    "kid-primary": b"ao-operator-test-secret-primary",
    "kid-secondary": b"ao-operator-test-secret-secondary",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _bundle_dir(work: Path, case_id: str) -> Path:
    bundle = work / case_id
    bundle.mkdir(parents=True, exist_ok=True)
    return bundle


def _chunk_path(bundle: Path, index: int) -> Path:
    return bundle / f"chunk-{index:04d}.bin"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(manifest: dict[str, Any], *, kid: str, secret: bytes) -> str:
    digest = hmac.new(secret, _canonical_manifest_bytes(manifest), hashlib.sha256)
    return f"{kid}:{digest.hexdigest()}"


def _verify(
    bundle: Path,
    manifest: dict[str, Any],
    signature: str,
    *,
    seen_nonces: set[str],
) -> tuple[str, list[str]]:
    """Return (verdict, errors) for a signed bundle.

    Enforces five tamper invariants distilled from the AO Runtime
    signed_bundle_transfer contract: declared chunk size must match
    actual size, manifest digest must match actual chunk bytes, chunk
    order must match manifest order (no swaps), the signing key id must
    be in the registered set with a matching HMAC, and the nonce must
    not appear in the seen-nonces replay window.
    """
    errors: list[str] = []
    if not bundle.exists():
        return ("FAIL", ["bundle_dir_missing"])

    declared_chunks = list(manifest.get("chunks") or [])

    for entry in declared_chunks:
        idx = int(entry["index"])
        path = _chunk_path(bundle, idx)
        if not path.is_file():
            errors.append(f"missing_chunk:{idx}")
            continue
        actual_size = path.stat().st_size
        if actual_size != int(entry["size"]):
            errors.append(
                f"truncated_or_oversize_chunk:index={idx},declared={entry['size']},actual={actual_size}"
            )

    for entry in declared_chunks:
        idx = int(entry["index"])
        path = _chunk_path(bundle, idx)
        if not path.is_file():
            continue
        actual_digest = _digest(path.read_bytes())
        if actual_digest != entry.get("sha256"):
            errors.append(
                f"chunk_digest_mismatch:index={idx},declared={entry.get('sha256')},actual={actual_digest}"
            )

    try:
        kid, sig_hex = signature.split(":", 1)
    except ValueError:
        errors.append("malformed_signature")
        kid, sig_hex = "", ""
    secret = REGISTERED_KEYS.get(kid)
    if secret is None:
        errors.append(f"unregistered_signing_key:kid={kid!r}")
    else:
        expected = hmac.new(secret, _canonical_manifest_bytes(manifest), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig_hex):
            errors.append("signature_mismatch")

    nonce = manifest.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        errors.append("missing_nonce")
    elif nonce in seen_nonces:
        errors.append(f"nonce_replayed:{nonce}")

    return ("PASS" if not errors else "FAIL", errors)


def _case_summary(
    case_id: str,
    *,
    observed_verdict: str,
    chunk_count: int,
    observed_errors: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "chunk_count": chunk_count,
        "observed_errors": observed_errors,
        "detail": detail,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def _build_clean_bundle(work: Path, case_id: str, *, nonce: str) -> tuple[Path, dict[str, Any], str]:
    bundle = _bundle_dir(work, case_id)
    payloads = [b"alpha-bytes", b"bravo-bytes-longer", b"charlie"]
    chunks_meta = []
    for i, payload in enumerate(payloads):
        path = _chunk_path(bundle, i)
        path.write_bytes(payload)
        chunks_meta.append({"index": i, "size": len(payload), "sha256": _digest(payload)})
    manifest = {
        "approval_id": f"approval-{case_id}",
        "nonce": nonce,
        "chunks": chunks_meta,
    }
    signature = _sign(manifest, kid="kid-primary", secret=REGISTERED_KEYS["kid-primary"])
    return bundle, manifest, signature


def run_clean_signed_bundle_passes(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "clean_signed_bundle_passes"
    bundle, manifest, signature = _build_clean_bundle(work, case_id, nonce="nonce-clean-001")
    verdict, errors = _verify(bundle, manifest, signature, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="control: registered kid signs canonical manifest with fresh nonce",
    )


def run_truncated_bundle_rejected(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "truncated_bundle_rejected"
    bundle, manifest, signature = _build_clean_bundle(work, case_id, nonce="nonce-truncate-002")
    truncated_idx = 1
    target = _chunk_path(bundle, truncated_idx)
    target.write_bytes(target.read_bytes()[:3])
    verdict, errors = _verify(bundle, manifest, signature, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="mutation: chunk-1 payload truncated below manifest declared size",
    )


def run_swapped_chunk_rejected(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "swapped_chunk_rejected"
    bundle, manifest, signature = _build_clean_bundle(work, case_id, nonce="nonce-swap-003")
    one = _chunk_path(bundle, 1)
    two = _chunk_path(bundle, 2)
    bytes_one, bytes_two = one.read_bytes(), two.read_bytes()
    one.write_bytes(bytes_two)
    two.write_bytes(bytes_one)
    verdict, errors = _verify(bundle, manifest, signature, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="mutation: chunk-1 and chunk-2 payloads swapped on disk",
    )


def run_wrong_signing_key_rejected(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "wrong_signing_key_rejected"
    bundle, manifest, _signature = _build_clean_bundle(work, case_id, nonce="nonce-wrongkey-004")
    rogue_signature = _sign(manifest, kid="kid-rogue", secret=b"rogue-secret-not-registered")
    verdict, errors = _verify(bundle, manifest, rogue_signature, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="mutation: bundle signed with kid-rogue (not in REGISTERED_KEYS)",
    )


def run_replayed_bundle_rejected(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "replayed_bundle_rejected"
    nonce = "nonce-replayed-005"
    seen_nonces.add(nonce)
    bundle, manifest, signature = _build_clean_bundle(work, case_id, nonce=nonce)
    verdict, errors = _verify(bundle, manifest, signature, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="mutation: bundle nonce already present in seen-nonces replay window",
    )


def run_manifest_digest_mismatch_rejected(work: Path, *, seen_nonces: set[str]) -> dict[str, Any]:
    case_id = "manifest_digest_mismatch_rejected"
    bundle, manifest, _signature = _build_clean_bundle(work, case_id, nonce="nonce-digest-006")
    bogus_digest = "0" * 64
    manifest["chunks"][0] = {**manifest["chunks"][0], "sha256": bogus_digest}
    resigned = _sign(manifest, kid="kid-primary", secret=REGISTERED_KEYS["kid-primary"])
    verdict, errors = _verify(bundle, manifest, resigned, seen_nonces=seen_nonces)
    return _case_summary(
        case_id,
        observed_verdict=verdict,
        chunk_count=len(manifest["chunks"]),
        observed_errors=errors,
        detail="mutation: manifest declares bogus chunk-0 digest; signature still valid",
    )


CASE_RUNNERS = {
    "clean_signed_bundle_passes": run_clean_signed_bundle_passes,
    "truncated_bundle_rejected": run_truncated_bundle_rejected,
    "swapped_chunk_rejected": run_swapped_chunk_rejected,
    "wrong_signing_key_rejected": run_wrong_signing_key_rejected,
    "replayed_bundle_rejected": run_replayed_bundle_rejected,
    "manifest_digest_mismatch_rejected": run_manifest_digest_mismatch_rejected,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    seen_nonces: set[str] = set()
    cases = [CASE_RUNNERS[case_id](work_dir, seen_nonces=seen_nonces) for case_id in CASE_IDS]
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
            "Remote-transfer signed-bundle tamper modes are locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix signed-bundle tamper invariant blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-signed-bundle-tamper-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-signed-bundle-tamper-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
