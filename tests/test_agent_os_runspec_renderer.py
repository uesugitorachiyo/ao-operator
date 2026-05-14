from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import agent_os_runspec_renderer


def handoff(*, dispatch_authorized: bool = False) -> dict:
    return {
        "schema": "ao-operator/agent-os-phase-handoff/v1",
        "verdict": "PASS",
        "dispatch_authorized": dispatch_authorized,
        "live_providers_run": False,
        "handoff_packets": [
            {
                "packet_id": "01-planner",
                "role": "planner",
                "depends_on": [],
                "dispatch_mode": "ao-role",
                "scoped_context": {
                    "reads": ["task brief"],
                    "writes": ["docs/specs/"],
                },
                "verification_commands": ["python3 scripts/validate_factory.py --json"],
            },
            {
                "packet_id": "02-implementer",
                "role": "implementer",
                "depends_on": ["planner"],
                "dispatch_mode": "ao-role",
                "scoped_context": {
                    "reads": ["slice contract"],
                    "writes": ["declared writes"],
                },
                "verification_commands": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
            },
        ],
    }


def write_handoff(root: Path, payload: dict) -> Path:
    path = root / "handoff.json"
    path.write_text(agent_os_runspec_renderer.json_dumps(payload), encoding="utf-8")
    return path


def write_provider_profile(root: Path, body: str) -> Path:
    path = root / "provider.env"
    path.write_text(body, encoding="utf-8")
    return path


def write_state_baseline(
    root: Path,
    *,
    dispatch_authorized: bool = False,
    architecture_ready: bool = True,
    verdict: str = "PASS",
) -> Path:
    path = root / "state-v2.json"
    path.write_text(
        agent_os_runspec_renderer.json_dumps(
            {
                "schema": "ao-operator/agent-os-state/v2",
                "verdict": verdict,
                "architecture_ready": architecture_ready,
                "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
                "dispatch_authorized": dispatch_authorized,
                "live_providers_run": False,
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_renderer_builds_non_dispatch_runspec_from_handoff_packets(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    payload = agent_os_runspec_renderer.render_agent_os_runspec(root=tmp_path, handoff_report=handoff_path)

    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["runspec"]["metadata"]["name"] == "agent-os-phase-draft"
    assert payload["runspec"]["spec"]["tasks"][0]["id"] == "agent-os-planner"
    assert payload["runspec"]["spec"]["tasks"][1]["deps"] == ["agent-os-planner"]
    assert payload["runspec"]["spec"]["tasks"][0]["spec"]["promptFile"].endswith("01-planner.md")
    assert payload["runspec"]["spec"]["tasks"][0]["spec"]["workspace"] == "."


def test_renderer_applies_provider_profile_by_role(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    profile = write_provider_profile(
        tmp_path,
        "\n".join(
            [
                "FACTORY_V3_DEFAULT_PROVIDER=codex",
                "FACTORY_V3_PLANNER_PROVIDER=claude",
                "FACTORY_V3_IMPLEMENTER_PROVIDER=codex",
            ]
        ),
    )

    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=tmp_path,
        handoff_report=handoff_path,
        provider_profile=profile,
    )

    tasks = payload["runspec"]["spec"]["tasks"]
    assert payload["verdict"] == "PASS"
    assert payload["provider_profile"] == "provider.env"
    assert payload["provider_profile_checked"] is True
    assert tasks[0]["spec"]["provider"] == "claude"
    assert tasks[0]["spec"]["agent"] == "claude-default"
    assert tasks[1]["spec"]["provider"] == "codex"
    assert tasks[1]["spec"]["agent"] == "codex-default"


def test_renderer_records_state_v2_baseline_metadata(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    state = write_state_baseline(tmp_path)

    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=tmp_path,
        handoff_report=handoff_path,
        state_baseline=state,
    )

    assert payload["verdict"] == "PASS"
    assert payload["state_baseline_checked"] is True
    assert payload["state_baseline"] == "state-v2.json"
    assert payload["state_schema_version"] == "ao-operator/agent-os-state/v2"
    assert payload["role_graph_schema"] == "ao-operator/agent-os-role-graph/v1"
    assert payload["architecture_ready"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_renderer_fails_closed_when_state_v2_authorizes_dispatch(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    state = write_state_baseline(tmp_path, dispatch_authorized=True)

    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=tmp_path,
        handoff_report=handoff_path,
        state_baseline=state,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert "state baseline dispatch_authorized must remain false" in payload["errors"]


def test_renderer_fails_closed_when_state_v2_is_not_architecture_ready(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    state = write_state_baseline(tmp_path, architecture_ready=False, verdict="FAIL")

    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=tmp_path,
        handoff_report=handoff_path,
        state_baseline=state,
    )

    assert payload["verdict"] == "FAIL"
    assert "state baseline verdict must be PASS" in payload["errors"]
    assert "state baseline architecture_ready must be true" in payload["errors"]


def test_renderer_fails_closed_for_unsupported_provider_profile_value(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    profile = write_provider_profile(tmp_path, "FACTORY_V3_DEFAULT_PROVIDER=api-key-provider\n")

    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=tmp_path,
        handoff_report=handoff_path,
        provider_profile=profile,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert "FACTORY_V3_DEFAULT_PROVIDER resolved to unsupported provider 'api-key-provider'" in payload["errors"]


def test_renderer_fails_closed_when_handoff_authorizes_dispatch(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff(dispatch_authorized=True))
    payload = agent_os_runspec_renderer.render_agent_os_runspec(root=tmp_path, handoff_report=handoff_path)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert "handoff dispatch_authorized must remain false" in payload["errors"]


def test_renderer_writes_status_and_yaml_outputs(tmp_path):
    handoff_path = write_handoff(tmp_path, handoff())
    status_path = tmp_path / "status" / "agent-os-runspec-renderer.json"
    runspec_path = tmp_path / "ao" / "runspecs" / "agent-os-phase-draft.yaml"

    code = agent_os_runspec_renderer.main(
        [
            "--root",
            str(tmp_path),
            "--handoff-report",
            str(handoff_path),
            "--provider-profile",
            str(write_provider_profile(tmp_path, "FACTORY_V3_DEFAULT_PROVIDER=codex\n")),
            "--write-output",
            str(status_path),
            "--write-runspec",
            str(runspec_path),
            "--json",
        ]
    )

    assert code == 0
    assert status_path.is_file()
    assert runspec_path.is_file()
    assert "kind: Run" in runspec_path.read_text(encoding="utf-8")
    assert "id: agent-os-implementer" in runspec_path.read_text(encoding="utf-8")
