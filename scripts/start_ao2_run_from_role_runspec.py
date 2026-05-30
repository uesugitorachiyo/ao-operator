#!/usr/bin/env python3
"""ao-operator -> AO2 bridge: start an AO2 run from an AO Operator RunSpec.

The bridge is the Phase 2 exit-gate entry point that proves AO Operator can
delegate a governed run to AO2 instead of owning runtime execution itself.

What this script does and does NOT do:

- it canonicalizes every role id in the input RunSpec via the deterministic
  AO Operator -> AO2 provider-contract mapping module and writes a signed-
  intent-style evidence JSON that captures the mapping the bridge committed
  to. This evidence is what reviewers diff between hosts.

- it optionally shells out to `ao2 factory plan --runspec ...` (when
  `--invoke-ao2` is passed) to produce the AO2 plan artifact, then records
  the AO2 plan path + planning-evidence path back into the bridge evidence.
  The plan path is treated as the AO2-owned run identifier.

- it never embeds environment variables, provider tokens, or any provider
  prompt body into the evidence. The bridge keeps secrets out of the
  artifact even when the RunSpec references env-resolved provider keys.

- it does not pick a provider. AO2's provider adapter resolves the live
  provider behind the contract slug; ao-operator just declares which contract
  applies to each role.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ao_operator_ao2_provider_contract as mapping  # noqa: E402


SCHEMA = "ao-operator/start-ao2-run-from-role-runspec/v1"
ACTION = "start-ao2-run-from-role-runspec"

TRUST_BOUNDARY: dict[str, str] = {
    "factory_v3_role": "ao_operator_runspec_input_canonicalization",
    "ao2_role": "trusted_execution_runtime_and_signed_evidence_owner",
    "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
    "bridge_owner": "factory_v3_start_ao2_run_from_role_runspec",
}

# AO2-native bridge-evidence contract emitted by `ao2 factory bridge`.
# The passthrough mode validates against these exact constants so a drift in
# either side (e.g. AO2 changing the schema URI or the trust-boundary owner
# string) is rejected before the file is observed.
AO2_NATIVE_BRIDGE_SCHEMA = "ao2.factory-bridge.v1"
AO2_NATIVE_BRIDGE_ACTION = "factory-bridge"
AO2_NATIVE_BRIDGE_TRUST_BOUNDARY: dict[str, str] = {
    "factory_v3_role": "parity_oracle_only",
    "ao2_role": "ao2_native_bridge_evidence_owner",
    "control_plane_role": "read_only_observer_after_signed_evidence",
    "bridge_owner": "ao2_factory_bridge_subcommand",
}
AO2_NATIVE_BRIDGE_ALLOWED_STATUSES: frozenset[str] = frozenset(
    {"mapping_resolved_dry_run"}
)

# AO2-native bridge passthrough trust boundary recorded in the ao-operator
# evidence wrapper. Mirrors the cancel-authority producer's passthrough mode:
# ao-operator keeps a copy on disk but credits AO2 as the canonical owner.
PASSTHROUGH_TRUST_BOUNDARY: dict[str, str] = {
    "factory_v3_role": "parity_oracle_only_observer",
    "ao2_role": "ao2_native_bridge_evidence_owner",
    "control_plane_role": "read_only_observer_after_signed_evidence",
    "bridge_owner": "ao2_factory_bridge_subcommand",
    "passthrough_owner": "factory_v3_start_ao2_run_from_role_runspec",
}

REDACTED_ENV_SUBSTRINGS: tuple[str, ...] = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTH",
)


class PassthroughError(RuntimeError):
    """Raised when an AO2-native bridge evidence file fails passthrough validation."""


def _utc_now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_runspec(path: Path) -> dict[str, Any]:
    return mapping._load_runspec(path)  # type: ignore[attr-defined]


def _resolve_roles_with_unknowns(
    runspec: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    role_ids = mapping.extract_role_ids(runspec)
    resolved: list[dict[str, str]] = []
    unknown: list[str] = []
    for role_id in role_ids:
        try:
            resolved.append(mapping.resolve_role(role_id))
        except mapping.UnknownRoleError:
            unknown.append(role_id)
    return resolved, unknown


def _redacted_env_keys() -> list[str]:
    matches: list[str] = []
    for key in os.environ:
        upper = key.upper()
        if any(sub in upper for sub in REDACTED_ENV_SUBSTRINGS):
            matches.append(key)
    return sorted(matches)


def _safe_argv(argv: list[str]) -> list[str]:
    safe: list[str] = []
    for token in argv:
        upper = token.upper()
        if any(sub in upper and "=" in token for sub in REDACTED_ENV_SUBSTRINGS):
            safe.append("<redacted>")
        else:
            safe.append(token)
    return safe


def invoke_ao2_factory_plan(
    ao2_bin: str,
    runspec_path: Path,
    target: Path,
    out: Path,
) -> dict[str, Any]:
    argv = [
        ao2_bin,
        "factory",
        "plan",
        "--runspec",
        str(runspec_path),
        "--request",
        str(runspec_path),
        "--target",
        str(target),
        "--out",
        str(out),
        "--json",
    ]
    completed = subprocess.run(  # noqa: S603 - argv is fully controlled
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    invocation: dict[str, Any] = {
        "argv": _safe_argv(argv),
        "exit_code": completed.returncode,
    }
    stdout_text = completed.stdout or ""
    if stdout_text.strip():
        try:
            invocation["plan_response"] = json.loads(stdout_text)
        except json.JSONDecodeError:
            invocation["plan_response_text"] = stdout_text.strip()[:4096]
    if completed.stderr:
        invocation["stderr_excerpt"] = completed.stderr.strip()[:1024]
    if completed.returncode != 0:
        invocation["status"] = "ao2_plan_failed"
    else:
        invocation["status"] = "ao2_plan_succeeded"
    return invocation


def build_bridge_evidence(
    runspec_path: Path,
    runspec_value: dict[str, Any],
    resolved_roles: list[dict[str, str]],
    unknown_roles: list[str],
    ao2_invocation: dict[str, Any] | None,
) -> dict[str, Any]:
    status: str
    if unknown_roles:
        status = "blocked_unknown_roles"
    elif ao2_invocation is None:
        status = "mapping_resolved_dry_run"
    elif ao2_invocation.get("status") == "ao2_plan_succeeded":
        status = "ao2_plan_started"
    else:
        status = "ao2_plan_failed"

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "action": ACTION,
        "generated_at": _utc_now_iso(),
        "status": status,
        "trust_boundary": dict(sorted(TRUST_BOUNDARY.items())),
        "input_runspec": {
            "path": str(runspec_path),
            "sha256": sha256_file(runspec_path),
            "schema": runspec_value.get("schema") or runspec_value.get("apiVersion"),
            "name": (
                runspec_value.get("metadata", {}).get("name")
                if isinstance(runspec_value.get("metadata"), dict)
                else runspec_value.get("slug")
            ),
        },
        "mapping": {
            "schema": mapping.SCHEMA,
            "version": mapping.MAPPING_VERSION,
            "digest": mapping.mapping_digest(),
        },
        "resolved_roles": resolved_roles,
        "unknown_roles": unknown_roles,
        "redacted_env_keys_observed": _redacted_env_keys(),
    }
    if ao2_invocation is not None:
        evidence["ao2_invocation"] = ao2_invocation
    return evidence


def write_evidence(evidence: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_native_bridge_evidence(path: Path) -> dict[str, Any]:
    """Read a candidate AO2-native bridge evidence file from `ao2 factory bridge`."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence input not found: {path}"
        ) from exc
    except OSError as exc:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence input unreadable: {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence input is not valid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PassthroughError(
            f"--ao2-native-bridge-evidence input did not parse to a JSON object: {path}"
        )
    return payload


def validate_native_bridge_evidence(payload: dict[str, Any], path: Path) -> None:
    """Validate an AO2-native bridge evidence file before passthrough.

    Locks the four cross-language contract surfaces: schema URI, action,
    trust boundary, and mapping digest. The digest check is the load-bearing
    parity check -- if AO2 ships a mapping that the ao-operator Python module
    no longer agrees with, passthrough refuses so the watchdog never observes
    drifted evidence.
    """

    schema = payload.get("schema")
    if schema != AO2_NATIVE_BRIDGE_SCHEMA:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence schema must be {AO2_NATIVE_BRIDGE_SCHEMA!r}; "
            f"got {schema!r} in {path}"
        )
    action = payload.get("action")
    if action != AO2_NATIVE_BRIDGE_ACTION:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence action must be {AO2_NATIVE_BRIDGE_ACTION!r}; "
            f"got {action!r} in {path}"
        )
    status = payload.get("status")
    if status not in AO2_NATIVE_BRIDGE_ALLOWED_STATUSES:
        raise PassthroughError(
            "--ao2-native-bridge-evidence status must be one of "
            f"{sorted(AO2_NATIVE_BRIDGE_ALLOWED_STATUSES)}; "
            f"got {status!r} in {path}"
        )
    trust_boundary = payload.get("trust_boundary")
    if not isinstance(trust_boundary, dict):
        raise PassthroughError(
            "--ao2-native-bridge-evidence trust_boundary must be an object; "
            f"got {type(trust_boundary).__name__} in {path}"
        )
    for key, expected in AO2_NATIVE_BRIDGE_TRUST_BOUNDARY.items():
        observed = trust_boundary.get(key)
        if observed != expected:
            raise PassthroughError(
                f"--ao2-native-bridge-evidence trust_boundary[{key!r}] must be "
                f"{expected!r}; got {observed!r} in {path}"
            )
    mapping_block = payload.get("mapping")
    if not isinstance(mapping_block, dict):
        raise PassthroughError(
            "--ao2-native-bridge-evidence mapping must be an object; "
            f"got {type(mapping_block).__name__} in {path}"
        )
    expected_digest = mapping.mapping_digest()
    observed_digest = mapping_block.get("digest")
    if observed_digest != expected_digest:
        raise PassthroughError(
            "--ao2-native-bridge-evidence mapping.digest does not match the "
            f"ao-operator mapping module digest; expected {expected_digest!r} "
            f"got {observed_digest!r} in {path}. Regenerate the AO2 bridge "
            "evidence with a matching ao2 binary."
        )
    expected_mapping_schema = mapping.SCHEMA
    observed_mapping_schema = mapping_block.get("schema")
    if observed_mapping_schema != expected_mapping_schema:
        raise PassthroughError(
            f"--ao2-native-bridge-evidence mapping.schema must be "
            f"{expected_mapping_schema!r}; got {observed_mapping_schema!r} in {path}"
        )
    resolved_roles = payload.get("resolved_roles")
    if not isinstance(resolved_roles, list):
        raise PassthroughError(
            "--ao2-native-bridge-evidence resolved_roles must be an array; "
            f"got {type(resolved_roles).__name__} in {path}"
        )
    unknown_roles = payload.get("unknown_roles")
    if not isinstance(unknown_roles, list):
        raise PassthroughError(
            "--ao2-native-bridge-evidence unknown_roles must be an array; "
            f"got {type(unknown_roles).__name__} in {path}"
        )
    if unknown_roles:
        raise PassthroughError(
            "--ao2-native-bridge-evidence unknown_roles must be empty for a "
            f"mapping_resolved_dry_run; got {unknown_roles!r} in {path}"
        )
    if "role_contracts" in payload:
        _validate_role_contracts_block(payload["role_contracts"], path)


