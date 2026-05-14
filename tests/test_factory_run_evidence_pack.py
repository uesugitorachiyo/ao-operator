from __future__ import annotations

import builtins
import json
import shutil
from pathlib import Path

import pytest

import evidence_pack_verify
import factory_run


def _force_missing_cryptography(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("cryptography"):
            raise ImportError("cryptography intentionally unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def _intake() -> factory_run.Intake:
    return factory_run.Intake(
        slug="evidence-pack-live",
        brief_path=Path("brief.md"),
        brief="Goal: evidence pack live integration",
        classification="small",
        shape="bug-fix",
        blocked=False,
        blocker="",
        acceptance=["pack verifies"],
        scoped_reads=[],
        scoped_writes=[],
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    status = tmp_path / "run-artifacts" / "evidence-pack-live"
    roles = status / "roles"
    patches = status / "patches"
    roles.mkdir(parents=True)
    patches.mkdir()
    paths = {
        "status": status / "evidence-pack-live-status.md",
        "evaluation": tmp_path / "docs" / "evaluations" / "evidence-pack-live-evaluation.md",
        "events": status / "evidence-pack-live-ao-events.md",
        "roles_dir": roles,
        "patches_dir": patches,
        "evidence_packs_dir": status / "evidence-packs",
    }
    paths["evaluation"].parent.mkdir(parents=True)
    paths["status"].write_text("# status\n", encoding="utf-8")
    paths["evaluation"].write_text("# evaluation\n", encoding="utf-8")
    paths["events"].write_text("2026-05-11T18:00:01+00:00  task.completed task=intake {}\n", encoding="utf-8")
    (roles / "intake.md").write_text("Result: DONE\n", encoding="utf-8")
    (patches / "implementer.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
    return paths


def _repo_path(root: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _requires_zstd() -> None:
    if shutil.which("zstd") is None:
        pytest.skip("zstd CLI is not available")


def test_write_live_evidence_pack_outputs_replayable_archive(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()

    report = factory_run.write_live_evidence_pack(
        paths=_paths(tmp_path),
        intake=_intake(),
        tasks=[{"id": "intake", "role": "Planner Intake"}],
        providers={"intake": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    assert report["verdict"] == "PASS"
    assert _repo_path(tmp_path, report["archive"]).is_file()
    assert evidence_pack_verify.verify_pack(_repo_path(tmp_path, report["archive"]), hmac_key=bytes.fromhex(key_hex))["verdict"] == "PASS"


def test_write_live_evidence_pack_records_summary_json(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()

    report = factory_run.write_live_evidence_pack(
        paths=_paths(tmp_path),
        intake=_intake(),
        tasks=[{"id": "intake", "role": "Planner Intake"}],
        providers={"intake": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    summary = json.loads(Path(str(report["summary"])).read_text(encoding="utf-8"))
    assert summary["schema"] == "ao-operator/evidence-pack-live-run/v1"
    assert summary["verify"]["verdict"] == "PASS"
    assert summary["replay"]["verdict"] == "PASS"
    assert summary["pack"] == "run-artifacts/evidence-pack-live/evidence-packs/evidence-pack-feedfacecafebeef"
    assert summary["archive"] == "run-artifacts/evidence-pack-live/evidence-packs/evidence-pack-feedfacecafebeef.tar.zst"
    assert summary["verify"]["pack"] == "run-artifacts/evidence-pack-live/evidence-packs/evidence-pack-feedfacecafebeef.tar.zst"
    assert summary["replay"]["pack"] == "run-artifacts/evidence-pack-live/evidence-packs/evidence-pack-feedfacecafebeef.tar.zst"


def test_write_live_evidence_pack_preserves_deterministic_task_metadata(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()

    report = factory_run.write_live_evidence_pack(
        paths=_paths(tmp_path),
        intake=_intake(),
        tasks=[
            {
                "id": "intake",
                "role": "Planner Intake",
                "deterministic": True,
                "replay_command": ["python3", "scripts/replay_intake.py"],
                "replay_outputs": ["evidence-pack-live-status.md"],
            }
        ],
        providers={"intake": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    manifest = json.loads((_repo_path(tmp_path, report["pack"]) / "manifest.json").read_text(encoding="utf-8"))
    task = manifest["tasks"][0]
    assert task["deterministic"] is True
    assert task["replay_command"] == ["python3", "scripts/replay_intake.py"]
    assert task["replay_outputs"] == ["evidence-pack-live-status.md"]
    replay = evidence_pack_verify.replay_pack(
        _repo_path(tmp_path, report["pack"]),
        hmac_key=bytes.fromhex(key_hex),
    )
    assert replay["checks"]["deterministic_non_llm_replay"] == "PASS"


def test_write_live_evidence_pack_executes_deterministic_replay_when_enabled(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()
    status_name = "evidence-pack-live-status.md"

    report = factory_run.write_live_evidence_pack(
        paths=_paths(tmp_path),
        intake=_intake(),
        tasks=[
            {
                "id": "intake",
                "role": "Planner Intake",
                "deterministic": True,
                "replay_command": [
                    "python3",
                    "-c",
                    "from pathlib import Path; Path('evidence-pack-live-status.md').write_text('# status\\n', encoding='utf-8')",
                ],
                "replay_outputs": [status_name],
            }
        ],
        providers={"intake": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        execute_deterministic_replay=True,
        deterministic_replay_timeout_seconds=2,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    assert report["verdict"] == "PASS"
    assert report["replay"]["checks"]["deterministic_command_execution"] == "PASS"
    summary = json.loads(Path(str(report["summary"])).read_text(encoding="utf-8"))
    assert summary["replay"]["checks"]["deterministic_command_execution"] == "PASS"


def test_write_live_evidence_pack_materializes_missing_deterministic_outputs(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()
    paths = _paths(tmp_path)
    paths["events"].write_text(
        "2026-05-11T18:00:01+00:00  task.completed task=report-writer {}\n",
        encoding="utf-8",
    )

    report = factory_run.write_live_evidence_pack(
        paths=paths,
        intake=_intake(),
        tasks=[
            {
                "id": "report-writer",
                "role": "Evidence Report Writer",
                "deterministic": True,
                "replay_command": [
                    "python3",
                    "-c",
                    "from pathlib import Path; Path('evidence-profile-deterministic-replay.json').write_text('{\"schema\":\"ao-operator/evidence-profile-deterministic-replay/v1\",\"verdict\":\"PASS\"}\\n', encoding='utf-8')",
                ],
                "replay_outputs": ["evidence-profile-deterministic-replay.json"],
            }
        ],
        providers={"report-writer": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        execute_deterministic_replay=True,
        deterministic_replay_timeout_seconds=2,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    materialized = (
        tmp_path
        / "docs"
        / "status"
        / "evidence-pack-live"
        / "deterministic-replay"
        / "report-writer"
        / "evidence-profile-deterministic-replay.json"
    )
    assert materialized.is_file()
    assert report["verdict"] == "PASS"
    assert report["replay"]["checks"]["deterministic_command_execution"] == "PASS"
    manifest = json.loads((_repo_path(tmp_path, report["pack"]) / "manifest.json").read_text(encoding="utf-8"))
    task = manifest["tasks"][0]
    assert len(task["artifact_shas"]) == 1


def test_materialize_declared_status_artifacts_writes_profile_report(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    paths = _paths(tmp_path)
    event_text = "\n".join(
        [
            "2026-05-11T18:00:01+00:00  agent.stdout                  task=report-writer                {\"line\": \"Result: DONE\\nArtifact: docs/evidence/evidence-pack-live/evidence-report.md\\nEvidence:\\n- schema: ao-operator/evidence-report/v1\\nConcerns:\\n- none\\nBlocker: none\"}",
            "2026-05-11T18:00:02+00:00  task.completed                task=report-writer                {}",
        ]
    )

    written = factory_run.materialize_declared_status_artifacts(
        paths,
        _intake(),
        event_text,
        [{"id": "report-writer", "writes": ["docs/evidence/<slug>/evidence-report.md"]}],
    )

    report = tmp_path / "docs" / "evidence" / "evidence-pack-live" / "evidence-report.md"
    assert written == [report]
    body = report.read_text(encoding="utf-8")
    assert "schema: ao-operator/evidence-report/v1" in body
    assert "slug: evidence-pack-live" in body
    assert "Artifact: docs/evidence/evidence-pack-live/evidence-report.md" in body


def test_write_live_evidence_pack_redacts_public_sources_before_hashing(tmp_path, monkeypatch):
    _requires_zstd()
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    key_hex = b"0123456789abcdef".hex()
    paths = _paths(tmp_path)
    paths["status"].write_text("workspace=/Users/example/private/ao-operator\n", encoding="utf-8")

    report = factory_run.write_live_evidence_pack(
        paths=paths,
        intake=_intake(),
        tasks=[{"id": "intake", "role": "Planner Intake"}],
        providers={"intake": "codex"},
        run_id="feedfacecafebeef",
        hmac_key_hex=key_hex,
        factory_version="test-factory",
        ao_runtime_version="test-ao",
    )

    assert report["verdict"] == "PASS"
    assert "[REDACTED_LOCAL_PATH]" in paths["status"].read_text(encoding="utf-8")
    assert "/Users/example" not in paths["status"].read_text(encoding="utf-8")
    pack_root = _repo_path(tmp_path, report["pack"])
    redacted_artifacts = [
        path.read_text(encoding="utf-8")
        for path in (pack_root / "artifacts").glob("*/evidence-pack-live-status.md")
    ]
    assert redacted_artifacts == ["workspace=[REDACTED_LOCAL_PATH]\n"]


def test_write_live_evidence_pack_requires_exactly_one_signer(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)

    try:
        factory_run.write_live_evidence_pack(
            paths=_paths(tmp_path),
            intake=_intake(),
            tasks=[{"id": "intake", "role": "Planner Intake"}],
            providers={"intake": "codex"},
            run_id="feedfacecafebeef",
            hmac_key_hex="",
            ed25519_private_key=None,
            factory_version="test-factory",
            ao_runtime_version="test-ao",
        )
    except ValueError as exc:
        assert "exactly one evidence-pack signer" in str(exc)
    else:
        raise AssertionError("expected missing signer to raise")


def test_write_live_evidence_pack_accepts_ed25519_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    _force_missing_cryptography(monkeypatch)

    try:
        factory_run.write_live_evidence_pack(
            paths=_paths(tmp_path),
            intake=_intake(),
            tasks=[{"id": "intake", "role": "Planner Intake"}],
            providers={"intake": "codex"},
            run_id="feedfacecafebeef",
            hmac_key_hex=None,
            ed25519_private_key=tmp_path / "operator-ed25519.pem",
            factory_version="test-factory",
            ao_runtime_version="test-ao",
        )
    except ImportError as exc:
        assert "install cryptography" in str(exc)
    else:
        raise AssertionError("expected missing optional cryptography to raise in this environment")
