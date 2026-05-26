from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "ao_operator_ao2_provider_contract.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ao_operator_ao2_provider_contract as mapping  # noqa: E402


# ---------------------------------------------------------------------------
# Static invariants the mapping module promises.
# ---------------------------------------------------------------------------


def test_every_canonical_role_has_a_provider_contract():
    assert set(mapping.AO2_PROVIDER_CONTRACTS) == set(mapping.CANONICAL_ROLES)


def test_every_alias_target_is_a_canonical_role():
    assert set(mapping.ROLE_ALIASES.values()).issubset(set(mapping.CANONICAL_ROLES))


def test_canonical_role_self_maps_for_every_canonical():
    # Every canonical role id must round-trip through canonical_role() as itself
    # regardless of dash/underscore spelling.
    for canonical in mapping.CANONICAL_ROLES:
        assert mapping.canonical_role(canonical) == canonical
        assert mapping.canonical_role(canonical.replace("_", "-")) == canonical


def test_provider_contract_slugs_are_unique_and_well_formed():
    seen: set[str] = set()
    for role, contract in mapping.AO2_PROVIDER_CONTRACTS.items():
        slug = contract["slug"]
        assert slug.startswith("ao2.provider-contract."), (
            f"contract slug for {role!r} must start with ao2.provider-contract."
        )
        assert slug.endswith(".v1"), f"contract slug for {role!r} must be versioned (.v1)"
        assert slug not in seen, f"duplicate slug {slug!r}"
        seen.add(slug)


def test_every_contract_records_evidence_obligation_and_closure_owner():
    for role, contract in mapping.AO2_PROVIDER_CONTRACTS.items():
        for required in ("slug", "sandbox", "evidence_obligation", "closure_owner"):
            assert required in contract, f"contract for {role!r} missing {required!r}"
        assert contract["closure_owner"] == "ao2_native_evaluator_closer", (
            "closure_owner must be the AO2 native evaluator-closer so AO2 keeps "
            "closure authority for every provider contract"
        )


def test_resolve_role_returns_full_record():
    result = mapping.resolve_role("planner-intake")
    assert result["role_id"] == "planner-intake"
    assert result["canonical_role"] == "intake"
    assert result["ao2_provider_contract_slug"] == "ao2.provider-contract.intake.v1"
    assert result["closure_owner"] == "ao2_native_evaluator_closer"


def test_resolve_role_rejects_unknown_role_id():
    with pytest.raises(mapping.UnknownRoleError):
        mapping.resolve_role("totally-not-a-real-role")


# ---------------------------------------------------------------------------
# Both runspec flavors collapse to the same canonical roles for the same
# logical role. This is the property the bridge depends on.
# ---------------------------------------------------------------------------


FLAVOR_PAIRS: list[tuple[str, str, str]] = [
    ("intake", "intake", "planner-intake"),
    ("planner", "planner", "agent-os-planner"),
    ("plan_hardener", "plan-hardener", "agent-os-plan-hardener"),
    ("factory_manager", "factory-manager", "agent-os-factory-manager"),
    ("implementer", "implementer", "implementer-slice"),
    ("implementer", "implementer-slice", "agent-os-implementer"),
    ("reviewer", "reviewer", "reviewer-slice"),
    ("reviewer", "slice-reviewer", "agent-os-slice-reviewer"),
    ("integrator", "integrator", "agent-os-integrator"),
    ("evaluator_closer", "evaluator-closer", "agent-os-evaluator-closer"),
]


@pytest.mark.parametrize("canonical,alias_a,alias_b", FLAVOR_PAIRS)
def test_both_runspec_flavors_resolve_to_same_contract(
    canonical: str, alias_a: str, alias_b: str
) -> None:
    assert mapping.canonical_role(alias_a) == canonical
    assert mapping.canonical_role(alias_b) == canonical
    slug = mapping.AO2_PROVIDER_CONTRACTS[canonical]["slug"]
    assert mapping.resolve_role(alias_a)["ao2_provider_contract_slug"] == slug
    assert mapping.resolve_role(alias_b)["ao2_provider_contract_slug"] == slug


# ---------------------------------------------------------------------------
# Numbered fan-out: ids like `implementer-slice-1` strip the trailing `-N`
# suffix as a final fallback and canonicalize through the parent alias.
# Byte-identical to the Rust mirror in ao2 factory_bridge.
# ---------------------------------------------------------------------------


NUMBERED_FAN_OUT_PAIRS: list[tuple[str, str]] = [
    ("implementer-slice-1", "implementer"),
    ("implementer-slice-12", "implementer"),
    ("implementer_slice_3", "implementer"),
    ("reviewer-slice-7", "reviewer"),
    ("slice-reviewer-2", "reviewer"),
    ("implementer-1", "implementer"),
    ("evaluator-closer-9", "evaluator_closer"),
    ("planner-intake-1", "intake"),
    ("agent-os-implementer-5", "implementer"),
]


@pytest.mark.parametrize("role_id,canonical", NUMBERED_FAN_OUT_PAIRS)
def test_numbered_fan_out_canonicalizes_to_parent_alias(
    role_id: str, canonical: str
) -> None:
    assert mapping.canonical_role(role_id) == canonical


NON_NUMERIC_SUFFIX_REJECTS: list[str] = [
    "implementer-slice-a",
    "implementer-slice-",
    "foo-bar",
    "-1",
    "-12",
]


@pytest.mark.parametrize("role_id", NON_NUMERIC_SUFFIX_REJECTS)
def test_non_numeric_suffix_or_unknown_stem_still_rejects(role_id: str) -> None:
    with pytest.raises(mapping.UnknownRoleError):
        mapping.canonical_role(role_id)


