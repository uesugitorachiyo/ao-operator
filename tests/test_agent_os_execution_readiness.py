from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_role_output_schema
import check_agent_os_execution_hygiene
import check_agent_os_accepted_execution_commit_guard
import ingest_agent_os_role_outputs
import run_agent_os_runspec_execution
import validate_agent_os_runspec_evaluator_closure
import validate_agent_os_runspec_execution_approval


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def approval_gate(root: Path, *, provider_profile_matches: bool = True) -> Path:
    runspec = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text("kind: Run\nspec:\n  tasks: []\n", encoding="utf-8")
    runspec_sha = run_agent_os_runspec_execution.sha256_file(runspec)
    return write_json(
        root / "approval-gate.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-gate/v1",
            "verdict": "PASS",
            "approval_request_ready": True,
            "approval_file": "approval.json",
            "approval_file_present": False,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": runspec_sha,
            "runspec_lock": {
                "algorithm": "sha256",
                "path": "ao/runspecs/agent-os-phase-draft.yaml",
                "sha256": runspec_sha,
            },
            "task_count": 7,
            "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml", "--home", "/tmp/ao-operator-ao-agent-os-phase-draft"],
            "provider_profile": ".env.example",
            "provider_profile_checked": True,
            "provider_profile_matches": provider_profile_matches,
            "provider_mismatches": [] if provider_profile_matches else [{"role": "planner", "expected": "claude", "actual": "codex"}],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def approval_file(
    root: Path,
    *,
    approved: bool = True,
    approved_at: str = "2026-05-07T05:00:00Z",
    expires_at: str = "2026-05-08T05:00:00Z",
    runspec_sha256: str | None = None,
) -> Path:
    if runspec_sha256 is None:
        runspec_sha256 = run_agent_os_runspec_execution.sha256_file(
            root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
        )
    return write_json(
        root / "approval.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
            "approved": approved,
            "operator": "operator",
            "approved_at": approved_at,
            "expires_at": expires_at,
            "runspec_path": "ao/runspecs/agent-os-phase-draft.yaml",
            "runspec_sha256": runspec_sha256,
            "task_count": 7,
            "accepted_risk": "Approve one Agent OS RunSpec execution.",
        },
    )


def execution_report(root: Path, *, verdict: str = "PASS", accepted: bool = True) -> Path:
    return write_json(
        root / "execution-report.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-report/v1",
            "verdict": verdict,
            "ao_completed": verdict == "PASS",
            "evaluator_accepted": accepted,
            "role_outputs": [
                str(root / "outputs" / "planner.json"),
                str(root / "outputs" / "evaluator-closer.json"),
            ],
            "dispatch_authorized": False,
            "live_providers_run": verdict == "PASS",
        },
    )


