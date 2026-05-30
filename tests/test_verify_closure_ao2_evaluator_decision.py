"""Phase 2 exit-gate #4: verify_closure consults the AO2 native verifier verdict.

These tests cover the new ``verify_closure.ao2_evaluator_decision_evidence``
function plus its integration through ``verify_closure.run()``. They use a
fake ao2 binary written into ``tmp_path`` so the tests do not depend on a
real Rust build.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_closure  # noqa: E402


DECISION_SCHEMA = verify_closure.AO2_NATIVE_EVALUATOR_DECISION_SCHEMA
VERIFICATION_SCHEMA = verify_closure.AO2_NATIVE_EVALUATOR_VERIFICATION_SCHEMA
VERIFICATION_OWNER = verify_closure.AO2_NATIVE_EVALUATOR_VERIFICATION_OWNER
FACTORY_V3_ROLE = verify_closure.AO2_NATIVE_EVALUATOR_FACTORY_V3_ROLE


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_decision(repo: Path, relative: str = "run-artifacts/demo/ao2-native-evaluator-decision.json") -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": DECISION_SCHEMA,
                "native_evaluator_decision": {
                    "schema_version": "ao2.native-evaluator-decision.v1",
                    "verdict": "accepted",
                },
                "trust_boundary": {
                    "decision_owner": "ao2",
                    "factory_v3_role": "parity_oracle_only",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _accepted_verification() -> dict:
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "status": "accepted",
        "signature_status": "signed",
        "signature_verified": True,
        "signature_digest_match": True,
        "public_key_digest_match": True,
        "signed_payload_digest_match": True,
        "decision_payload_matches_signed_payload": True,
        "signature_requirement_satisfied": True,
        "trust_boundary_ok": True,
        "factory_v3_role": FACTORY_V3_ROLE,
        "ao2_decision_owner": VERIFICATION_OWNER,
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "verdict": {"status": "accepted"},
    }


def _write_fake_ao2(path: Path, stdout: str, exit_code: int = 0) -> Path:
    script = f"#!/usr/bin/env bash\nprintf '%s' {stdout!r}\nexit {exit_code}\n"
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_discovery_excludes_signed_payload_sidecar(tmp_path: Path):
    decision_dir = tmp_path / "run-artifacts" / "demo"
    decision_dir.mkdir(parents=True)
    decision = decision_dir / "release-ao2-native-evaluator-decision.json"
    sidecar = decision_dir / "release-ao2-native-evaluator-decision.signed-payload.json"
    decision.write_text("{}", encoding="utf-8")
    sidecar.write_text("{}", encoding="utf-8")

    found = verify_closure._discover_ao2_native_evaluator_decisions(tmp_path)

    assert decision.resolve() in found
    assert sidecar.resolve() not in found
    assert all(not str(path).endswith(".signed-payload.json") for path in found)


def test_discovery_matches_release_prefixed_decision(tmp_path: Path):
    decision_dir = tmp_path / "run-artifacts" / "nightly-ao2"
    decision_dir.mkdir(parents=True)
    decision = decision_dir / "release-ao2-native-evaluator-decision.json"
    decision.write_text("{}", encoding="utf-8")

    found = verify_closure._discover_ao2_native_evaluator_decisions(tmp_path)

    assert decision.resolve() in found


def test_discovery_matches_plain_ao2_native_evaluator_decision(tmp_path: Path):
    decision = _write_decision(tmp_path)

    found = verify_closure._discover_ao2_native_evaluator_decisions(tmp_path)

    assert decision.resolve() in found


# ---------------------------------------------------------------------------
# _check_ao2_native_evaluator_verification
# ---------------------------------------------------------------------------


def test_check_verification_accepts_fully_clean_payload():
    assert verify_closure._check_ao2_native_evaluator_verification(_accepted_verification()) == []


@pytest.mark.parametrize(
    "field,bad_value,expected_fragment",
    [
        ("schema_version", "wrong.schema.v1", "schema_version must be"),
        ("status", "rejected", "status must be 'accepted'"),
        ("signature_status", "unsigned", "signature_status must be 'signed'"),
        ("signature_verified", False, "signature_verified must be true"),
        ("trust_boundary_ok", False, "trust_boundary_ok must be true"),
        ("decision_payload_matches_signed_payload", False, "decision_payload_matches_signed_payload must be true"),
        ("ao2_decision_owner", "someone_else", "ao2_decision_owner must be"),
        ("factory_v3_role", "decision_owner", "factory_v3_role must be"),
    ],
)
def test_check_verification_flags_each_bad_field(field: str, bad_value, expected_fragment: str):
    payload = _accepted_verification()
    payload[field] = bad_value
    details = verify_closure._check_ao2_native_evaluator_verification(payload)
    assert any(expected_fragment in detail for detail in details), details


def test_check_verification_rejects_non_dict_payload():
    assert verify_closure._check_ao2_native_evaluator_verification(["not-a-dict"]) == [
        "AO2 verifier returned a non-object JSON value"
    ]


# ---------------------------------------------------------------------------
# ao2_evaluator_decision_evidence
# ---------------------------------------------------------------------------


def test_no_decisions_and_not_required_returns_pass(tmp_path: Path):
    result = verify_closure.ao2_evaluator_decision_evidence(tmp_path, require=False)
    assert result["verdict"] == "PASS"
    assert result["decision_count"] == 0
    assert result["details"] == []


def test_no_decisions_but_required_returns_fail(tmp_path: Path):
    result = verify_closure.ao2_evaluator_decision_evidence(tmp_path, require=True)
    assert result["verdict"] == "FAIL"
    assert result["decision_count"] == 0
    assert result["details"] == ["required AO2 native evaluator decision was not found"]


def test_decision_present_but_not_required_returns_pass_without_invoking_binary(tmp_path: Path):
    _write_decision(tmp_path)
    # ao2_binary is intentionally bogus — the function must not run it when
    # the check is not opt-in.
    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=False, ao2_binary="/does/not/exist/ao2"
    )
    assert result["verdict"] == "PASS"
    assert result["decision_count"] == 1
    assert result["details"] == []


def test_decision_required_and_verifier_accepts(tmp_path: Path):
    _write_decision(tmp_path)
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(_accepted_verification()))

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "PASS", result
    assert result["decision_count"] == 1
    assert result["details"] == []
    assert result["reports"][0]["verdict"] == "PASS"
    assert result["reports"][0]["verification_status"] == "accepted"
    assert result["ao2_binary_resolved"] == str(fake_ao2)


def test_decision_required_and_verifier_rejects_signature(tmp_path: Path):
    _write_decision(tmp_path)
    rejected = _accepted_verification()
    rejected["status"] = "rejected"
    rejected["signature_status"] = "unsigned"
    rejected["signature_verified"] = False
    rejected["signature_requirement_satisfied"] = False
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(rejected))

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "FAIL"
    assert any("status must be 'accepted'" in detail for detail in result["details"])
    assert any("signature_status must be 'signed'" in detail for detail in result["details"])
    assert any("signature_verified must be true" in detail for detail in result["details"])


def test_decision_required_but_decision_schema_wrong(tmp_path: Path):
    decision_dir = tmp_path / "run-artifacts" / "demo"
    decision_dir.mkdir(parents=True)
    (decision_dir / "ao2-native-evaluator-decision.json").write_text(
        json.dumps({"schema_version": "wrong.schema.v1"}),
        encoding="utf-8",
    )
    # The fake binary will not be called because the decision schema check fires first.
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(_accepted_verification()))

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "FAIL"
    assert any(
        "schema_version must be" in detail and DECISION_SCHEMA in detail
        for detail in result["details"]
    )


def test_decision_required_but_verifier_exits_nonzero(tmp_path: Path):
    _write_decision(tmp_path)
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", "verifier exploded", exit_code=2)

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "FAIL"
    assert any("ao2 factory verify-evaluator-decision exited 2" in detail for detail in result["details"])


def test_decision_required_but_verifier_returns_invalid_json(tmp_path: Path):
    _write_decision(tmp_path)
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", "not json {")

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "FAIL"
    assert any("returned invalid JSON" in detail for detail in result["details"])


def test_decision_required_but_ao2_binary_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_decision(tmp_path)
    # Strip every locator the discover routine inspects.
    monkeypatch.delenv("AO2_BINARY", raising=False)
    monkeypatch.delenv("AO2_BIN", raising=False)
    monkeypatch.setenv("PATH", "")

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=None
    )

    assert result["verdict"] == "FAIL"
    assert any("ao2 binary not found" in detail for detail in result["details"])
    assert result["ao2_binary_resolved"] is None


def test_multiple_decisions_each_verified(tmp_path: Path):
    _write_decision(
        tmp_path, "run-artifacts/run-a/ao2-native-evaluator-decision.json"
    )
    _write_decision(
        tmp_path, "run-artifacts/run-b/release-ao2-native-evaluator-decision.json"
    )
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(_accepted_verification()))

    result = verify_closure.ao2_evaluator_decision_evidence(
        tmp_path, require=True, ao2_binary=str(fake_ao2)
    )

    assert result["verdict"] == "PASS", result
    assert result["decision_count"] == 2
    assert len(result["reports"]) == 2
    assert all(report["verdict"] == "PASS" for report in result["reports"])


# ---------------------------------------------------------------------------
# _find_ao2_binary
# ---------------------------------------------------------------------------


def test_find_ao2_binary_prefers_AO2_BINARY_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "explicit-ao2"
    fake.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("AO2_BINARY", str(fake))
    monkeypatch.delenv("AO2_BIN", raising=False)
    assert verify_closure._find_ao2_binary(tmp_path) == str(fake)


def test_find_ao2_binary_falls_back_to_sibling_release_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "ao-operator"
    repo.mkdir()
    sibling_ao2 = tmp_path / "ao2" / "target" / "release"
    sibling_ao2.mkdir(parents=True)
    binary = sibling_ao2 / "ao2"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.delenv("AO2_BINARY", raising=False)
    monkeypatch.delenv("AO2_BIN", raising=False)
    monkeypatch.setenv("PATH", "")  # rule out shutil.which fallback
    assert verify_closure._find_ao2_binary(repo) == str(binary)


# ---------------------------------------------------------------------------
# integration through run()
# ---------------------------------------------------------------------------


def test_run_integration_fails_when_decision_required_and_verifier_rejects(tmp_path: Path):
    _write_decision(tmp_path)
    rejected = _accepted_verification()
    rejected["status"] = "rejected"
    rejected["trust_boundary_ok"] = False
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(rejected))

    result = verify_closure.run(
        tmp_path,
        include_pytest=False,
        timeout=10,
        dry_run=False,
        extra=[],
        require_ao2_evaluator_decision=True,
        ao2_binary=str(fake_ao2),
    )

    assert result["verdict"] == "FAIL", result
    assert "ao2_evaluator_decision_evidence" in result
    assert result["ao2_evaluator_decision_evidence"]["verdict"] == "FAIL"
    assert any("trust_boundary_ok must be true" in err for err in result["errors"])


def test_run_integration_passes_when_decision_required_and_verifier_accepts(tmp_path: Path):
    # Make the closure commands list non-empty so the result is not WARN.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / "skills.toml").write_text("[globals]\n", encoding="utf-8")
    (scripts / "validate.py").write_text("print('ok')\n", encoding="utf-8")
    _write_decision(tmp_path)
    fake_ao2 = _write_fake_ao2(tmp_path / "ao2", json.dumps(_accepted_verification()))

    result = verify_closure.run(
        tmp_path,
        include_pytest=False,
        timeout=10,
        dry_run=False,
        extra=[],
        require_ao2_evaluator_decision=True,
        ao2_binary=str(fake_ao2),
    )

    assert result["verdict"] == "PASS", result
    assert result["ao2_evaluator_decision_evidence"]["verdict"] == "PASS"
    assert result["ao2_evaluator_decision_evidence"]["decision_count"] == 1


def test_run_integration_default_behavior_unchanged_when_check_not_required(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / "skills.toml").write_text("[globals]\n", encoding="utf-8")
    (scripts / "validate.py").write_text("print('ok')\n", encoding="utf-8")
    # A decision is present but require_ao2_evaluator_decision is False
    # (default). Closure must not fail just because the decision exists, even
    # if there is no ao2 binary anywhere — pre-existing closures must stay
    # green.
    _write_decision(tmp_path)

    result = verify_closure.run(
        tmp_path,
        include_pytest=False,
        timeout=10,
        dry_run=False,
        extra=[],
    )

    assert result["verdict"] == "PASS", result
    assert result["ao2_evaluator_decision_evidence"]["verdict"] == "PASS"


def test_self_test_passes_with_new_required_check():
    # The script's self_test() must keep returning 0 after the new
    # require-AO2-evaluator-decision branch was added.
    assert verify_closure.self_test() == 0
