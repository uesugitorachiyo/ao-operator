from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import check_agent_os_runspec_dag_edge_coverage


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def role_graph() -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-role-graph/v1",
        "verdict": "PASS",
        "roles": [
            {"id": "planner"},
            {"id": "implementer"},
            {"id": "evaluator-closer"},
        ],
        "edges": [
            {"from": "planner", "to": "implementer"},
            {"from": "implementer", "to": "evaluator-closer"},
        ],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def renderer_report() -> dict[str, object]:
    tasks = [
        {
            "id": "agent-os-planner",
            "kind": "agent",
            "deps": [],
            "spec": {
                "provider": "codex",
                "dispatchAuthorized": False,
                "promptFile": "ao/prompts/agent-os-phase/01-planner.md",
            },
        },
        {
            "id": "agent-os-implementer",
            "kind": "agent",
            "deps": ["agent-os-planner"],
            "spec": {
                "provider": "codex",
                "dispatchAuthorized": False,
                "promptFile": "ao/prompts/agent-os-phase/02-implementer.md",
            },
        },
        {
            "id": "agent-os-evaluator-closer",
            "kind": "agent",
            "deps": ["agent-os-implementer"],
            "spec": {
                "provider": "codex",
                "dispatchAuthorized": False,
                "promptFile": "ao/prompts/agent-os-phase/03-evaluator-closer.md",
            },
        },
    ]
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "verdict": "PASS",
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec": {"spec": {"tasks": tasks}},
        "task_count": 3,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def write_fixture(root: Path, *, report: dict[str, object] | None = None) -> tuple[Path, Path]:
    role_graph_path = write_json(root / "role-graph.json", role_graph())
    renderer_path = write_json(root / "renderer.json", report or renderer_report())
    return renderer_path, role_graph_path


def test_dag_edge_coverage_accepts_linear_role_graph_aligned_runspec(tmp_path):
    renderer_path, role_graph_path = write_fixture(tmp_path)

    payload = check_agent_os_runspec_dag_edge_coverage.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["schema"] == "ao-operator/agent-os-runspec-dag-edge-coverage/v1"
    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 3
    assert payload["edge_count"] == 2
    assert payload["entry_task_ids"] == ["agent-os-planner"]
    assert payload["terminal_task_ids"] == ["agent-os-evaluator-closer"]
    assert payload["role_graph_alignment"] is True
    assert payload["topological_task_ids"] == [
        "agent-os-planner",
        "agent-os-implementer",
        "agent-os-evaluator-closer",
    ]
    assert payload["mutation_case_count"] == 5
    assert {case["observed_verdict"] for case in payload["mutation_cases"]} == {"FAIL"}
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_dag_edge_coverage_rejects_cycle_in_runspec(tmp_path):
    mutated = deepcopy(renderer_report())
    tasks = mutated["runspec"]["spec"]["tasks"]  # type: ignore[index]
    tasks[0]["deps"] = ["agent-os-evaluator-closer"]
    renderer_path, role_graph_path = write_fixture(tmp_path, report=mutated)

    payload = check_agent_os_runspec_dag_edge_coverage.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("cycle" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_dag_edge_coverage_rejects_role_graph_edge_drift(tmp_path):
    mutated = deepcopy(renderer_report())
    tasks = mutated["runspec"]["spec"]["tasks"]  # type: ignore[index]
    tasks[1]["deps"] = []
    renderer_path, role_graph_path = write_fixture(tmp_path, report=mutated)

    payload = check_agent_os_runspec_dag_edge_coverage.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "runspec direct dependency edges must match role graph edges" in payload["errors"]
    assert payload["entry_task_ids"] == ["agent-os-implementer", "agent-os-planner"]
