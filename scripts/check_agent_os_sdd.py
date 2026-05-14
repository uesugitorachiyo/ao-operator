#!/usr/bin/env python3
"""Validate the AO Operator Agent OS doc-only SDD contract."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SDD = "docs/sdd/13-agent-os.md"
DEFAULT_CONTRACT = "docs/contracts/ao-operator-agent-os.contract.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-sdd-validation.json"
REQUIRED_SECTIONS = [
    "Mission Router",
    "Project State Layer",
    "Role Capability Schema",
    "Specialist Registry",
    "Phase Compiler",
    "Verification Matrix",
    "UAT Gate",
    "Learning Loop",
    "Operator Cockpit",
    "Negative Constraints",
    "Implementation Slices",
    "Acceptance Criteria",
]
REQUIRED_PHASES = [
    "agent-os-sdd",
    "mission-router-state",
    "codebase-mapper-specialists",
    "capability-validation",
    "phase-compiler-verification",
    "uat-learning-cockpit",
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


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def add_check(
    checks: list[dict[str, str]],
    errors: list[str],
    check_id: str,
    ok: bool,
    message: str,
) -> None:
    checks.append({"id": check_id, "status": "PASS" if ok else "FAIL"})
    if not ok:
        errors.append(message)


def list_strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def validate_sdd(text: str, checks: list[dict[str, str]], errors: list[str]) -> None:
    add_check(checks, errors, "sdd.exists", bool(text.strip()), "Agent OS SDD is missing")
    add_check(checks, errors, "sdd.classification", "Classification: COMPLEX" in text, "Agent OS SDD must declare Classification: COMPLEX")
    add_check(checks, errors, "sdd.shape", "Shape: greenfield" in text, "Agent OS SDD must declare Shape: greenfield")
    for section in REQUIRED_SECTIONS:
        add_check(
            checks,
            errors,
            f"sdd.section:{section}",
            f"## {section}" in text,
            f"Agent OS SDD missing section: {section}",
        )
    add_check(
        checks,
        errors,
        "sdd.no_provider_dispatch",
        "MUST NOT dispatch AO providers" in text,
        "Agent OS SDD must forbid provider dispatch in the doc-only slice",
    )


def validate_contract(contract: dict[str, Any], checks: list[dict[str, str]], errors: list[str]) -> None:
    add_check(
        checks,
        errors,
        "contract.schema",
        contract.get("schema") == "ao-operator/agent-os-sdd-contract/v1",
        "Agent OS contract schema must be ao-operator/agent-os-sdd-contract/v1",
    )
    add_check(checks, errors, "contract.classification", contract.get("classification") == "COMPLEX", "Agent OS contract must be COMPLEX")
    add_check(checks, errors, "contract.shape", contract.get("shape") == "greenfield", "Agent OS contract must be greenfield")
    add_check(
        checks,
        errors,
        "contract.dispatch_false",
        contract.get("dispatch_authorized") is False,
        "Agent OS contract dispatch_authorized must be false",
    )
    add_check(
        checks,
        errors,
        "contract.live_false",
        contract.get("live_providers_run") is False,
        "Agent OS contract live_providers_run must be false",
    )
    for key in ["problem", "success_criteria", "negative_constraints", "sensitive_fields", "trigger_hints"]:
        value = contract.get(key)
        present = bool(value) and (isinstance(value, str) or isinstance(value, list))
        add_check(checks, errors, f"contract.{key}", present, f"Agent OS contract missing {key}")
    phases = list_strings(contract.get("phases"))
    add_check(
        checks,
        errors,
        "contract.phases",
        phases == REQUIRED_PHASES,
        "Agent OS contract phases must match the planned six-phase roadmap",
    )
    shall = contract.get("shall_statements", [])
    shall_ok = isinstance(shall, list) and len(shall) >= 4 and all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and any(word in str(item.get("requirement", "")) for word in ["SHALL", "MUST", "SHOULD", "MAY"])
        for item in shall
    )
    add_check(checks, errors, "contract.shall_statements", shall_ok, "Agent OS contract needs at least four RFC-2119 SHALL statements")
    acs = contract.get("acceptance_criteria", [])
    acs_ok = isinstance(acs, list) and len(acs) >= 2 and all(
        isinstance(item, dict)
        and item.get("id")
        and item.get("shall_refs")
        and item.get("oracle")
        and item.get("verification")
        and item.get("file_hints")
        and item.get("risk_tags")
        for item in acs
    )
    add_check(checks, errors, "contract.acceptance_criteria", acs_ok, "Agent OS contract acceptance criteria need verifiable oracles")
    slices = contract.get("slices", [])
    slices_ok = isinstance(slices, list) and bool(slices) and all(
        isinstance(item, dict)
        and item.get("id")
        and isinstance(item.get("reads"), list)
        and isinstance(item.get("writes"), list)
        and item.get("acceptance")
        and item.get("verification")
        for item in slices
    )
    add_check(checks, errors, "contract.slices", slices_ok, "Agent OS contract slices must declare reads, writes, acceptance, and verification")


def build_report(
    *,
    root: Path = ROOT,
    sdd: str | Path = DEFAULT_SDD,
    contract: str | Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    sdd_path = resolve_path(root, sdd)
    contract_path = resolve_path(root, contract)
    text = load_text(sdd_path)
    contract_data = load_json(contract_path)
    checks: list[dict[str, str]] = []
    errors: list[str] = []
    validate_sdd(text, checks, errors)
    validate_contract(contract_data, checks, errors)
    ready = not errors
    return {
        "schema": "ao-operator/agent-os-sdd-validation/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if ready else "FAIL",
        "current_state": "AGENT_OS_SDD_ACCEPTED_NOT_IMPLEMENTED" if ready else "BLOCKED",
        "classification": contract_data.get("classification"),
        "shape": contract_data.get("shape"),
        "phase_count": len(list_strings(contract_data.get("phases"))),
        "sdd": relpath(root, sdd_path),
        "contract": relpath(root, contract_path),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "checks": checks,
        "errors": errors,
        "next_safe_command": (
            "Plan the mission-router/state implementation slice; do not dispatch AO providers from the SDD gate."
            if ready
            else "Fix Agent OS SDD contract blockers before planning implementation."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the AO Operator Agent OS SDD")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--sdd", default=DEFAULT_SDD)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_report(root=args.root, sdd=args.sdd, contract=args.contract)
    if args.write_output is not None:
        output_path = resolve_path(args.root, args.write_output)
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
