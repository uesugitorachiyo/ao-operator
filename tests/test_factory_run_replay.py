from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import evidence_pack_writer
import factory_run
from test_evidence_pack_writer import _inputs


def test_factory_run_replay_emits_replay_report(tmp_path, monkeypatch, capsys):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "factory_run.py",
            "replay",
            str(pack),
            "--hmac-key-hex",
            key.hex(),
        ],
    )

    rc = factory_run.main()

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "ao-operator/evidence-pack-replay/v1"
    assert report["verdict"] == "PASS"
    assert report["checks"]["verification"] == "PASS"
    assert report["checks"]["event_task_coverage"] == "PASS"
    assert report["checks"]["transcript_paths"] == "PASS"
    assert report["checks"]["artifact_refs"] == "PASS"
    assert report["checks"]["deterministic_non_llm_replay"] == "SKIPPED"


def test_factory_run_replay_fails_when_manifest_task_has_no_event(tmp_path, monkeypatch, capsys):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        replace(_inputs(tmp_path), events=[]),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "factory_run.py",
            "replay",
            str(pack),
            "--hmac-key-hex",
            key.hex(),
        ],
    )

    rc = factory_run.main()

    assert rc == 1
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["verification"] == "PASS"
    assert report["checks"]["event_task_coverage"] == "FAIL"
    assert "event_task_missing:intake" in report["errors"]


def test_factory_run_replay_write_report_persists_json(tmp_path, monkeypatch, capsys):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    report_path = tmp_path / "replay-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "factory_run.py",
            "replay",
            str(pack),
            "--hmac-key-hex",
            key.hex(),
            "--write-report",
            str(report_path),
        ],
    )

    rc = factory_run.main()

    assert rc == 0
    stdout_report = json.loads(capsys.readouterr().out)
    persisted = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert persisted == stdout_report
    assert persisted["schema"] == "ao-operator/evidence-pack-replay/v1"


def test_factory_run_replay_execute_deterministic_flag(tmp_path, monkeypatch, capsys):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        replace(
            _inputs(tmp_path),
            tasks=[
                evidence_pack_writer.TaskRecord(
                    task_id="intake",
                    role="planner-intake",
                    status="completed",
                    started_at="2026-05-11T18:00:01+00:00",
                    completed_at="2026-05-11T18:01:00+00:00",
                    deterministic=True,
                    replay_command=[
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('report.md').write_text('evidence\\n', encoding='utf-8')",
                    ],
                    replay_outputs=["report.md"],
                )
            ],
        ),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "factory_run.py",
            "replay",
            str(pack),
            "--hmac-key-hex",
            key.hex(),
            "--execute-deterministic",
            "--deterministic-timeout-seconds",
            "2",
        ],
    )

    rc = factory_run.main()

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["deterministic_command_execution"] == "PASS"
