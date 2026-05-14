from __future__ import annotations

import json
from pathlib import Path

import check_live_operator_sequence


def slice_item(order: int, slice_id: str, *, live: bool = False, override: bool = False) -> dict[str, object]:
    command = "python3 scripts/factory_run.py --run" if live else f"python3 scripts/{slice_id}.py --json"
    item: dict[str, object] = {
        "order": order,
        "id": slice_id,
        "mode": "diagnostic" if slice_id == "00-diagnostic" else "live-run" if live else "validation",
        "live_provider": live,
        "task_count": 27,
        "objective": f"Run {slice_id}.",
        "reads": ["input"],
        "writes": [] if slice_id == "24-check-live-acceptance" else ["output"],
        "commands": [command],
        "evidence": ["evidence"],
        "stop_rules": ["stop"],
    }
    if override:
        item.update(
            {
                "requires_override": True,
                "approval_env": "FACTORY_V3_ALLOW_LARGE_LIVE_RUN",
                "task_count": 57,
            }
        )
    return item


def manifest() -> dict[str, object]:
    slices = [
        slice_item(0, "00-diagnostic"),
        slice_item(1, "01-validation"),
    ]
    for offset, slice_id in enumerate(check_live_operator_sequence.EXPECTED_SEQUENCE, start=14):
        slices.append(
            slice_item(
                offset,
                slice_id,
                live=slice_id in {"17-run-bounded-live-10", "26-large-live-override-run"},
                override=slice_id == "26-large-live-override-run",
            )
        )
    return {
        "schema": "ao-operator/operator-slices/v1",
        "slug": "stress",
        "title": "Stress slices",
        "classification": "COMPLEX",
        "shape": "refactor",
        "max_live_tasks_default": 50,
        "objective": "Operate bounded live dispatch safely.",
        "negative_constraints": ["MUST NOT run large live topology"],
        "sensitive_fields": ["provider OAuth credentials"],
        "slices": slices,
    }


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest_path = write_json(tmp_path / "operator-slices.json", manifest())
    packet_path = write_json(
        tmp_path / "packet.json",
        {
            "schema": "ao-operator/live-dispatch-packet/v1",
            "dispatch_authorized": False,
            "live_providers_run": False,
            "post_run_acceptance": {"slice_id": "24-check-live-acceptance"},
        },
    )
    gate_path = write_json(
        tmp_path / "gate.json",
        {
            "schema": "ao-operator/live-dispatch-gate/v1",
            "acceptance_slice": "24-check-live-acceptance",
            "dispatch_authorized": False,
            "live_providers_run": False,
            "ready_for_operator_approval": True,
        },
    )
    return manifest_path, packet_path, gate_path


def test_sequence_passes_for_expected_manifest_and_artifacts(tmp_path):
    manifest_path, packet_path, gate_path = write_artifacts(tmp_path)

    payload = check_live_operator_sequence.check_sequence(
        root=tmp_path,
        manifest=manifest_path,
        packet=packet_path,
        gate=gate_path,
    )

    assert payload["verdict"] == "PASS"
    assert payload["acceptance_slice"] == "24-check-live-acceptance"
    assert payload["live_providers_run"] is False


def test_sequence_fails_when_acceptance_order_is_stale(tmp_path):
    manifest_path, packet_path, gate_path = write_artifacts(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in data["slices"]:
        if item["id"] == "24-check-live-acceptance":
            item["order"] = 15
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    payload = check_live_operator_sequence.check_sequence(
        root=tmp_path,
        manifest=manifest_path,
        packet=packet_path,
        gate=gate_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("order" in error for error in payload["errors"])


def test_sequence_fails_when_packet_acceptance_slice_is_stale(tmp_path):
    manifest_path, packet_path, gate_path = write_artifacts(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["post_run_acceptance"]["slice_id"] = "23-check-live-acceptance"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    payload = check_live_operator_sequence.check_sequence(
        root=tmp_path,
        manifest=manifest_path,
        packet=packet_path,
        gate=gate_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("dispatch packet acceptance slice" in error for error in payload["errors"])


def test_main_writes_output(tmp_path, capsys):
    manifest_path, packet_path, gate_path = write_artifacts(tmp_path)
    output = tmp_path / "sequence.json"

    result = check_live_operator_sequence.main(
        [
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "--packet",
            str(packet_path),
            "--gate",
            str(gate_path),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-operator-sequence/v1"