def test_mapping_digest_unchanged_after_fan_out_suffix_stripping_added(
    tmp_path: Path,
) -> None:
    """The numeric-suffix fallback lives in `canonical_role`, not the static
    `mapping_table()`, so the cross-language `mapping_digest()` must remain
    pinned. Locks the digest against silent drift.
    """
    expected_digest = (
        "cda521f5bd1ae42f06ab2f44689161034fa8790163b020ba888719312635cd99"
    )
    assert mapping.mapping_digest() == expected_digest


# ---------------------------------------------------------------------------
# Determinism: digest must be stable across repeated calls and equal for an
# independent recomputation of the canonical table.
# ---------------------------------------------------------------------------


def test_mapping_digest_is_stable_across_calls():
    digest_a = mapping.mapping_digest()
    digest_b = mapping.mapping_digest()
    assert digest_a == digest_b
    assert len(digest_a) == 64


def test_mapping_table_round_trips_through_json():
    table = mapping.mapping_table()
    serialized = json.dumps(table, sort_keys=True)
    again = json.loads(serialized)
    assert again == table


# ---------------------------------------------------------------------------
# Extraction from real runspec shapes.
# ---------------------------------------------------------------------------


FACTORY_V3_RUNSPEC = {
    "schema": "ao-operator/runspec/v1",
    "slug": "bug-fix",
    "roles": [
        {"id": "intake"},
        {"id": "planner"},
        {"id": "implementer"},
        {"id": "reviewer"},
        {"id": "evaluator-closer"},
    ],
}

AO_DEV_V1_RUNSPEC = {
    "apiVersion": "ao.dev/v1",
    "kind": "Run",
    "metadata": {"name": "ao-operator-smoke"},
    "spec": {
        "tasks": [
            {"id": "planner-intake", "kind": "agent", "spec": {}},
            {"id": "plan-hardener", "kind": "agent", "spec": {}},
            {"id": "factory-manager", "kind": "agent", "spec": {}},
            {"id": "implementer-slice", "kind": "agent", "spec": {}},
            {"id": "reviewer-slice", "kind": "agent", "spec": {}},
            {"id": "integrator", "kind": "agent", "spec": {}},
            {"id": "evaluator-closer", "kind": "agent", "spec": {}},
            {"id": "non-agent-task", "kind": "publish", "spec": {}},
        ]
    },
}


def test_extract_role_ids_factory_v3_runspec():
    assert mapping.extract_role_ids(FACTORY_V3_RUNSPEC) == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator-closer",
    ]


def test_extract_role_ids_ao_dev_v1_runspec_skips_non_agent_tasks():
    ids = mapping.extract_role_ids(AO_DEV_V1_RUNSPEC)
    assert ids == [
        "planner-intake",
        "plan-hardener",
        "factory-manager",
        "implementer-slice",
        "reviewer-slice",
        "integrator",
        "evaluator-closer",
    ]


def test_resolve_runspec_full_factory_v3_runspec():
    resolved = mapping.resolve_runspec(FACTORY_V3_RUNSPEC)
    assert [r["canonical_role"] for r in resolved] == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator_closer",
    ]


def test_resolve_runspec_unknown_role_raises():
    bad = {"roles": [{"id": "implementer"}, {"id": "ghost-role"}]}
    with pytest.raises(mapping.UnknownRoleError):
        mapping.resolve_runspec(bad)


# ---------------------------------------------------------------------------
# CLI: exercised via subprocess so the script is callable from operator
# tooling on Mac/Ubuntu/Windows without import shenanigans.
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_digest_matches_module_digest():
    result = _run(["digest"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == mapping.mapping_digest()


def test_cli_role_resolves_known_role():
    result = _run(["role", "planner-intake"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["canonical_role"] == "intake"
    assert payload["ao2_provider_contract_slug"] == "ao2.provider-contract.intake.v1"


def test_cli_role_rejects_unknown_with_nonzero_exit():
    result = _run(["role", "ghost-role"])
    assert result.returncode == 2
    assert "no AO2 provider-contract mapping" in result.stderr


def test_cli_table_emits_full_table_with_digest_stable(tmp_path: Path):
    result = _run(["table"])
    assert result.returncode == 0, result.stderr
    table = json.loads(result.stdout)
    assert table["schema"] == mapping.SCHEMA
    assert set(table["canonical_roles"]) == set(mapping.CANONICAL_ROLES)
    assert "ao2_provider_contracts" in table


def test_cli_runspec_resolves_real_factory_v3_runspec(tmp_path: Path):
    import yaml  # type: ignore

    runspec_path = tmp_path / "runspec.yaml"
    runspec_path.write_text(yaml.safe_dump(FACTORY_V3_RUNSPEC), encoding="utf-8")
    result = _run(["runspec", "--runspec", str(runspec_path)])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mapping_digest"] == mapping.mapping_digest()
    assert [r["canonical_role"] for r in payload["resolved_roles"]] == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator_closer",
    ]


def test_cli_runspec_rejects_unknown_role_with_nonzero_exit(tmp_path: Path):
    import yaml  # type: ignore

    bad = {"roles": [{"id": "implementer"}, {"id": "ghost-role"}]}
    runspec_path = tmp_path / "bad.yaml"
    runspec_path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    result = _run(["runspec", "--runspec", str(runspec_path)])
    assert result.returncode == 2
    assert "no AO2 provider-contract mapping" in result.stderr
