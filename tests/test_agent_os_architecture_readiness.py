from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import summarize_agent_os_architecture_readiness


def write_json(root: Path, rel: str, payload: dict) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def baseline(schema: str, **extra: object) -> dict:
    payload = {
        "schema": schema,
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    payload.update(extra)
    return payload


def write_baselines(root: Path) -> None:
    write_json(
        root,
        "role-graph.json",
        baseline(
            "ao-operator/agent-os-role-graph/v1",
            role_count=7,
            state_schema_version="ao-operator/agent-os-state/v2",
        ),
    )
    write_json(
        root,
        "state-v2.json",
        baseline(
            "ao-operator/agent-os-state/v2",
            role_graph_schema="ao-operator/agent-os-role-graph/v1",
        ),
    )
    write_json(
        root,
        "commit-guard.json",
        baseline(
            "ao-operator/agent-os-accepted-execution-commit-guard/v1",
            commit_success_evidence_allowed=False,
            raw_snapshot_commit_allowed=False,
        ),
    )
    write_json(
        root,
        "route-matrix.json",
        baseline("ao-operator/agent-os-postrun-route-matrix/v1", case_count=6),
    )
    write_json(
        root,
        "runspec-matrix.json",
        baseline("ao-operator/agent-os-runspec-compatibility-matrix/v1", case_count=3),
    )


def test_architecture_readiness_passes_when_all_baselines_are_safe(tmp_path):
    write_baselines(tmp_path)

    payload = summarize_agent_os_architecture_readiness.summarize(
        root=tmp_path,
        role_graph="role-graph.json",
        state_v2="state-v2.json",
        commit_guard="commit-guard.json",
        route_matrix="route-matrix.json",
        runspec_matrix="runspec-matrix.json",
    )

    assert payload["verdict"] == "PASS"
    assert payload["architecture_ready"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["baseline_count"] == 5
    assert payload["next_safe_command"] == "Start router architecture implementation behind these compatibility baselines."


def test_architecture_readiness_fails_when_baseline_allows_dispatch(tmp_path):
    write_baselines(tmp_path)
    write_json(
        tmp_path,
        "runspec-matrix.json",
        baseline(
            "ao-operator/agent-os-runspec-compatibility-matrix/v1",
            case_count=3,
            dispatch_authorized=True,
        ),
    )

    payload = summarize_agent_os_architecture_readiness.summarize(
        root=tmp_path,
        role_graph="role-graph.json",
        state_v2="state-v2.json",
        commit_guard="commit-guard.json",
        route_matrix="route-matrix.json",
        runspec_matrix="runspec-matrix.json",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["architecture_ready"] is False
    assert any("runspec_matrix dispatch_authorized must remain false" in blocker for blocker in payload["blockers"])


def test_architecture_readiness_fails_when_commit_guard_allows_success_commit(tmp_path):
    write_baselines(tmp_path)
    write_json(
        tmp_path,
        "commit-guard.json",
        baseline(
            "ao-operator/agent-os-accepted-execution-commit-guard/v1",
            commit_success_evidence_allowed=True,
            raw_snapshot_commit_allowed=False,
        ),
    )

    payload = summarize_agent_os_architecture_readiness.summarize(
        root=tmp_path,
        role_graph="role-graph.json",
        state_v2="state-v2.json",
        commit_guard="commit-guard.json",
        route_matrix="route-matrix.json",
        runspec_matrix="runspec-matrix.json",
    )

    assert payload["verdict"] == "FAIL"
    assert "commit_guard must not allow success evidence commits before accepted execution" in payload["blockers"]


def test_cli_writes_architecture_readiness_summary(tmp_path):
    write_baselines(tmp_path)
    output = tmp_path / "summary.json"

    code = summarize_agent_os_architecture_readiness.main(
        [
            "--root",
            str(tmp_path),
            "--role-graph",
            "role-graph.json",
            "--state-v2",
            "state-v2.json",
            "--commit-guard",
            "commit-guard.json",
            "--route-matrix",
            "route-matrix.json",
            "--runspec-matrix",
            "runspec-matrix.json",
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert output.is_file()
    assert "ao-operator/agent-os-architecture-readiness/v1" in output.read_text(encoding="utf-8")
