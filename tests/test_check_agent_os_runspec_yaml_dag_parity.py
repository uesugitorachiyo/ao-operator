from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_runspec_yaml_dag_parity


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


def runspec_yaml(*, planner_deps: str = "[]", implementer_deps: str = '["agent-os-planner"]') -> str:
    return f"""apiVersion: ao.dev/v1
kind: Run
metadata:
  name: agent-os-phase-draft
spec:
  tasks:
    - id: agent-os-planner
      kind: agent
      deps: {planner_deps}
      spec:
        dispatchAuthorized: false
    - id: agent-os-implementer
      kind: agent
      deps: {implementer_deps}
      spec:
        dispatchAuthorized: false
    - id: agent-os-evaluator-closer
      kind: agent
      deps: ["agent-os-implementer"]
      spec:
        dispatchAuthorized: false
"""


def write_fixture(root: Path, *, yaml_body: str | None = None) -> tuple[Path, Path]:
    runspec_path = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec_path.parent.mkdir(parents=True, exist_ok=True)
    runspec_path.write_text(yaml_body or runspec_yaml(), encoding="utf-8")
    role_graph_path = write_json(root / "role-graph.json", role_graph())
    renderer_path = write_json(root / "renderer.json", renderer_report())
    return renderer_path, role_graph_path


def test_yaml_dag_parity_accepts_yaml_renderer_and_role_graph_alignment(tmp_path):
    renderer_path, role_graph_path = write_fixture(tmp_path)

    payload = check_agent_os_runspec_yaml_dag_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["schema"] == "ao-operator/agent-os-runspec-yaml-dag-parity/v1"
    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 3
    assert payload["yaml_edge_count"] == 2
    assert payload["renderer_edge_count"] == 2
    assert payload["role_graph_edge_count"] == 2
    assert payload["yaml_renderer_alignment"] is True
    assert payload["yaml_role_graph_alignment"] is True
    assert payload["entry_task_ids"] == ["agent-os-planner"]
    assert payload["terminal_task_ids"] == ["agent-os-evaluator-closer"]
    assert payload["mutation_case_count"] == 4
    assert {case["observed_verdict"] for case in payload["mutation_cases"]} == {"FAIL"}
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_yaml_dag_parity_rejects_yaml_only_edge_drift(tmp_path):
    renderer_path, role_graph_path = write_fixture(tmp_path, yaml_body=runspec_yaml(implementer_deps="[]"))

    payload = check_agent_os_runspec_yaml_dag_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "yaml dependency edges must match renderer dependency edges" in payload["errors"]
    assert "yaml dependency edges must match role graph edges" in payload["errors"]
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_yaml_dag_parity_rejects_yaml_cycle(tmp_path):
    renderer_path, role_graph_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_deps='["agent-os-evaluator-closer"]'),
    )

    payload = check_agent_os_runspec_yaml_dag_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
        role_graph_report=role_graph_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("cycle" in error for error in payload["errors"])
