from __future__ import annotations

import json
from pathlib import Path

import build_live_dispatch_packet


def manifest() -> dict[str, object]:
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
        "slices": [
            {
                "order": 0,
                "id": "00-diagnostic",
                "mode": "diagnostic",
                "live_provider": False,
                "task_count": 0,
                "objective": "Capture diagnostics.",
                "reads": [],
                "writes": [],
                "commands": ["python3 scripts/summarize_ao_failure.py /tmp/ao --json"],
                "evidence": ["summary"],
                "stop_rules": ["Stop on missing AO home."],
            },
            {
                "order": 1,
                "id": "01-validation",
                "mode": "validation",
                "live_provider": False,
                "task_count": 0,
                "objective": "Validate locally.",
                "reads": [],
                "writes": [],
                "commands": ["python3 scripts/validate_factory.py --json"],
                "evidence": ["PASS"],
                "stop_rules": ["Stop on FAIL."],
            },
            {
                "order": 2,
                "id": "02-live",
                "mode": "live-run",
                "live_provider": True,
                "task_count": 27,
                "objective": "Run bounded live profile.",
                "reads": ["brief.md"],
                "writes": ["run-artifacts/live/"],
                "commands": ["python3 scripts/factory_run.py --brief brief.md --run"],
                "evidence": ["AO completed=true"],
                "stop_rules": ["Stop on blockers."],
            },
            {
                "order": 3,
                "id": "03-acceptance",
                "mode": "validation",
                "live_provider": False,
                "task_count": 27,
                "objective": "Check acceptance.",
                "reads": ["run-artifacts/live/"],
                "writes": [],
                "commands": ["python3 scripts/check_live_acceptance.py --slug live --json"],
                "evidence": ["ACCEPTED"],
                "stop_rules": ["Stop on FAIL."],
            },
        ],
    }


def readiness_summary(verdict: str = "PASS") -> dict[str, object]:
    return {
        "schema": "ao-operator/bounded-live-readiness-summary/v1",
        "generated_at": "2026-05-06T00:00:00+00:00",
        "verdict": verdict,
        "slug": "live",
        "mode": "pre-live-readiness",
        "live_providers_run": False,
        "checks": [
            {
                "id": "doctor.pass",
                "status": verdict,
                "expected_exit": 0,
                "actual_exit": 0,
                "expected_verdict": "PASS",
                "actual_verdict": "PASS",
            }
        ],
    }


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_packet_uses_readiness_and_does_not_authorize_dispatch(tmp_path):
    manifest_path = write_json(tmp_path / "operator-slices.json", manifest())
    readiness_path = write_json(tmp_path / "readiness.json", readiness_summary())

    packet = build_live_dispatch_packet.build_packet(
        root=tmp_path,
        manifest=str(manifest_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        readiness_summary=str(readiness_path),
        live_slug="live",
        ao_runtime_path="/tmp/ao-runtime",
    )

    assert packet["verdict"] == "PASS"
    assert packet["dispatch_authorized"] is False
    assert packet["live_providers_run"] is False
    assert packet["live_slice"]["command"] == "python3 scripts/factory_run.py --brief brief.md --run"
    assert packet["operator_slice_dispatch"]["command"].endswith("--slice 02-live --execute --allow-live --json")
    assert packet["environment"]["exports"][0] == "export FACTORY_V3_AO_RUNTIME_PATH=/tmp/ao-runtime"
    assert packet["post_run_acceptance"]["commands"] == ["python3 scripts/check_live_acceptance.py --slug live --json"]


def test_build_packet_fails_when_readiness_is_not_pass(tmp_path):
    manifest_path = write_json(tmp_path / "operator-slices.json", manifest())
    readiness_path = write_json(tmp_path / "readiness.json", readiness_summary("FAIL"))

    packet = build_live_dispatch_packet.build_packet(
        root=tmp_path,
        manifest=str(manifest_path),
        live_slice_id="02-live",
        acceptance_slice_id="03-acceptance",
        readiness_summary=str(readiness_path),
    )

    assert packet["verdict"] == "FAIL"
    assert any("readiness summary verdict must be PASS" in error for error in packet["errors"])


def test_main_writes_packet(tmp_path, capsys):
    manifest_path = write_json(tmp_path / "operator-slices.json", manifest())
    readiness_path = write_json(tmp_path / "readiness.json", readiness_summary())
    packet_path = tmp_path / "packet.json"

    result = build_live_dispatch_packet.main(
        [
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "--live-slice",
            "02-live",
            "--acceptance-slice",
            "03-acceptance",
            "--readiness-summary",
            str(readiness_path),
            "--write-packet",
            str(packet_path),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packet"] == str(packet_path)
    written = json.loads(packet_path.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-dispatch-packet/v1"
