from __future__ import annotations

import json
from pathlib import Path

import check_live_success_commit_guard
from test_check_live_acceptance import write_live_artifacts


def write_routing(
    path: Path,
    *,
    classification: str = "PENDING_LIVE_RUN",
    route: str = "WAIT_FOR_LIVE_RUN",
    commit_allowed: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "ao-operator/live-postrun-routing/v1",
                "classification": classification,
                "route": route,
                "commit_success_evidence_allowed": commit_allowed,
                "raw_snapshot_commit_allowed": False,
                "live_providers_run": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_pending_route_passes_but_blocks_success_commit(tmp_path):
    routing = write_routing(tmp_path / "routing.json")

    payload = check_live_success_commit_guard.check_guard(root=tmp_path, routing_path=routing)

    assert payload["verdict"] == "PASS"
    assert payload["classification"] == "PENDING_LIVE_RUN"
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["raw_snapshot_commit_allowed"] is False
    assert payload["live_providers_run"] is False


def test_run_acceptance_route_allows_commit_when_acceptance_passes(tmp_path):
    write_live_artifacts(tmp_path)
    routing = write_routing(
        tmp_path / "routing.json",
        classification="ACCEPTED",
        route="RUN_ACCEPTANCE",
        commit_allowed=True,
    )

    payload = check_live_success_commit_guard.check_guard(root=tmp_path, routing_path=routing)

    assert payload["verdict"] == "PASS"
    assert payload["acceptance_verdict"] == "PASS"
    assert payload["commit_success_evidence_allowed"] is True


def test_run_acceptance_route_fails_when_acceptance_fails(tmp_path):
    routing = write_routing(
        tmp_path / "routing.json",
        classification="ACCEPTED",
        route="RUN_ACCEPTANCE",
        commit_allowed=True,
    )

    payload = check_live_success_commit_guard.check_guard(root=tmp_path, routing_path=routing)

    assert payload["verdict"] == "FAIL"
    assert payload["commit_success_evidence_allowed"] is False
    assert any("requires live acceptance PASS" in error for error in payload["errors"])


def test_acceptance_pass_requires_run_acceptance_route(tmp_path):
    write_live_artifacts(tmp_path)
    routing = write_routing(tmp_path / "routing.json")

    payload = check_live_success_commit_guard.check_guard(root=tmp_path, routing_path=routing)

    assert payload["verdict"] == "FAIL"
    assert any("live acceptance PASS requires postrun route RUN_ACCEPTANCE" in error for error in payload["errors"])


def test_fails_for_missing_routing(tmp_path):
    payload = check_live_success_commit_guard.check_guard(root=tmp_path, routing_path=tmp_path / "missing.json")

    assert payload["verdict"] == "FAIL"
    assert any("postrun routing unavailable" in error for error in payload["errors"])


def test_main_writes_output(tmp_path, capsys):
    routing = write_routing(tmp_path / "routing.json")
    output = tmp_path / "guard.json"

    result = check_live_success_commit_guard.main(
        [
            "--root",
            str(tmp_path),
            "--routing",
            str(routing),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == "ao-operator/live-success-commit-guard/v1"
    assert written["commit_success_evidence_allowed"] is False