def _validate_role_contracts_block(block: Any, path: Path) -> None:
    """Lock the optional role_contracts trust contract on AO2-native evidence.

    When `ao2 factory bridge --role-contracts-dir` is invoked, the AO2-native
    payload carries a top-level `role_contracts` block summarizing which
    ao-operator role TOMLs were loaded. The trust direction is fixed: AO2 owns
    the contract refs (`owner == "ao2"`) and ao-operator contracts are inputs,
    never authorities (`factory_v3_required_to_load == False`). Passthrough
    refuses to envelope drifted shapes so observers cannot be tricked into
    treating ao-operator contracts as the trust source.
    """
    if not isinstance(block, dict):
        raise PassthroughError(
            "--ao2-native-bridge-evidence role_contracts must be an object; "
            f"got {type(block).__name__} in {path}"
        )
    owner = block.get("owner")
    if owner != "ao2":
        raise PassthroughError(
            "--ao2-native-bridge-evidence role_contracts.owner must be 'ao2'; "
            f"got {owner!r} in {path}"
        )
    required = block.get("factory_v3_required_to_load")
    if required is not False:
        raise PassthroughError(
            "--ao2-native-bridge-evidence role_contracts.factory_v3_required_to_load "
            f"must be False (AO2 owns the trust path); got {required!r} in {path}"
        )
    loaded_count = block.get("loaded_count")
    if not isinstance(loaded_count, int) or isinstance(loaded_count, bool) or loaded_count < 0:
        raise PassthroughError(
            "--ao2-native-bridge-evidence role_contracts.loaded_count must be a "
            f"non-negative integer; got {loaded_count!r} in {path}"
        )
    missing_roles = block.get("missing_roles")
    if not isinstance(missing_roles, list) or not all(
        isinstance(role, str) for role in missing_roles
    ):
        raise PassthroughError(
            "--ao2-native-bridge-evidence role_contracts.missing_roles must be an "
            f"array of strings; got {missing_roles!r} in {path}"
        )


