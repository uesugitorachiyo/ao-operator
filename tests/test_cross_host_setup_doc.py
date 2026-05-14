from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cross_host_setup_doc_covers_each_platform_and_commands() -> None:
    body = (ROOT / "docs" / "cross-host-setup.md").read_text(encoding="utf-8")
    for heading in ("## Ubuntu Coordinator", "## Mac Worker", "## Windows Worker"):
        assert heading in body
    for command in (
        "scripts/cross-host-tunnel.sh",
        "cross-host-tunnel.ps1",
        "ao daemon start --foreground",
        "AO_WORKER_TAGS=mac,live",
        'tags = ["win"]',
        "AO_LIVE_CROSS_HOST=1",
        "prepare_windows_outbound_bootstrap.py",
        "Windows initiates outbound SSH",
        "[coordinator.tls]",
        "[coordinator.wal_http.tls]",
        "AO_WAL_HTTP_TLS_CERT",
        "Plain WAL HTTP remains loopback-only",
        "AO_COORDINATOR_TLS_CA",
        "remote_transfer_v2_tls_ubuntu_validate.sh",
        "Plain LAN exposure of unauthenticated write-capable endpoints is forbidden",
    ):
        assert command in body


def test_release_v02_records_ao_runtime_tls_posture() -> None:
    body = (ROOT / "run-artifacts/release-v0.2/ao-runtime-tls-posture.md").read_text(
        encoding="utf-8"
    )

    for text in (
        "e5a2b0dd",
        "15afe91f",
        "d9eb68a",
        "0cdcdd2",
        "0c5850b",
        "c47d7e4",
        "383bb56",
        "AO_WORKER_RUNTIME_TLS_CERT",
        "AO_COORDINATOR_TLS_CA",
        "[coordinator.tls]",
        "[coordinator.wal_http.tls]",
        "AO_WAL_HTTP_TLS_CERT",
        "remote_transfer_v2_tls_ubuntu_validate.sh",
        "WAL HTTP is guarded to loopback",
        "Plain WAL HTTP remains loopback-only",
        "Direct-network WAL replication uses `https://.../replication/wal`",
        "ao-runtime/advertised-primary/v1",
        "--expected-sha256",
        "non-loopback `http://` advertised-primary URLs are rejected",
        "oversized advertised-primary rejection before replica config mutation",
        "structured Mac launchd plist and Windows Task Scheduler XML parsing",
        "native Mac launchd installed-worker validation",
        "Windows native Task Scheduler validation remains blocked from Ubuntu",
    ):
        assert text in body
