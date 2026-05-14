from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_identity_signature


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_bundle(root: Path) -> None:
    write_json(
        root / "run-artifacts/live/approval-bundle.json",
        {
            "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
            "verdict": "PASS",
            "approval_template": {"approved": False, "runspec_sha256": "abc123"},
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is required for identity signing proof")
def test_identity_signature_fixture_signs_and_verifies_bundle(tmp_path):
    seed_bundle(tmp_path)

    report = check_agent_os_approval_identity_signature.check_identity_signature(
        root=tmp_path,
        fixture_root=tmp_path / "fixture",
        approval_bundle="run-artifacts/live/approval-bundle.json",
    )

    assert report["verdict"] == "PASS"
    assert report["identity_signature"] is True
    assert report["signature_verified"] is True
    assert report["private_key_committed"] is False
    assert report["fixture"] == "isolated-temp"
    assert report["dispatch_authorized"] is False
    assert report["live_providers_run"] is False
    assert "operator_ed25519" not in json.dumps(report)
    assert "OPENSSH PRIVATE KEY" not in json.dumps(report)


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is required for identity signing proof")
def test_identity_signature_detects_tampered_bundle(tmp_path):
    seed_bundle(tmp_path)
    report = check_agent_os_approval_identity_signature.check_identity_signature(
        root=tmp_path,
        fixture_root=tmp_path / "fixture",
        approval_bundle="run-artifacts/live/approval-bundle.json",
        tamper_after_sign=True,
    )

    assert report["verdict"] == "FAIL"
    assert report["signature_verified"] is False
    assert "identity signature verification failed" in report["errors"]


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is required for identity signing proof")
def test_identity_signature_cli_writes_report(tmp_path, capsys):
    seed_bundle(tmp_path)
    output = tmp_path / "run-artifacts/live/identity-signature.json"

    code = check_agent_os_approval_identity_signature.main(
        [
            "--root",
            str(tmp_path),
            "--fixture-root",
            str(tmp_path / "fixture"),
            "--approval-bundle",
            "run-artifacts/live/approval-bundle.json",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-identity-signature/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
