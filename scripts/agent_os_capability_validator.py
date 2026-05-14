#!/usr/bin/env python3
"""Validate Agent OS role capabilities without enabling dispatch."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = "docs/contracts/ao-operator-agent-capabilities.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-capability-validation.json"
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_DISPATCH_MODES = {"ao-role", "local-validation", "manual-review"}
REQUIRED_ROLE_FIELDS = [
    "id",
    "contract",
    "capabilities",
    "allowed_tools",
    "reads",
    "writes",
    "risk_level",
    "dispatch_mode",
    "provider_boundary",
    "verification",
]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def role_errors(root: Path, role: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    role_id = str(role.get("id") or "")
    for field in REQUIRED_ROLE_FIELDS:
        if not role.get(field):
            errors.append(f"role {role_id or '<missing>'} missing {field}")
    if role.get("risk_level") not in VALID_RISK_LEVELS:
        errors.append(f"role {role_id} risk_level must be one of {sorted(VALID_RISK_LEVELS)}")
    if role.get("dispatch_mode") not in VALID_DISPATCH_MODES:
        errors.append(f"role {role_id} dispatch_mode must be one of {sorted(VALID_DISPATCH_MODES)}")
    for field in ["capabilities", "allowed_tools", "reads", "writes"]:
        if not string_list(role.get(field)):
            errors.append(f"role {role_id} {field} must be a non-empty string list")

    contract_path = resolve_path(root, str(role.get("contract") or ""))
    contract = load_toml(contract_path)
    if not contract:
        errors.append(f"role {role_id} contract missing or invalid: {relpath(root, contract_path)}")
    elif contract.get("name") != role_id:
        errors.append(f"role {role_id} contract name mismatch: {contract.get('name')}")
    elif not string_list(contract.get("inputs")) or not string_list(contract.get("outputs")):
        errors.append(f"role {role_id} contract must declare inputs and outputs")

    for skill in string_list(role.get("required_skills", [])):
        skill_path = root / "skills" / skill / "SKILL.md"
        if not skill_path.is_file():
            errors.append(f"role {role_id} required skill missing: {skill}")
    return errors


def specialist_errors(specialist: dict[str, Any]) -> list[str]:
    specialist_id = str(specialist.get("id") or "<missing>")
    errors: list[str] = []
    if specialist.get("executable") is not False:
        errors.append(f"specialist {specialist_id} must remain non-executable until a future role-contract slice")
    for field in ["id", "capabilities", "allowed_tools", "activation_gate"]:
        if not specialist.get(field):
            errors.append(f"specialist {specialist_id} missing {field}")
    if not string_list(specialist.get("capabilities")):
        errors.append(f"specialist {specialist_id} capabilities must be a non-empty string list")
    if not string_list(specialist.get("allowed_tools")):
        errors.append(f"specialist {specialist_id} allowed_tools must be a non-empty string list")
    return errors


def validate_capabilities(
    *,
    root: Path = ROOT,
    contract: str | Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract_path = resolve_path(root, contract)
    data = load_json(contract_path)
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-capability-contract/v1":
        errors.append("schema must be ao-operator/agent-os-capability-contract/v1")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must be false")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must be false")
    if not string_list(data.get("negative_constraints")):
        errors.append("negative_constraints must be a non-empty string list")

    core_roles = [item for item in data.get("core_roles", []) if isinstance(item, dict)] if isinstance(data.get("core_roles"), list) else []
    specialists = [item for item in data.get("specialists", []) if isinstance(item, dict)] if isinstance(data.get("specialists"), list) else []
    if not core_roles:
        errors.append("core_roles must be a non-empty list")
    if not specialists:
        errors.append("specialists must be a non-empty list")
    for role in core_roles:
        errors.extend(role_errors(root, role))
    for specialist in specialists:
        errors.extend(specialist_errors(specialist))

    return {
        "schema": "ao-operator/agent-os-capability-validation/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "contract": relpath(root, contract_path),
        "core_role_count": len(core_roles),
        "specialist_count": len(specialists),
        "inactive_specialists": [str(item.get("id")) for item in specialists if item.get("executable") is False],
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Plan phase compiler and verification matrix using validated capabilities."
            if not errors
            else "Fix capability contract errors before using specialist roles."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AO Operator Agent OS capabilities")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = validate_capabilities(root=args.root, contract=args.contract)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
