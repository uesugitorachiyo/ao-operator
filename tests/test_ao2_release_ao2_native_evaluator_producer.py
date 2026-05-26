from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_ao2_native_evaluator_producer.py"
VERIFIER_SCRIPT = ROOT / "scripts" / "ao2_release_ao2_native_evaluator_verification.py"

PRODUCER_SCHEMA = "ao-operator/ao2-release-ao2-native-evaluator-producer/v1"
AO2_DECISION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-result.v1"
AO2_VERIFICATION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-verification.v1"


def run_producer(
    *,
    write_json: Path,
    ao2_decision_out: Path,
    evidence_pack: Path | None = None,
    report: Path | None = None,
    factory_decision: Path | None = None,
    signing_key: Path | None = None,
    signer_id: str | None = None,
    ao2_binary: str | None = None,
    extra_env: dict[str, str] | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--write-json",
        str(write_json),
        "--ao2-decision-out",
        str(ao2_decision_out),
        "--json",
    ]
    if ao2_binary is not None:
        args.extend(["--ao2-binary", ao2_binary])
    if evidence_pack is not None:
        args.extend(["--evidence-pack", str(evidence_pack)])
    if report is not None:
        args.extend(["--report", str(report)])
    if factory_decision is not None:
        args.extend(["--factory-decision", str(factory_decision)])
    if signing_key is not None:
        args.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        args.extend(["--signer-id", signer_id])
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    payload = json.loads(result.stdout)
    on_disk = json.loads(write_json.read_text(encoding="utf-8"))
    assert payload == on_disk
    return payload, result


