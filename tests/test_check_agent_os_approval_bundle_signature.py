from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_bundle_signature


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def bundle_payload() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
        "verdict": "PASS",
        "approval_gate": "run-artifacts/live/gate.json",
        "approval_file_target": "run-artifacts/live/approval.json",
        "approval_template": {
            "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
            "approved": False,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": "abc123",
            "task_count": 7,
        },
        "runspec_lock": {"algorithm": "sha256", "path": "ao/runspecs/agent-os-phase-draft.yaml", "sha256": "abc123"},
        "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml"],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def test_signature_writer_creates_tamper_evident_sidecar(tmp_path):
    bundle = write_json(tmp_path / "bundle.json", bundle_payload())
    output = tmp_path / "signature.json"

    report = check_agent_os_approval_bundle_signature.check_signature(
        root=tmp_path,
        approval_bundle=bundle,
        signature_file=output,
        write_signature=True,
    )

    assert report["verdict"] == "PASS"
    assert report["signature_present"] is True
    assert report["signature_matches"] is True
    assert output.is_file()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["subject_sha256"] == report["subject_sha256"]
    assert saved["dispatch_authorized"] is False


def test_signature_verification_fails_after_bundle_tampering(tmp_path):
    bundle = write_json(tmp_path / "bundle.json", bundle_payload())
    signature = tmp_path / "signature.json"
    check_agent_os_approval_bundle_signature.check_signature(
        root=tmp_path,
        approval_bundle=bundle,
        signature_file=signature,
        write_signature=True,
    )
    payload = bundle_payload()
    payload["approval_file_target"] = "run-artifacts/live/tampered.json"
    write_json(bundle, payload)

    report = check_agent_os_approval_bundle_signature.check_signature(
        root=tmp_path,
        approval_bundle=bundle,
        signature_file=signature,
    )

    assert report["verdict"] == "FAIL"
    assert report["signature_matches"] is False
    assert "approval bundle signature mismatch" in report["errors"]


def test_signature_refuses_dispatching_bundle(tmp_path):
    payload = bundle_payload()
    payload["dispatch_authorized"] = True
    bundle = write_json(tmp_path / "bundle.json", payload)

    report = check_agent_os_approval_bundle_signature.check_signature(root=tmp_path, approval_bundle=bundle)

    assert report["verdict"] == "FAIL"
    assert "approval bundle dispatch_authorized must remain false" in report["errors"]


def test_cli_writes_signature_report(tmp_path, capsys):
    bundle = write_json(tmp_path / "bundle.json", bundle_payload())
    signature = tmp_path / "signature.json"
    output = tmp_path / "signature-report.json"

    code = check_agent_os_approval_bundle_signature.main(
        [
            "--root",
            str(tmp_path),
            "--approval-bundle",
            str(bundle),
            "--signature-file",
            str(signature),
            "--write-signature",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-bundle-signature/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
