from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_runspec_yaml_semantic_parity


TASKS = [
    {
        "id": "agent-os-planner",
        "deps": [],
        "kind": "agent",
        "spec": {
            "agent": "codex-default",
            "dispatchAuthorized": False,
            "policyProfile": "ao/policy/local-dev.yaml",
            "promptFile": "ao/prompts/agent-os-phase/01-planner.md",
            "provider": "codex",
            "workspace": ".",
        },
    },
    {
        "id": "agent-os-implementer",
        "deps": ["agent-os-planner"],
        "kind": "agent",
        "spec": {
            "agent": "codex-default",
            "dispatchAuthorized": False,
            "policyProfile": "ao/policy/local-dev.yaml",
            "promptFile": "ao/prompts/agent-os-phase/02-implementer.md",
            "provider": "codex",
            "workspace": ".",
        },
    },
    {
        "id": "agent-os-evaluator-closer",
        "deps": ["agent-os-implementer"],
        "kind": "agent",
        "spec": {
            "agent": "codex-default",
            "dispatchAuthorized": False,
            "policyProfile": "ao/policy/local-dev.yaml",
            "promptFile": "ao/prompts/agent-os-phase/03-evaluator-closer.md",
            "provider": "codex",
            "workspace": ".",
        },
    },
]


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def renderer_report(tasks: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "verdict": "PASS",
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "runspec": {"spec": {"tasks": tasks if tasks is not None else TASKS}},
        "task_count": len(tasks if tasks is not None else TASKS),
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def runspec_yaml(
    *,
    planner_provider: str = "codex",
    planner_prompt: str = "ao/prompts/agent-os-phase/01-planner.md",
    planner_workspace: str = ".",
    planner_policy: str = "ao/policy/local-dev.yaml",
    planner_kind: str = "agent",
    planner_dispatch: str = "false",
) -> str:
    return (
        "apiVersion: ao.dev/v1\n"
        "kind: Run\n"
        "metadata:\n"
        "  name: agent-os-phase-draft\n"
        "spec:\n"
        "  tasks:\n"
        "    - id: agent-os-planner\n"
        f"      kind: {planner_kind}\n"
        "      deps: []\n"
        "      spec:\n"
        f"        provider: {planner_provider}\n"
        "        agent: codex-default\n"
        f"        promptFile: {planner_prompt}\n"
        f"        workspace: {planner_workspace}\n"
        f"        policyProfile: {planner_policy}\n"
        f"        dispatchAuthorized: {planner_dispatch}\n"
        "    - id: agent-os-implementer\n"
        "      kind: agent\n"
        "      deps: [\"agent-os-planner\"]\n"
        "      spec:\n"
        "        provider: codex\n"
        "        agent: codex-default\n"
        "        promptFile: ao/prompts/agent-os-phase/02-implementer.md\n"
        "        workspace: .\n"
        "        policyProfile: ao/policy/local-dev.yaml\n"
        "        dispatchAuthorized: false\n"
        "    - id: agent-os-evaluator-closer\n"
        "      kind: agent\n"
        "      deps: [\"agent-os-implementer\"]\n"
        "      spec:\n"
        "        provider: codex\n"
        "        agent: codex-default\n"
        "        promptFile: ao/prompts/agent-os-phase/03-evaluator-closer.md\n"
        "        workspace: .\n"
        "        policyProfile: ao/policy/local-dev.yaml\n"
        "        dispatchAuthorized: false\n"
    )


def write_fixture(root: Path, *, yaml_body: str | None = None) -> Path:
    runspec_path = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec_path.parent.mkdir(parents=True, exist_ok=True)
    runspec_path.write_text(yaml_body or runspec_yaml(), encoding="utf-8")
    return write_json(root / "renderer.json", renderer_report())


def test_yaml_semantic_parity_accepts_full_alignment(tmp_path):
    renderer_path = write_fixture(tmp_path)

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["schema"] == "ao-operator/agent-os-runspec-yaml-semantic-parity/v1"
    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 3
    assert payload["renderer_task_count"] == 3
    assert payload["common_task_count"] == 3
    assert payload["aligned_task_count"] == 3
    assert payload["drifted_task_count"] == 0
    assert payload["all_aligned"] is True
    assert payload["fields_checked"] == [
        "provider",
        "promptFile",
        "workspace",
        "policyProfile",
        "kind",
        "dispatchAuthorized",
    ]
    assert all(ids == [] for ids in payload["field_drift"].values())
    assert payload["mutation_case_count"] == 6
    observed = {case["id"]: case["observed_verdict"] for case in payload["mutation_cases"]}
    assert observed == {
        "yaml_provider_drift_refused": "FAIL",
        "yaml_prompt_drift_refused": "FAIL",
        "yaml_workspace_drift_refused": "FAIL",
        "yaml_policy_drift_refused": "FAIL",
        "yaml_kind_drift_refused": "FAIL",
        "yaml_dispatch_authorized_refused": "FAIL",
    }
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_yaml_semantic_parity_rejects_provider_drift(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_provider="anthropic"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "agent-os-planner" in payload["field_drift"]["provider"]
    assert payload["drifted_task_count"] == 1
    assert payload["all_aligned"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_yaml_semantic_parity_rejects_prompt_drift(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_prompt="ao/prompts/agent-os-phase/99-drifted.md"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "agent-os-planner" in payload["field_drift"]["promptFile"]


def test_yaml_semantic_parity_rejects_workspace_drift(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_workspace="../elsewhere"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "agent-os-planner" in payload["field_drift"]["workspace"]


def test_yaml_semantic_parity_rejects_policy_drift(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_policy="ao/policy/elevated.yaml"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "agent-os-planner" in payload["field_drift"]["policyProfile"]


def test_yaml_semantic_parity_rejects_kind_drift(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_kind="shell"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert "agent-os-planner" in payload["field_drift"]["kind"]


def test_yaml_semantic_parity_rejects_dispatch_authorized_true(tmp_path):
    renderer_path = write_fixture(
        tmp_path,
        yaml_body=runspec_yaml(planner_dispatch="true"),
    )

    payload = check_agent_os_runspec_yaml_semantic_parity.build_report(
        root=tmp_path,
        renderer_report=renderer_path,
    )

    assert payload["verdict"] == "FAIL"
    assert any("dispatchAuthorized" in error or "dispatch" in error.lower() for error in payload["errors"])
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