def build_passthrough_evidence(
    native_payload: dict[str, Any],
    native_path: Path,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a validated AO2-native bridge evidence body in a ao-operator
    observer envelope so the same on-disk file can be consumed by tools that
    still expect the legacy schema. Keeps the original payload verbatim under
    ``ao2_native_bridge_evidence`` and never re-derives mapping/resolved-roles
    fields. When ``verification`` is supplied (slice 9 opt-in
    `--verify-bridge-evidence`), the AO2-owned
    `ao2.factory-bridge-evidence-verification.v1` verdict is recorded under
    ``ao2_native_bridge_evidence_verification`` so reviewers can see that
    ao-operator shelled out to the AO2 verifier and accepted the result."""

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "action": ACTION,
        "generated_at": _utc_now_iso(),
        "status": "passthrough_ao2_native",
        "trust_boundary": dict(sorted(PASSTHROUGH_TRUST_BOUNDARY.items())),
        "ao2_native_bridge_evidence": native_payload,
        "ao2_native_bridge_evidence_path": str(native_path),
        "ao2_native_bridge_evidence_sha256": sha256_file(native_path),
        "mapping": {
            "schema": mapping.SCHEMA,
            "version": mapping.MAPPING_VERSION,
            "digest": mapping.mapping_digest(),
        },
        "redacted_env_keys_observed": _redacted_env_keys(),
    }
    if verification is not None:
        evidence["ao2_native_bridge_evidence_verification"] = verification
    role_contracts = native_payload.get("role_contracts")
    if isinstance(role_contracts, dict):
        missing = role_contracts.get("missing_roles") or []
        evidence["role_contracts_summary"] = {
            "owner": role_contracts.get("owner"),
            "loaded_count": role_contracts.get("loaded_count"),
            "missing_role_count": len(missing) if isinstance(missing, list) else None,
            "factory_v3_required_to_load": role_contracts.get(
                "factory_v3_required_to_load"
            ),
        }
    return evidence


def invoke_ao2_verify_bridge_evidence(
    ao2_bin: str, evidence_path: Path
) -> dict[str, Any]:
    """Shell out to `ao2 factory verify-bridge-evidence` and return the
    structured verdict (an `ao2.factory-bridge-evidence-verification.v1`
    JSON body produced by the AO2-owned slice-4 verifier).

    Failure modes that bubble up as ``PassthroughError`` (caller decides the
    exit code): missing binary, non-JSON stdout, non-`accepted` status. The
    verifier itself exits non-zero when status is `rejected`, but ao-operator
    additionally validates the status field defensively so a buggy verifier
    that exits 0 with `rejected` still fails closed.
    """

    argv = [
        ao2_bin,
        "factory",
        "verify-bridge-evidence",
        "--evidence",
        str(evidence_path),
        "--json",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - argv is fully controlled
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PassthroughError(
            f"--verify-bridge-evidence requires the `ao2` binary on PATH or via "
            f"--ao2-bin; got {ao2_bin!r}: {exc}"
        ) from exc
    stdout_text = (completed.stdout or "").strip()
    if not stdout_text:
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence emitted no JSON on stdout "
            f"(exit={completed.returncode}); stderr excerpt: "
            f"{(completed.stderr or '').strip()[:512]!r}"
        )
    try:
        report = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence stdout is not JSON "
            f"(exit={completed.returncode}): {exc}; excerpt: "
            f"{stdout_text[:512]!r}"
        ) from exc
    if not isinstance(report, dict):
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence stdout did not parse to an "
            f"object (exit={completed.returncode})"
        )
    schema = report.get("schema_version")
    if schema != "ao2.factory-bridge-evidence-verification.v1":
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence emitted unexpected schema "
            f"{schema!r}; expected 'ao2.factory-bridge-evidence-verification.v1'"
        )
    status = report.get("status")
    if status != "accepted":
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence rejected the AO2-native bridge "
            f"evidence at {evidence_path} (status={status!r}, "
            f"exit={completed.returncode}); refusing passthrough"
        )
    if completed.returncode != 0:
        raise PassthroughError(
            "ao2 factory verify-bridge-evidence reported status=accepted but "
            f"exited non-zero ({completed.returncode}); refusing passthrough"
        )
    return report


def resolve_ao2_bin(ao2_bin: str, factory_root: Path) -> str:
    """Prefer a checked-out AO2 release binary over a stale `ao2` on PATH."""
    if ao2_bin != "ao2":
        return ao2_bin
    adjacent = factory_root.resolve().parent / "ao2" / "target" / "release" / "ao2"
    if adjacent.is_file():
        return str(adjacent)
    return ao2_bin


def run(args: argparse.Namespace) -> int:
    if args.ao2_native_bridge_evidence is not None:
        native_path: Path = args.ao2_native_bridge_evidence
        try:
            native_payload = _load_native_bridge_evidence(native_path)
            validate_native_bridge_evidence(native_payload, native_path)
        except PassthroughError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        verification: dict[str, Any] | None = None
        if not args.allow_unverified_bridge_evidence:
            ao2_bin = resolve_ao2_bin(args.ao2_bin, args.factory_root)
            try:
                verification = invoke_ao2_verify_bridge_evidence(ao2_bin, native_path)
            except PassthroughError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        evidence = build_passthrough_evidence(native_payload, native_path, verification)
        write_evidence(evidence, args.out)
        if args.json:
            print(json.dumps(evidence, indent=2, sort_keys=True))
        else:
            print(f"status={evidence['status']}")
            print(f"mapping_digest={evidence['mapping']['digest']}")
            print(
                "ao2_native_bridge_evidence_sha256="
                f"{evidence['ao2_native_bridge_evidence_sha256']}"
            )
            print(
                "resolved_role_count="
                f"{len(native_payload.get('resolved_roles') or [])}"
            )
            print(
                "unknown_role_count="
                f"{len(native_payload.get('unknown_roles') or [])}"
            )
            if verification is not None:
                print(
                    "ao2_native_bridge_evidence_verification_status="
                    f"{verification.get('status')}"
                )
            summary = evidence.get("role_contracts_summary")
            if isinstance(summary, dict):
                print(
                    "role_contracts_owner="
                    f"{summary.get('owner')}"
                )
                print(
                    "role_contracts_loaded_count="
                    f"{summary.get('loaded_count')}"
                )
                print(
                    "role_contracts_missing_role_count="
                    f"{summary.get('missing_role_count')}"
                )
            print(f"evidence={args.out}")
        return 0

    runspec_path: Path = args.runspec
    if not runspec_path.is_file():
        print(f"missing runspec: {runspec_path}", file=sys.stderr)
        return 2
    runspec_value = _load_runspec(runspec_path)
    resolved_roles, unknown_roles = _resolve_roles_with_unknowns(runspec_value)
    ao2_invocation: dict[str, Any] | None = None
    if args.invoke_ao2 and not unknown_roles:
        ao2_bin = resolve_ao2_bin(args.ao2_bin, args.factory_root)
        plan_out: Path = args.ao2_plan_out
        plan_out.parent.mkdir(parents=True, exist_ok=True)
        ao2_invocation = invoke_ao2_factory_plan(
            ao2_bin=ao2_bin,
            runspec_path=runspec_path,
            target=args.ao2_target,
            out=plan_out,
        )
    evidence = build_bridge_evidence(
        runspec_path=runspec_path,
        runspec_value=runspec_value,
        resolved_roles=resolved_roles,
        unknown_roles=unknown_roles,
        ao2_invocation=ao2_invocation,
    )
    write_evidence(evidence, args.out)
    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        print(f"status={evidence['status']}")
        print(f"input_runspec_sha256={evidence['input_runspec']['sha256']}")
        print(f"mapping_digest={evidence['mapping']['digest']}")
        print(f"resolved_role_count={len(resolved_roles)}")
        print(f"unknown_role_count={len(unknown_roles)}")
        print(f"evidence={args.out}")
    if evidence["status"] in {"blocked_unknown_roles", "ao2_plan_failed"}:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bridge: start an AO2 run from an existing AO Operator RunSpec "
            "with deterministic role -> AO2 provider-contract mapping "
            "captured as evidence. Default mode derives evidence locally "
            "from --runspec; pass --ao2-native-bridge-evidence to validate "
            "and re-emit a pre-built AO2-native evidence file produced by "
            "`ao2 factory bridge` so ao-operator becomes a pure observer."
        ),
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--runspec",
        type=Path,
        help=(
            "Path to an AO Operator RunSpec (ao-operator/runspec/v1 or "
            "ao.dev/v1). Derives bridge evidence locally; ao-operator owns "
            "the mapping and signs the evidence."
        ),
    )
    source_group.add_argument(
        "--ao2-native-bridge-evidence",
        type=Path,
        help=(
            "Path to an `ao2.factory-bridge.v1` JSON produced by "
            "`ao2 factory bridge`. Validates schema, action, trust boundary, "
            "and mapping digest, then re-emits the body verbatim inside a "
            "ao-operator observer envelope. AO2 owns the canonical evidence."
        ),
    )
    parser.add_argument("--out", type=Path, required=True, help="bridge evidence JSON path")
    parser.add_argument(
        "--invoke-ao2",
        action="store_true",
        help="also invoke `ao2 factory plan` and record the response in evidence",
    )
    parser.add_argument(
        "--ao2-bin", default="ao2", help="ao2 binary name or path (default: ao2)"
    )
    parser.add_argument(
        "--ao2-target",
        type=Path,
        default=Path("."),
        help="--target passed to `ao2 factory plan` (default: .)",
    )
    parser.add_argument(
        "--ao2-plan-out",
        type=Path,
        default=Path("ao2-factory-plan.json"),
        help="--out passed to `ao2 factory plan` (default: ao2-factory-plan.json)",
    )
    parser.add_argument(
        "--factory-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ao-operator root, used to locate sibling AO2 binary (default: repo root)",
    )
    parser.add_argument("--json", action="store_true", help="echo evidence JSON on stdout")
    parser.add_argument(
        "--allow-unverified-bridge-evidence",
        action="store_true",
        help=(
            "Passthrough mode only. Opt out of the default-on AO2 verifier "
            "shell-out for `--ao2-native-bridge-evidence`. When set, "
            "passthrough only structurally validates the payload and omits "
            "the `ao2_native_bridge_evidence_verification` block from the "
            "envelope. Intended for legacy callers that pass synthetic or "
            "intentionally-unsigned payloads (e.g. unit tests)."
        ),
    )
    parser.add_argument(
        "--verify-bridge-evidence",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
