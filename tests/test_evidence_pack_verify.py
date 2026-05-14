from __future__ import annotations

import json
import shutil
import sys
import tarfile
from pathlib import Path
from dataclasses import replace

import pytest

import evidence_pack_verify
import evidence_pack_writer
from test_evidence_pack_writer import _inputs


def test_verify_pack_accepts_valid_hmac_directory(tmp_path):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )

    report = evidence_pack_verify.verify_pack(pack, hmac_key=key)

    assert report["verdict"] == "PASS"
    assert report["checks"]["signature"] == "PASS"
    assert report["checks"]["merkle_root"] == "PASS"
    assert report["checks"]["artifact_shas"] == "PASS"


def test_verify_pack_rejects_tampered_artifact(tmp_path):
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    artifact = next((pack / "artifacts").glob("*/*"))
    artifact.write_text("tampered\n", encoding="utf-8")

    report = evidence_pack_verify.verify_pack(pack, hmac_key=key)

    assert report["verdict"] == "FAIL"
    assert any("artifact_sha_mismatch" in error for error in report["errors"])


def test_verify_pack_accepts_tar_zst_archive(tmp_path):
    if shutil.which("zstd") is None:
        pytest.skip("zstd CLI not installed")
    key = b"0123456789abcdef"
    pack = evidence_pack_writer.write_pack(
        _inputs(tmp_path),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )
    archive = evidence_pack_writer.write_tar_zst(pack, tmp_path / "archives")

    report = evidence_pack_verify.verify_pack(archive, hmac_key=key)

    assert report["verdict"] == "PASS"


def test_safe_extract_tar_rejects_symlink_members(tmp_path):
    archive = tmp_path / "malicious.tar"
    with tarfile.open(archive, "w") as tf:
        member = tarfile.TarInfo("evidence-pack-run/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/tmp/ao-operator-escape"
        tf.addfile(member)

    with pytest.raises(ValueError, match="unsafe tar member type"):
        evidence_pack_verify._safe_extract_tar(archive, tmp_path / "extract")

    assert not (tmp_path / "extract" / "evidence-pack-run" / "link").exists()


def test_replay_pack_validates_deterministic_task_declarations(tmp_path):
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
                    replay_command=["python3", "scripts/replay_intake.py"],
                    replay_outputs=["report.md"],
                )
            ],
        ),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )

    report = evidence_pack_verify.replay_pack(pack, hmac_key=key)

    assert report["verdict"] == "PASS"
    assert report["checks"]["deterministic_non_llm_replay"] == "PASS"
    assert report["deterministic_task_count"] == 1
    assert "Validated 1 deterministic" in report["deterministic_replay_note"]
    assert report["checks"]["deterministic_command_execution"] == "SKIPPED"


def test_replay_pack_executes_deterministic_command_when_explicitly_enabled(tmp_path):
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

    report = evidence_pack_verify.replay_pack(
        pack,
        hmac_key=key,
        execute_deterministic=True,
        deterministic_timeout_seconds=2,
    )

    assert report["verdict"] == "PASS"
    assert report["checks"]["deterministic_command_execution"] == "PASS"
    assert report["deterministic_executions"][0]["verdict"] == "PASS"


def test_replay_pack_resolves_python3_through_portable_python(tmp_path, monkeypatch):
    key = b"0123456789abcdef"
    monkeypatch.setenv("FACTORY_V3_PYTHON", sys.executable)
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
                        "python3",
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

    report = evidence_pack_verify.replay_pack(
        pack,
        hmac_key=key,
        execute_deterministic=True,
        deterministic_timeout_seconds=2,
    )

    assert report["verdict"] == "PASS"
    assert report["checks"]["deterministic_command_execution"] == "PASS"


def test_replay_pack_rejects_deterministic_command_output_hash_mismatch(tmp_path):
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
                        "from pathlib import Path; Path('report.md').write_text('different\\n', encoding='utf-8')",
                    ],
                    replay_outputs=["report.md"],
                )
            ],
        ),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )

    report = evidence_pack_verify.replay_pack(
        pack,
        hmac_key=key,
        execute_deterministic=True,
        deterministic_timeout_seconds=2,
    )

    assert report["verdict"] == "FAIL"
    assert report["checks"]["deterministic_command_execution"] == "FAIL"
    assert "deterministic_replay_output_hash_mismatch:intake:report.md" in report["errors"]


def test_replay_pack_rejects_network_replay_command(tmp_path):
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
                    replay_command=["curl", "https://example.com/report.md"],
                    replay_outputs=["report.md"],
                )
            ],
        ),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )

    report = evidence_pack_verify.replay_pack(
        pack,
        hmac_key=key,
        execute_deterministic=True,
        deterministic_timeout_seconds=2,
    )

    assert report["verdict"] == "FAIL"
    assert report["checks"]["deterministic_command_execution"] == "FAIL"
    assert "deterministic_replay_command_denied:intake:curl" in report["errors"]


def test_replay_pack_rejects_incomplete_deterministic_task_declaration(tmp_path):
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
                    replay_command=[],
                    replay_outputs=["report.md"],
                )
            ],
        ),
        tmp_path / "packs",
        evidence_pack_writer.HMACSigner(key),
    )

    report = evidence_pack_verify.replay_pack(pack, hmac_key=key)

    assert report["verdict"] == "FAIL"
    assert report["checks"]["deterministic_non_llm_replay"] == "FAIL"
    assert "deterministic_replay_command_missing:intake" in report["errors"]


def test_replay_report_example_is_valid_json():
    report = json.loads(
        Path("docs/evidence/evidence-pack-replay-report.example.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["schema"] == "ao-operator/evidence-pack-replay/v1"
    assert report["checks"]["deterministic_non_llm_replay"] == "PASS"
    assert report["deterministic_task_count"] == 1