def run_verifier(
    *,
    write_json: Path,
    ao2_binary: str | None = None,
    ao2_native_decision: Path | None = None,
    ao2_producer_summary: Path | None = None,
    extra_env: dict[str, str] | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    args = [
        sys.executable,
        str(VERIFIER_SCRIPT),
        "--write-json",
        str(write_json),
        "--json",
    ]
    if ao2_binary is not None:
        args.extend(["--ao2-binary", ao2_binary])
    if ao2_native_decision is not None:
        args.extend(["--ao2-native-decision", str(ao2_native_decision)])
    if ao2_producer_summary is not None:
        args.extend(["--ao2-producer-summary", str(ao2_producer_summary)])
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    return json.loads(result.stdout), result


def _empty_path_env() -> dict[str, str]:
    return {"PATH": ""}


def _write_fake_evaluate_binary(
    *,
    path: Path,
    decision_path_to_write: Path,
    decision_body: dict,
    stdout_payload: dict | None = None,
    exit_code: int = 0,
    write_decision_file: bool = True,
) -> Path:
    """Create a stub `ao2` binary that mimics `ao2 factory evaluate`.

    The stub:
      * writes ``decision_body`` (a JSON object) to ``decision_path_to_write``
        when ``write_decision_file`` is True; and
      * prints ``stdout_payload`` (defaulting to a minimal valid
        ``ao2.ao-operator-compat-native-evaluator-result.v1`` payload that
        references ``decision_path_to_write``) on stdout, then exits with
        ``exit_code``.
    """
    if stdout_payload is None:
        stdout_payload = {
            "schema_version": AO2_DECISION_SCHEMA,
            "owner": "ao2-native-evaluator-closer",
            "verdict": "accepted",
            "decision_path": str(decision_path_to_write),
            "factory_v3_role": "parity_oracle_only",
            "factory_v3_evaluator_compared_when_supplied": False,
        }
    decision_text = json.dumps(decision_body)
    stdout_text = json.dumps(stdout_payload)
    write_block = ""
    if write_decision_file:
        # Use cat << to write the decision file deterministically.
        write_block = (
            f"mkdir -p {decision_path_to_write.parent!s}\n"
            f"cat > {decision_path_to_write!s} << 'AO2_DECISION_EOF'\n"
            f"{decision_text}\n"
            "AO2_DECISION_EOF\n"
        )
    script = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f"{write_block}"
        f"printf '%s' {stdout_text!r}\n"
        f"exit {exit_code}\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_fake_verifier_binary(*, path: Path, payload: dict, exit_code: int = 0) -> Path:
    script = (
        "#!/usr/bin/env bash\n"
        f"printf '%s' {json.dumps(payload)!r}\n"
        f"exit {exit_code}\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------------------------------------------------------------------------
# Producer: missing-inputs paths
# ---------------------------------------------------------------------------


def test_producer_missing_inputs_when_no_evidence_pack_or_binary(tmp_path: Path) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    payload, _ = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["schema_version"] == PRODUCER_SCHEMA
    assert payload["status"] == "missing_inputs"
    assert payload["ao2_native_decision_emitted"] is False
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-native-evaluator-closer"
    assert payload["control_plane_role"] == "read_only_observer"
    assert "evidence_pack" in payload["missing"]
    assert any(m.startswith("ao2_binary_not_on_path:") for m in payload["missing"])
    assert payload["ao2_native_decision_path"] == str(decision_out)
    assert payload["ao2_native_decision_schema"] == AO2_DECISION_SCHEMA
    assert payload["inputs"]["ao2_binary_resolved"] is None
    assert payload["inputs"]["evidence_pack"] is None
    # Producer should not have written the decision file
    assert not decision_out.exists()


def test_producer_missing_inputs_when_evidence_pack_path_missing(tmp_path: Path) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    nonexistent_pack = tmp_path / "evidence-pack.json"
    payload, _ = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary="ao2-not-installed",
        evidence_pack=nonexistent_pack,
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("evidence_pack_file_not_found:") for m in payload["missing"]
    )


def test_producer_missing_inputs_when_binary_unresolved_but_pack_present(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text(json.dumps({"schema_version": "ao2.evidence-pack.v1"}), encoding="utf-8")
    payload, _ = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary="ao2-not-installed",
        evidence_pack=pack,
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert payload["missing"] == ["ao2_binary_not_on_path:ao2-not-installed"]
    assert payload["inputs"]["evidence_pack"] == str(pack)


# ---------------------------------------------------------------------------
# Producer: produced (happy path + ao2 stub errors)
# ---------------------------------------------------------------------------


def test_producer_invokes_ao2_evaluate_and_writes_decision(tmp_path: Path) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text(json.dumps({"schema_version": "ao2.evidence-pack.v1"}), encoding="utf-8")
    fake_ao2 = _write_fake_evaluate_binary(
        path=tmp_path / "ao2",
        decision_path_to_write=decision_out,
        decision_body={
            "schema_version": AO2_DECISION_SCHEMA,
            "owner": "ao2-native-evaluator-closer",
            "verdict": "accepted",
            "decision_path": str(decision_out),
        },
    )
    payload, _ = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_ao2),
        evidence_pack=pack,
    )
    assert payload is not None
    assert payload["schema_version"] == PRODUCER_SCHEMA
    assert payload["status"] == "produced"
    assert payload["ao2_native_decision_emitted"] is True
    assert payload["ao2_native_decision_verdict"] == "accepted"
    assert payload["ao2_native_decision_path"] == str(decision_out)
    assert payload["ao2_native_decision_schema"] == AO2_DECISION_SCHEMA
    assert payload["ao2_native_decision_summary"]["schema_version"] == AO2_DECISION_SCHEMA
    assert payload["ao2_native_decision_summary"]["owner"] == "ao2-native-evaluator-closer"
    assert payload["inputs"]["evidence_pack"] == str(pack)
    assert payload["inputs"]["ao2_binary_resolved"] == str(fake_ao2)
    # The decision file the stub wrote must exist
    on_disk_decision = json.loads(decision_out.read_text(encoding="utf-8"))
    assert on_disk_decision["schema_version"] == AO2_DECISION_SCHEMA


