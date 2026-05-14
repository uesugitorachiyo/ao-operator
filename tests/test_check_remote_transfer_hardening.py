from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_hardening


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_ao_runtime(root: Path) -> Path:
    ao = root / "ao-runtime"
    write(
        ao / "progress/slice-reports/remote_transfer_v2_phase3_signed_manifest_verification.md",
        "\n".join(
            [
                "Result: DONE",
                "Added Ed25519 signature metadata to BundleManifest.",
                "canonical signing payload bytes",
                "required_signature_rejects_unsigned_manifest",
                "required_signature_rejects_tampered_manifest_metadata",
                "AO_WORKSPACE_SIGNING_KEY and AO_WORKSPACE_VERIFY_KEY handling as key file paths only.",
            ]
        ),
    )
    write(
        ao / "progress/slice-reports/remote_transfer_v2_phase2b_grpc_chunked_upload.md",
        "\n".join(
            [
                "Result: DONE_WITH_CONCERNS",
                "BeginWorkspaceUpload",
                "UploadWorkspaceChunk",
                "CommitWorkspaceUpload",
                "chunked_workspace_upload_commits_and_dispatches_by_bundle_id",
                "chunked_workspace_upload_hash_mismatch_reports_failed_chunk_index",
                "begin_rejects_declared_uploads_with_too_many_chunks",
            ]
        ),
    )
    write(
        ao / "docs/remote-worker-workspace-transfer-spec.md",
        "\n".join(
            [
                "Remote Transfer v2 supports chunked RuntimeService path.",
                "Required signed-manifest mode verifies Ed25519 signatures before trusting bundle metadata.",
                "Delete partial chunks under the receiver staging directory.",
                "Retry only the failed chunk index.",
                "No provider-token transfer in chunks, manifests, bundle IDs, or task payloads.",
            ]
        ),
    )
    return ao


def seed_factory(root: Path) -> None:
    base = root / "run-artifacts/remote-transfer-v2-stress-live"
    write(
        base / "chunked-upload-validation-20260506T233808Z.md",
        "\n".join(
            [
                "Verdict: PASS",
                "Missing chunk commit cleans partial staging and returns retry chunk index.",
                "Total hash mismatch cleans staging.",
            ]
        ),
    )
    write(
        base / "remote-codex-worker-runtime-smoke-20260507T004907Z.md",
        "\n".join(
            [
                "Verdict: PASS",
                "Mac dispatched the already Mac-signed bundle to the local coordinator.",
                "Ubuntu verified the signed bundle.",
                "task.completed",
            ]
        ),
    )
    write(
        base / "mac-ubuntu-remote-smoke-large-64m-20260506T233645Z.json",
        json.dumps(
            {
                "schema": "ao-operator/mac-ubuntu-remote-smoke/v1",
                "verdict": "PASS",
                "provider_dispatch": False,
                "extra_bytes": 67108864,
                "remote_cleanup_absent": True,
            }
        ),
    )


def test_remote_transfer_hardening_passes_with_signing_chunk_cleanup_and_smoke_evidence(tmp_path):
    ao = seed_ao_runtime(tmp_path)
    seed_factory(tmp_path)

    payload = check_remote_transfer_hardening.summarize(root=tmp_path, ao_runtime=ao)

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["controls"]["manifest_signing"]["verdict"] == "PASS"
    assert payload["controls"]["chunk_cleanup"]["verdict"] == "PASS"
    assert payload["controls"]["large_transfer_smoke"]["verdict"] == "PASS"
    assert payload["controls"]["worker_runtime_signed_smoke"]["verdict"] == "PASS"
    assert payload["next_safe_command"] == "Remote transfer signing and chunk cleanup hardening evidence passes."


def test_remote_transfer_hardening_blocks_when_manifest_signing_evidence_is_missing(tmp_path):
    ao = seed_ao_runtime(tmp_path)
    seed_factory(tmp_path)
    (ao / "progress/slice-reports/remote_transfer_v2_phase3_signed_manifest_verification.md").unlink()

    payload = check_remote_transfer_hardening.summarize(root=tmp_path, ao_runtime=ao)

    assert payload["verdict"] == "FAIL"
    assert "manifest_signing" in payload["blockers"]


def test_cli_writes_remote_transfer_hardening_report(tmp_path, capsys):
    ao = seed_ao_runtime(tmp_path)
    seed_factory(tmp_path)
    output = tmp_path / "run-artifacts/report.json"

    code = check_remote_transfer_hardening.main(
        ["--root", str(tmp_path), "--ao-runtime", str(ao), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/remote-transfer-hardening/v1"
    assert saved["dispatch_authorized"] is False
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
