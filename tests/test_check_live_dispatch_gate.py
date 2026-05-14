from __future__ import annotations

import json
from pathlib import Path

import build_live_dispatch_packet
import check_live_dispatch_gate
from test_build_live_dispatch_packet import manifest, readiness_summary, write_json
from test_check_bounded_live_readiness import fake_runner


def write_gate_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
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


def test_gate_passes_without_authorizing_dispatch(tmp_path):
    manifest_path, readiness_path, packet_path = write_gate_bundle(tmp_path)

    payload = check_live_dispatch_gate.check_gate(
        root=tmp_path,
        slug="live",
        manifest=str(manifest_path),
        contract="contract.json",
        topology="topology.yaml",
        packet=str(packet_path),
        readiness_summary_path=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        runner=fake_runner,
    )

    assert payload["verdict"] == "PASS"
    assert payload["ready_for_operator_approval"] is True
    assert payload["operator_approval_required"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["readiness"]["verdict"] == "PASS"
    assert payload["packet_verification"]["verdict"] == "PASS"


def test_gate_fails_when_readiness_fails(tmp_path):
    manifest_path, readiness_path, packet_path = write_gate_bundle(tmp_path)

    def runner(command: list[str], *, root: Path, env: dict[str, str]) -> dict[str, object]:
        report = fake_runner(command, root=root, env=env)
        if "factory_doctor.py" in " ".join(command):
            report["exit"] = 1
        return report

    payload = check_live_dispatch_gate.check_gate(
        root=tmp_path,
        manifest=str(manifest_path),
        packet=str(packet_path),
        readiness_summary_path=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        runner=runner,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["ready_for_operator_approval"] is False
    assert any("bounded live readiness must be PASS" in error for error in payload["errors"])


def test_gate_fails_when_packet_is_stale(tmp_path):
    manifest_path, readiness_path, packet_path = write_gate_bundle(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["live_slice"]["command"] = "python3 scripts/factory_run.py --brief stale.md --run"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    payload = check_live_dispatch_gate.check_gate(
        root=tmp_path,
        manifest=str(manifest_path),
        packet=str(packet_path),
        readiness_summary_path=str(readiness_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        runner=fake_runner,
    )

    assert payload["verdict"] == "FAIL"
    assert any("dispatch packet verification must be PASS" in error for error in payload["errors"])
    assert any("live command does not match manifest" in error for error in payload["errors"])


def test_main_writes_gate(monkeypatch, tmp_path, capsys):
    manifest_path, readiness_path, packet_path = write_gate_bundle(tmp_path)
    gate_path = tmp_path / "gate.json"
    monkeypatch.setattr(check_live_dispatch_gate.check_bounded_live_readiness, "run_command", fake_runner)

    result = check_live_dispatch_gate.main(
        [
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "--packet",
            str(packet_path),
            "--readiness-summary",
            str(readiness_path),
            "--live-slice",
            "02-live",
            "--acceptance-slice",
            "03-acceptance",
            "--write-gate",
            str(gate_path),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == str(gate_path)
    written = json.loads(gate_path.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-dispatch-gate/v1"
