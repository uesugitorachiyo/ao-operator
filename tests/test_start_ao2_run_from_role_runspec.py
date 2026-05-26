from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "start_ao2_run_from_role_runspec.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ao_operator_ao2_provider_contract as mapping  # noqa: E402
import start_ao2_run_from_role_runspec as bridge  # noqa: E402


GOOD_RUNSPEC: dict = {
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

AO_DEV_V1_RUNSPEC: dict = {
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
        ]
    },
}

BAD_RUNSPEC: dict = {
    "schema": "ao-operator/runspec/v1",
    "slug": "bug-fix",
    "roles": [
        {"id": "implementer"},
        {"id": "ghost-role"},
    ],
}


def _write_runspec(tmp_path: Path, name: str, value: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    return path


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


# ---------------------------------------------------------------------------
# Mapping-only mode (default). The bridge MUST produce evidence without
# requiring an ao2 binary on the host.
# ---------------------------------------------------------------------------


def test_default_dry_run_writes_evidence_for_factory_v3_runspec(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    result = _run(["--runspec", str(runspec_path), "--out", str(out_path)])
    assert result.returncode == 0, result.stderr
    assert out_path.is_file()
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == bridge.SCHEMA
    assert evidence["action"] == bridge.ACTION
    assert evidence["status"] == "mapping_resolved_dry_run"
    assert evidence["input_runspec"]["path"] == str(runspec_path)
    assert evidence["mapping"]["digest"] == mapping.mapping_digest()
    assert [r["canonical_role"] for r in evidence["resolved_roles"]] == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator_closer",
    ]
    assert evidence["unknown_roles"] == []
    assert "ao2_invocation" not in evidence


def test_default_dry_run_handles_ao_dev_v1_runspec(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "smoke.yaml", AO_DEV_V1_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    result = _run(["--runspec", str(runspec_path), "--out", str(out_path)])
    assert result.returncode == 0, result.stderr
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "mapping_resolved_dry_run"
    assert evidence["input_runspec"]["schema"] == "ao.dev/v1"
    assert evidence["input_runspec"]["name"] == "ao-operator-smoke"
    canonicals = [r["canonical_role"] for r in evidence["resolved_roles"]]
    assert canonicals == [
        "intake",
        "plan_hardener",
        "factory_manager",
        "implementer",
        "reviewer",
        "integrator",
        "evaluator_closer",
    ]


# ---------------------------------------------------------------------------
# Failure: unknown roles must block before any ao2 invocation.
# ---------------------------------------------------------------------------


def test_unknown_role_blocks_with_nonzero_exit_and_records_unknown(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "bad.yaml", BAD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    result = _run(
        ["--runspec", str(runspec_path), "--out", str(out_path), "--invoke-ao2"]
    )
    assert result.returncode == 1, result.stderr
    assert out_path.is_file()
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "blocked_unknown_roles"
    assert evidence["unknown_roles"] == ["ghost-role"]
    # Critically, ao2 must NOT have been invoked when a role is unmapped.
    assert "ao2_invocation" not in evidence


# ---------------------------------------------------------------------------
# Determinism: two runs on the same input produce identical evidence
# bodies modulo timestamp and runspec_path differences.
# ---------------------------------------------------------------------------


def test_evidence_is_deterministic_modulo_timestamp(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    assert _run(["--runspec", str(runspec_path), "--out", str(out_a)]).returncode == 0
    assert _run(["--runspec", str(runspec_path), "--out", str(out_b)]).returncode == 0
    payload_a = json.loads(out_a.read_text(encoding="utf-8"))
    payload_b = json.loads(out_b.read_text(encoding="utf-8"))
    for body in (payload_a, payload_b):
        body.pop("generated_at", None)
    assert payload_a == payload_b


# ---------------------------------------------------------------------------
# Trust boundary: AO2 keeps closure ownership of every resolved role.
# ---------------------------------------------------------------------------


def test_every_resolved_role_records_ao2_native_closure_owner(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    _run(["--runspec", str(runspec_path), "--out", str(out_path)])
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    for resolved in evidence["resolved_roles"]:
        assert resolved["closure_owner"] == "ao2_native_evaluator_closer"


# ---------------------------------------------------------------------------
# Secret hygiene: env-var values that look like tokens MUST NOT appear in the
# evidence body. The bridge only records which env keys were present, not the
# values. ARGV with `KEY=value` token shapes must be redacted as well.
# ---------------------------------------------------------------------------


def test_env_token_values_never_appear_in_evidence(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    env = dict(os.environ)
    env["FAKE_PROVIDER_API_KEY"] = "shibboleth-do-not-leak"
    env["FAKE_OAUTH_TOKEN"] = "another-shibboleth"
    env["UNRELATED_CONFIG"] = "this-value-is-not-a-secret"
    result = _run(["--runspec", str(runspec_path), "--out", str(out_path)], env=env)
    assert result.returncode == 0, result.stderr
    body = out_path.read_text(encoding="utf-8")
    assert "shibboleth-do-not-leak" not in body
    assert "another-shibboleth" not in body
    evidence = json.loads(body)
    assert "FAKE_PROVIDER_API_KEY" in evidence["redacted_env_keys_observed"]
    assert "FAKE_OAUTH_TOKEN" in evidence["redacted_env_keys_observed"]
    assert "UNRELATED_CONFIG" not in evidence["redacted_env_keys_observed"]


def test_safe_argv_redacts_token_shaped_args():
    argv = [
        "ao2",
        "factory",
        "plan",
        "--token=AKIA1234567890",
        "--harmless",
        "value",
    ]
    safe = bridge._safe_argv(argv)
    assert "AKIA1234567890" not in " ".join(safe)
    assert "<redacted>" in safe


# ---------------------------------------------------------------------------
# Mapping digest pin: the digest the bridge records MUST equal the standalone
# CLI digest. If they diverge, evidence collected by the bridge will not
# reconcile against the mapping module's own self-report. This protects the
# "deterministic mapping recorded in evidence" exit-gate requirement.
# ---------------------------------------------------------------------------


def test_bridge_mapping_digest_matches_standalone_cli_digest(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    _run(["--runspec", str(runspec_path), "--out", str(out_path)])
    evidence = json.loads(out_path.read_text(encoding="utf-8"))

    standalone = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "ao_operator_ao2_provider_contract.py"),
            "digest",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert standalone.returncode == 0, standalone.stderr
    assert evidence["mapping"]["digest"] == standalone.stdout.strip()


# ---------------------------------------------------------------------------
# Optional: real AO2 invocation. Only runs when an ao2 binary is reachable.
# Skipped on hosts without ao2 so the suite stays green on Mac dev boxes
# that haven't built the AO2 release binary yet.
# ---------------------------------------------------------------------------


def _ao2_binary_available() -> bool:
    candidate = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    if candidate.is_file():
        return True
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    return debug.is_file()


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_invoke_ao2_records_ao2_response_in_evidence(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    out_path = tmp_path / "bridge-evidence.json"
    plan_out = tmp_path / "ao2-plan.json"
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    ao2_bin = str(release if release.is_file() else debug)
    result = _run(
        [
            "--runspec",
            str(runspec_path),
            "--out",
            str(out_path),
            "--invoke-ao2",
            "--ao2-bin",
            ao2_bin,
            "--ao2-target",
            str(tmp_path),
            "--ao2-plan-out",
            str(plan_out),
        ]
    )
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    # AO2 may legitimately fail this call (the example RunSpec is not a real
    # factory plan-request), but the bridge MUST have actually invoked it and
    # recorded the ao2 exit code in evidence so reviewers see the boundary.
    assert "ao2_invocation" in evidence
    assert evidence["ao2_invocation"]["exit_code"] is not None
    assert evidence["status"] in {"ao2_plan_started", "ao2_plan_failed"}
    assert result.returncode in {0, 1}


# ---------------------------------------------------------------------------
# AO2-native passthrough mode: validate + re-emit a pre-built
# `ao2.factory-bridge.v1` evidence file produced by `ao2 factory bridge`.
# Mirrors the cancel-authority producer's --ao2-native-attestation contract
# (Phase 2 exit-gate item #1/#2, AO2 as canonical evidence owner).
# ---------------------------------------------------------------------------


def _well_formed_ao2_native_payload(*, override: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "ao2.factory-bridge.v1",
        "action": "factory-bridge",
        "generated_at": "2026-05-25T00:00:00Z",
        "produced_at_ms": 1700000000000,
        "status": "mapping_resolved_dry_run",
        "trust_boundary": {
            "ao2_role": "ao2_native_bridge_evidence_owner",
            "bridge_owner": "ao2_factory_bridge_subcommand",
            "control_plane_role": "read_only_observer_after_signed_evidence",
            "factory_v3_role": "parity_oracle_only",
        },
        "input_runspec": {
            "name": "bug-fix",
            "path": "/tmp/runspec.yaml",
            "schema": "ao-operator/runspec/v1",
            "sha256": "0" * 64,
        },
        "mapping": {
            "schema": mapping.SCHEMA,
            "version": mapping.MAPPING_VERSION,
            "digest": mapping.mapping_digest(),
        },
        "resolved_roles": [
            {
                "ao2_provider_contract_slug": "ao2.provider-contract.implementer.v1",
                "canonical_role": "implementer",
                "closure_owner": "ao2_native_evaluator_closer",
                "evidence_obligation": "implementation_digest_patch_and_test_evidence",
                "role_id": "implementer",
                "sandbox": "scoped_write_with_digest_patch_and_repair_budget",
            },
        ],
        "unknown_roles": [],
        "redacted_env_keys_observed": [],
    }
    if override:
        payload.update(override)
    return payload


def _write_native_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "ao2-bridge-evidence.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_passthrough_accepts_valid_ao2_native_bridge_evidence(tmp_path: Path):
    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    # Synthetic payload has no AO2 signature; pass the escape valve since
    # this test is asserting structural validation + passthrough envelope
    # shape, not signing semantics. End-to-end signed verification is
    # exercised in test_verify_bridge_evidence_records_verdict_when_signed.
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == bridge.SCHEMA
    assert evidence["action"] == bridge.ACTION
    assert evidence["status"] == "passthrough_ao2_native"
    assert evidence["ao2_native_bridge_evidence"]["schema"] == "ao2.factory-bridge.v1"
    assert evidence["ao2_native_bridge_evidence_path"] == str(native_path)
    assert len(evidence["ao2_native_bridge_evidence_sha256"]) == 64
    assert evidence["mapping"]["digest"] == mapping.mapping_digest()
    # The Python wrapper credits AO2 as canonical owner, never claims to be it.
    assert evidence["trust_boundary"]["ao2_role"] == "ao2_native_bridge_evidence_owner"
    assert evidence["trust_boundary"]["passthrough_owner"] == (
        "factory_v3_start_ao2_run_from_role_runspec"
    )
    # Default text mode summary is on stderr-equivalent (stdout) -- spot-check key=value lines.
    assert "status=passthrough_ao2_native" in result.stdout
    assert f"mapping_digest={mapping.mapping_digest()}" in result.stdout
    assert "ao2_native_bridge_evidence_sha256=" in result.stdout


def test_passthrough_refuses_wrong_schema(tmp_path: Path):
    native_path = _write_native_payload(
        tmp_path, _well_formed_ao2_native_payload(override={"schema": "ao2.other.v1"})
    )
    out_path = tmp_path / "ao-operator-evidence.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
        ]
    )
    assert result.returncode == 2
    assert "schema must be 'ao2.factory-bridge.v1'" in result.stderr
    assert not out_path.exists()


def test_passthrough_refuses_wrong_action(tmp_path: Path):
    native_path = _write_native_payload(
        tmp_path, _well_formed_ao2_native_payload(override={"action": "other-thing"})
    )
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "action must be 'factory-bridge'" in result.stderr


def test_passthrough_refuses_wrong_status(tmp_path: Path):
    native_path = _write_native_payload(
        tmp_path, _well_formed_ao2_native_payload(override={"status": "blocked_unknown_roles"})
    )
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "status must be one of" in result.stderr


def test_passthrough_refuses_wrong_trust_boundary(tmp_path: Path):
    bad_payload = _well_formed_ao2_native_payload()
    bad_payload["trust_boundary"]["factory_v3_role"] = "primary_owner"
    native_path = _write_native_payload(tmp_path, bad_payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "trust_boundary['factory_v3_role']" in result.stderr


def test_passthrough_refuses_mismatched_mapping_digest(tmp_path: Path):
    bad_payload = _well_formed_ao2_native_payload()
    bad_payload["mapping"]["digest"] = "0" * 64
    native_path = _write_native_payload(tmp_path, bad_payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "mapping.digest does not match" in result.stderr
    assert mapping.mapping_digest() in result.stderr


def test_passthrough_refuses_unknown_roles_present(tmp_path: Path):
    bad_payload = _well_formed_ao2_native_payload()
    bad_payload["unknown_roles"] = ["ghost-role"]
    native_path = _write_native_payload(tmp_path, bad_payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "unknown_roles must be empty" in result.stderr


def test_passthrough_refuses_missing_input(tmp_path: Path):
    missing_path = tmp_path / "does-not-exist.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(missing_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "input not found" in result.stderr


def test_passthrough_refuses_non_json_input(tmp_path: Path):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("not json at all", encoding="utf-8")
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(bad_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def _role_contracts_block(*, loaded_count: int = 2, missing_roles: list[str] | None = None) -> dict[str, Any]:
    return {
        "owner": "ao2",
        "path": "/tmp/agents",
        "factory_v3_required_to_load": False,
        "loaded_count": loaded_count,
        "missing_roles": list(missing_roles or []),
    }


def test_passthrough_surfaces_role_contracts_summary_when_present(tmp_path: Path):
    payload = _well_formed_ao2_native_payload()
    payload["role_contracts"] = _role_contracts_block(
        loaded_count=2,
        missing_roles=["planner", "factory_manager"],
    )
    native_path = _write_native_payload(tmp_path, payload)
    out_path = tmp_path / "ao-operator-evidence.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    summary = evidence["role_contracts_summary"]
    assert summary["owner"] == "ao2"
    assert summary["loaded_count"] == 2
    assert summary["missing_role_count"] == 2
    assert summary["factory_v3_required_to_load"] is False
    # Native body retained verbatim so observers can re-derive details.
    assert evidence["ao2_native_bridge_evidence"]["role_contracts"]["loaded_count"] == 2
    # Text summary surfaces the load counts so watchdog stdout parsers see them.
    assert "role_contracts_owner=ao2" in result.stdout
    assert "role_contracts_loaded_count=2" in result.stdout
    assert "role_contracts_missing_role_count=2" in result.stdout


def test_passthrough_omits_role_contracts_summary_when_absent(tmp_path: Path):
    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert "role_contracts_summary" not in evidence
    assert "role_contracts_owner=" not in result.stdout


def test_passthrough_refuses_role_contracts_with_wrong_owner(tmp_path: Path):
    payload = _well_formed_ao2_native_payload()
    payload["role_contracts"] = _role_contracts_block()
    payload["role_contracts"]["owner"] = "factory_v3"
    native_path = _write_native_payload(tmp_path, payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 2
    assert "role_contracts.owner must be 'ao2'" in result.stderr


def test_passthrough_refuses_role_contracts_with_factory_v3_required_true(tmp_path: Path):
    payload = _well_formed_ao2_native_payload()
    payload["role_contracts"] = _role_contracts_block()
    payload["role_contracts"]["factory_v3_required_to_load"] = True
    native_path = _write_native_payload(tmp_path, payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 2
    assert "factory_v3_required_to_load" in result.stderr


def test_passthrough_refuses_role_contracts_with_bad_loaded_count(tmp_path: Path):
    payload = _well_formed_ao2_native_payload()
    payload["role_contracts"] = _role_contracts_block()
    payload["role_contracts"]["loaded_count"] = -1
    native_path = _write_native_payload(tmp_path, payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 2
    assert "role_contracts.loaded_count" in result.stderr


def test_passthrough_refuses_role_contracts_with_non_string_missing_roles(tmp_path: Path):
    payload = _well_formed_ao2_native_payload()
    payload["role_contracts"] = _role_contracts_block()
    payload["role_contracts"]["missing_roles"] = ["planner", 7]
    native_path = _write_native_payload(tmp_path, payload)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 2
    assert "role_contracts.missing_roles" in result.stderr


def test_runspec_and_native_evidence_are_mutually_exclusive(tmp_path: Path):
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    result = _run(
        [
            "--runspec",
            str(runspec_path),
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr.lower() or "mutually exclusive" in (
        result.stderr.lower()
    )


def test_either_runspec_or_native_evidence_is_required(tmp_path: Path):
    result = _run(["--out", str(tmp_path / "out.json")])
    assert result.returncode != 0
    assert "one of" in result.stderr.lower() or "required" in result.stderr.lower()


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_passthrough_accepts_real_ao2_native_evidence_produced_by_bridge(tmp_path: Path):
    """End-to-end: run `ao2 factory bridge` then pipe its evidence through
    ao-operator's passthrough mode. Confirms the cross-language contract."""

    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    native_out = tmp_path / "ao2-native-bridge-evidence.json"
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    ao2_bin = str(release if release.is_file() else debug)
    produce = subprocess.run(
        [
            ao2_bin,
            "factory",
            "bridge",
            "--runspec",
            str(runspec_path),
            "--out",
            str(native_out),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert produce.returncode == 0, produce.stderr
    assert native_out.is_file()

    factory_v3_out = tmp_path / "ao-operator-evidence.json"
    # The `ao2 factory bridge` invocation above was not given --signing-key,
    # so the AO2-native bridge evidence is unsigned and the default-on AO2
    # verifier shell-out would reject it. This test asserts the
    # cross-language schema contract, not signing; opt out via the escape
    # valve. End-to-end signed verification is exercised in
    # test_verify_bridge_evidence_records_verdict_when_signed.
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_out),
            "--out",
            str(factory_v3_out),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(factory_v3_out.read_text(encoding="utf-8"))
    assert evidence["status"] == "passthrough_ao2_native"
    assert evidence["mapping"]["digest"] == mapping.mapping_digest()
    assert evidence["ao2_native_bridge_evidence"]["status"] == "mapping_resolved_dry_run"
    native_canonicals = [
        role["canonical_role"]
        for role in evidence["ao2_native_bridge_evidence"]["resolved_roles"]
    ]
    assert native_canonicals == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator_closer",
    ]


# ---------------------------------------------------------------------------
# Slice 9/12: AO2-owned bridge-evidence verifier shell-out.
#
# Slice 9 introduced opt-in `--verify-bridge-evidence`. Slice 12 flipped the
# default so passthrough mode shells out to the AO2 verifier by default.
# `--allow-unverified-bridge-evidence` is the explicit opt-out for legacy
# callers that pass synthetic or intentionally-unsigned payloads. The legacy
# `--verify-bridge-evidence` flag is preserved as a hidden no-op so existing
# scripts that pass it continue to parse cleanly.
# ---------------------------------------------------------------------------


def test_allow_unverified_bridge_evidence_preserves_legacy_behavior(tmp_path: Path):
    """The escape valve must skip the AO2 verifier shell-out entirely and
    produce an envelope without a verification block, mirroring the
    pre-default-on behavior so callers that need to pass synthetic payloads
    (unit tests, replay) can still produce envelopes without an ao2 binary
    on PATH.
    """

    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--allow-unverified-bridge-evidence",
        ]
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(out_path.read_text(encoding="utf-8"))
    assert "ao2_native_bridge_evidence_verification" not in evidence
    assert (
        "ao2_native_bridge_evidence_verification_status=" not in result.stdout
    )


def test_verify_bridge_evidence_required_by_default_fails_closed_when_ao2_binary_missing(
    tmp_path: Path,
):
    """Under default-on (no flag), passthrough mode must shell out to the
    AO2 verifier and fail closed if the ao2 binary cannot be located. No
    skipif: a bogus `--ao2-bin` path exercises the FileNotFoundError branch
    on every host.
    """

    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    bogus_bin = tmp_path / "definitely-not-an-ao2-binary"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--ao2-bin",
            str(bogus_bin),
        ]
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "requires the `ao2` binary" in result.stderr
    assert not out_path.exists()


def test_legacy_verify_bridge_evidence_flag_remains_accepted_as_no_op(
    tmp_path: Path,
):
    """The pre-slice-12 `--verify-bridge-evidence` flag is now redundant
    (signing is required by default) but must still parse cleanly so any
    existing scripts that pass it continue to work. With a bogus
    `--ao2-bin` path the behavior is identical to default-on: fail closed
    with the standard "requires the `ao2` binary" message.
    """

    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    bogus_bin = tmp_path / "definitely-not-an-ao2-binary"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--ao2-bin",
            str(bogus_bin),
            "--verify-bridge-evidence",
        ]
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "requires the `ao2` binary" in result.stderr
    assert not out_path.exists()


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_verify_bridge_evidence_fails_closed_when_native_payload_unsigned(
    tmp_path: Path,
):
    """Synthetic well-formed payload has no signature block; the AO2
    verifier must reject it and ao-operator must surface that failure as a
    closed exit code (2) with a clear stderr message.
    """

    native_path = _write_native_payload(tmp_path, _well_formed_ao2_native_payload())
    out_path = tmp_path / "ao-operator-evidence.json"
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    ao2_bin = str(release if release.is_file() else debug)
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_path),
            "--out",
            str(out_path),
            "--ao2-bin",
            ao2_bin,
            "--verify-bridge-evidence",
        ]
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "rejected" in result.stderr or "rejected" in result.stdout
    assert not out_path.exists()


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_verify_bridge_evidence_records_verdict_when_signed(tmp_path: Path):
    """End-to-end happy path: ao2 factory bridge --signing-key produces a
    signed payload + sidecars, ao-operator passthrough with
    --verify-bridge-evidence shells out to ao2 factory verify-bridge-evidence,
    accepts the verdict, and records it in the envelope.
    """

    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    ao2_bin = str(release if release.is_file() else debug)

    # Generate a fresh signing key via `ao2 workbench support-keygen`.
    key_path = tmp_path / "bridge-signing-key.pem"
    keygen = subprocess.run(
        [
            ao2_bin,
            "workbench",
            "support-keygen",
            "--out",
            str(key_path),
            "--bits",
            "2048",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert keygen.returncode == 0, keygen.stderr
    assert key_path.is_file()

    # Produce a signed AO2-native bridge evidence file.
    runspec_path = _write_runspec(tmp_path, "runspec.yaml", GOOD_RUNSPEC)
    native_out = tmp_path / "ao2-native-bridge-evidence.json"
    produce = subprocess.run(
        [
            ao2_bin,
            "factory",
            "bridge",
            "--runspec",
            str(runspec_path),
            "--out",
            str(native_out),
            "--signing-key",
            str(key_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert produce.returncode == 0, produce.stderr
    assert native_out.is_file()
    # Sidecars from slice 3 must be present on disk for the verifier.
    assert (
        native_out.with_suffix(".signed-payload.json").is_file()
        or Path(str(native_out) + ".signed-payload.json").is_file()
    )

    # Run ao-operator passthrough with the opt-in verify flag.
    factory_v3_out = tmp_path / "ao-operator-evidence.json"
    result = _run(
        [
            "--ao2-native-bridge-evidence",
            str(native_out),
            "--out",
            str(factory_v3_out),
            "--ao2-bin",
            ao2_bin,
            "--verify-bridge-evidence",
        ]
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    evidence = json.loads(factory_v3_out.read_text(encoding="utf-8"))
    assert "ao2_native_bridge_evidence_verification" in evidence
    verification = evidence["ao2_native_bridge_evidence_verification"]
    assert (
        verification["schema_version"]
        == "ao2.factory-bridge-evidence-verification.v1"
    )
    assert verification["status"] == "accepted"
    assert verification["signature_verified"] is True
    # Default text mode prints the verification status as a key=value line.
    assert (
        "ao2_native_bridge_evidence_verification_status=accepted" in result.stdout
    )