def test_producer_errors_when_ao2_evaluate_exits_nonzero(tmp_path: Path) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text("{}", encoding="utf-8")
    fake_ao2 = _write_fake_evaluate_binary(
        path=tmp_path / "ao2",
        decision_path_to_write=decision_out,
        decision_body={},
        stdout_payload={
            "schema_version": AO2_DECISION_SCHEMA,
            "owner": "ao2-native-evaluator-closer",
        },
        exit_code=3,
        write_decision_file=False,
    )
    _, result = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_ao2),
        evidence_pack=pack,
        expect_returncode=1,
    )
    assert "ao2 factory evaluate failed" in result.stderr


def test_producer_errors_when_ao2_evaluate_returns_wrong_schema(tmp_path: Path) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text("{}", encoding="utf-8")
    fake_ao2 = _write_fake_evaluate_binary(
        path=tmp_path / "ao2",
        decision_path_to_write=decision_out,
        decision_body={"schema_version": "ao2.something-else/v0"},
        stdout_payload={
            "schema_version": "ao2.something-else/v0",
            "owner": "ao2-native-evaluator-closer",
        },
    )
    _, result = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_ao2),
        evidence_pack=pack,
        expect_returncode=1,
    )
    assert "unexpected schema_version" in result.stderr
    assert AO2_DECISION_SCHEMA in result.stderr


def test_producer_errors_when_ao2_evaluate_skips_writing_decision_file(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text("{}", encoding="utf-8")
    fake_ao2 = _write_fake_evaluate_binary(
        path=tmp_path / "ao2",
        decision_path_to_write=decision_out,
        decision_body={"schema_version": AO2_DECISION_SCHEMA},
        write_decision_file=False,
    )
    _, result = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_ao2),
        evidence_pack=pack,
        expect_returncode=1,
    )
    assert "did not write the AO2 native decision file" in result.stderr


# ---------------------------------------------------------------------------
# Verifier: --ao2-producer-summary integration
# ---------------------------------------------------------------------------


def test_verifier_inherits_missing_inputs_from_producer_summary(tmp_path: Path) -> None:
    # First, run the producer in missing-inputs mode
    producer_summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    producer_payload, _ = run_producer(
        write_json=producer_summary_path,
        ao2_decision_out=decision_out,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert producer_payload is not None
    assert producer_payload["status"] == "missing_inputs"

    # Then run the verifier consuming that summary
    verifier_out = tmp_path / "verification.json"
    verifier_payload, _ = run_verifier(
        write_json=verifier_out,
        ao2_binary="ao2-not-installed",
        ao2_producer_summary=producer_summary_path,
        extra_env=_empty_path_env(),
    )
    assert verifier_payload is not None
    assert verifier_payload["schema_version"] == AO2_VERIFICATION_SCHEMA
    assert verifier_payload["status"] == "missing_inputs"
    assert "ao2_producer_status_missing_inputs" in verifier_payload["missing"]
    assert verifier_payload["producer"]["status"] == "missing_inputs"
    assert verifier_payload["inputs"]["ao2_producer_summary"] == str(producer_summary_path)


def test_verifier_runs_for_real_when_producer_summary_status_is_produced(
    tmp_path: Path,
) -> None:
    # First, drive the producer to status=produced via a stub `ao2 factory evaluate`.
    producer_summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    pack = tmp_path / "evidence-pack.json"
    pack.write_text("{}", encoding="utf-8")
    fake_evaluate = _write_fake_evaluate_binary(
        path=tmp_path / "ao2-evaluate",
        decision_path_to_write=decision_out,
        decision_body={
            "schema_version": AO2_DECISION_SCHEMA,
            "owner": "ao2-native-evaluator-closer",
            "verdict": "accepted",
        },
    )
    producer_payload, _ = run_producer(
        write_json=producer_summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_evaluate),
        evidence_pack=pack,
    )
    assert producer_payload is not None
    assert producer_payload["status"] == "produced"

    # Now run the verifier consuming that summary; supply a *different* stub
    # `ao2` binary that mimics `ao2 factory verify-evaluator-decision`.
    fake_verifier = _write_fake_verifier_binary(
        path=tmp_path / "ao2-verify",
        payload={
            "schema_version": AO2_VERIFICATION_SCHEMA,
            "status": "accepted",
            "signature_status": "signed",
            "signature_verified": True,
            "signature_requirement_satisfied": True,
            "trust_boundary_ok": True,
            "factory_v3_role": "parity_oracle_only",
            "ao2_decision_owner": "ao2-native-evaluator-decision-verifier",
            "control_plane_role": "read_only_observer_after_signed_evidence",
            "verdict": {"status": "accepted"},
        },
    )
    verifier_out = tmp_path / "verification.json"
    verifier_payload, _ = run_verifier(
        write_json=verifier_out,
        ao2_binary=str(fake_verifier),
        ao2_producer_summary=producer_summary_path,
    )
    assert verifier_payload is not None
    assert verifier_payload["schema_version"] == AO2_VERIFICATION_SCHEMA
    assert verifier_payload["status"] == "accepted"
    assert verifier_payload["signature_verified"] is True
    assert verifier_payload["producer"]["status"] == "produced"
    assert verifier_payload["inputs"]["ao2_producer_summary"] == str(
        producer_summary_path
    )


