from __future__ import annotations

import json
from pathlib import Path

import build_live_dispatch_packet
import verify_live_dispatch_packet
from test_build_live_dispatch_packet import manifest, readiness_summary, write_json


def write_packet_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest_path = write_json(tmp_path / "operator-slices.json", manifest())
    readiness_path = write_json(tmp_path / "readiness.json", readiness_summary())
    packet = build_live_dispatch_packet.build_packet(
        root=tmp_path,
        manifest=str(manifest_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        readiness_summary=str(readiness_path),
        live_slug="live",
    )
    packet_path = write_json(tmp_path / "packet.json", packet)
    return manifest_path, readiness_path, packet_path


def test_verify_packet_accepts_current_packet(tmp_path):
    manifest_path, readiness_path, packet_path = write_packet_bundle(tmp_path)

    payload = verify_live_dispatch_packet.verify_packet(
        root=tmp_path,
        packet_path=str(packet_path),
        manifest=str(manifest_path),
        readiness_summary=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
    )

    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_verify_packet_rejects_authorized_packet(tmp_path):
    manifest_path, readiness_path, packet_path = write_packet_bundle(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["dispatch_authorized"] = True
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    payload = verify_live_dispatch_packet.verify_packet(
        root=tmp_path,
        packet_path=str(packet_path),
        manifest=str(manifest_path),
        readiness_summary=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
    )

    assert payload["verdict"] == "FAIL"
    assert any("dispatch_authorized must be false" in error for error in payload["errors"])


def test_verify_packet_rejects_stale_live_command(tmp_path):
    manifest_path, readiness_path, packet_path = write_packet_bundle(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["live_slice"]["command"] = "python3 scripts/factory_run.py --brief stale.md --run"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    payload = verify_live_dispatch_packet.verify_packet(
        root=tmp_path,
        packet_path=str(packet_path),
        manifest=str(manifest_path),
        readiness_summary=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
    )

    assert payload["verdict"] == "FAIL"
    assert any("live command does not match manifest" in error for error in payload["errors"])


def test_verify_packet_rejects_stale_readiness(tmp_path):
    manifest_path, readiness_path, packet_path = write_packet_bundle(tmp_path)
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness["generated_at"] = "2026-05-06T01:00:00+00:00"
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")

    payload = verify_live_dispatch_packet.verify_packet(
        root=tmp_path,
        packet_path=str(packet_path),
        manifest=str(manifest_path),
        readiness_summary=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
    )

    assert payload["verdict"] == "FAIL"
    assert any("preflight generated_at" in error for error in payload["errors"])


def test_main_emits_json(tmp_path, capsys):
    manifest_path, readiness_path, packet_path = write_packet_bundle(tmp_path)

    result = verify_live_dispatch_packet.main(
        [
            "--root",
            str(tmp_path),
            "--packet",
            str(packet_path),
            "--manifest",
            str(manifest_path),
            "--readiness-summary",
            str(readiness_path),
            "--live-slice",
            "02-live",
            "--acceptance-slice",
            "03-acceptance",
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "ao-operator/live-dispatch-packet-verification/v1"
    assert payload["verdict"] == "PASS"
