#!/usr/bin/env python3
"""Deterministic AO Operator role -> AO2 provider-contract mapping.

This module is the single source of truth for how factory-v3 AO Operator
role identifiers (whether expressed in the factory-v3/runspec/v1 shape with
top-level `roles:` or in the ao.dev/v1 `Run` shape with `spec.tasks`) collapse
into a fixed AO2 provider-contract. The mapping is intentionally a frozen
table so that:

- the same RunSpec resolves to the same provider contract on every host;
- the mapping's sha256 digest is a content-addressable fingerprint that
  bridge evidence can pin so reviewers can confirm what mapping shipped;
- the tests live in the same package so a change to the table fails the
  matching tests before it can leak through to a bridge invocation.

Provider contracts are AO2-owned trust artifacts: they declare the sandbox,
evidence obligations, and closure-owner that AO2 enforces for a given role
class. factory-v3 does not pick a provider binary here -- AO2 still resolves
the live provider through its scripted/codex/claude-cli adapter contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "factory-v3/ao-operator-ao2-provider-contract/v1"
MAPPING_VERSION = "1.0.0"

TRUST_BOUNDARY: dict[str, str] = {
    "factory_v3_role": "ao_operator_role_canonicalization_and_mapping_source",
    "ao2_role": "provider_contract_owner_and_closure_authority",
    "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
    "mapping_owner": "factory_v3_to_ao2_provider_contract_mapping_module",
}

# Canonical role ids the bridge knows how to translate. Every alias resolves
# to one of these. New canonical roles MUST land with a matching AO2
# provider-contract entry below or the table will be rejected at import time.
CANONICAL_ROLES: tuple[str, ...] = (
    "intake",
    "planner",
    "plan_hardener",
    "factory_manager",
    "implementer",
    "reviewer",
    "integrator",
    "evaluator_closer",
)

# AO Operator emits a handful of legacy role-id spellings across the two
# runspec flavors. The alias map normalizes them so the bridge does not have
# to special-case format-specific names. Aliases are matched case-sensitively
# after a `lower()`/`strip()`/`replace('_', '-')` pass (see `canonical_role`).
ROLE_ALIASES: dict[str, str] = {
    # intake
    "intake": "intake",
    "planner-intake": "intake",
    "planner_intake": "intake",
    # planner
    "planner": "planner",
    "agent-os-planner": "planner",
    "agent_os_planner": "planner",
    # plan hardener
    "plan-hardener": "plan_hardener",
    "plan_hardener": "plan_hardener",
    "agent-os-plan-hardener": "plan_hardener",
    "agent_os_plan_hardener": "plan_hardener",
    # factory manager
    "factory-manager": "factory_manager",
    "factory_manager": "factory_manager",
    "agent-os-factory-manager": "factory_manager",
    "agent_os_factory_manager": "factory_manager",
    # implementer
    "implementer": "implementer",
    "implementer-slice": "implementer",
    "implementer_slice": "implementer",
    "agent-os-implementer": "implementer",
    "agent_os_implementer": "implementer",
    # reviewer
    "reviewer": "reviewer",
    "reviewer-slice": "reviewer",
    "reviewer_slice": "reviewer",
    "slice-reviewer": "reviewer",
    "slice_reviewer": "reviewer",
    "agent-os-slice-reviewer": "reviewer",
    "agent_os_slice_reviewer": "reviewer",
    # integrator
    "integrator": "integrator",
    "agent-os-integrator": "integrator",
    "agent_os_integrator": "integrator",
    # evaluator/closer
    "evaluator-closer": "evaluator_closer",
    "evaluator_closer": "evaluator_closer",
    "agent-os-evaluator-closer": "evaluator_closer",
    "agent_os_evaluator_closer": "evaluator_closer",
}

# Provider-contract entries. Each canonical role maps to exactly one AO2
# provider-contract slug, the sandbox bucket AO2 should apply for that role
# class, and the obligation kind the AO2 closure verifier should attach to
# evidence packs produced under this contract.
AO2_PROVIDER_CONTRACTS: dict[str, dict[str, str]] = {
    "intake": {
        "slug": "ao2.provider-contract.intake.v1",
        "sandbox": "read_only_brief_summarization",
        "evidence_obligation": "intake_summary_with_brief_digest",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "planner": {
        "slug": "ao2.provider-contract.planner.v1",
        "sandbox": "read_only_planning_with_scoped_writes",
        "evidence_obligation": "plan_artifact_with_role_contract_refs",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "plan_hardener": {
        "slug": "ao2.provider-contract.plan-hardener.v1",
        "sandbox": "read_only_planning_with_scoped_writes",
        "evidence_obligation": "hardened_plan_with_threat_model_refs",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "factory_manager": {
        "slug": "ao2.provider-contract.factory-manager.v1",
        "sandbox": "read_only_orchestration",
        "evidence_obligation": "factory_manager_dispatch_decisions",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "implementer": {
        "slug": "ao2.provider-contract.implementer.v1",
        "sandbox": "scoped_write_with_digest_patch_and_repair_budget",
        "evidence_obligation": "implementation_digest_patch_and_test_evidence",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "reviewer": {
        "slug": "ao2.provider-contract.reviewer.v1",
        "sandbox": "read_only_review",
        "evidence_obligation": "review_artifact_with_diff_and_test_refs",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "integrator": {
        "slug": "ao2.provider-contract.integrator.v1",
        "sandbox": "scoped_write_with_merge_and_repair_budget",
        "evidence_obligation": "integration_evidence_with_merge_refs",
        "closure_owner": "ao2_native_evaluator_closer",
    },
    "evaluator_closer": {
        "slug": "ao2.provider-contract.evaluator-closer.v1",
        "sandbox": "read_only_evaluation_with_signed_decision",
        "evidence_obligation": "evaluator_decision_signed_with_trust_boundary",
        "closure_owner": "ao2_native_evaluator_closer",
    },
}


# Fail fast at import time if a canonical role lacks a contract or vice versa.
_missing_contracts = set(CANONICAL_ROLES) - set(AO2_PROVIDER_CONTRACTS)
_unknown_contracts = set(AO2_PROVIDER_CONTRACTS) - set(CANONICAL_ROLES)
if _missing_contracts:
    raise RuntimeError(
        "canonical roles missing AO2 provider contract: "
        + ", ".join(sorted(_missing_contracts))
    )
if _unknown_contracts:
    raise RuntimeError(
        "AO2 provider contracts not in CANONICAL_ROLES: "
        + ", ".join(sorted(_unknown_contracts))
    )

_unknown_alias_targets = set(ROLE_ALIASES.values()) - set(CANONICAL_ROLES)
if _unknown_alias_targets:
    raise RuntimeError(
        "ROLE_ALIASES targets not in CANONICAL_ROLES: "
        + ", ".join(sorted(_unknown_alias_targets))
    )


class UnknownRoleError(ValueError):
    """Raised when a role id cannot be canonicalized via ROLE_ALIASES."""


def _normalize(role_id: str) -> str:
    return role_id.strip().lower().replace("_", "-")


def canonical_role(role_id: str) -> str:
    """Return the canonical role id for a raw AO Operator role id.

    Lookup is case-insensitive and treats underscores and dashes as
    equivalent so callers can pass either runspec flavor without
    pre-normalizing. As a final fallback, a trailing numeric fan-out
    suffix (``-N`` with one or more ASCII digits) is stripped and the
    lookup retried, so numbered fan-out ids like ``implementer-slice-1``
    canonicalize to the parent canonical role through ``ROLE_ALIASES``.
    Raises UnknownRoleError if no alias matches.
    """
    normalized = _normalize(role_id)
    if normalized in ROLE_ALIASES:
        return ROLE_ALIASES[normalized]
    # Also try the underscore form for direct CANONICAL_ROLES lookups.
    underscore = normalized.replace("-", "_")
    if underscore in CANONICAL_ROLES:
        return underscore
    stripped = _strip_numeric_fan_out_suffix(normalized)
    if stripped is not None:
        if stripped in ROLE_ALIASES:
            return ROLE_ALIASES[stripped]
        stripped_underscore = stripped.replace("-", "_")
        if stripped_underscore in CANONICAL_ROLES:
            return stripped_underscore
    raise UnknownRoleError(
        f"AO Operator role id {role_id!r} has no AO2 provider-contract mapping; "
        "either add an alias to ROLE_ALIASES or a canonical role + contract entry."
    )


def _strip_numeric_fan_out_suffix(normalized: str) -> str | None:
    """Strip a trailing ``-N`` (one or more ASCII digits) from ``normalized``.

    Returns the stripped string when ``normalized`` ends in ``-`` + ASCII
    digits; otherwise returns ``None``. ASCII-only digit check so behaviour
    is byte-identical to the Rust mirror in ``ao2 factory_bridge`` and the
    mapping digest stays stable (the digest covers only the static tables,
    not this function body).
    """
    end = len(normalized)
    while end > 0 and normalized[end - 1] in "0123456789":
        end -= 1
    if end == len(normalized) or end == 0 or normalized[end - 1] != "-":
        return None
    return normalized[: end - 1]


def resolve_role(role_id: str) -> dict[str, str]:
    """Return the AO2 provider-contract record for a raw AO Operator role id."""
    canonical = canonical_role(role_id)
    contract = AO2_PROVIDER_CONTRACTS[canonical]
    return {
        "role_id": role_id,
        "canonical_role": canonical,
        "ao2_provider_contract_slug": contract["slug"],
        "sandbox": contract["sandbox"],
        "evidence_obligation": contract["evidence_obligation"],
        "closure_owner": contract["closure_owner"],
    }


def extract_role_ids(runspec: dict[str, Any]) -> list[str]:
    """Pull the ordered list of role ids out of a RunSpec.

    Supports both shapes the AO Operator emits:
      - factory-v3/runspec/v1: top-level `roles: [{id, ...}]`
      - ao.dev/v1 `Run`: `spec.tasks: [{id, kind: agent, ...}]`

    Tasks with `kind` set to something other than `agent` are skipped because
    only agent tasks are subject to the provider-contract mapping. Non-dict
    entries are skipped silently; structural validation is the runspec
    validator's job, not the mapping module's.
    """
    role_ids: list[str] = []
    roles_list = runspec.get("roles")
    if isinstance(roles_list, list):
        for entry in roles_list:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                role_ids.append(entry["id"])
        return role_ids
    spec = runspec.get("spec")
    if isinstance(spec, dict):
        tasks = spec.get("tasks")
        if isinstance(tasks, list):
            for entry in tasks:
                if not isinstance(entry, dict):
                    continue
                kind = entry.get("kind", "agent")
                if kind != "agent":
                    continue
                if isinstance(entry.get("id"), str):
                    role_ids.append(entry["id"])
    return role_ids


def resolve_runspec(runspec: dict[str, Any]) -> list[dict[str, str]]:
    """Resolve every role id in a RunSpec, preserving order.

    Raises UnknownRoleError on the first id that cannot be mapped. Callers
    that need to collect every unresolved id should iterate `extract_role_ids`
    and call `canonical_role` themselves.
    """
    resolved: list[dict[str, str]] = []
    for role_id in extract_role_ids(runspec):
        resolved.append(resolve_role(role_id))
    return resolved


def mapping_table() -> dict[str, Any]:
    """Return a deterministic JSON-serializable snapshot of the mapping."""
    sorted_aliases = dict(sorted(ROLE_ALIASES.items()))
    sorted_contracts = {
        role: dict(sorted(AO2_PROVIDER_CONTRACTS[role].items()))
        for role in sorted(AO2_PROVIDER_CONTRACTS)
    }
    return {
        "schema": SCHEMA,
        "mapping_version": MAPPING_VERSION,
        "canonical_roles": list(CANONICAL_ROLES),
        "role_aliases": sorted_aliases,
        "ao2_provider_contracts": sorted_contracts,
        "trust_boundary": dict(sorted(TRUST_BOUNDARY.items())),
    }


def mapping_digest() -> str:
    """Stable sha256 hex of the canonicalized mapping table.

    Evidence consumers can store this digest to detect mapping drift between
    bridge invocations on different hosts or after upgrades.
    """
    payload = json.dumps(mapping_table(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_runspec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "PyYAML is required to load RunSpec YAML files; install via "
            "`pip install pyyaml`"
        ) from exc
    value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise SystemExit(f"RunSpec {path} did not parse to a mapping")
    return value


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve AO Operator role ids to AO2 provider contracts; emit "
            "the mapping table or its content-addressable digest."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    table_cmd = sub.add_parser("table", help="emit the full mapping table as JSON")
    table_cmd.set_defaults(command="table")

    digest_cmd = sub.add_parser("digest", help="emit the mapping table sha256 digest")
    digest_cmd.set_defaults(command="digest")

    role_cmd = sub.add_parser("role", help="resolve a single role id")
    role_cmd.add_argument("role_id")

    runspec_cmd = sub.add_parser("runspec", help="resolve every role in a RunSpec YAML")
    runspec_cmd.add_argument("--runspec", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.command == "table":
        _emit(mapping_table())
        return 0
    if args.command == "digest":
        print(mapping_digest())
        return 0
    if args.command == "role":
        try:
            _emit(resolve_role(args.role_id))
            return 0
        except UnknownRoleError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "runspec":
        runspec = _load_runspec(args.runspec)
        try:
            resolved = resolve_runspec(runspec)
        except UnknownRoleError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _emit(
            {
                "schema": SCHEMA,
                "mapping_digest": mapping_digest(),
                "runspec_path": str(args.runspec),
                "resolved_roles": resolved,
            }
        )
        return 0
    parser.error("unknown command")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