def test_verifier_rejects_producer_summary_with_wrong_schema(tmp_path: Path) -> None:
    bad_summary = tmp_path / "producer-summary.json"
    bad_summary.write_text(
        json.dumps({"schema_version": "ao-operator/something-else/v1"}),
        encoding="utf-8",
    )
    verifier_out = tmp_path / "verification.json"
    _, result = run_verifier(
        write_json=verifier_out,
        ao2_binary="ao2-not-installed",
        ao2_producer_summary=bad_summary,
        extra_env=_empty_path_env(),
        expect_returncode=1,
    )
    assert "unexpected schema_version" in result.stderr
    assert PRODUCER_SCHEMA in result.stderr


def test_verifier_errors_when_producer_summary_path_missing(tmp_path: Path) -> None:
    verifier_out = tmp_path / "verification.json"
    missing_summary = tmp_path / "does-not-exist.json"
    _, result = run_verifier(
        write_json=verifier_out,
        ao2_binary="ao2-not-installed",
        ao2_producer_summary=missing_summary,
        extra_env=_empty_path_env(),
        expect_returncode=1,
    )
    assert "--ao2-producer-summary path does not exist" in result.stderr


def test_producer_summary_contains_no_secrets(tmp_path: Path) -> None:
    # Pass a signing-key path with a token-shaped basename and ensure the
    # producer never writes the file contents — only the path.
    summary_path = tmp_path / "producer-summary.json"
    decision_out = tmp_path / "ao2-native-decision.json"
    sensitive_key = tmp_path / "secret-bearer-sk-live.key"
    sensitive_key.write_text("Bearer sk-live-test-secret-token\n", encoding="utf-8")
    pack = tmp_path / "evidence-pack.json"
    pack.write_text("{}", encoding="utf-8")
    fake_ao2 = _write_fake_evaluate_binary(
        path=tmp_path / "ao2",
        decision_path_to_write=decision_out,
        decision_body={
            "schema_version": AO2_DECISION_SCHEMA,
            "owner": "ao2-native-evaluator-closer",
        },
    )
    payload, _ = run_producer(
        write_json=summary_path,
        ao2_decision_out=decision_out,
        ao2_binary=str(fake_ao2),
        evidence_pack=pack,
        signing_key=sensitive_key,
    )
    assert payload is not None
    text = json.dumps(payload)
    assert "sk-live-test-secret-token" not in text
    assert "Bearer sk-live" not in text
    # Path itself is fine — only file contents must not leak.
    assert "secret-bearer-sk-live.key" in text
