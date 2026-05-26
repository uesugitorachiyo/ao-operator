from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_ao2_native_evaluator_verification.py"

AO2_VERIFICATION_SCHEMA = "ao2.ao-operator-compat-native-evaluator-verification.v1"


def run_helper(
    *,
    write_json: Path,
    ao2_binary: str | None = None,
    ao2_native_decision: Path | None = None,
    extra_env: dict[str, str] | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    args = [sys.executable, str(SCRIPT), "--write-json", str(write_json), "--json"]
    if ao2_binary is not None:
        args.extend(["--ao2-binary", ao2_binary])
    if ao2_native_decision is not None:
        args.extend(["--ao2-native-decision", str(ao2_native_decision)])
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


def _empty_path_env() -> dict[str, str]:
    # Strip PATH so `shutil.which("ao2-not-installed")` always returns None
    # regardless of the test host's installed binaries.
    return {"PATH": ""}


def test_missing_inputs_when_no_native_decision_supplied(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    payload, _ = run_helper(
        write_json=out,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["schema_version"] == AO2_VERIFICATION_SCHEMA
    assert payload["status"] == "missing_inputs"
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-native-evaluator-decision-verifier"
    assert payload["control_plane_role"] == "read_only_observer"
    assert payload["trust_boundary_ok"] is False
    assert payload["signature_status"] == "missing"
    assert payload["signature_verified"] is False
    assert payload["signature_requirement_satisfied"] is False
    assert payload["verdict"]["status"] == "missing_inputs"
    assert payload["verdict"]["factory_v3_required_to_decide"] is False
    assert "ao2_native_decision" in payload["missing"]
    assert any(
        m.startswith("ao2_binary_not_on_path:") for m in payload["missing"]
    )
    assert payload["inputs"]["ao2_binary"] == "ao2-not-installed"
    assert payload["inputs"]["ao2_binary_resolved"] is None
    assert payload["inputs"]["ao2_native_decision"] is None


def test_missing_inputs_when_native_decision_path_does_not_exist(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    missing_decision = tmp_path / "does-not-exist.json"
    payload, _ = run_helper(
        write_json=out,
        ao2_binary="ao2-not-installed",
        ao2_native_decision=missing_decision,
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("ao2_native_decision_file_not_found:") for m in payload["missing"]
    )


def test_missing_inputs_when_binary_missing_but_decision_exists(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    decision = tmp_path / "ao2-native-decision.json"
    decision.write_text(json.dumps({"native_evaluator_decision": {}}), encoding="utf-8")
    payload, _ = run_helper(
        write_json=out,
        ao2_binary="ao2-not-installed",
        ao2_native_decision=decision,
        extra_env=_empty_path_env(),
    )
    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert payload["missing"] == ["ao2_binary_not_on_path:ao2-not-installed"]
    assert payload["inputs"]["ao2_native_decision"] == str(decision)


def _write_fake_ao2_binary(path: Path, stdout: str, exit_code: int = 0) -> Path:
    script = f"#!/usr/bin/env bash\nprintf '%s' {stdout!r}\nexit {exit_code}\n"
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_invokes_ao2_verifier_and_writes_returned_payload(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    decision = tmp_path / "ao2-native-decision.json"
    decision.write_text(json.dumps({"native_evaluator_decision": {}}), encoding="utf-8")
    fake_ao2 = _write_fake_ao2_binary(
        tmp_path / "ao2",
        json.dumps(
            {
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
            }
        ),
    )
    payload, _ = run_helper(
        write_json=out,
        ao2_binary=str(fake_ao2),
        ao2_native_decision=decision,
    )
    assert payload is not None
    assert payload["schema_version"] == AO2_VERIFICATION_SCHEMA
    assert payload["status"] == "accepted"
    assert payload["signature_verified"] is True
    assert payload["factory_v3_role"] == "parity_oracle_only"


def test_helper_errors_when_ao2_binary_exits_nonzero(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    decision = tmp_path / "ao2-native-decision.json"
    decision.write_text(json.dumps({"native_evaluator_decision": {}}), encoding="utf-8")
    fake_ao2 = _write_fake_ao2_binary(
        tmp_path / "ao2",
        "boom: not a valid evaluator decision",
        exit_code=2,
    )
    _, result = run_helper(
        write_json=out,
        ao2_binary=str(fake_ao2),
        ao2_native_decision=decision,
        expect_returncode=1,
    )
    assert "ao2 factory verify-evaluator-decision failed" in result.stderr


def test_helper_errors_when_ao2_binary_returns_unexpected_schema(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    decision = tmp_path / "ao2-native-decision.json"
    decision.write_text(json.dumps({"native_evaluator_decision": {}}), encoding="utf-8")
    fake_ao2 = _write_fake_ao2_binary(
        tmp_path / "ao2",
        json.dumps({"schema_version": "ao2.wrong/v0", "status": "accepted"}),
    )
    _, result = run_helper(
        write_json=out,
        ao2_binary=str(fake_ao2),
        ao2_native_decision=decision,
        expect_returncode=1,
    )
    assert "unexpected schema_version" in result.stderr
    assert AO2_VERIFICATION_SCHEMA in result.stderr


def test_helper_errors_when_ao2_binary_returns_invalid_json(tmp_path: Path) -> None:
    out = tmp_path / "verification.json"
    decision = tmp_path / "ao2-native-decision.json"
    decision.write_text(json.dumps({"native_evaluator_decision": {}}), encoding="utf-8")
    fake_ao2 = _write_fake_ao2_binary(
        tmp_path / "ao2",
        "not-json {{{",
    )
    _, result = run_helper(
        write_json=out,
        ao2_binary=str(fake_ao2),
        ao2_native_decision=decision,
        expect_returncode=1,
    )
    assert "returned invalid JSON" in result.stderr
