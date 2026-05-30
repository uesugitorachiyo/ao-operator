from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_release_handoff_checklist.py"


def raw_handoff(provider_status: str = "live_complete", claude_source: str = "live") -> dict:
    return {
        "schema_version": "ao2.cp-release-candidate-handoff.v1",
        "status": "ready",
        "handoff_kind": "phase1_release_candidate",
        "release": {
            "version": "0.4.79",
            "release_tag": "v0.4.79",
            "sha256": "a" * 64,
            "repositories": {
                "ao2": {"head": "1" * 40},
                "factory_v3": {"head": "2" * 40},
                "ao2_control_plane": {"head": "3" * 40},
            },
        },
        "gates": {
            "release_cockpit": "ready",
            "phase1_promotion": "observed",
            "decision_signature": "present",
            "provider_acceptance": provider_status,
        },
        "acceptance": {
            "codex": {
                "provider": "codex",
                "status": "passed",
                "source_class": "live",
                "run_id": "codex-live",
                "score": 1.0,
            },
            "claude": {
                "provider": "claude",
                "status": "passed",
                "source_class": claude_source,
                "run_id": "claude-live",
                "score": 1.0,
            },
        },
        "operator_handoff": {
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "front_end": "Hermes front end / queue / memory surface",
            "trusted_execution": "ao2 signed evidence boundary",
        },
        "links": {
            "release_candidate_handoff": "/api/v1/release/handoff",
            "release_candidate_handoff_json": "/api/v1/release/handoff.json",
        },
        "trust_boundary": {
            "role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
    }


def bridge_handoff(provider_status: str = "live_complete", claude_source: str = "live") -> dict:
    return {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-handoff-status",
        "status": "ready",
        "handoff_snapshot": raw_handoff(provider_status, claude_source),
        "links": {
            "release_candidate_handoff": "http://127.0.0.1:8744/api/v1/release/handoff",
            "release_candidate_handoff_json": "http://127.0.0.1:8744/api/v1/release/handoff.json",
        },
    }


def run_checklist(
    tmp_path: Path,
    handoff: dict,
    extra_args: list[str] | None = None,
) -> tuple[dict, Path]:
    handoff_path = tmp_path / "release-handoff-status.json"
    json_path = tmp_path / "release-handoff-checklist.json"
    md_path = tmp_path / "release-handoff-checklist.md"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--handoff",
            str(handoff_path),
            "--write-json",
            str(json_path),
            "--write-md",
            str(md_path),
            *(extra_args or []),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    return payload, md_path


def test_ao2_release_handoff_checklist_accepts_ready_bridge_handoff(tmp_path: Path) -> None:
    payload, md_path = run_checklist(
        tmp_path,
        bridge_handoff(),
        [
            "--expected-repo-head",
            "ao2=" + "1" * 40,
            "--expected-repo-head",
            "factory_v3=" + "2" * 40,
            "--expected-repo-head",
            "ao2_control_plane=" + "3" * 40,
        ],
    )

    assert payload["schema"] == "ao-operator/ao2-release-handoff-checklist/v1"
    assert payload["status"] == "ready_for_evaluator_closer"
    assert payload["release"]["release_tag"] == "v0.4.79"
    assert payload["blockers"] == []
    assert payload["operator_decision"]["factory_v3_evaluator_closer_required"] is True
    assert payload["operator_decision"]["control_plane_approves_release"] is False
    assert any(check["id"] == "provider_acceptance" for check in payload["checks"])
    markdown = md_path.read_text(encoding="utf-8")
    assert "AO2 Release Handoff Checklist" in markdown
    assert "ready_for_evaluator_closer" in markdown
    assert "ao-operator evaluator-closer" in markdown


def test_ao2_release_handoff_checklist_blocks_non_live_acceptance(tmp_path: Path) -> None:
    payload, _ = run_checklist(tmp_path, bridge_handoff(claude_source="planned"))

    assert payload["status"] == "blocked"
    assert any("claude_acceptance" in blocker for blocker in payload["blockers"])


def test_ao2_release_handoff_checklist_blocks_stale_release_publication_head(
    tmp_path: Path,
) -> None:
    payload, _ = run_checklist(
        tmp_path,
        bridge_handoff(),
        [
            "--expected-repo-head",
            "ao2=" + "9" * 40,
            "--expected-repo-head",
            "factory_v3=" + "2" * 40,
            "--expected-repo-head",
            "ao2_control_plane=" + "3" * 40,
        ],
    )

    assert payload["status"] == "blocked"
    assert any("repo_head_ao2" in blocker for blocker in payload["blockers"])
    check = next(item for item in payload["checks"] if item["id"] == "repo_head_ao2")
    assert check["observed"] == "1" * 40
    assert check["expected"] == "9" * 40


def test_ao2_release_handoff_checklist_allows_docs_only_metadata_refresh(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "ao2"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    docs_dir = repo / "run-artifacts" / "release-candidates"
    docs_dir.mkdir(parents=True)
    release_doc = docs_dir / "v0.4.80-phase1-release.json"
    release_doc.write_text('{"version":"0.4.80"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "release evidence"], cwd=repo, check=True, stdout=subprocess.PIPE)
    observed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    release_doc.write_text('{"version":"0.4.80","refreshed":true}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "refresh release evidence"], cwd=repo, check=True, stdout=subprocess.PIPE)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    handoff = bridge_handoff()
    handoff["handoff_snapshot"]["release"]["repositories"]["ao2"]["head"] = observed
    handoff["handoff_snapshot"]["release"]["repositories"]["ao2"]["path"] = str(repo)

    payload, _ = run_checklist(
        tmp_path,
        handoff,
        [
            "--expected-repo-head",
            f"ao2={expected}",
            "--expected-repo-head",
            "factory_v3=" + "2" * 40,
            "--expected-repo-head",
            "ao2_control_plane=" + "3" * 40,
        ],
    )

    assert payload["status"] == "ready_for_evaluator_closer"
    check = next(item for item in payload["checks"] if item["id"] == "repo_head_ao2")
    assert check["status"] == "passed_with_metadata_refresh"
    assert check["metadata_refresh_paths"] == [
        "run-artifacts/release-candidates/v0.4.80-phase1-release.json"
    ]
