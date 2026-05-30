from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_evaluator_closure_with_ao2_verification.py"

FACTORY_DECISION_SCHEMA = "ao-operator/ao2-release-evaluator-decision/v1"
AO2_VERIFICATION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-verification.v1"
CLOSURE_SCHEMA = "ao-operator/ao2-release-evaluator-closure-with-ao2-verification/v1"


def factory_decision(
    *,
    status: str = "accepted",
    decision: str = "accept_phase1_release_candidate",
    blockers: list[str] | None = None,
) -> dict:
    return {
        "schema": FACTORY_DECISION_SCHEMA,
        "status": status,
        "decision": decision,
        "release": {"version": "0.4.79", "release_tag": "v0.4.79"},
        "checks": [
            {
                "id": "readiness_status",
                "label": "Readiness status",
                "status": "ok",
                "observed": "ready",
                "expected": "ready",
            }
        ],
        "blockers": blockers or [],
        "self_reference_exception": {
            "status": "not_applicable",
            "reason": "no evaluator self-reference gap was detected",
        },
        "evidence": {
            "release_readiness_status": "/tmp/readiness.json",
            "release_handoff_checklist": "/tmp/checklist.json",
            "release_support_bundle_status": "/tmp/support.json",
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
        "next_action": (
            "release candidate is accepted by ao-operator evaluator-closer for release-line handoff"
            if status == "accepted"
            else "resolve blockers before release-line handoff"
        ),
    }


def ao2_verification(
    *,
    status: str = "accepted",
    signature_status: str = "signed",
    signature_verified: bool = True,
    trust_boundary_ok: bool = True,
    verdict: dict | None = None,
) -> dict:
    return {
        "schema_version": AO2_VERIFICATION_SCHEMA,
        "status": status,
        "decision_path": "/tmp/ao2-native-evaluator-decision.json",
        "signed_payload_path": "/tmp/ao2-native-evaluator-payload.json",
        "signed_payload": "native_evaluator_decision_without_signature_field",
        "signed_payload_digest_match": signature_verified,
        "decision_payload_matches_signed_payload": signature_verified,
        "signature_status": signature_status,
        "signature_digest_match": signature_verified,
        "public_key_digest_match": signature_verified,
        "signature_verified": signature_verified,
        "signature_requirement_satisfied": signature_status == "signed" and signature_verified,
        "trust_boundary_ok": trust_boundary_ok,
        "verdict": verdict or {"status": "accepted", "owner": "ao2-native-evaluator-closer"},
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-evaluator-decision-verifier",
        "control_plane_role": "read_only_observer_after_signed_evidence",
    }


def run_closure(
    tmp_path: Path,
    factory: dict,
    verification: dict,
    *,
    expect_returncode: int = 0,
) -> tuple[dict | None, str | None, subprocess.CompletedProcess[str]]:
    factory_path = tmp_path / "factory-decision.json"
    verification_path = tmp_path / "ao2-verification.json"
    json_path = tmp_path / "closure.json"
    md_path = tmp_path / "closure.md"
    factory_path.write_text(json.dumps(factory), encoding="utf-8")
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-decision",
            str(factory_path),
            "--ao2-verification",
            str(verification_path),
            "--write-json",
            str(json_path),
            "--write-md",
            str(md_path),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, None, result
    payload = json.loads(result.stdout)
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    return payload, md_path.read_text(encoding="utf-8"), result


def test_closure_accepts_when_factory_accepted_and_ao2_accepted(tmp_path: Path) -> None:
    payload, markdown, _ = run_closure(tmp_path, factory_decision(), ao2_verification())
    assert payload is not None and markdown is not None
    assert payload["schema"] == CLOSURE_SCHEMA
    assert payload["status"] == "accepted"
    assert payload["decision"] == "accept_release_closure"
    assert payload["blockers"] == []
    assert payload["factory_v3_decision"]["status"] == "accepted"
    assert payload["factory_v3_decision"]["decision"] == "accept_phase1_release_candidate"
    assert payload["ao2_verification"]["status"] == "accepted"
    assert payload["ao2_verification"]["signature_verified"] is True
    assert payload["ao2_verification"]["trust_boundary_ok"] is True
    assert payload["trust_boundary"]["closure_decision_owner"] == "ao2_native_evaluator_decision_verifier"
    assert payload["trust_boundary"]["factory_v3_role"] == "compat_closer_consumes_ao2_verdict"
    assert payload["trust_boundary"]["control_plane_role"] == "read_only_observer"
    assert payload["trust_boundary"]["control_plane_approves_release"] is False
    assert payload["trust_boundary"]["mutates_ao_artifacts"] is False
    assert payload["evidence"]["factory_v3_decision_path"].endswith("factory-decision.json")
    assert payload["evidence"]["ao2_verification_path"].endswith("ao2-verification.json")
    assert "AO2 Release Evaluator Closure" in markdown
    assert "accept_release_closure" in markdown
    assert "ao2_verification" in markdown


def test_closure_rejects_when_factory_accepted_but_ao2_rejected(tmp_path: Path) -> None:
    payload, markdown, _ = run_closure(
        tmp_path,
        factory_decision(),
        ao2_verification(status="rejected", signature_verified=False, trust_boundary_ok=False),
    )
    assert payload is not None and markdown is not None
    assert payload["status"] == "rejected"
    assert payload["decision"] == "reject_release_closure"
    assert payload["factory_v3_decision"]["status"] == "accepted"
    assert payload["ao2_verification"]["status"] == "rejected"
    assert any(
        "ao2_verification_status: expected accepted, observed rejected" in blocker
        for blocker in payload["blockers"]
    )
    assert "reject_release_closure" in markdown


def test_closure_rejects_when_factory_rejected_and_ao2_accepted(tmp_path: Path) -> None:
    payload, _, _ = run_closure(
        tmp_path,
        factory_decision(
            status="rejected",
            decision="reject_phase1_release_candidate",
            blockers=["readiness_status: expected ready, observed blocked"],
        ),
        ao2_verification(),
    )
    assert payload is not None
    assert payload["status"] == "rejected"
    assert payload["decision"] == "reject_release_closure"
    assert any(
        "factory_v3_decision_status: expected accepted, observed rejected" in blocker
        for blocker in payload["blockers"]
    )
    assert any(
        "factory_v3_blocker: readiness_status: expected ready, observed blocked" in blocker
        for blocker in payload["blockers"]
    )


def test_closure_rejects_when_both_rejected(tmp_path: Path) -> None:
    payload, _, _ = run_closure(
        tmp_path,
        factory_decision(
            status="rejected",
            decision="reject_phase1_release_candidate",
            blockers=["readiness_status: blocked"],
        ),
        ao2_verification(
            status="rejected",
            signature_verified=False,
            trust_boundary_ok=False,
            verdict={"status": "rejected", "owner": "ao2-native-evaluator-closer"},
        ),
    )
    assert payload is not None
    assert payload["status"] == "rejected"
    assert any(
        "factory_v3_decision_status" in blocker for blocker in payload["blockers"]
    )
    assert any(
        "ao2_verification_status" in blocker for blocker in payload["blockers"]
    )


def test_closure_rejects_when_ao2_verification_unsigned(tmp_path: Path) -> None:
    payload, _, _ = run_closure(
        tmp_path,
        factory_decision(),
        ao2_verification(
            status="rejected",
            signature_status="unsigned",
            signature_verified=False,
            trust_boundary_ok=True,
        ),
    )
    assert payload is not None
    assert payload["status"] == "rejected"
    assert any(
        "ao2_verification_signature_status: expected signed, observed unsigned" in blocker
        for blocker in payload["blockers"]
    )


def test_closure_rejects_when_trust_boundary_not_ok_even_with_accepted_status(tmp_path: Path) -> None:
    # Defense in depth: if upstream ever reports status=accepted but
    # trust_boundary_ok=false the closer must still refuse.
    payload, _, _ = run_closure(
        tmp_path,
        factory_decision(),
        ao2_verification(status="accepted", trust_boundary_ok=False),
    )
    assert payload is not None
    assert payload["status"] == "rejected"
    assert any(
        "ao2_verification_trust_boundary_ok: expected True, observed False" in blocker
        for blocker in payload["blockers"]
    )


def test_closure_errors_when_factory_decision_schema_invalid(tmp_path: Path) -> None:
    bad = factory_decision()
    bad["schema"] = "wrong-schema/v0"
    _, _, result = run_closure(tmp_path, bad, ao2_verification(), expect_returncode=2)
    assert "factory-decision schema" in result.stderr
    assert FACTORY_DECISION_SCHEMA in result.stderr


def test_closure_errors_when_ao2_verification_schema_invalid(tmp_path: Path) -> None:
    bad = ao2_verification()
    bad["schema_version"] = "ao2.wrong/v0"
    _, _, result = run_closure(tmp_path, factory_decision(), bad, expect_returncode=2)
    assert "ao2 verification schema" in result.stderr
    assert AO2_VERIFICATION_SCHEMA in result.stderr


def test_closure_errors_when_factory_v3_role_in_verification_is_wrong(tmp_path: Path) -> None:
    # The AO2 verifier always sets factory_v3_role = "parity_oracle_only"
    # in its output. Any other value means the verification did not come
    # from the AO2 verifier and must be refused.
    bad = ao2_verification()
    bad["factory_v3_role"] = "owner"
    _, _, result = run_closure(tmp_path, factory_decision(), bad, expect_returncode=2)
    assert "factory_v3_role" in result.stderr
    assert "parity_oracle_only" in result.stderr


def ao2_verification_missing_inputs(
    *,
    missing: list[str] | None = None,
) -> dict:
    """Mirror what scripts/ao2_release_ao2_native_evaluator_verification.py
    writes when the nightly pipeline runs before any AO2 native evaluator
    decision is wired through. Schema and discipline markers are present so
    the closer's schema validation passes; status=missing_inputs is the
    short-circuit signal.
    """
    return {
        "schema_version": AO2_VERIFICATION_SCHEMA,
        "status": "missing_inputs",
        "missing": missing or ["ao2_native_decision", "ao2_binary_not_on_path:ao2"],
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-evaluator-decision-verifier",
        "control_plane_role": "read_only_observer",
        "trust_boundary_ok": False,
        "signature_status": "missing",
        "signature_verified": False,
        "signature_requirement_satisfied": False,
        "signature_digest_match": False,
        "public_key_digest_match": False,
        "signed_payload_digest_match": False,
        "decision_payload_matches_signed_payload": False,
        "verdict": {
            "status": "missing_inputs",
            "factory_v3_required_to_decide": False,
            "owner": "ao2-native-evaluator-decision-verifier",
        },
    }


def test_closure_blocks_when_ao2_verification_missing_inputs(tmp_path: Path) -> None:
    # Phase 2 exit-gate item #4 discipline: the closer must NOT accept the
    # release closure when AO2 hasn't been asked. It emits status=blocked,
    # decision=blocked_awaiting_ao2_verification rather than a false reject.
    payload, markdown, _ = run_closure(
        tmp_path,
        factory_decision(),
        ao2_verification_missing_inputs(),
    )
    assert payload is not None and markdown is not None
    assert payload["status"] == "blocked"
    assert payload["decision"] == "blocked_awaiting_ao2_verification"
    assert payload["ao2_verification"]["status"] == "missing_inputs"
    assert payload["ao2_verification"]["missing"] == [
        "ao2_native_decision",
        "ao2_binary_not_on_path:ao2",
    ]
    assert payload["factory_v3_decision"]["status"] == "accepted"
    assert payload["release"] == {"version": "0.4.79", "release_tag": "v0.4.79"}
    assert payload["trust_boundary"]["closure_decision_owner"] == (
        "ao2_native_evaluator_decision_verifier"
    )
    assert payload["trust_boundary"]["control_plane_approves_release"] is False
    assert payload["trust_boundary"]["mutates_ao_artifacts"] is False
    assert any(
        "AO2 native verifier has not produced" in blocker
        for blocker in payload["blockers"]
    )
    assert any(
        "ao2_verification_missing_input: ao2_native_decision" in blocker
        for blocker in payload["blockers"]
    )
    assert "blocked_awaiting_ao2_verification" in markdown


def test_closure_blocks_when_factory_rejected_and_ao2_missing(tmp_path: Path) -> None:
    # Even when ao-operator has its own blockers, the AO2 missing-inputs path
    # takes precedence: AO2 owns the closure verdict, so the closure status
    # must reflect "AO2 has not been asked" rather than a ao-operator
    # rejection that no one has cross-checked.
    payload, _, _ = run_closure(
        tmp_path,
        factory_decision(
            status="rejected",
            decision="reject_phase1_release_candidate",
            blockers=["readiness_status: blocked"],
        ),
        ao2_verification_missing_inputs(missing=["dry_run"]),
    )
    assert payload is not None
    assert payload["status"] == "blocked"
    assert payload["decision"] == "blocked_awaiting_ao2_verification"
    assert payload["factory_v3_decision"]["status"] == "rejected"
    assert payload["factory_v3_decision"]["blockers"] == [
        "readiness_status: blocked"
    ]
    assert payload["ao2_verification"]["missing"] == ["dry_run"]
