#!/usr/bin/env python3
"""Gate B: pre-execution contract validation for AO Operator.

Gate B is intentionally deterministic and provider-free. It validates the
materialized intake contract/spec plus profile policy posture before any AO
role executes. In v0.3 this is opt-in from `factory_run.py` via
`--gate-b-strict`, preserving default v0.2 parity.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import validate_intake


SCHEMA = "ao-operator/gate-b/v1"
PROFILE_SCHEMA = "ao-operator/profile/v1"
SPEC_SCHEMA = "ao-operator/gate-b/spec/v1"
CONSTITUTION_SCHEMA = "ao-operator/gate-b/constitution/v1"
ANALYZE_SCHEMA = "ao-operator/gate-b/spec-kit-analyze/v1"
PARTITION_SCHEMA = "ao-operator/gate-b/partition/v1"
RFC_2119_TERMS = ("MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT")
EARS_PREFIXES = ("WHEN", "IF", "WHILE", "WHERE", "GIVEN")
CONSTITUTION_STATEMENTS = [
    {
        "id": "GB-SHALL-001",
        "text": "WHEN AO Operator receives intake artifacts, Gate B SHALL validate classification, shape, acceptance criteria, constraints, sensitive fields, trigger hints, and scoped slices before role dispatch.",
    },
    {
        "id": "GB-SHALL-002",
        "text": "WHEN a profile is selected, Gate B SHALL validate role reads, writes, skills, dependencies, and policy posture before role dispatch.",
    },
    {
        "id": "GR-SHALL-001",
        "text": "WHEN role execution completes, Gate R SHALL compare role artifacts against the Gate B role contract before closure is trusted.",
    },
    {
        "id": "GR-SHALL-002",
        "text": "IF a role reports an artifact outside its declared Gate B writes, Gate R MUST fail closure with the drift path named.",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(path)


def _list_str(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def concrete_path(value: str) -> str:
    candidate = value.strip().strip("`")
    if not candidate or candidate == "." or candidate.endswith("/"):
        return ""
    if "<slug>" in candidate or " " in candidate:
        return ""
    if "/" not in candidate:
        return ""
    return candidate


def validate_profile(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"path": str(path), "verdict": "FAIL", "errors": [f"profile JSON invalid: {exc}"]}

    if not isinstance(data, dict):
        return {"path": str(path), "verdict": "FAIL", "errors": ["profile must be a JSON object"]}
    if data.get("schema") != PROFILE_SCHEMA:
        errors.append(f"profile.schema must be {PROFILE_SCHEMA}")
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append("profile.roles must be a non-empty list")
    elif isinstance(roles, list):
        role_ids: set[str] = set()
        for index, role in enumerate(roles, start=1):
            if not isinstance(role, dict):
                errors.append(f"profile.roles[{index}] must be an object")
                continue
            role_id = role.get("id")
            if not isinstance(role_id, str) or not role_id:
                errors.append(f"profile.roles[{index}].id is required")
                continue
            if role_id in role_ids:
                errors.append(f"profile.roles[{index}].id duplicate: {role_id}")
            role_ids.add(role_id)
            for field in ("reads", "writes", "skills", "instructions", "deps"):
                if not _list_str(role.get(field)):
                    errors.append(f"profile.roles[{index}].{field} must be list[str]")

    posture = data.get("policy_posture")
    if posture is not None:
        if not isinstance(posture, dict):
            errors.append("policy_posture must be an object when present")
        else:
            shell = posture.get("shell")
            fs = posture.get("fs")
            network = posture.get("network")
            secrets = posture.get("secrets")
            if not isinstance(shell, dict):
                errors.append("policy_posture.shell must be an object")
            else:
                for field in ("allow_prefixes", "require_approval_for", "deny_prefixes"):
                    if not _list_str(shell.get(field)):
                        errors.append(f"policy_posture.shell.{field} must be list[str]")
            if not isinstance(fs, dict):
                errors.append("policy_posture.fs must be an object")
            else:
                for field in ("write_scopes_must_match_contract", "deny_outside_workspace"):
                    if not isinstance(fs.get(field), bool):
                        errors.append(f"policy_posture.fs.{field} must be bool")
            if not isinstance(network, dict):
                errors.append("policy_posture.network must be an object")
            else:
                if network.get("egress_default") not in {"allow", "deny"}:
                    errors.append("policy_posture.network.egress_default must be allow or deny")
                if not _list_str(network.get("allow_hosts")):
                    errors.append("policy_posture.network.allow_hosts must be list[str]")
            if not isinstance(secrets, dict):
                errors.append("policy_posture.secrets must be an object")
            else:
                if not _list_str(secrets.get("forbidden_env")):
                    errors.append("policy_posture.secrets.forbidden_env must be list[str]")
                if not isinstance(secrets.get("require_approval_for_read"), bool):
                    errors.append("policy_posture.secrets.require_approval_for_read must be bool")

    return {"path": str(path), "verdict": "PASS" if not errors else "FAIL", "errors": errors}


def role_contracts(profile_path: Path | None, slug: str) -> list[dict[str, Any]]:
    if profile_path is None or not profile_path.is_file():
        return []
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    roles = data.get("roles", []) if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("id") or "")
        out.append(
            {
                "id": role_id,
                "reads": [str(item).replace("<slug>", slug) for item in role.get("reads", [])],
                "writes": [str(item).replace("<slug>", slug) for item in role.get("writes", [])],
                "skills": [str(item) for item in role.get("skills", [])],
                "is_mutator": bool(role.get("is_mutator", False)),
            }
        )
    return out


def load_partition_slices(intake_artifacts: list[Path]) -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    for path in intake_artifacts:
        if path.suffix != ".json" or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        raw_slices = data.get("slices") if isinstance(data, dict) else None
        if not isinstance(raw_slices, list):
            continue
        for item in raw_slices:
            if isinstance(item, dict):
                slices.append(item)
    return slices


def render_slug(value: Any, slug: str) -> str:
    return str(value).replace("<slug>", slug)


def normalize_slice_list(value: Any, slug: str) -> list[str]:
    if not isinstance(value, list):
        return []
    return [render_slug(item, slug) for item in value if isinstance(item, str) and item]


def validate_partition_slices(raw_slices: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    write_owner: dict[str, str] = {}

    for index, item in enumerate(raw_slices, start=1):
        slice_id = item.get("id")
        if not isinstance(slice_id, str) or not slice_id:
            errors.append(f"partition.slices[{index}].id is required")
            slice_id = f"slice-{index}"

        reads = normalize_slice_list(item.get("reads"), slug)
        writes = normalize_slice_list(item.get("writes"), slug)
        verification = normalize_slice_list(item.get("verification"), slug)
        merge_owner = item.get("merge_owner")
        rejoin_artifact = item.get("rejoin_artifact")

        if not reads:
            errors.append(f"{slice_id}: reads must be non-empty list[str]")
        if not isinstance(item.get("writes"), list):
            errors.append(f"{slice_id}: writes must be list[str]")
        if not verification:
            errors.append(f"{slice_id}: verification must be non-empty list[str]")
        if not isinstance(merge_owner, str) or not merge_owner:
            errors.append(f"{slice_id}: merge_owner is required")
            merge_owner = ""
        if not isinstance(rejoin_artifact, str) or not concrete_path(render_slug(rejoin_artifact, slug)):
            errors.append(f"{slice_id}: rejoin_artifact must be a concrete path")
            rejoin_artifact = ""

        concrete_writes: list[str] = []
        for raw_write in writes:
            path = concrete_path(raw_write)
            if not path:
                errors.append(f"{slice_id}: write {raw_write!r} must be a concrete path")
                continue
            concrete_writes.append(path)
            previous = write_owner.get(path)
            if previous and previous != slice_id:
                errors.append(f"{slice_id}: write {path!r} overlaps with {previous}")
            else:
                write_owner[path] = slice_id

        normalized.append(
            {
                "id": slice_id,
                "slice_id": item.get("slice_id", index),
                "reads": reads,
                "writes": concrete_writes,
                "verification": verification,
                "merge_owner": str(merge_owner),
                "rejoin_artifact": render_slug(rejoin_artifact, slug) if rejoin_artifact else "",
            }
        )

    return {
        "schema": PARTITION_SCHEMA,
        "slices": normalized,
        "slice_count": len(normalized),
        "errors": errors,
        "verdict": "PASS" if not errors else "FAIL",
    }


def spec_contract(
    *,
    repo: Path,
    slug: str,
    intake_artifacts: list[Path],
    profile_path: Path | None,
    roles: list[dict[str, Any]],
    partition: dict[str, Any],
) -> dict[str, Any]:
    spec_roles: list[dict[str, Any]] = []
    role_artifacts: dict[str, str] = {}
    for role in roles:
        role_id = str(role.get("id") or "")
        role_artifact = f"run-artifacts/{slug}/roles/{role_id}.md"
        role_artifacts[role_id] = role_artifact
        declared_writes = [
            str(item).replace("<slug>", slug) for item in role.get("writes", [])
        ]
        concrete_writes = [path for path in (concrete_path(item) for item in declared_writes) if path]
        spec_roles.append(
            {
                "id": role_id,
                "reads": [str(item).replace("<slug>", slug) for item in role.get("reads", [])],
                "writes": declared_writes,
                "skills": [str(item) for item in role.get("skills", [])],
                "is_mutator": bool(role.get("is_mutator", False)),
                "role_artifact": role_artifact,
                "allowed_artifacts": list(dict.fromkeys([role_artifact, *concrete_writes])),
            }
        )
    return {
        "schema": SPEC_SCHEMA,
        "slug": slug,
        "intake_artifacts": [rel(repo, path) for path in intake_artifacts],
        "profile": rel(repo, profile_path) if profile_path else "default",
        "role_artifacts": role_artifacts,
        "roles": spec_roles,
        "partition_slices": partition["slices"],
    }


def constitution_contract() -> dict[str, Any]:
    return {
        "schema": CONSTITUTION_SCHEMA,
        "requirements": CONSTITUTION_STATEMENTS,
    }


def lint_constitution(constitution: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    requirements = constitution.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        return ["constitution.requirements must be a non-empty list"]
    for index, item in enumerate(requirements, start=1):
        if not isinstance(item, dict):
            errors.append(f"constitution.requirements[{index}] must be an object")
            continue
        req_id = item.get("id")
        text = item.get("text")
        if not isinstance(req_id, str) or not req_id:
            errors.append(f"constitution.requirements[{index}].id is required")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"constitution.requirements[{index}].text is required")
            continue
        stripped = text.strip()
        if not stripped.startswith(EARS_PREFIXES):
            errors.append(f"{req_id}: requirement must use an EARS trigger prefix")
        if not any(term in stripped for term in RFC_2119_TERMS):
            errors.append(f"{req_id}: requirement must use an RFC-2119 keyword")
    return errors


def spec_kit_analyze(spec: dict[str, Any], constitution: dict[str, Any]) -> dict[str, Any]:
    errors = lint_constitution(constitution)
    roles = spec.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append("spec.roles must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, role in enumerate(roles, start=1):
            if not isinstance(role, dict):
                errors.append(f"spec.roles[{index}] must be an object")
                continue
            role_id = role.get("id")
            if not isinstance(role_id, str) or not role_id:
                errors.append(f"spec.roles[{index}].id is required")
                continue
            if role_id in seen:
                errors.append(f"spec.roles[{index}].id duplicate: {role_id}")
            seen.add(role_id)
            if not _list_str(role.get("writes")):
                errors.append(f"spec.roles[{index}].writes must be list[str]")
            role_artifact = role.get("role_artifact")
            allowed = role.get("allowed_artifacts")
            if not isinstance(role_artifact, str) or not role_artifact:
                errors.append(f"spec.roles[{index}].role_artifact is required")
            if not _list_str(allowed):
                errors.append(f"spec.roles[{index}].allowed_artifacts must be list[str]")
            elif isinstance(role_artifact, str) and role_artifact not in allowed:
                errors.append(f"spec.roles[{index}].allowed_artifacts must include role_artifact")
    return {
        "schema": ANALYZE_SCHEMA,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def run_gate(
    *,
    repo: Path,
    slug: str,
    intake_artifacts: list[Path],
    profile_path: Path | None,
    partition_slices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intake_result = validate_intake.run([path.resolve() for path in intake_artifacts], repo.resolve())
    profile_result = validate_profile(profile_path) if profile_path else {
        "path": "",
        "verdict": "PASS",
        "errors": [],
    }
    roles = role_contracts(profile_path, slug)
    raw_partition_slices = (
        partition_slices if partition_slices is not None else load_partition_slices(intake_artifacts)
    )
    partition = validate_partition_slices(raw_partition_slices, slug)
    spec = spec_contract(
        repo=repo,
        slug=slug,
        intake_artifacts=intake_artifacts,
        profile_path=profile_path,
        roles=roles,
        partition=partition,
    )
    constitution = constitution_contract()
    analyze_result = spec_kit_analyze(spec, constitution)
    errors = list(intake_result.get("errors", [])) + [
        f"{profile_result['path']}: {error}" for error in profile_result.get("errors", [])
    ] + list(analyze_result.get("errors", [])) + list(partition.get("errors", []))
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "slug": slug,
        "intake_artifacts": [rel(repo, path) for path in intake_artifacts],
        "profile": rel(repo, profile_path) if profile_path else "default",
        "validators": {
            "validate_intake": intake_result,
            "profile_policy_posture": profile_result,
            "spec_kit_analyze": analyze_result,
        },
        "spec": spec,
        "constitution": constitution,
        "partition": partition,
        "role_contracts": roles,
        "errors": errors,
        "verdict": "PASS" if not errors else "FAIL",
        "next_safe_command": (
            "Gate B passed; role execution may proceed."
            if not errors
            else "Fix Gate B contract/profile errors before dispatch."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AO Operator Gate B.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--slug", required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--partition-slices", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("intake_artifacts", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_gate(
        repo=args.repo,
        slug=args.slug,
        intake_artifacts=args.intake_artifacts,
        profile_path=args.profile,
        partition_slices=(
            json.loads(args.partition_slices.read_text(encoding="utf-8"))
            if args.partition_slices
            else None
        ),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"verdict={report['verdict']}")
        for error in report["errors"]:
            print(f"error={error}", file=sys.stderr)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
