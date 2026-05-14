from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import agent_os_runspec_renderer
import agent_os_runspec_validator


def handoff() -> dict:
    return {
        "schema": "ao-operator/agent-os-phase-handoff/v1",
        "verdict": "PASS",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "handoff_packets": [
            {
                "packet_id": "01-planner",
                "role": "planner",
                "depends_on": [],
                "dispatch_mode": "ao-role",
                "scoped_context": {"reads": ["task brief"], "writes": ["docs/specs/"]},
                "verification_commands": ["python3 scripts/validate_factory.py --json"],
            },
            {
                "packet_id": "02-implementer",
                "role": "implementer",
                "depends_on": ["planner"],
                "dispatch_mode": "ao-role",
                "scoped_context": {"reads": ["slice contract"], "writes": ["declared writes"]},
                "verification_commands": ["python3 scripts/verify_closure.py --repo . --with-pytest --json"],
            },
        ],
    }


def write_rendered_artifacts(root: Path) -> Path:
    handoff_path = root / "handoff.json"
    handoff_path.write_text(agent_os_runspec_renderer.json_dumps(handoff()), encoding="utf-8")
    status_path = root / "status" / "agent-os-runspec-renderer.json"
    runspec_path = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    code = agent_os_runspec_renderer.main(
        [
            "--root",
            str(root),
            "--handoff-report",
            str(handoff_path),
            "--write-output",
            str(status_path),
            "--write-runspec",
            str(runspec_path),
            "--json",
        ]
    )
    assert code == 0
    return status_path


def test_validator_accepts_rendered_runspec_and_prompt_packets(tmp_path):
    report = write_rendered_artifacts(tmp_path)

    payload = agent_os_runspec_validator.validate_agent_os_runspec(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "PASS"
    assert payload["runspec_valid"] is True
    assert payload["task_count"] == 2
    assert payload["prompt_files_checked"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["errors"] == []


def test_validator_accepts_runspec_matching_provider_profile(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    profile = tmp_path / "all-codex.env"
    profile.write_text(
        "\n".join(
            [
                "FACTORY_V3_DEFAULT_PROVIDER=codex",
                "FACTORY_V3_PLANNER_PROVIDER=codex",
                "FACTORY_V3_IMPLEMENTER_PROVIDER=codex",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = agent_os_runspec_validator.validate_agent_os_runspec(
        root=tmp_path,
        renderer_report=report,
        provider_profile=profile,
    )

    assert payload["verdict"] == "PASS"
    assert payload["provider_profile"] == "all-codex.env"
    assert payload["provider_profile_checked"] is True
    assert payload["provider_profile_matches"] is True
    assert payload["provider_mismatches"] == []


def test_validator_rejects_runspec_provider_substitution_against_profile(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    profile = tmp_path / "all-claude.env"
    profile.write_text(
        "\n".join(
            [
                "FACTORY_V3_DEFAULT_PROVIDER=claude",
                "FACTORY_V3_PLANNER_PROVIDER=claude",
                "FACTORY_V3_IMPLEMENTER_PROVIDER=claude",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = agent_os_runspec_validator.validate_agent_os_runspec(
        root=tmp_path,
        renderer_report=report,
        provider_profile=profile,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["provider_profile_checked"] is True
    assert payload["provider_profile_matches"] is False
    assert "provider mismatch for planner: expected claude, got codex" in payload["errors"]
    assert payload["provider_mismatches"] == [
        {
            "role": "planner",
            "task_id": "agent-os-planner",
            "expected": "claude",
            "actual": "codex",
        },
        {
            "role": "implementer",
            "task_id": "agent-os-implementer",
            "expected": "claude",
            "actual": "codex",
        },
    ]


def test_validator_rejects_unknown_provider_in_profile(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    profile = tmp_path / "bad.env"
    profile.write_text("FACTORY_V3_DEFAULT_PROVIDER=local\n", encoding="utf-8")

    payload = agent_os_runspec_validator.validate_agent_os_runspec(
        root=tmp_path,
        renderer_report=report,
        provider_profile=profile,
    )

    assert payload["verdict"] == "FAIL"
    assert "FACTORY_V3_DEFAULT_PROVIDER resolved to unsupported provider 'local'" in payload["errors"]


def test_validator_fails_when_yaml_authorizes_dispatch(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    runspec = tmp_path / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.write_text(runspec.read_text(encoding="utf-8").replace("dispatchAuthorized: false", "dispatchAuthorized: true", 1), encoding="utf-8")

    payload = agent_os_runspec_validator.validate_agent_os_runspec(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "FAIL"
    assert payload["dispatch_authorized"] is False
    assert "runspec must not authorize dispatch" in payload["errors"]


def test_validator_fails_when_prompt_loses_scoped_context_warning(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    prompt = tmp_path / "ao" / "prompts" / "agent-os-phase" / "01-planner.md"
    prompt.write_text(prompt.read_text(encoding="utf-8").replace("Use only the scoped context below. Do not use full conversation history.\n", ""), encoding="utf-8")

    payload = agent_os_runspec_validator.validate_agent_os_runspec(root=tmp_path, renderer_report=report)

    assert payload["verdict"] == "FAIL"
    assert any("missing scoped context warning" in error for error in payload["errors"])


def test_cli_writes_validation_report(tmp_path):
    report = write_rendered_artifacts(tmp_path)
    profile = tmp_path / "all-codex.env"
    profile.write_text("FACTORY_V3_DEFAULT_PROVIDER=codex\n", encoding="utf-8")
    output = tmp_path / "status" / "agent-os-runspec-validation.json"

    code = agent_os_runspec_validator.main(
        [
            "--root",
            str(tmp_path),
            "--renderer-report",
            str(report),
            "--provider-profile",
            str(profile),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    assert output.is_file()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-runspec-validation/v1"
    assert saved["provider_profile_checked"] is True
