"""Tests for ``agents/intake.toml``.

AO2's ``ao2 factory bridge`` looks for ``intake.toml`` under
``--role-contracts-dir`` whenever a RunSpec task canonicalizes to the
``intake`` role (e.g. ``planner-intake``). Before this file existed,
AO2 reported ``planner-intake`` in ``role_contracts.missing_roles``
on every nightly run even when every other role contract loaded
cleanly. This test locks the TOML's well-formedness so the AO2
bridge can keep loading it.

These tests are intentionally narrow — they assert the contract
fields the bridge actually reads (``name``, ``description``,
``inputs``, ``outputs``, ``status_required``). They do not
re-implement AO2's loader; the cross-repo end-to-end smoke does
that (``run-artifacts/.../role-contracts-e2e-smoke``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
INTAKE_TOML = ROOT / "agents" / "intake.toml"


@pytest.fixture(scope="module")
def intake_contract() -> dict:
    raw = INTAKE_TOML.read_bytes()
    return tomllib.loads(raw.decode("utf-8"))


def test_intake_toml_exists() -> None:
    assert INTAKE_TOML.is_file(), (
        "agents/intake.toml must exist so the AO2 bridge resolves "
        "planner-intake without leaving it in role_contracts.missing_roles"
    )


def test_intake_contract_name_matches_canonical_role(
    intake_contract: dict,
) -> None:
    assert intake_contract.get("name") == "intake"


def test_intake_contract_has_required_string_fields(
    intake_contract: dict,
) -> None:
    name = intake_contract.get("name")
    description = intake_contract.get("description")
    assert isinstance(name, str) and name.strip(), "name must be a non-empty string"
    assert isinstance(description, str) and description.strip(), (
        "description must be a non-empty string"
    )


def test_intake_contract_inputs_and_outputs_are_string_arrays(
    intake_contract: dict,
) -> None:
    for field in ("inputs", "outputs"):
        value = intake_contract.get(field)
        assert isinstance(value, list), f"{field} must be a TOML array"
        assert value, f"{field} must be non-empty so the AO2 bridge has content to load"
        for item in value:
            assert isinstance(item, str) and item.strip(), (
                f"{field} entries must be non-empty strings; got {item!r}"
            )


def test_intake_contract_status_required_is_bool(intake_contract: dict) -> None:
    status_required = intake_contract.get("status_required")
    assert isinstance(status_required, bool), (
        "status_required must be a TOML boolean so AO2's loader can mirror "
        "its serialization (Value::Null vs json!(status_required))"
    )


def test_intake_contract_shape_matches_other_core_roles(
    intake_contract: dict,
) -> None:
    """Every existing core role TOML carries exactly these top-level keys.
    Intake must join that uniform shape so the AO2 loader (which reads each
    key independently) never has to special-case it."""
    expected_keys = {"name", "description", "inputs", "outputs", "status_required"}
    assert set(intake_contract.keys()) == expected_keys


def test_intake_contract_parity_with_planner_toml_shape() -> None:
    """Cross-check: parse ``planner.toml`` and confirm intake exposes the
    same key set with the same types. Locks the convention against drift
    in either direction."""
    planner_path = ROOT / "agents" / "planner.toml"
    planner = tomllib.loads(planner_path.read_text(encoding="utf-8"))
    intake = tomllib.loads(INTAKE_TOML.read_text(encoding="utf-8"))
    assert set(planner.keys()) == set(intake.keys())
    for key in planner.keys():
        assert type(planner[key]) is type(intake[key]), (
            f"{key} type must match planner.toml; planner={type(planner[key])} "
            f"intake={type(intake[key])}"
        )