def postrun_route(root: Path, *, route: str = "PENDING_RUN", commit_allowed: bool = False) -> Path:
    return write_json(
        root / "postrun-route.json",
        {
            "schema": "ao-operator/agent-os-runspec-postrun-route/v1",
            "verdict": "PASS",
            "route": route,
            "commit_success_evidence_allowed": commit_allowed,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def evaluator_closure(root: Path, *, accepted: bool = False) -> Path:
    return write_json(
        root / "closure.json",
        {
            "schema": "ao-operator/agent-os-runspec-evaluator-closure/v1",
            "verdict": "PASS" if accepted else "FAIL",
            "accepted": accepted,
            "closure_authorized": accepted,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def role_output(path: Path, *, role: str = "planner", full_transcript: bool = False) -> Path:
    return write_json(
        path,
        {
            "schema": "ao-operator/agent-os-role-output/v1",
            "role": role,
            "Result": "PASS",
            "Artifact": "run-artifacts/example.json",
            "Evidence": "deterministic evidence",
            "Concerns": "",
            "Blocker": "",
            "full_transcript": "entire conversation" if full_transcript else "",
        },
    )


def role_artifact(path: Path, *, role: str = "planner", result: str = "DONE", blocker: str = "none") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {role} Role Artifact

Result: {result}
Artifact: run-artifacts/example/roles/{role}.md
Evidence:
- AO task.completed event observed.
- Agent STATUS block captured from AO event stream.
Concerns:
- none
Blocker: {blocker}

## Captured STATUS

```text
Result: {result}
Blocker: {blocker}
```
""",
        encoding="utf-8",
    )
    return path


def test_approval_validator_records_missing_approval_as_not_approved(tmp_path):
    gate = approval_gate(tmp_path)

    payload = validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate)

    assert payload["verdict"] == "PASS"
    assert payload["approval_valid"] is False
    assert payload["approval_state"] == "NOT_APPROVED"
    assert payload["dispatch_authorized"] is False


def test_approval_validator_accepts_valid_explicit_approval(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)

    payload = validate_agent_os_runspec_execution_approval.validate_approval(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "PASS"
    assert payload["approval_valid"] is True
    assert payload["approval_state"] == "APPROVED"
    assert payload["provider_profile"] == ".env.example"
    assert payload["provider_profile_checked"] is True
    assert payload["provider_profile_matches"] is True
    assert payload["approval_time_checked"] is True
    assert payload["runspec_sha256"]
    assert payload["approval_runspec_sha256"] == payload["runspec_sha256"]
    assert payload["dispatch_authorized"] is False


def test_approval_validator_blocks_runspec_hash_mismatch(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path, runspec_sha256="f" * 64)

    payload = validate_agent_os_runspec_execution_approval.validate_approval(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["approval_valid"] is False
    assert "approval runspec_sha256 must match approval gate" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_approval_validator_blocks_expired_approval(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path, expires_at="2026-05-07T05:30:00Z")

    payload = validate_agent_os_runspec_execution_approval.validate_approval(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["approval_valid"] is False
    assert "approval has expired" in payload["errors"]


def test_approval_validator_blocks_future_approval_window(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path, approved_at="2026-05-07T07:00:00Z")

    payload = validate_agent_os_runspec_execution_approval.validate_approval(
        root=tmp_path,
        approval_gate=gate,
        approval_file=approval,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["approval_valid"] is False
    assert "approval is not active yet" in payload["errors"]


def test_approval_validator_blocks_provider_profile_mismatch(tmp_path):
    gate = approval_gate(tmp_path, provider_profile_matches=False)
    approval = approval_file(tmp_path)

    payload = validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate, approval_file=approval)

    assert payload["verdict"] == "FAIL"
    assert payload["approval_valid"] is False
    assert "approval gate provider profile must be checked and match" in payload["errors"]
    assert "approval gate must not contain provider mismatches" in payload["errors"]
    assert payload["dispatch_authorized"] is False


def test_execution_launcher_blocks_without_valid_approval(tmp_path):
    gate = approval_gate(tmp_path)
    approval_report = write_json(tmp_path / "approval-report.json", validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate))

    payload = run_agent_os_runspec_execution.prepare_execution(root=tmp_path, approval_report=approval_report)

    assert payload["verdict"] == "BLOCKED"
    assert payload["approval_report"] == "approval-report.json"
    assert payload["approval_lifecycle"]["approval_state"] == "ABSENT"
    assert payload["approval_lifecycle"]["approval_usable"] is False
    assert payload["would_run_provider"] is False
    assert payload["runspec_sha256"] == payload["current_runspec_sha256"]
    assert "explicit approval is not valid" in payload["errors"]


def test_execution_launcher_default_write_output_records_current_runspec_hash(tmp_path, capsys):
    gate = approval_gate(tmp_path)
    approval_report = write_json(
        tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-validation.json",
        validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate),
    )

    code = run_agent_os_runspec_execution.main(
        [
            "--root",
            str(tmp_path),
            "--approval-report",
            str(approval_report),
            "--write-output",
            "--json",
        ]
    )

    output = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
    saved = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert saved["verdict"] == "BLOCKED"
    assert saved["dispatch_authorized"] is False
    assert saved["would_run_provider"] is False
    assert saved["runspec_sha256"] == saved["current_runspec_sha256"]
    assert printed["output"] == str(output)


def test_execution_launcher_rechecks_lifecycle_and_blocks_stale_validation_report(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path, expires_at="2026-05-07T07:00:00Z")
    stale_but_once_valid_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(
            root=tmp_path,
            approval_gate=gate,
            approval_file=approval,
            now="2026-05-07T06:00:00Z",
        ),
    )

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=stale_but_once_valid_report,
        now="2026-05-07T08:00:00Z",
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["approval_lifecycle"]["approval_state"] == "EXPIRED"
    assert payload["approval_lifecycle"]["approval_usable"] is False
    assert "approval lifecycle must be usable at execution time" in payload["errors"]
    assert "approval file is expired" in payload["errors"]
    assert payload["would_run_provider"] is False


def test_execution_launcher_rechecks_lifecycle_and_blocks_missing_approval_file(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)
    approval_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(
            root=tmp_path,
            approval_gate=gate,
            approval_file=approval,
            now="2026-05-07T06:00:00Z",
        ),
    )
    approval.unlink()

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=approval_report,
        now="2026-05-07T06:30:00Z",
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["approval_lifecycle"]["approval_state"] == "ABSENT"
    assert payload["approval_lifecycle"]["approval_usable"] is False
    assert "approval lifecycle must be usable at execution time" in payload["errors"]


def test_execution_launcher_blocks_valid_approval_report_without_provider_alignment(tmp_path):
    approval_report = write_json(
        tmp_path / "approval-report.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-approval-validation/v1",
            "approval_valid": True,
            "execution_command": ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml"],
            "dispatch_authorized": False,
            "provider_profile_checked": False,
            "provider_profile_matches": True,
            "provider_mismatches": [],
        },
    )

    payload = run_agent_os_runspec_execution.prepare_execution(root=tmp_path, approval_report=approval_report, execute=True)

    assert payload["verdict"] == "BLOCKED"
    assert payload["would_run_provider"] is False
    assert "approval provider profile must be checked and match" in payload["errors"]


def test_execution_launcher_plans_valid_approval_without_execute(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)
    approval_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate, approval_file=approval, now="2026-05-07T06:00:00Z"),
    )

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=approval_report,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "PLAN"
    assert payload["would_run_provider"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["runspec_sha256"] == payload["current_runspec_sha256"]
    assert payload["planned_command"] == ["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml", "--home", "/tmp/ao-operator-ao-agent-os-phase-draft"]


def test_execution_launcher_blocks_when_runspec_changes_after_approval(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)
    approval_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate, approval_file=approval, now="2026-05-07T06:00:00Z"),
    )
    (tmp_path / "ao" / "runspecs" / "agent-os-phase-draft.yaml").write_text(
        "kind: Run\nmetadata:\n  name: changed\n",
        encoding="utf-8",
    )

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=approval_report,
        execute=True,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "BLOCKED"
    assert payload["would_run_provider"] is False
    assert "current RunSpec sha256 must match approved RunSpec sha256" in payload["errors"]


def test_execution_launcher_runs_approved_command_only_when_execute_requested(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)
    approval_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate, approval_file=approval, now="2026-05-07T06:00:00Z"),
    )
    calls = []

    def fake_runner(command, *, cwd):
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, 0, stdout="AO done\n", stderr="")

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=approval_report,
        execute=True,
        command_runner=fake_runner,
        now="2026-05-07T06:00:00Z",
    )

    assert calls == [(["ao", "run", "ao/runspecs/agent-os-phase-draft.yaml", "--home", "/tmp/ao-operator-ao-agent-os-phase-draft"], tmp_path)]
    assert payload["verdict"] == "PASS"
    assert payload["ao_completed"] is True
    assert payload["dispatch_authorized"] is True
    assert payload["live_providers_run"] is True
    assert payload["live_command_exit"] == 0
    assert payload["stdout_tail"] == "AO done\n"


def test_execution_launcher_records_failed_approved_command(tmp_path):
    gate = approval_gate(tmp_path)
    approval = approval_file(tmp_path)
    approval_report = write_json(
        tmp_path / "approval-report.json",
        validate_agent_os_runspec_execution_approval.validate_approval(root=tmp_path, approval_gate=gate, approval_file=approval, now="2026-05-07T06:00:00Z"),
    )

    def fake_runner(command, *, cwd):
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="provider failed\n")

    payload = run_agent_os_runspec_execution.prepare_execution(
        root=tmp_path,
        approval_report=approval_report,
        execute=True,
        command_runner=fake_runner,
        now="2026-05-07T06:00:00Z",
    )

    assert payload["verdict"] == "FAIL"
    assert payload["ao_completed"] is False
    assert payload["diagnostics_required"] is True
    assert payload["live_providers_run"] is True
    assert payload["live_command_exit"] == 7
    assert payload["stderr_tail"] == "provider failed\n"


def test_evaluator_closure_accepts_completed_execution_with_evaluator_acceptance(tmp_path):
    report = execution_report(tmp_path, verdict="PASS", accepted=True)

    payload = validate_agent_os_runspec_evaluator_closure.validate_closure(root=tmp_path, execution_report=report)

    assert payload["verdict"] == "PASS"
    assert payload["accepted"] is True
    assert payload["closure_authorized"] is True
    assert payload["dispatch_authorized"] is False


def test_agent_os_commit_guard_refuses_pending_or_blocked_evidence_without_failing(tmp_path):
    route = postrun_route(tmp_path, route="PENDING_RUN", commit_allowed=False)
    report = execution_report(tmp_path, verdict="BLOCKED", accepted=False)
    closure = evaluator_closure(tmp_path, accepted=False)

    payload = check_agent_os_accepted_execution_commit_guard.check_guard(
        root=tmp_path,
        postrun_route=route,
        execution_report=report,
        evaluator_closure=closure,
    )

    assert payload["verdict"] == "PASS"
    assert payload["commit_success_evidence_allowed"] is False
    assert payload["route"] == "PENDING_RUN"
    assert payload["closure_authorized"] is False
    assert payload["dispatch_authorized"] is False


def test_agent_os_commit_guard_fails_accepted_route_without_closure(tmp_path):
    route = postrun_route(tmp_path, route="ACCEPTED", commit_allowed=True)
    report = execution_report(tmp_path, verdict="PASS", accepted=True)
    closure = evaluator_closure(tmp_path, accepted=False)

    payload = check_agent_os_accepted_execution_commit_guard.check_guard(
        root=tmp_path,
        postrun_route=route,
        execution_report=report,
        evaluator_closure=closure,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["commit_success_evidence_allowed"] is False
    assert any("evaluator closure must authorize success commit" in error for error in payload["errors"])


def test_agent_os_commit_guard_allows_completed_accepted_execution(tmp_path):
    route = postrun_route(tmp_path, route="ACCEPTED", commit_allowed=True)
    report = execution_report(tmp_path, verdict="PASS", accepted=True)
    closure = evaluator_closure(tmp_path, accepted=True)

    payload = check_agent_os_accepted_execution_commit_guard.check_guard(
        root=tmp_path,
        postrun_route=route,
        execution_report=report,
        evaluator_closure=closure,
    )

    assert payload["verdict"] == "PASS"
    assert payload["commit_success_evidence_allowed"] is True
    assert payload["raw_snapshot_commit_allowed"] is False
    assert payload["next_safe_command"] == "Commit accepted Agent OS execution evidence only."


def test_agent_os_commit_guard_rejects_synthetic_accepted_execution_without_provider_run(tmp_path):
    route = postrun_route(tmp_path, route="ACCEPTED", commit_allowed=True)
    report = execution_report(tmp_path, verdict="PASS", accepted=True)
    data = json.loads(report.read_text(encoding="utf-8"))
    data["fixture_only"] = True
    data["live_providers_run"] = False
    report.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    closure = evaluator_closure(tmp_path, accepted=True)

    payload = check_agent_os_accepted_execution_commit_guard.check_guard(
        root=tmp_path,
        postrun_route=route,
        execution_report=report,
        evaluator_closure=closure,
    )

    assert payload["verdict"] == "FAIL"
    assert payload["commit_success_evidence_allowed"] is False
    assert any("accepted execution commit requires live provider execution" in error for error in payload["errors"])


def test_role_output_ingestion_converts_markdown_artifacts_and_updates_execution_report(tmp_path):
    report = execution_report(tmp_path, verdict="PASS", accepted=False)
    planner = role_artifact(tmp_path / "roles" / "planner.md", role="planner", result="DONE")
    evaluator = role_artifact(tmp_path / "roles" / "evaluator-closer.md", role="evaluator-closer", result="DONE_WITH_CONCERNS")

    payload = ingest_agent_os_role_outputs.ingest_role_outputs(
        root=tmp_path,
        execution_report=report,
        role_artifacts=[planner, evaluator],
        output_dir=tmp_path / "role-outputs",
    )

    updated = json.loads(report.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["role_outputs_ingested"] == 2
    assert payload["evaluator_accepted"] is True
    assert updated["evaluator_accepted"] is True
    assert len(updated["role_outputs"]) == 2
    evaluator_output = json.loads((tmp_path / "role-outputs" / "evaluator-closer.json").read_text(encoding="utf-8"))
    assert evaluator_output["Result"] == "DONE_WITH_CONCERNS"
    assert evaluator_output["source_artifact"] == "roles/evaluator-closer.md"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_role_output_ingestion_requires_evaluator_closer_acceptance(tmp_path):
    report = execution_report(tmp_path, verdict="PASS", accepted=False)
    planner = role_artifact(tmp_path / "roles" / "planner.md", role="planner", result="DONE")

    payload = ingest_agent_os_role_outputs.ingest_role_outputs(
        root=tmp_path,
        execution_report=report,
        role_artifacts=[planner],
        output_dir=tmp_path / "role-outputs",
    )

    updated = json.loads(report.read_text(encoding="utf-8"))
    assert payload["verdict"] == "FAIL"
    assert payload["evaluator_accepted"] is False
    assert updated["evaluator_accepted"] is False
    assert any("evaluator-closer role output is required" in error for error in payload["errors"])


def test_role_output_schema_validator_requires_status_fields(tmp_path):
    good = role_output(tmp_path / "planner.json")
    bad = write_json(tmp_path / "bad.json", {"schema": "ao-operator/agent-os-role-output/v1", "role": "implementer", "Result": "PASS"})

    payload = check_agent_os_role_output_schema.validate_role_outputs(root=tmp_path, role_outputs=[good, bad])

    assert payload["verdict"] == "FAIL"
    assert any("missing Artifact" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False


def test_hygiene_gate_rejects_full_transcript_and_secret_markers(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Use only scoped context\nOPENAI_API_KEY=bad\n", encoding="utf-8")
    output = role_output(tmp_path / "role.json", full_transcript=True)

    payload = check_agent_os_execution_hygiene.check_hygiene(root=tmp_path, prompt_paths=[prompt], role_outputs=[output])

    assert payload["verdict"] == "FAIL"
    assert any("forbidden secret marker" in error for error in payload["errors"])
    assert any("full transcript" in error for error in payload["errors"])
    assert payload["dispatch_authorized"] is False
