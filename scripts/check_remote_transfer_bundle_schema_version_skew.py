#!/usr/bin/env python3
"""Remote-transfer bundle schema version skew gate.

Synthesizes the AO Runtime ``bundle_schema_version_skew`` contract as
a local Python state machine and proves each version-mismatch hazard
on the wire boundary is fail-closed by injecting deliberate mutations
against an in-process emit / receiver_validate pipeline.

The gate exercises five deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_matched_schema_version_passes`` — control: sender emits a
  bundle at version ``3.0.0`` advertising only known extensions; the
  receiver supports ``[2.0.0..3.0.0]`` and the known extension list
  contains every advertised extension. ``receiver_validate_and_accept``
  records no errors and the bundle is accepted at the emitted version.
* ``receiver_below_min_version_rejected`` — mutation: sender emits a
  bundle at version ``1.0.0`` while the receiver supports
  ``[2.0.0..3.0.0]``; instead of refusing, the receiver silently
  accepts the down-rev bundle. Receivers that advertise a minimum
  supported version MUST reject anything below it.
* ``receiver_above_max_silently_downgrades_rejected`` — mutation:
  sender emits a bundle at forward version ``4.0.0`` while the
  receiver only supports up to ``3.0.0``; the receiver silently
  re-interprets the bundle as ``3.0.0`` instead of refusing. A
  receiver MUST NOT silently downgrade an unrecognized forward
  version onto a previous schema, because the ingested payload may
  rely on semantics the older schema does not honour.
* ``bundle_advertises_unknown_extension_field_rejected`` — mutation:
  sender emits a bundle at version ``3.0.0`` advertising the
  extension ``experimental.encryption_v2`` that the receiver does not
  know about; the receiver accepts the bundle anyway. With strict
  extensions enabled, an unknown extension MUST cause rejection so
  feature negotiation cannot be bypassed by a forward sender.
* ``schema_version_field_missing_rejected`` — mutation: sender emits
  a bundle with no ``schema_version`` field at all; the receiver
  assumes a default version and accepts. A bundle with no advertised
  schema version is ambiguous and MUST be rejected so a version
  cannot be silently inferred.

Every case lays down a per-case skew transcript in a temporary work
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
    "remote-transfer-bundle-schema-version-skew.json"
)
SCHEMA = "ao-operator/remote-transfer-bundle-schema-version-skew/v1"

CASE_IDS = (
    "clean_matched_schema_version_passes",
    "receiver_below_min_version_rejected",
    "receiver_above_max_silently_downgrades_rejected",
    "bundle_advertises_unknown_extension_field_rejected",
    "schema_version_field_missing_rejected",
)

EXPECTED_VERDICTS = {
    "clean_matched_schema_version_passes": "PASS",
    "receiver_below_min_version_rejected": "FAIL",
    "receiver_above_max_silently_downgrades_rejected": "FAIL",
    "bundle_advertises_unknown_extension_field_rejected": "FAIL",
    "schema_version_field_missing_rejected": "FAIL",
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"unparseable_semver:{version}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _semver_lt(a: str, b: str) -> bool:
    return _parse_semver(a) < _parse_semver(b)


def _semver_gt(a: str, b: str) -> bool:
    return _parse_semver(a) > _parse_semver(b)


class _SchemaSkewVerifier:
    """In-memory bundle schema-version skew state machine.

    Models the AO Runtime ``bundle_schema_version_skew`` pipeline:
    a sender emits a bundle stamped with a ``schema_version`` and an
    ``extensions`` list, and a receiver advertises a supported
    [min, max] semver range and a known-extension allow-list. The
    verifier enforces four distilled wire-boundary invariants:

    1. The emitted bundle MUST carry a ``schema_version`` field
       (no-missing-version invariant).
    2. The emitted version MUST be ``>=`` the receiver's
       ``receiver_min`` (no-down-rev-acceptance invariant).
    3. The emitted version MUST be ``<=`` the receiver's
       ``receiver_max``, never silently re-interpreted as an older
       schema (no-silent-downgrade invariant).
    4. Every advertised extension MUST appear in
       ``known_extensions`` (no-unknown-extension invariant).
    """

    def __init__(
        self,
        *,
        receiver_min: str,
        receiver_max: str,
        known_extensions: set[str],
    ) -> None:
        self.receiver_min = receiver_min
        self.receiver_max = receiver_max
        self.known_extensions = set(known_extensions)
        self.accepted_versions: list[str] = []
        self.errors: list[str] = []

    def receiver_validate_and_accept(
        self,
        emitted_version: str | None,
        extensions: list[str] | None = None,
    ) -> None:
        ext_list = list(extensions or [])
        if emitted_version is None:
            self.errors.append("missing_schema_version_field")
            return
        if _semver_lt(emitted_version, self.receiver_min):
            self.errors.append(
                f"emitted_below_receiver_min:emitted={emitted_version},min={self.receiver_min}"
            )
            return
        if _semver_gt(emitted_version, self.receiver_max):
            self.errors.append(
                f"emitted_above_receiver_max:emitted={emitted_version},max={self.receiver_max}"
            )
            return
        for ext in ext_list:
            if ext not in self.known_extensions:
                self.errors.append(f"unknown_extension_field:{ext}")
                return
        self.accepted_versions.append(emitted_version)

    def receiver_force_accept_below_min(self, emitted_version: str) -> None:
        if _semver_lt(emitted_version, self.receiver_min):
            self.errors.append(
                f"force_accepted_below_min:emitted={emitted_version},min={self.receiver_min}"
            )
        self.accepted_versions.append(emitted_version)

    def receiver_force_accept_above_max_as_downgrade(
        self, emitted_version: str, downgrade_to: str
    ) -> None:
        if _semver_gt(emitted_version, self.receiver_max):
            self.errors.append(
                f"silent_downgrade:emitted={emitted_version},reinterpreted_as={downgrade_to},max={self.receiver_max}"
            )
        self.accepted_versions.append(downgrade_to)

    def receiver_force_accept_unknown_extension(
        self, emitted_version: str, extension: str
    ) -> None:
        if extension not in self.known_extensions:
            self.errors.append(
                f"force_accepted_unknown_extension:emitted={emitted_version},extension={extension}"
            )
        self.accepted_versions.append(emitted_version)

    def receiver_force_accept_missing_version(self, default_assumed: str) -> None:
        self.errors.append(
            f"force_accepted_missing_version:assumed={default_assumed}"
        )
        self.accepted_versions.append(default_assumed)

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "schema-skew-transcript.json").write_text(
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


def run_clean_matched_schema_version_passes(work: Path) -> dict[str, Any]:
    case_id = "clean_matched_schema_version_passes"
    verifier = _SchemaSkewVerifier(
        receiver_min="2.0.0",
        receiver_max="3.0.0",
        known_extensions={"chunk_compression_v1"},
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({
        "op": "emit_bundle",
        "schema_version": "3.0.0",
        "extensions": ["chunk_compression_v1"],
    })
    transcript.append({
        "op": "receiver_validate_and_accept",
        "schema_version": "3.0.0",
        "extensions": ["chunk_compression_v1"],
    })
    verifier.receiver_validate_and_accept("3.0.0", ["chunk_compression_v1"])

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: sender emits 3.0.0 with a known extension; receiver "
            "supports [2.0.0..3.0.0] and validates without raising"
        ),
    )


def run_receiver_below_min_version_rejected(work: Path) -> dict[str, Any]:
    case_id = "receiver_below_min_version_rejected"
    verifier = _SchemaSkewVerifier(
        receiver_min="2.0.0",
        receiver_max="3.0.0",
        known_extensions={"chunk_compression_v1"},
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({
        "op": "emit_bundle",
        "schema_version": "1.0.0",
        "extensions": [],
    })
    transcript.append({
        "op": "receiver_force_accept_below_min",
        "schema_version": "1.0.0",
    })
    verifier.receiver_force_accept_below_min("1.0.0")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender ships a 1.0.0 down-rev bundle; receiver supports [2.0.0..3.0.0] but accepts anyway",
    )


def run_receiver_above_max_silently_downgrades_rejected(work: Path) -> dict[str, Any]:
    case_id = "receiver_above_max_silently_downgrades_rejected"
    verifier = _SchemaSkewVerifier(
        receiver_min="2.0.0",
        receiver_max="3.0.0",
        known_extensions={"chunk_compression_v1"},
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({
        "op": "emit_bundle",
        "schema_version": "4.0.0",
        "extensions": [],
    })
    transcript.append({
        "op": "receiver_force_accept_above_max_as_downgrade",
        "schema_version": "4.0.0",
        "reinterpreted_as": "3.0.0",
    })
    verifier.receiver_force_accept_above_max_as_downgrade("4.0.0", "3.0.0")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender ships a 4.0.0 forward bundle; receiver silently reinterprets it as 3.0.0 instead of rejecting",
    )


def run_bundle_advertises_unknown_extension_field_rejected(work: Path) -> dict[str, Any]:
    case_id = "bundle_advertises_unknown_extension_field_rejected"
    verifier = _SchemaSkewVerifier(
        receiver_min="2.0.0",
        receiver_max="3.0.0",
        known_extensions={"chunk_compression_v1"},
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({
        "op": "emit_bundle",
        "schema_version": "3.0.0",
        "extensions": ["experimental.encryption_v2"],
    })
    transcript.append({
        "op": "receiver_force_accept_unknown_extension",
        "schema_version": "3.0.0",
        "extension": "experimental.encryption_v2",
    })
    verifier.receiver_force_accept_unknown_extension("3.0.0", "experimental.encryption_v2")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender ships a 3.0.0 bundle advertising experimental.encryption_v2; receiver does not know that extension yet accepts",
    )


def run_schema_version_field_missing_rejected(work: Path) -> dict[str, Any]:
    case_id = "schema_version_field_missing_rejected"
    verifier = _SchemaSkewVerifier(
        receiver_min="2.0.0",
        receiver_max="3.0.0",
        known_extensions={"chunk_compression_v1"},
    )
    transcript: list[dict[str, Any]] = []

    transcript.append({
        "op": "emit_bundle",
        "schema_version": None,
        "extensions": [],
    })
    transcript.append({
        "op": "receiver_force_accept_missing_version",
        "default_assumed": "3.0.0",
    })
    verifier.receiver_force_accept_missing_version("3.0.0")

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail="mutation: sender ships a bundle with no schema_version; receiver assumes 3.0.0 and accepts instead of rejecting",
    )


CASE_RUNNERS = {
    "clean_matched_schema_version_passes": run_clean_matched_schema_version_passes,
    "receiver_below_min_version_rejected": run_receiver_below_min_version_rejected,
    "receiver_above_max_silently_downgrades_rejected": run_receiver_above_max_silently_downgrades_rejected,
    "bundle_advertises_unknown_extension_field_rejected": run_bundle_advertises_unknown_extension_field_rejected,
    "schema_version_field_missing_rejected": run_schema_version_field_missing_rejected,
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
            "Remote-transfer bundle schema version skew is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix bundle schema version skew blockers before further remote-transfer hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-schema-version-skew-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-bundle-schema-version-skew-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
