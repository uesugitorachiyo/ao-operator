#!/usr/bin/env python3
"""Import and validate workflow-as-data RunSpec YAML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


SCHEMA = "ao-operator/runspec/v1"
ROLE_FIELDS = ("id", "provider_key", "host_tag", "deps", "reads", "writes")


class RunSpecImportError(ValueError):
    """Raised when a workflow-as-data RunSpec is malformed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RunSpecImportError(message)


def validate_runspec(payload: Any) -> dict[str, Any]:
    _require(isinstance(payload, dict), "runspec must be a YAML mapping")
    _require(payload.get("schema") == SCHEMA, f"schema must be {SCHEMA!r}")
    for field in ("slug", "profile", "brief"):
        _require(isinstance(payload.get(field), str) and payload[field], f"{field} must be a non-empty string")
    gates = payload.get("gates")
    _require(isinstance(gates, dict), "gates must be a mapping")
    _require(isinstance(gates.get("gate_b"), bool), "gates.gate_b must be bool")
    _require(isinstance(gates.get("gate_r"), bool), "gates.gate_r must be bool")
    roles = payload.get("roles")
    _require(isinstance(roles, list) and roles, "roles must be a non-empty list")
    seen: set[str] = set()
    for index, role in enumerate(roles):
        _require(isinstance(role, dict), f"roles[{index}] must be a mapping")
        for field in ROLE_FIELDS:
            _require(field in role, f"roles[{index}].{field} is required")
        rid = role["id"]
        _require(isinstance(rid, str) and rid, f"roles[{index}].id must be a non-empty string")
        _require(rid not in seen, f"duplicate role id {rid!r}")
        seen.add(rid)
        _require(
            isinstance(role["provider_key"], str) and role["provider_key"],
            f"roles[{index}].provider_key must be a non-empty string",
        )
        for list_field in ("host_tag", "deps", "reads", "writes"):
            value = role[list_field]
            _require(
                isinstance(value, list) and all(isinstance(item, str) for item in value),
                f"roles[{index}].{list_field} must be list[str]",
            )
    for role in roles:
        for dep in role["deps"]:
            _require(dep in seen, f"role {role['id']!r} has unknown dep {dep!r}")
    return payload


def import_runspec(path: str | Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RunSpecImportError(f"malformed YAML: {exc}") from exc
    return validate_runspec(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import and validate .factory/runspec.yaml")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", help="Print hydrated RunSpec JSON")
    args = parser.parse_args(argv)
    try:
        payload = import_runspec(args.path)
    except RunSpecImportError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
