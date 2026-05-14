from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_runspec_compatibility_matrix


def renderer_report(*, dispatch_authorized: bool = False) -> dict:
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "verdict": "PASS",
        "dispatch_authorized": dispatch_authorized,
        "live_providers_run": False,
        "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
        "prompt_files": [
            "ao/prompts/agent-os-phase/01-planner.md",
            "ao/prompts/agent-os-phase/02-implementer.md",
        ],
        "runspec": {
            "apiVersion": "ao.dev/v1",
            "kind": "Run",
            "metadata": {"name": "agent-os-phase-draft"},
            "spec": {
                "tasks": [
                    {
                        "id": "agent-os-planner",
                        "kind": "agent",
                        "deps": [],
                        "spec": {
                            "provider": "codex",
                            "promptFile": "ao/prompts/agent-os-phase/01-planner.md",
                            "dispatchAuthorized": False,
                        },
                    },
                    {
                        "id": "agent-os-implementer",
                        "kind": "agent",
                        "deps": ["agent-os-planner"],
                        "spec": {
                            "provider": "codex",
                            "promptFile": "ao/prompts/agent-os-phase/02-implementer.md",
                            "dispatchAuthorized": False,
                        },
                    },
                ]
            },
        },
    }


def write_fixture(root: Path, report: dict) -> Path:
    report_path = root / "status" / "agent-os-runspec-renderer.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runspec = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text(
        "\n".join(
            [
                "apiVersion: ao.dev/v1",
                "kind: Run",
                "metadata:",
                "  name: agent-os-phase-draft",
                "spec:",
                "  tasks:",
                "    - id: agent-os-planner",
                "      kind: agent",
                "      deps: []",
                "      spec:",
                "        provider: codex",
                "        promptFile: ao/prompts/agent-os-phase/01-planner.md",
                "        dispatchAuthorized: false",
                "    - id: agent-os-implementer",
                "      kind: agent",
                "      deps: [\"agent-os-planner\"]",
                "      spec:",
                "        provider: codex",
                "        promptFile: ao/prompts/agent-os-phase/02-implementer.md",
                "        dispatchAuthorized: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report_path


def test_compatibility_matrix_accepts_current_and_legacy_non_dispatch_shapes(tmp_path):
    report = write_fixture(tmp_path, renderer_report())

    payload = check_agent_os_runspec_compatibility_matrix.check_matrix(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 3
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert {case["id"] for case in payload["cases"]} == {
        "current_renderer_report",
        "current_yaml_draft",
        "legacy_renderer_v1_fixture",
    }


def test_compatibility_matrix_fails_closed_when_renderer_authorizes_dispatch(tmp_path):
    report = write_fixture(tmp_path, renderer_report(dispatch_authorized=True))

    payload = check_agent_os_runspec_compatibility_matrix.check_matrix(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert any("renderer dispatch_authorized must remain false" in error for error in payload["errors"])


def test_compatibility_matrix_fails_when_yaml_loses_report_task(tmp_path):
    report = write_fixture(tmp_path, renderer_report())
    runspec = tmp_path / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.write_text(
        runspec.read_text(encoding="utf-8").replace("    - id: agent-os-implementer\n", ""),
        encoding="utf-8",
    )

    payload = check_agent_os_runspec_compatibility_matrix.check_matrix(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "FAIL"
    assert any("yaml task ids must match renderer task ids" in error for error in payload["errors"])


def test_cli_writes_compatibility_matrix_report(tmp_path):
    report = write_fixture(tmp_path, renderer_report())
    output = tmp_path / "status" / "agent-os-runspec-compatibility-matrix.json"

    code = check_agent_os_runspec_compatibility_matrix.main(
        [
            "--root",
            str(tmp_path),
            "--renderer-report",
            str(report),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert output.is_file()
    assert "ao-operator/agent-os-runspec-compatibility-matrix/v1" in output.read_text(encoding="utf-8")
