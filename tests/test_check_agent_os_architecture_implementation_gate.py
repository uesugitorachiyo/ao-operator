from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_architecture_implementation_gate


STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"


def write_json(root: Path, rel: str, payload: dict[str, object]) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def report(schema: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": schema,
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    payload.update(extra)
    return payload


def seed_architecture_reports(root: Path) -> None:
    roles = [
        "planner",
        "plan-hardener",
        "factory-manager",
        "implementer",
        "slice-reviewer",
        "integrator",
        "evaluator-closer",
    ]
    tasks = [
        {
            "id": f"agent-os-{role}",
            "deps": [] if index == 0 else [f"agent-os-{roles[index - 1]}"],
            "spec": {
                "dispatchAuthorized": False,
                "promptFile": f"ao/prompts/agent-os-phase/{index + 1:02d}-{role}.md",
                "provider": "codex",
            },
        }
        for index, role in enumerate(roles)
    ]
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-architecture-readiness.json",
        report("ao-operator/agent-os-architecture-readiness/v1", architecture_ready=True),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-role-graph.json",
        report(
            "ao-operator/agent-os-role-graph/v1",
            role_count=7,
            roles=[{"id": role} for role in roles],
            state_schema_version="ao-operator/agent-os-state/v2",
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-router-v2-state.json",
        report(
            "ao-operator/agent-os-state/v2",
            architecture_ready=True,
            blockers=[],
            role_graph_schema="ao-operator/agent-os-role-graph/v1",
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-state-v2.json",
        report(
            "ao-operator/agent-os-state/v2",
            blockers=[],
            role_graph_schema="ao-operator/agent-os-role-graph/v1",
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-phase-handoff.json",
        report(
            "ao-operator/agent-os-phase-handoff/v1",
            handoff_packets=[
                {
                    "packet_id": f"{index + 1:02d}-{role}",
                    "role": role,
                    "dispatch_mode": "ao-role",
                    "depends_on": [] if index == 0 else [roles[index - 1]],
                }
                for index, role in enumerate(roles)
            ],
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-runspec-renderer.json",
        report(
            "ao-operator/agent-os-runspec-renderer/v1",
            architecture_ready=True,
            role_graph_schema="ao-operator/agent-os-role-graph/v1",
            state_baseline=f"{STATUS_ROOT}/agent-os-router-v2-state.json",
            state_baseline_checked=True,
            state_schema_version="ao-operator/agent-os-state/v2",
            task_count=7,
            runspec={"spec": {"tasks": tasks}},
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-runspec-validation.json",
        report(
            "ao-operator/agent-os-runspec-validation/v1",
            provider_profile_matches=True,
            prompt_files_checked=7,
            task_count=7,
        ),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-runspec-provider-boundary-matrix.json",
        report("ao-operator/agent-os-runspec-provider-boundary-matrix/v1", case_count=4),
    )
    write_json(
        root,
        f"{STATUS_ROOT}/agent-os-execution-hygiene.json",
        report("ao-operator/agent-os-execution-hygiene/v1"),
    )
    for rel in [
        "scripts/agent_os_role_graph.py",
        "scripts/agent_os_router.py",
        "scripts/agent_os_state_v2.py",
        "scripts/agent_os_runspec_renderer.py",
        "scripts/agent_os_runspec_validator.py",
        "scripts/run_agent_os_runspec_execution.py",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# implementation surface\n", encoding="utf-8")


def test_architecture_implementation_gate_passes_for_coherent_surfaces(tmp_path):
    seed_architecture_reports(tmp_path)

    payload = check_agent_os_architecture_implementation_gate.summarize(root=tmp_path)

    assert payload["schema"] == "ao-operator/agent-os-architecture-implementation-gate/v1"
    assert payload["verdict"] == "PASS"
    assert payload["implementation_ready"] is True
    assert payload["role_count"] == 7
    assert payload["handoff_packet_count"] == 7
    assert payload["runspec_task_count"] == 7
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["checks"]["role_handoff_runspec_alignment"] == "PASS"


def test_architecture_implementation_gate_fails_when_renderer_allows_dispatch(tmp_path):
    seed_architecture_reports(tmp_path)
    renderer_path = tmp_path / STATUS_ROOT / "agent-os-runspec-renderer.json"
    renderer = json.loads(renderer_path.read_text(encoding="utf-8"))
    renderer["runspec"]["spec"]["tasks"][0]["spec"]["dispatchAuthorized"] = True
    write_json(tmp_path, f"{STATUS_ROOT}/agent-os-runspec-renderer.json", renderer)

    payload = check_agent_os_architecture_implementation_gate.summarize(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert payload["implementation_ready"] is False
    assert "runspec task agent-os-planner dispatchAuthorized must be false" in payload["blockers"]


def test_architecture_implementation_gate_fails_when_roles_and_handoff_drift(tmp_path):
    seed_architecture_reports(tmp_path)
    handoff_path = tmp_path / STATUS_ROOT / "agent-os-phase-handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_packets"].pop()
    write_json(tmp_path, f"{STATUS_ROOT}/agent-os-phase-handoff.json", handoff)

    payload = check_agent_os_architecture_implementation_gate.summarize(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert "role graph roles must match handoff packet roles" in payload["blockers"]


def test_architecture_implementation_gate_cli_writes_output(tmp_path, capsys):
    seed_architecture_reports(tmp_path)
    output = tmp_path / STATUS_ROOT / "agent-os-architecture-implementation-gate.json"

    code = check_agent_os_architecture_implementation_gate.main(
        ["--root", str(tmp_path), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-architecture-implementation-gate/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
