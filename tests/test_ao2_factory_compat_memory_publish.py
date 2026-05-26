"""Tests for ``scripts/ao2_factory_compat_memory_publish.py``.

Phase 2 exit-gate item #3 closure: this producer turns the existing
factory-compat memory store into an ``ao2.cp-ingest-receipt.v1``
envelope the Hermes AO2-refs auto-discovery already consumes. The
tests verify the four production-quality invariants:

  1. Skipped semantics when the operator has not configured the
     control-plane URL or the bearer-token env var. The producer must
     never touch the ao2 CLI in those cases — the run is a noop, not a
     failure.
  2. Signed-publish discipline (slice-19 default-on). The signing key
     is required unless ``--allow-unsigned-memory-export`` is set.
  3. AO2 owns the receipt schema. The producer rejects responses that
     do not conform to ``ao2.cp-ingest-receipt.v1``.
  4. Bearer tokens never appear in any committed artifact. The status
     JSON, command summary, and receipt file are scrubbed.

The tests stub ``ao2`` with a Python script that mimics the CLI shape
of ``ao2 memory export`` and ``ao2 memory publish``. The fake records
its invocations so each test can assert what the producer did and did
not call.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ao2_factory_compat_memory_publish as producer  # noqa: E402


CONTROL_PLANE_URL = "https://cp.example.test"
RECEIPT_SHA = "fixture-receipt-sha256"
RECEIPT_STORED_AT = "2026-05-25T05:00:00Z"
RECEIPT_INGESTED_SCHEMA = "ao2.memory-export.v1"
EXPORT_SIGNER_ID = "ao2-memory"
SECRET_TOKEN = "super-secret-cp-token-DO-NOT-LOG"


def _write_fake_ao2(
    tmp_path: Path,
    *,
    export_payload: dict | None = None,
    publish_payload: dict | None = None,
    export_exit: int = 0,
    publish_exit: int = 0,
) -> tuple[Path, Path]:
    """Materialise a fake ao2 binary that captures invocation arguments."""
    log_path = tmp_path / "ao2-fake.log"

    default_export = {
        "schema_version": producer.AO2_MEMORY_EXPORT_SCHEMA,
        "signer_id": EXPORT_SIGNER_ID,
        "signature": "fixture-signature",
        "exported_count": 1,
    }
    default_publish = {
        "schema_version": "ao2.memory-publish-response.v1",
        "endpoint": f"{CONTROL_PLANE_URL}/api/v1/memory/signed-export",
        "export_path": "<placeholder>",
        "receipt": {
            "schema_version": producer.AO2_CP_INGEST_RECEIPT_SCHEMA,
            "sha256": RECEIPT_SHA,
            "stored_at": RECEIPT_STORED_AT,
            "ingested_schema_version": RECEIPT_INGESTED_SCHEMA,
        },
    }
    export_payload = export_payload or default_export
    publish_payload = publish_payload or default_publish

    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import json
        import os
        import sys
        from pathlib import Path

        LOG = Path({str(log_path)!r})
        EXPORT_PAYLOAD = {json.dumps(export_payload)!r}
        PUBLISH_PAYLOAD = {json.dumps(publish_payload)!r}
        EXPORT_EXIT = {export_exit}
        PUBLISH_EXIT = {publish_exit}

        def main(argv):
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(argv) + "\\n")
            if len(argv) >= 3 and argv[1] == "memory" and argv[2] == "export":
                payload = json.loads(EXPORT_PAYLOAD)
                # Write a real export file so the producer can stat it.
                out_idx = argv.index("--out")
                out_path = Path(argv[out_idx + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(payload), encoding="utf-8")
                sys.stdout.write(json.dumps(payload))
                return EXPORT_EXIT
            if len(argv) >= 3 and argv[1] == "memory" and argv[2] == "publish":
                payload = json.loads(PUBLISH_PAYLOAD)
                if "--export" in argv:
                    payload["export_path"] = argv[argv.index("--export") + 1]
                sys.stdout.write(json.dumps(payload))
                return PUBLISH_EXIT
            sys.stderr.write("fake ao2: unsupported subcommand: " + " ".join(argv[1:]) + "\\n")
            return 2

        if __name__ == "__main__":
            sys.exit(main(sys.argv))
        """
    )
    ao2_path = tmp_path / "fake-ao2"
    ao2_path.write_text(script, encoding="utf-8")
    ao2_path.chmod(ao2_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return ao2_path, log_path


def _make_target(tmp_path: Path) -> Path:
    target = tmp_path / "factory-target"
    target.mkdir(parents=True)
    return target


def _read_log(log_path: Path) -> list[list[str]]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


def _build_args(
    tmp_path: Path,
    ao2_path: Path,
    *,
    control_plane_url: str | None = CONTROL_PLANE_URL,
    target: Path | None = None,
    signing_key: Path | None = None,
    allow_unsigned: bool = False,
    api_token_env: str = producer.DEFAULT_API_TOKEN_ENV,
) -> tuple[list[str], Path, Path]:
    target = target or _make_target(tmp_path)
    export_out = tmp_path / "export.json"
    receipt_out = tmp_path / "receipt.json"
    out = tmp_path / "summary.json"
    signing_key_path = (
        signing_key
        if signing_key is not None
        else tmp_path / "signing.key"
    )
    if signing_key is None and not allow_unsigned:
        signing_key_path.write_text("FIXTURE-SIGNING-KEY", encoding="utf-8")

    argv: list[str] = [
        "--ao2-binary",
        str(ao2_path),
        "--target",
        str(target),
        "--export-out",
        str(export_out),
        "--receipt-out",
        str(receipt_out),
        "--signer-id",
        EXPORT_SIGNER_ID,
        "--api-token-env",
        api_token_env,
        "--out",
        str(out),
    ]
    if control_plane_url is not None:
        argv.extend(["--control-plane-url", control_plane_url])
    if not allow_unsigned:
        argv.extend(["--signing-key", str(signing_key_path)])
    if allow_unsigned:
        argv.append("--allow-unsigned-memory-export")
    return argv, receipt_out, out


@pytest.fixture(autouse=True)
def _clear_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AO2_CP_API_TOKEN", raising=False)
    monkeypatch.delenv("AO2_CP_API_TOKEN_PROD", raising=False)


def test_skipped_when_no_control_plane_url(tmp_path: Path) -> None:
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    argv, _, out = _build_args(
        tmp_path,
        ao2_path,
        control_plane_url=None,
    )
    rc = producer.main(argv)
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["receipt"] is None
    assert payload["receipt_path"] is None
    assert "control-plane URL" in payload["reason"]
    # The ao2 binary must never be invoked when skipped.
    assert _read_log(log_path) == []


def test_skipped_when_api_token_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AO2_CP_API_TOKEN", raising=False)
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    argv, _, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert "AO2_CP_API_TOKEN" in payload["reason"]
    assert _read_log(log_path) == []


def test_skipped_with_custom_token_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ao2_path, _ = _write_fake_ao2(tmp_path)
    argv, _, out = _build_args(
        tmp_path,
        ao2_path,
        api_token_env="AO2_CP_API_TOKEN_PROD",
    )
    rc = producer.main(argv)
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert "AO2_CP_API_TOKEN_PROD" in payload["reason"]


def test_produced_writes_signed_export_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 0, out.read_text(encoding="utf-8")

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "produced"
    assert payload["stage"] == "complete"
    assert payload["completed"] == ["memory-export", "memory-publish"]
    assert payload["export_schema_version"] == producer.AO2_MEMORY_EXPORT_SCHEMA
    assert payload["export_signature_present"] is True

    receipt_on_disk = json.loads(receipt_out.read_text(encoding="utf-8"))
    assert receipt_on_disk["schema_version"] == producer.AO2_CP_INGEST_RECEIPT_SCHEMA
    assert receipt_on_disk["sha256"] == RECEIPT_SHA
    assert receipt_on_disk["stored_at"] == RECEIPT_STORED_AT
    assert receipt_on_disk["ingested_schema_version"] == RECEIPT_INGESTED_SCHEMA

    # Verify the producer invoked both ao2 subcommands in order.
    log = _read_log(log_path)
    assert [entry[1:3] for entry in log] == [
        ["memory", "export"],
        ["memory", "publish"],
    ]
    publish_call = log[1]
    assert "--control-plane-url" in publish_call
    assert "--api-token" in publish_call


def test_token_never_appears_in_status_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(tmp_path)
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 0
    raw = out.read_text(encoding="utf-8")
    assert SECRET_TOKEN not in raw

    payload = json.loads(raw)
    publish_cmd = payload["command_summary"]["memory_publish"]
    assert "--api-token" in publish_cmd
    assert SECRET_TOKEN not in publish_cmd
    assert "<redacted>" in publish_cmd

    # Receipt file must never carry the token either.
    assert SECRET_TOKEN not in receipt_out.read_text(encoding="utf-8")


def test_receipt_schema_rejected_when_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(
        tmp_path,
        publish_payload={
            "schema_version": "ao2.memory-publish-response.v1",
            "receipt": {
                "schema_version": "ao2.something-else.v1",
                "sha256": "x",
                "stored_at": RECEIPT_STORED_AT,
            },
        },
    )
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "memory-publish"
    assert "schema_version" in payload["reason"]
    assert not receipt_out.exists()


def test_publish_command_failure_surfaces_failed_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(tmp_path, publish_exit=7)
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "memory-publish"
    assert payload["completed"] == ["memory-export"]
    assert payload["export_path"].endswith("export.json")
    assert SECRET_TOKEN not in out.read_text(encoding="utf-8")
    assert not receipt_out.exists()


def test_export_command_failure_surfaces_failed_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(tmp_path, export_exit=5)
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "memory-export"
    assert payload["completed"] == []
    assert payload["export_path"] is None
    assert not receipt_out.exists()


def test_signing_key_required_unless_allow_unsigned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    argv, receipt_out, out = _build_args(
        tmp_path,
        ao2_path,
        allow_unsigned=False,
        signing_key=tmp_path / "no-such.key",  # will not exist on disk
    )
    # Remove the signing key flag to simulate omission entirely.
    sk_idx = argv.index("--signing-key")
    del argv[sk_idx : sk_idx + 2]
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "preflight"
    assert "signing-key" in payload["reason"]
    assert _read_log(log_path) == []


def test_allow_unsigned_passes_flag_to_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    argv, _, out = _build_args(tmp_path, ao2_path, allow_unsigned=True)
    rc = producer.main(argv)
    assert rc == 0, out.read_text(encoding="utf-8")
    log = _read_log(log_path)
    publish_call = log[1]
    assert "--allow-unsigned-memory-export" in publish_call
    export_call = log[0]
    # Signing key flag must not appear on the export call in unsigned mode.
    assert "--signing-key" not in export_call


def test_target_must_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, log_path = _write_fake_ao2(tmp_path)
    missing_target = tmp_path / "no-such-target"
    argv, _, out = _build_args(tmp_path, ao2_path, target=missing_target)
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "preflight"
    assert "target" in payload["reason"]
    assert _read_log(log_path) == []


def test_export_schema_validation_rejects_wrong_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, log_path = _write_fake_ao2(
        tmp_path,
        export_payload={
            "schema_version": "ao2.memory-export.legacy",
            "signer_id": EXPORT_SIGNER_ID,
        },
    )
    argv, receipt_out, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "memory-export"
    # Publish must not run when export schema is wrong.
    log = _read_log(log_path)
    assert len(log) == 1
    assert not receipt_out.exists()


def test_trust_boundary_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(tmp_path)
    argv, _, out = _build_args(tmp_path, ao2_path)
    rc = producer.main(argv)
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    boundary = payload["trust_boundary"]
    assert boundary["factory_v3_role"] == "parity_oracle_only"
    assert boundary["ao2_decision_owner"] == "ao2-cli-memory-publish"
    assert boundary["control_plane_role"].startswith("read_only_observer")


def test_out_stdout_when_no_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AO2_CP_API_TOKEN", SECRET_TOKEN)
    ao2_path, _ = _write_fake_ao2(tmp_path)
    argv, _, _ = _build_args(tmp_path, ao2_path)
    out_idx = argv.index("--out")
    del argv[out_idx : out_idx + 2]
    rc = producer.main(argv)
    assert rc == 0
    captured = capsys.readouterr()
    assert SECRET_TOKEN not in captured.out
    payload = json.loads(captured.out)
    assert payload["status"] == "produced"


def test_schema_version_constant() -> None:
    assert producer.ORCHESTRATOR_SCHEMA == (
        "ao-operator/ao2-factory-compat-memory-publish/v1"
    )
    assert producer.AO2_CP_INGEST_RECEIPT_SCHEMA == "ao2.cp-ingest-receipt.v1"
