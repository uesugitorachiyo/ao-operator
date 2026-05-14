from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_runspec_execution_approval_gate
import preserve_agent_os_runspec_diagnostics
import rehearse_agent_os_runspec_execution
import route_agent_os_runspec_postrun


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validation_report(root: Path, *, valid: bool = True, provider_profile_matches: bool = True) -> Path:
    runspec = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text("kind: Run\nspec:\n  tasks: []\n", encoding="utf-8")
    return write_json(
        root / "validation.json",
        {
            "schema": "ao-operator/agent-os-runspec-validation/v1",
            "verdict": "PASS" if valid else "FAIL",
            "runspec_valid": valid,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "task_count": 7,
            "prompt_files_checked": 7,
            "provider_profile": ".env.example",
            "provider_profile_checked": True,
            "provider_profile_matches": provider_profile_matches,
            "provider_mismatches": [] if provider_profile_matches else [{"role": "planner", "expected": "claude", "actual": "codex"}],
            "dispatch_authorized": False,
            "live_providers_run": False,
            "errors": [] if valid else ["invalid"],
        },
    )


def test_execution_approval_gate_prepares_command_without_dispatch(tmp_path):
    validation = validation_report(tmp_path)

    payload = check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation)

    assert payload["verdict"] == "PASS"
    assert payload["approval_request_ready"] is True
    assert payload["approval_file_present"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["provider_profile"] == ".env.example"
    assert payload["provider_profile_matches"] is True
    assert payload["runspec_sha256"]
    assert payload["runspec_lock"]["algorithm"] == "sha256"
    assert payload["runspec_lock"]["path"] == "ao/runspecs/agent-os-phase-draft.yaml"
    assert payload["execution_command"] == [
        "ao",
        "run",
        "ao/runspecs/agent-os-phase-draft.yaml",
        "--home",
        "/tmp/ao-operator-ao-agent-os-phase-draft",
    ]


def test_execution_approval_gate_blocks_invalid_validation(tmp_path):
    validation = validation_report(tmp_path, valid=False)

    payload = check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation)

    assert payload["verdict"] == "FAIL"
    assert payload["approval_request_ready"] is False
    assert "RunSpec validation must pass before execution approval" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_execution_approval_gate_blocks_provider_profile_mismatch(tmp_path):
    validation = validation_report(tmp_path, provider_profile_matches=False)

    payload = check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation)

    assert payload["verdict"] == "FAIL"
    assert payload["approval_request_ready"] is False
    assert "RunSpec provider profile must be checked and match before execution approval" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_execution_approval_gate_blocks_missing_runspec_lock_source(tmp_path):
    validation = validation_report(tmp_path)
    (tmp_path / "ao" / "runspecs" / "agent-os-phase-draft.yaml").unlink()

    payload = check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation)

    assert payload["verdict"] == "FAIL"
    assert payload["approval_request_ready"] is False
    assert "RunSpec file must exist before execution approval lock" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_no_provider_rehearsal_proves_missing_approval_refuses_execution(tmp_path):
    validation = validation_report(tmp_path)
    gate = check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation)
    gate_path = write_json(tmp_path / "gate.json", gate)

    payload = rehearse_agent_os_runspec_execution.rehearse(root=tmp_path, approval_gate=gate_path)

    assert payload["verdict"] == "PASS"
    assert payload["refused_without_approval"] is True
    assert payload["would_run_provider"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_postrun_router_reports_pending_when_no_execution_report_exists(tmp_path):
    validation = validation_report(tmp_path)
    gate = write_json(tmp_path / "gate.json", check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation))

    payload = route_agent_os_runspec_postrun.route(root=tmp_path, approval_gate=gate, execution_report=tmp_path / "missing.json")

    assert payload["verdict"] == "PASS"
    assert payload["route"] == "PENDING_RUN"
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["dispatch_authorized"] is False


def test_postrun_router_sends_failed_execution_to_diagnostics(tmp_path):
    validation = validation_report(tmp_path)
    gate = write_json(tmp_path / "gate.json", check_agent_os_runspec_execution_approval_gate.build_gate(root=tmp_path, validation_report=validation))
    execution = write_json(tmp_path / "execution.json", {"verdict": "FAIL", "ao_completed": False, "task_failed_count": 1})

    payload = route_agent_os_runspec_postrun.route(root=tmp_path, approval_gate=gate, execution_report=execution)

    assert payload["route"] == "DIAGNOSTIC_REQUIRED"
    assert payload["diagnostics_required"] is True
    assert payload["commit_success_evidence_allowed"] is False


def test_diagnostics_preservation_passes_when_route_does_not_need_diagnostics(tmp_path):
    route = write_json(tmp_path / "route.json", {"schema": "ao-operator/agent-os-runspec-postrun-route/v1", "verdict": "PASS", "route": "PENDING_RUN", "diagnostics_required": False})

    payload = preserve_agent_os_runspec_diagnostics.preserve(root=tmp_path, route_report=route)

    assert payload["verdict"] == "PASS"
    assert payload["diagnostics_required"] is False
    assert payload["summary_written"] is False
    assert payload["raw_snapshot_commit_allowed"] is False


def test_diagnostics_preservation_writes_sanitized_summary_when_executed(tmp_path):
    route = write_json(tmp_path / "route.json", {"schema": "ao-operator/agent-os-runspec-postrun-route/v1", "verdict": "PASS", "route": "DIAGNOSTIC_REQUIRED", "diagnostics_required": True})
    ao_home = tmp_path / "ao-home"
    events = ao_home / "runs" / "r-test" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        json.dumps({"kind": "task.failed", "task_id": "agent-os-planner", "error": "429 Too Many Requests"}) + "\n",
        encoding="utf-8",
    )

    payload = preserve_agent_os_runspec_diagnostics.preserve(
        root=tmp_path,
        route_report=route,
        ao_home=ao_home,
        execute=True,
        timestamp="20260507-000000",
    )

    assert payload["verdict"] == "PASS"
    assert payload["summary_written"] is True
    assert payload["raw_snapshot_commit_allowed"] is False
    assert payload["primary_normalized_reason"] == "provider-rate-limit"
    assert "/tmp/[REDACTED_AO_HOME]" in json.dumps(payload["summary_payload"])
