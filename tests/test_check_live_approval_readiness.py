from __future__ import annotations

import json
from pathlib import Path

import check_live_approval_readiness


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_bundle(tmp_path: Path, *, live_slice: str = "17-run-bounded-live-10") -> dict[str, Path]:
    acceptance_slice = "24-check-live-acceptance"
    paths = {
        "readiness": write_json(
            tmp_path / "readiness.json",
            {
                "schema": "ao-operator/bounded-live-readiness-summary/v1",
                "verdict": "PASS",
                "live_providers_run": False,
                "checks": [{"id": "live_slice.blocked_without_allow_live", "status": "PASS"}],
            },
        ),
        "packet": write_json(
            tmp_path / "packet.json",
            {
                "schema": "ao-operator/live-dispatch-packet/v1",
                "verdict": "PASS",
                "dispatch_authorized": False,
                "live_providers_run": False,
                "live_slice": {"id": live_slice},
                "post_run_acceptance": {"slice_id": acceptance_slice},
            },
        ),
        "gate": write_json(
            tmp_path / "gate.json",
            {
                "schema": "ao-operator/live-dispatch-gate/v1",
                "verdict": "PASS",
                "ready_for_operator_approval": True,
                "dispatch_authorized": False,
                "live_providers_run": False,
                "live_slice": live_slice,
                "acceptance_slice": acceptance_slice,
            },
        ),
        "route": write_json(
            tmp_path / "route.json",
            {
                "schema": "ao-operator/live-postrun-routing/v1",
                "verdict": "PASS",
                "route": "WAIT_FOR_LIVE_RUN",
                "next_slice": live_slice,
                "commit_success_evidence_allowed": False,
            },
        ),
        "success_guard": write_json(
            tmp_path / "success.json",
            {
                "schema": "ao-operator/live-success-commit-guard/v1",
                "verdict": "PASS",
                "commit_success_evidence_allowed": False,
                "live_providers_run": False,
            },
        ),
        "sequence": write_json(
            tmp_path / "sequence.json",
            {
                "schema": "ao-operator/live-operator-sequence/v1",
                "verdict": "PASS",
                "live_slice": live_slice,
                "acceptance_slice": acceptance_slice,
                "live_providers_run": False,
            },
        ),
    }
    return paths


def call_check(tmp_path: Path, paths: dict[str, Path]):
    return check_live_approval_readiness.check_approval_readiness(
        root=tmp_path,
        readiness_path=paths["readiness"],
        packet_path=paths["packet"],
        gate_path=paths["gate"],
        route_path=paths["route"],
        success_guard_path=paths["success_guard"],
        sequence_path=paths["sequence"],
    )


def test_approval_readiness_passes_without_authorizing_dispatch(tmp_path):
    paths = write_bundle(tmp_path)

    payload = call_check(tmp_path, paths)

    assert payload["verdict"] == "PASS"
    assert payload["approval_request_ready"] is True
    assert payload["operator_approval_required"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["live_slice"] == "17-run-bounded-live-10"


def test_approval_readiness_fails_if_gate_authorizes_dispatch(tmp_path):
    paths = write_bundle(tmp_path)
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    gate["dispatch_authorized"] = True
    paths["gate"].write_text(json.dumps(gate), encoding="utf-8")

    payload = call_check(tmp_path, paths)

    assert payload["verdict"] == "FAIL"
    assert payload["approval_request_ready"] is False
    assert any("dispatch_authorized=false" in error for error in payload["errors"])


def test_approval_readiness_fails_if_route_points_elsewhere(tmp_path):
    paths = write_bundle(tmp_path)
    route = json.loads(paths["route"].read_text(encoding="utf-8"))
    route["next_slice"] = "16-run-bounded-live-10"
    paths["route"].write_text(json.dumps(route), encoding="utf-8")

    payload = call_check(tmp_path, paths)

    assert payload["verdict"] == "FAIL"
    assert any("postrun route next_slice" in error for error in payload["errors"])


def test_main_writes_output(tmp_path, capsys):
    paths = write_bundle(tmp_path)
    output = tmp_path / "approval.json"

    result = check_live_approval_readiness.main(
        [
            "--root",
            str(tmp_path),
            "--readiness",
            str(paths["readiness"]),
            "--packet",
            str(paths["packet"]),
            "--gate",
            str(paths["gate"]),
            "--route",
            str(paths["route"]),
            "--success-guard",
            str(paths["success_guard"]),
            "--sequence",
            str(paths["sequence"]),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-approval-readiness/v1"
