from __future__ import annotations

import json
from pathlib import Path

import validate_operator_slices


def valid_manifest() -> dict[str, object]:
    return {
        "schema": "ao-operator/operator-slices/v1",
        "slug": "stress",
        "title": "Stress slices",
        "classification": "COMPLEX",
        "shape": "refactor",
        "max_live_tasks_default": 50,
        "objective": "Operate stress work safely.",
        "negative_constraints": ["MUST NOT run large live topology"],
        "sensitive_fields": ["provider OAuth credentials"],
        "slices": [
            {
                "order": 0,
                "id": "00-diagnostics",
                "mode": "diagnostic",
                "live_provider": False,
                "task_count": 0,
                "objective": "Capture diagnostics.",
                "reads": ["/tmp/ao"],
                "writes": ["run-artifacts/snapshots/"],
                "commands": ["python3 scripts/summarize_ao_failure.py /tmp/ao --json"],
                "evidence": ["summary JSON"],
                "stop_rules": ["Stop if AO home is missing."],
            },
            {
                "order": 1,
                "id": "01-validation",
                "mode": "validation",
                "live_provider": False,
                "task_count": 27,
                "objective": "Validate bounded profile.",
                "reads": ["topology.yaml"],
                "writes": [],
                "commands": ["python3 scripts/validate_factory.py --json"],
                "evidence": ["PASS"],
                "stop_rules": ["Stop on FAIL."],
            },
            {
                "order": 2,
                "id": "02-live",
                "mode": "live-run",
                "live_provider": True,
                "task_count": 27,
                "objective": "Run bounded live profile.",
                "reads": ["brief.md"],
                "writes": ["run-artifacts/live/"],
                "commands": ["python3 scripts/factory_run.py --brief brief.md --run"],
                "evidence": ["AO completed=true"],
                "stop_rules": ["Stop on blockers."],
            },
        ],
    }


def test_default_operator_slice_manifest_passes():
    result = validate_operator_slices.validate_path(
        Path("examples/remote-transfer-v2-stress/operator-slices.json")
    )

    assert result["verdict"] == "PASS"
    assert result["slice_count"] == 156


def test_default_manifest_includes_50_slice_dry_run_prep():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    prep = next(item for item in slices if item["id"] == "27-prepare-50-slice-dry-run-profile")
    assert prep["live_provider"] is False
    assert prep["task_count"] == 107
    assert prep["commands"] == [
        "python3 scripts/prepare_live_profile_dry_run.py --slices 50 --report run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_50_slice_live_sequence():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    assert by_id["29-record-50-slice-provider-budget"]["live_provider"] is False
    assert by_id["30-rehearse-50-slice-live-sequence"]["live_provider"] is False
    assert by_id["31-run-50-slice-live"]["live_provider"] is True
    assert by_id["31-run-50-slice-live"]["requires_override"] is True
    assert by_id["32-route-50-slice-postrun"]["live_provider"] is False
    assert by_id["33-summarize-50-slice-operator-state"]["live_provider"] is False
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_clean_clone_readiness_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    clean_clone = by_id["70-check-clean-clone-readiness"]
    assert clean_clone["live_provider"] is False
    assert clean_clone["task_count"] == 0
    assert clean_clone["commands"] == [
        "python3 scripts/check_clean_clone_readiness.py --write-output --json"
    ]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-migration-matrix.json" in clean_clone["reads"]
    assert "agent_os_runspec_provider_profile_validation=PASS from clean clone" in clean_clone["evidence"]
    assert "Stop if any Agent OS architecture baseline fails in a clean clone." in clean_clone["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_role_graph_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    role_graph = by_id["71-record-agent-os-role-graph-state-versioning"]
    assert role_graph["live_provider"] is False
    assert role_graph["task_count"] == 0
    assert role_graph["commands"] == [
        "python3 scripts/agent_os_role_graph.py --write-output --json"
    ]
    assert "docs/sdd/44-agent-os-role-graph-state-versioning.md" in role_graph["reads"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_accepted_execution_commit_guard_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    guard = by_id["72-check-agent-os-accepted-execution-commit-guard"]
    assert guard["live_provider"] is False
    assert guard["task_count"] == 0
    assert guard["commands"] == [
        "python3 scripts/check_agent_os_accepted_execution_commit_guard.py --write-output --json"
    ]
    assert "raw_snapshot_commit_allowed=false" in guard["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_postrun_route_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["73-check-agent-os-postrun-route-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_postrun_route_matrix.py --write-output --json"
    ]
    assert "case_count=6" in matrix["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_state_v2_persistence_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    state = by_id["74-record-agent-os-state-v2-persistence"]
    assert state["live_provider"] is False
    assert state["task_count"] == 0
    assert state["commands"] == [
        "python3 scripts/agent_os_state_v2.py --write-output --json"
    ]
    assert "schema=ao-operator/agent-os-state/v2" in state["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_compatibility_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["75-check-agent-os-runspec-compatibility-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_runspec_compatibility_matrix.py --write-output --json"
    ]
    assert "case_count=3" in matrix["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_architecture_readiness_summary_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    summary = by_id["76-summarize-agent-os-architecture-readiness"]
    assert summary["live_provider"] is False
    assert summary["task_count"] == 0
    assert summary["commands"] == [
        "python3 scripts/summarize_agent_os_architecture_readiness.py --write-output --json"
    ]
    assert "architecture_ready=true" in summary["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_router_v2_state_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    router = by_id["77-record-agent-os-router-v2-state"]
    assert router["live_provider"] is False
    assert router["task_count"] == 0
    assert router["commands"] == [
        "python3 scripts/agent_os_router.py --brief examples/agent-os/mission-router-state-brief.md --label release --state-version v2 --architecture-readiness run-artifacts/remote-transfer-v2-stress-live/agent-os-architecture-readiness.json --write-state run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json --json"
    ]
    assert "schema=ao-operator/agent-os-state/v2" in router["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_state_evidence_hygiene_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    hygiene = by_id["78-check-agent-os-state-evidence-hygiene"]
    assert hygiene["live_provider"] is False
    assert hygiene["task_count"] == 0
    assert hygiene["commands"] == [
        "python3 scripts/check_agent_os_state_evidence_hygiene.py --write-output --json"
    ]
    assert "dirty_state_artifacts=[]" in hygiene["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approved_execution_fixture_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    fixture = by_id["79-check-agent-os-approved-execution-fixture"]
    assert fixture["live_provider"] is False
    assert fixture["task_count"] == 0
    assert fixture["commands"] == [
        "python3 scripts/check_agent_os_approved_execution_fixture.py --write-output --json"
    ]
    assert "commit_success_evidence_allowed=false" in fixture["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_lifecycle_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    lifecycle = by_id["94-check-agent-os-approval-lifecycle"]
    assert lifecycle["live_provider"] is False
    assert lifecycle["task_count"] == 0
    assert lifecycle["commands"] == [
        "python3 scripts/check_agent_os_approval_lifecycle.py --write-output --json"
    ]
    assert "approval_state=ABSENT" in lifecycle["evidence"]
    assert "approval_usable=false" in lifecycle["evidence"]
    assert "Stop if an expired approval file is considered usable." in lifecycle["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_failed_diagnostics_fixture_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    fixture = by_id["83-check-agent-os-failed-diagnostics-fixture"]
    assert fixture["live_provider"] is False
    assert fixture["task_count"] == 0
    assert fixture["commands"] == [
        "python3 scripts/check_agent_os_failed_diagnostics_fixture.py --write-output --json"
    ]
    assert "primary_normalized_reason=provider-rate-limit" in fixture["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_alignment_drift_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    drift = by_id["84-check-agent-os-approval-alignment-drift"]
    assert drift["live_provider"] is False
    assert drift["task_count"] == 0
    assert drift["commands"] == [
        "python3 scripts/check_agent_os_approval_alignment_drift.py --write-output --json"
    ]
    assert "provider_profile_matches=true" in drift["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_repeated_run_hygiene_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    hygiene = by_id["85-check-repeated-run-hygiene"]
    assert hygiene["live_provider"] is False
    assert hygiene["task_count"] == 0
    assert hygiene["commands"] == [
        "python3 scripts/check_repeated_run_hygiene.py --write-output --json"
    ]
    assert "same-slug-dry-run-after-live=PASS" in hygiene["evidence"]
    assert "Stop if stale accepted evidence survives a repeated-run scenario." in hygiene["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_normalized_failure_diagnostics_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    diagnostics = by_id["86-check-normalized-failure-diagnostics"]
    assert diagnostics["live_provider"] is False
    assert diagnostics["task_count"] == 0
    assert diagnostics["commands"] == [
        "python3 scripts/check_normalized_failure_diagnostics.py --write-output --json"
    ]
    assert "primary_normalized_reason=provider-rate-limit" in diagnostics["evidence"]
    assert "Stop if evaluator evidence omits normalized failure reasons." in diagnostics["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_state_v2_renderer_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    renderer = by_id["87-render-agent-os-runspec-with-state-v2"]
    assert renderer["live_provider"] is False
    assert renderer["task_count"] == 0
    assert renderer["commands"] == [
        "python3 scripts/agent_os_runspec_renderer.py --provider-profile .env.example --state-baseline run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json --write-output --write-runspec --json"
    ]
    assert "state_schema_version=ao-operator/agent-os-state/v2" in renderer["evidence"]
    assert "Stop if state baseline dispatch_authorized is not false." in renderer["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_architecture_implementation_gate_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    gate = by_id["112-check-agent-os-architecture-implementation-gate"]
    assert gate["live_provider"] is False
    assert gate["task_count"] == 0
    assert gate["commands"] == [
        "python3 scripts/check_agent_os_architecture_implementation_gate.py --write-output --json"
    ]
    assert "implementation_ready=true" in gate["evidence"]
    assert "role_handoff_runspec_alignment=PASS" in gate["evidence"]
    assert "Stop if any implementation surface authorizes dispatch." in gate["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_router_transition_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["113-check-agent-os-router-transition-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_router_transition_matrix.py --write-output --json"
    ]
    assert "case_count=9" in matrix["evidence"]
    assert "live-provider blocker preserved" in matrix["evidence"]
    assert "Stop if the matrix artifact authorizes dispatch." in matrix["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_failure_injection_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["114-check-agent-os-runspec-failure-injection-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_runspec_failure_injection_matrix.py --write-output --json"
    ]
    assert "case_count=7" in matrix["evidence"]
    assert "stale_approval_hash_refused=REFUSED" in matrix["evidence"]
    assert "Stop if any refusal case passes unexpectedly." in matrix["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_router_migration_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["80-check-agent-os-router-migration-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_router_migration_matrix.py --write-output --json"
    ]
    assert "case_count=6" in matrix["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_provider_boundary_matrix_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    matrix = by_id["81-check-agent-os-runspec-provider-boundary-matrix"]
    assert matrix["live_provider"] is False
    assert matrix["task_count"] == 0
    assert matrix["commands"] == [
        "python3 scripts/check_agent_os_runspec_provider_boundary_matrix.py --write-output --json"
    ]
    assert "mixed_profile yaml_provider_set=[claude,codex]" in matrix["evidence"]
    assert "all cases yaml_verified=true" in matrix["evidence"]
    assert "provider_substitution_refusal verdict FAIL" in matrix["evidence"]
    assert "Stop if rendered YAML providers differ from the renderer report." in matrix["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_state_stale_cleanup_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    cleanup = by_id["82-cleanup-agent-os-state-stale-artifacts"]
    assert cleanup["live_provider"] is False
    assert cleanup["task_count"] == 0
    assert cleanup["commands"] == [
        "python3 scripts/cleanup_agent_os_state_artifacts.py --write-output --json"
    ]
    assert "mode=dry-run" in cleanup["evidence"]
    assert "apply mode requires explicit --apply" in cleanup["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_75_slice_non_live_escalation_lane():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    assert by_id["34-prepare-75-slice-dry-run-profile"]["live_provider"] is False
    assert by_id["34-prepare-75-slice-dry-run-profile"]["task_count"] == 157
    assert by_id["35-check-75-slice-live-approval-gate"]["requires_override"] is True
    assert by_id["35-check-75-slice-live-approval-gate"]["live_provider"] is False
    assert by_id["36-record-75-slice-provider-budget"]["live_provider"] is False
    assert by_id["37-rehearse-75-slice-live-sequence"]["live_provider"] is False
    assert by_id["38-record-75-slice-live-approval-sdd"]["requires_override"] is True
    assert by_id["38-record-75-slice-live-approval-sdd"]["live_provider"] is False
    assert by_id["38-record-75-slice-live-approval-sdd"]["commands"] == [
        "python3 scripts/check_75_slice_live_approval_sdd.py --write-output --json"
    ]
    assert all("75-slice" not in item["id"] or item["live_provider"] is False for item in by_id.values())
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_sdd_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    agent_os = by_id["39-record-agent-os-sdd-contract"]
    assert agent_os["live_provider"] is False
    assert agent_os["task_count"] == 0
    assert agent_os["commands"] == [
        "python3 scripts/check_agent_os_sdd.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_router_state_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    router = by_id["40-record-agent-os-mission-router-state"]
    assert router["live_provider"] is False
    assert router["task_count"] == 0
    assert router["commands"] == [
        "python3 scripts/agent_os_router.py --brief examples/agent-os/mission-router-state-brief.md --label release --state-version v1 --write-state run-artifacts/remote-transfer-v2-stress-live/agent-os-mission-router-state.json --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_codebase_specialists_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    mapper = by_id["41-record-agent-os-codebase-specialists"]
    assert mapper["live_provider"] is False
    assert mapper["task_count"] == 0
    assert mapper["commands"] == [
        "python3 scripts/agent_os_codebase_map.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_capability_validation_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    capability = by_id["42-record-agent-os-capability-validation"]
    assert capability["live_provider"] is False
    assert capability["task_count"] == 0
    assert capability["commands"] == [
        "python3 scripts/agent_os_capability_validator.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_security_sdlc_roadmap_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    security = by_id["64-security-sdlc-roadmap-cert-pentest"]
    assert security["live_provider"] is False
    assert security["task_count"] == 0
    assert security["commands"] == [
        "python3 scripts/check_security_sdlc_roadmap.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_threat_model_and_pentest_slices():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    threat = by_id["65-record-security-threat-model"]
    pentest = by_id["66-record-manual-pentest-gate"]
    assert threat["live_provider"] is False
    assert pentest["live_provider"] is False
    assert threat["commands"] == [
        "python3 scripts/check_security_threat_model.py --write-output --json"
    ]
    assert pentest["commands"] == [
        "python3 scripts/check_pentest_gate.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_host_key_pentest_report_and_supply_chain_slices():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    host_key = by_id["67-record-host-key-evidence-gate"]
    report = by_id["68-classify-manual-pentest-report-template"]
    supply = by_id["69-record-supply-chain-gate"]
    assert host_key["live_provider"] is False
    assert report["live_provider"] is False
    assert supply["live_provider"] is False
    assert host_key["commands"] == [
        "python3 scripts/check_host_key_evidence.py --write-output --json"
    ]
    assert report["commands"] == [
        "python3 scripts/classify_pentest_report.py --write-output --json"
    ]
    assert supply["commands"] == [
        "python3 scripts/check_supply_chain_gate.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_phase_compiler_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    compiler = by_id["43-record-agent-os-phase-compiler"]
    assert compiler["live_provider"] is False
    assert compiler["task_count"] == 0
    assert compiler["commands"] == [
        "python3 scripts/agent_os_phase_compiler.py --write-output --json"
    ]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json" in compiler["reads"]
    assert "state_baseline.schema=ao-operator/agent-os-state/v2" in compiler["evidence"]
    assert "Stop if state_v2 dispatch_authorized is not false." in compiler["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_phase_handoff_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    handoff = by_id["44-record-agent-os-phase-handoff"]
    assert handoff["live_provider"] is False
    assert handoff["task_count"] == 0
    assert handoff["commands"] == [
        "python3 scripts/agent_os_phase_handoff.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_uat_state_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    uat = by_id["45-record-agent-os-uat-state"]
    assert uat["live_provider"] is False
    assert uat["task_count"] == 0
    assert uat["commands"] == [
        "python3 scripts/agent_os_uat_state.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_learning_extract_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    learning = by_id["46-record-agent-os-learning-extract"]
    assert learning["live_provider"] is False
    assert learning["task_count"] == 0
    assert learning["commands"] == [
        "python3 scripts/agent_os_learning_extract.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_operator_cockpit_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    cockpit = by_id["47-record-agent-os-operator-cockpit"]
    assert cockpit["live_provider"] is False
    assert cockpit["task_count"] == 0
    assert "docs/sdd/61-agent-os-runspec-execution-plan-lock.md" in cockpit["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json" in cockpit["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json" in cockpit["reads"]
    assert cockpit["commands"] == [
        "python3 scripts/agent_os_operator_cockpit.py --write-output --json"
    ]
    assert "state_v2 readiness is visible" in cockpit["evidence"]
    assert "execution_lock records sha256 RunSpec lock" in cockpit["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_hardening_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    hardening = by_id["88-check-remote-transfer-hardening"]
    assert hardening["live_provider"] is False
    assert hardening["task_count"] == 0
    assert "docs/sdd/62-remote-transfer-hardening-evidence-gate.md" in hardening["reads"]
    assert hardening["commands"] == [
        "python3 scripts/check_remote_transfer_hardening.py --write-output --json"
    ]
    assert "manifest_signing=PASS" in hardening["evidence"]
    assert "chunk_cleanup=PASS" in hardening["evidence"]
    assert "Stop if signed-manifest evidence is missing." in hardening["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_resource_performance_guardrails_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    resource = by_id["89-check-resource-performance-guardrails"]
    assert resource["live_provider"] is False
    assert resource["task_count"] == 0
    assert "docs/sdd/63-resource-performance-guardrails.md" in resource["reads"]
    assert resource["commands"] == [
        "python3 scripts/check_resource_performance_gate.py --write-output --json"
    ]
    assert "provider_budget=PASS" in resource["evidence"]
    assert "temp_footprint=PASS" in resource["evidence"]
    assert "Stop if temp AO/worktree footprint exceeds documented limits." in resource["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_execution_approval_bundle_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    bundle = by_id["90-generate-agent-os-execution-approval-bundle"]
    assert bundle["live_provider"] is False
    assert bundle["task_count"] == 0
    assert "docs/sdd/64-agent-os-execution-approval-bundle.md" in bundle["reads"]
    assert "docs/sdd/61-agent-os-runspec-execution-plan-lock.md" in bundle["reads"]
    assert bundle["commands"] == [
        "python3 scripts/generate_agent_os_approval_bundle.py --write-output --json"
    ]
    assert "approval_template approved=false" in bundle["evidence"]
    assert "approval_template includes runspec_sha256" in bundle["evidence"]
    assert "Stop if the approval template sets approved=true." in bundle["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_operator_guardrail_summary_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    summary = by_id["91-check-operator-guardrail-summary"]
    assert summary["live_provider"] is False
    assert summary["task_count"] == 0
    assert "docs/sdd/65-operator-guardrail-summary.md" in summary["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-cleanup.json" in summary["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-launch-proof.json" in summary["reads"]
    assert summary["commands"] == [
        "python3 scripts/check_operator_guardrail_summary.py --write-output --json"
    ]
    assert "operator guardrail summary verdict PASS" in summary["evidence"]
    assert "positive_approval_path=PLAN_WITHOUT_DISPATCH" in summary["evidence"]
    assert "Stop if any guardrail report dispatch_authorized or live_providers_run is true." in summary["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_materialization_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    materialization = by_id["92-dry-run-agent-os-approval-materialization"]
    assert materialization["live_provider"] is False
    assert materialization["task_count"] == 0
    assert "docs/sdd/66-agent-os-approval-materialization.md" in materialization["reads"]
    assert materialization["commands"] == [
        "python3 scripts/materialize_agent_os_approval.py --write-output --json"
    ]
    assert "approval_file_written=false" in materialization["evidence"]
    assert "Stop if approval_file_written is true in the default dry-run slice." in materialization["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_release_artifact_index_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    index = by_id["93-check-release-artifact-index"]
    assert index["live_provider"] is False
    assert index["task_count"] == 0
    assert "docs/sdd/67-release-artifact-index.md" in index["reads"]
    assert index["commands"] == [
        "python3 scripts/check_release_artifact_index.py --write-output --json"
    ]
    assert "docs/sdd/37-public-release-security-and-dast.md" in index["reads"]
    assert "docs/sdd/38-security-sdlc-roadmap.md" in index["reads"]
    assert "docs/sdd/39-security-threat-model-data-flow.md" in index["reads"]
    assert "docs/sdd/40-manual-penetration-test-gate.md" in index["reads"]
    assert "docs/sdd/41-host-key-evidence-gate.md" in index["reads"]
    assert "docs/sdd/42-manual-pentest-report-classifier.md" in index["reads"]
    assert "docs/sdd/43-supply-chain-audit-gate.md" in index["reads"]
    assert "docs/sdd/69-agent-os-approved-launch-proof.md" in index["reads"]
    assert "docs/sdd/70-agent-os-approval-cleanup.md" in index["reads"]
    assert "docs/sdd/71-agent-os-approval-audit-history.md" in index["reads"]
    assert "docs/sdd/72-agent-os-post-approval-cleanup-route.md" in index["reads"]
    assert "docs/sdd/73-agent-os-approval-materialization-runbook.md" in index["reads"]
    assert "docs/sdd/74-agent-os-approval-audit-retention.md" in index["reads"]
    assert "docs/sdd/75-agent-os-approval-bundle-signature.md" in index["reads"]
    assert "docs/sdd/76-agent-os-approval-revocation.md" in index["reads"]
    assert "docs/sdd/77-agent-os-approval-identity-signature.md" in index["reads"]
    assert "docs/sdd/78-agent-os-approval-revocation-apply-proof.md" in index["reads"]
    assert "docs/sdd/79-agent-os-approval-audit-archive-restore.md" in index["reads"]
    assert "docs/sdd/80-mac-ubuntu-approval-artifact-parity.md" in index["reads"]
    assert "docs/sdd/81-mac-ubuntu-signed-approval-bundle-transfer.md" in index["reads"]
    assert "docs/sdd/87-agent-os-router-transition-matrix.md" in index["reads"]
    assert "docs/sdd/88-agent-os-runspec-failure-injection-matrix.md" in index["reads"]
    assert "docs/sdd/89-operator-safe-next-command.md" in index["reads"]
    assert "docs/sdd/90-agent-os-runspec-dag-edge-coverage.md" in index["reads"]
    assert "docs/sdd/91-agent-os-runspec-yaml-dag-parity.md" in index["reads"]
    assert "docs/sdd/92-agent-os-runspec-yaml-semantic-parity.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-identity-signature.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-revocation-apply-proof.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-audit-archive-restore.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-approval-artifact-parity.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/mac-ubuntu-signed-approval-bundle-transfer.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/public-release-security-surface.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/dast-readiness.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/security-sdlc-roadmap.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/security-threat-model.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/manual-pentest-gate.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/host-key-evidence.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/manual-pentest-report-classifier.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/supply-chain-gate.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-transition-matrix.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-failure-injection-matrix.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/operator-safe-next-command.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-dag-edge-coverage.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-yaml-dag-parity.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-yaml-semantic-parity.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-yaml-schema-injection.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-ao-preflight-compatibility.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-default-state-version.json" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph-backward-compat.json" in index["reads"]
    assert "docs/sdd/96-agent-os-role-graph-backward-compat.md" in index["reads"]
    assert "docs/sdd/105-remote-transfer-resource-exhaustion-guard.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-resource-exhaustion-guard.json" in index["reads"]
    assert "docs/sdd/106-remote-transfer-clock-skew-tolerance.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-clock-skew-tolerance.json" in index["reads"]
    assert "docs/sdd/107-remote-transfer-bundle-id-uniqueness.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-id-uniqueness.json" in index["reads"]
    assert "docs/sdd/108-remote-transfer-bundle-content-type-allowlist.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-content-type-allowlist.json" in index["reads"]
    assert "docs/sdd/109-remote-transfer-per-tenant-quota-isolation.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-per-tenant-quota-isolation.json" in index["reads"]
    assert "docs/sdd/110-remote-transfer-wire-encryption-required.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-wire-encryption-required.json" in index["reads"]
    assert "docs/sdd/111-remote-transfer-sender-identity-rotation.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/remote-transfer-sender-identity-rotation.json" in index["reads"]
    assert "docs/sdd/112-ai-agent-blast-radius-inventory.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/ai-agent-blast-radius-inventory.json" in index["reads"]
    assert "docs/sdd/113-ai-agent-destructive-action-approval.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/ai-agent-destructive-action-approval.json" in index["reads"]
    assert "docs/sdd/114-ai-agent-credential-reachability.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/ai-agent-credential-reachability.json" in index["reads"]
    assert "docs/sdd/115-ai-agent-instruction-packaging-leak-detection.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/ai-agent-instruction-packaging-leak-detection.json" in index["reads"]
    assert "docs/sdd/116-mcp-tool-poisoning-detection.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/mcp-tool-poisoning-detection.json" in index["reads"]
    assert "docs/sdd/117-deepsec-diff-review-advisory-sast.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/deepsec-diff-review-advisory-sast.json" in index["reads"]
    assert "docs/sdd/118-agent-supply-chain-integrity.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-supply-chain-integrity.json" in index["reads"]
    assert "docs/sdd/119-prompt-injection-escape-boundary.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/prompt-injection-escape-boundary.json" in index["reads"]
    assert "docs/sdd/120-approval-clock-skew-defense.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/approval-clock-skew-defense.json" in index["reads"]
    assert "docs/sdd/121-agent-log-redaction-round-trip.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-log-redaction-round-trip.json" in index["reads"]
    assert "docs/sdd/122-per-tenant-blast-radius-cap.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/per-tenant-blast-radius-cap.json" in index["reads"]
    assert "docs/sdd/123-sandbox-egress-allowlist.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/sandbox-egress-allowlist.json" in index["reads"]
    assert "docs/sdd/124-agent-tool-arg-injection-escape.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-tool-arg-injection-escape.json" in index["reads"]
    assert "docs/sdd/125-agent-output-canary-leak-detection.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-output-canary-leak-detection.json" in index["reads"]
    assert "docs/sdd/126-agent-os-execution-budget-enforcement.md" in index["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-execution-budget-enforcement.json" in index["reads"]
    assert "artifact_count=72" in index["evidence"]
    assert "sdd_count=72" in index["evidence"]
    assert "Stop if any indexed artifact has verdict other than PASS." in index["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_operator_safe_next_command_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    safe_next = by_id["115-check-operator-safe-next-command"]
    assert safe_next["live_provider"] is False
    assert safe_next["task_count"] == 0
    assert "docs/sdd/89-operator-safe-next-command.md" in safe_next["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json" in safe_next["reads"]
    assert safe_next["commands"] == [
        "python3 scripts/check_operator_safe_next_command.py --write-output --json"
    ]
    assert "safe_action=START_NEXT_GATED_SDD_LANE" in safe_next["evidence"]
    assert "Stop if any source report dispatch_authorized or live_providers_run is true." in safe_next["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_dag_edge_coverage_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    dag = by_id["116-check-agent-os-runspec-dag-edge-coverage"]
    assert dag["live_provider"] is False
    assert dag["task_count"] == 0
    assert "docs/sdd/90-agent-os-runspec-dag-edge-coverage.md" in dag["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json" in dag["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json" in dag["reads"]
    assert dag["commands"] == [
        "python3 scripts/check_agent_os_runspec_dag_edge_coverage.py --write-output --json"
    ]
    assert "role_graph_alignment=true" in dag["evidence"]
    assert "mutation_case_count=5" in dag["evidence"]
    assert "Stop if RunSpec direct dependency edges drift from the role graph." in dag["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_yaml_dag_parity_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    parity = by_id["117-check-agent-os-runspec-yaml-dag-parity"]
    assert parity["live_provider"] is False
    assert parity["task_count"] == 0
    assert "docs/sdd/91-agent-os-runspec-yaml-dag-parity.md" in parity["reads"]
    assert "ao/runspecs/agent-os-phase-draft.yaml" in parity["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json" in parity["reads"]
    assert "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-graph.json" in parity["reads"]
    assert parity["commands"] == [
        "python3 scripts/check_agent_os_runspec_yaml_dag_parity.py --write-output --json"
    ]
    assert "yaml_renderer_alignment=true" in parity["evidence"]
    assert "yaml_role_graph_alignment=true" in parity["evidence"]
    assert "mutation_case_count=4" in parity["evidence"]
    assert "Stop if committed RunSpec YAML dependency edges drift from renderer JSON." in parity["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_cleanup_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    cleanup = by_id["95-check-agent-os-approval-cleanup"]
    assert cleanup["live_provider"] is False
    assert cleanup["task_count"] == 0
    assert "docs/sdd/70-agent-os-approval-cleanup.md" in cleanup["reads"]
    assert cleanup["commands"] == [
        "python3 scripts/cleanup_agent_os_approval.py --write-output --json"
    ]
    assert "approval_state=ABSENT" in cleanup["evidence"]
    assert "Do not pass --apply from this default reporting slice." in cleanup["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approved_launch_proof_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    proof = by_id["96-check-agent-os-approved-launch-proof"]
    assert proof["live_provider"] is False
    assert proof["task_count"] == 0
    assert "docs/sdd/69-agent-os-approved-launch-proof.md" in proof["reads"]
    assert proof["commands"] == [
        "python3 scripts/check_agent_os_approved_launch_proof.py --write-output --json"
    ]
    assert "launcher_after_approval verdict PLAN" in proof["evidence"]
    assert "Do not write the real repository approval file." in proof["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_audit_history_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    audit = by_id["97-check-agent-os-approval-audit-history"]
    assert audit["live_provider"] is False
    assert audit["task_count"] == 0
    assert "docs/sdd/71-agent-os-approval-audit-history.md" in audit["reads"]
    assert audit["commands"] == [
        "python3 scripts/check_agent_os_approval_audit_history.py --append --write-output --json"
    ]
    assert "event_count>=1" in audit["evidence"]
    assert "Do not copy nested approval payloads into audit events." in audit["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_post_approval_cleanup_route_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    route = by_id["98-check-agent-os-post-approval-cleanup-route"]
    assert route["live_provider"] is False
    assert route["task_count"] == 0
    assert "docs/sdd/72-agent-os-post-approval-cleanup-route.md" in route["reads"]
    assert route["commands"] == [
        "python3 scripts/check_agent_os_post_approval_cleanup_route.py --write-output --json"
    ]
    assert "postrun_route route ACCEPTED" in route["evidence"]
    assert "Stop if cleanup does not remove the fixture approval file." in route["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_runbook_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    runbook = by_id["99-check-agent-os-approval-runbook"]
    assert runbook["live_provider"] is False
    assert runbook["task_count"] == 0
    assert "docs/sdd/73-agent-os-approval-materialization-runbook.md" in runbook["reads"]
    assert runbook["commands"] == [
        "python3 scripts/check_agent_os_approval_runbook.py --write-output --json"
    ]
    assert "required_item_count=9" in runbook["evidence"]
    assert "Stop if the runbook omits no-dispatch constraints." in runbook["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_audit_retention_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    retention = by_id["100-check-agent-os-approval-audit-retention"]
    assert retention["live_provider"] is False
    assert retention["task_count"] == 0
    assert "docs/sdd/74-agent-os-approval-audit-retention.md" in retention["reads"]
    assert retention["commands"] == [
        "python3 scripts/check_agent_os_approval_audit_retention.py --write-output --json"
    ]
    assert "rotation_due=false" in retention["evidence"]
    assert "Do not truncate audit logs from this slice." in retention["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_bundle_signature_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    signature = by_id["101-check-agent-os-approval-bundle-signature"]
    assert signature["live_provider"] is False
    assert signature["task_count"] == 0
    assert "docs/sdd/75-agent-os-approval-bundle-signature.md" in signature["reads"]
    assert signature["commands"] == [
        "python3 scripts/check_agent_os_approval_bundle_signature.py --write-signature --write-output --json"
    ]
    assert "signature_matches=true" in signature["evidence"]
    assert "Do not write approval files from this slice." in signature["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_revocation_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    revocation = by_id["102-check-agent-os-approval-revocation"]
    assert revocation["live_provider"] is False
    assert revocation["task_count"] == 0
    assert "docs/sdd/76-agent-os-approval-revocation.md" in revocation["reads"]
    assert revocation["commands"] == [
        "python3 scripts/check_agent_os_approval_revocation.py --write-output --json"
    ]
    assert "revocation_applied=false" in revocation["evidence"]
    assert "Do not pass --apply from this default reporting slice." in revocation["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_identity_signature_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    signature = by_id["103-check-agent-os-approval-identity-signature"]
    assert signature["live_provider"] is False
    assert signature["task_count"] == 0
    assert "docs/sdd/77-agent-os-approval-identity-signature.md" in signature["reads"]
    assert signature["commands"] == [
        "python3 scripts/check_agent_os_approval_identity_signature.py --write-output --json"
    ]
    assert "signature_verified=true" in signature["evidence"]
    assert "Do not commit private signing keys." in signature["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_revocation_apply_proof_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    proof = by_id["104-check-agent-os-approval-revocation-apply-proof"]
    assert proof["live_provider"] is False
    assert proof["task_count"] == 0
    assert "docs/sdd/78-agent-os-approval-revocation-apply-proof.md" in proof["reads"]
    assert proof["commands"] == [
        "python3 scripts/check_agent_os_approval_revocation_apply_proof.py --write-output --json"
    ]
    assert "revocation_applied=true" in proof["evidence"]
    assert "Stop if revocation logs include accepted_risk or nested approval payloads." in proof["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approval_audit_archive_restore_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    restore = by_id["105-check-agent-os-approval-audit-archive-restore"]
    assert restore["live_provider"] is False
    assert restore["task_count"] == 0
    assert "docs/sdd/79-agent-os-approval-audit-archive-restore.md" in restore["reads"]
    assert restore["commands"] == [
        "python3 scripts/check_agent_os_approval_audit_archive_restore.py --write-output --json"
    ]
    assert "restore_verified=true" in restore["evidence"]
    assert "Stop if restored audit SHA-256 differs from source." in restore["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_approval_artifact_parity_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    parity = by_id["106-check-mac-ubuntu-approval-artifact-parity"]
    assert parity["live_provider"] is False
    assert parity["task_count"] == 0
    assert "docs/sdd/80-mac-ubuntu-approval-artifact-parity.md" in parity["reads"]
    assert parity["commands"] == [
        "python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --remote-host \"$FACTORY_V3_REMOTE_HOST\" --write-output --json"
    ]
    assert "artifact_parity=true" in parity["evidence"]
    assert "remote_git_synced=true" in parity["evidence"]
    assert "Stop if any approval artifact SHA-256 differs." in parity["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_signed_approval_bundle_transfer_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    transfer = by_id["107-check-mac-ubuntu-signed-approval-bundle-transfer"]
    assert transfer["live_provider"] is False
    assert transfer["task_count"] == 0
    assert "docs/sdd/81-mac-ubuntu-signed-approval-bundle-transfer.md" in transfer["reads"]
    assert transfer["commands"] == [
        "python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py --remote-host \"$FACTORY_V3_REMOTE_HOST\" --write-output --json"
    ]
    assert "signature_verified=true" in transfer["evidence"]
    assert "identity_verified=true" in transfer["evidence"]
    assert "remote_cleanup_absent=true" in transfer["evidence"]
    assert "Stop if remote signature verification fails." in transfer["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_remote_approval_materialization_dry_run_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    dry_run = by_id["108-check-mac-ubuntu-remote-approval-materialization-dry-run"]
    assert dry_run["live_provider"] is False
    assert dry_run["task_count"] == 0
    assert "docs/sdd/82-mac-ubuntu-remote-approval-materialization-dry-run.md" in dry_run["reads"]
    assert dry_run["commands"] == [
        "python3 scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py --remote-host \"$FACTORY_V3_REMOTE_HOST\" --write-output --json"
    ]
    assert "materialization_dry_run_passed=true" in dry_run["evidence"]
    assert "approval_file_written=false" in dry_run["evidence"]
    assert "Stop if remote materialization writes an approval file." in dry_run["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_remote_approval_revocation_rollback_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    rollback = by_id["109-check-mac-ubuntu-remote-approval-revocation-rollback"]
    assert rollback["live_provider"] is False
    assert rollback["task_count"] == 0
    assert "docs/sdd/83-mac-ubuntu-remote-approval-revocation-rollback.md" in rollback["reads"]
    assert rollback["commands"] == [
        "python3 scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py --remote-host \"$FACTORY_V3_REMOTE_HOST\" --write-output --json"
    ]
    assert "revocation_applied=true" in rollback["evidence"]
    assert "rollback_restore_verified=true" in rollback["evidence"]
    assert "Stop if remote rollback restore is not verified." in rollback["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_remote_approval_runbook_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    runbook = by_id["110-check-mac-ubuntu-remote-approval-runbook"]
    assert runbook["live_provider"] is False
    assert runbook["task_count"] == 0
    assert "docs/sdd/84-mac-ubuntu-remote-approval-runbook.md" in runbook["reads"]
    assert "docs/runbooks/mac-ubuntu-remote-approval-operations.md" in runbook["reads"]
    assert runbook["commands"] == [
        "python3 scripts/check_mac_ubuntu_remote_approval_runbook.py --write-output --json"
    ]
    assert "required_item_count=17" in runbook["evidence"]
    assert "Stop if the runbook omits revocation rollback." in runbook["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mac_ubuntu_remote_approved_fixture_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    fixture = by_id["111-check-mac-ubuntu-remote-approved-fixture"]
    assert fixture["live_provider"] is False
    assert fixture["task_count"] == 0
    assert "docs/sdd/85-mac-ubuntu-remote-approved-fixture.md" in fixture["reads"]
    assert fixture["commands"] == [
        "python3 scripts/check_mac_ubuntu_remote_approved_fixture.py --remote-host \"$FACTORY_V3_REMOTE_HOST\" --write-output --json"
    ]
    assert "launcher_plan_verified=true" in fixture["evidence"]
    assert "would_run_provider=false" in fixture["evidence"]
    assert "Stop if the launcher does not stop at PLAN." in fixture["stop_rules"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_clock_skew_tolerance_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    skew = by_id["132-check-remote-transfer-clock-skew-tolerance"]
    assert skew["live_provider"] is False
    assert skew["task_count"] == 0
    assert "docs/sdd/106-remote-transfer-clock-skew-tolerance.md" in skew["reads"]
    assert "scripts/check_remote_transfer_clock_skew_tolerance.py" in skew["reads"]
    assert skew["commands"] == [
        "python3 scripts/check_remote_transfer_clock_skew_tolerance.py --write-output --json"
    ]
    assert "Remote-transfer clock skew tolerance verdict PASS" in skew["evidence"]
    assert "case_count=5" in skew["evidence"]
    assert "mutation_case_count=4" in skew["evidence"]
    assert "clean_within_skew_tolerance_passes=PASS" in skew["evidence"]
    assert "sender_clock_ahead_of_receiver_rejected=FAIL" in skew["evidence"]
    assert "sender_clock_behind_receiver_rejected=FAIL" in skew["evidence"]
    assert "future_dated_bundle_accepted_as_currently_valid_rejected=FAIL" in skew["evidence"]
    assert "ttl_window_straddling_skew_silently_extended_rejected=FAIL" in skew["evidence"]
    assert "dispatch_authorized=false" in skew["evidence"]
    assert "live_providers_run=false" in skew["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_bundle_id_uniqueness_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    uniq = by_id["133-check-remote-transfer-bundle-id-uniqueness"]
    assert uniq["live_provider"] is False
    assert uniq["task_count"] == 0
    assert "docs/sdd/107-remote-transfer-bundle-id-uniqueness.md" in uniq["reads"]
    assert "scripts/check_remote_transfer_bundle_id_uniqueness.py" in uniq["reads"]
    assert uniq["commands"] == [
        "python3 scripts/check_remote_transfer_bundle_id_uniqueness.py --write-output --json"
    ]
    assert "Remote-transfer bundle-id uniqueness verdict PASS" in uniq["evidence"]
    assert "case_count=5" in uniq["evidence"]
    assert "mutation_case_count=4" in uniq["evidence"]
    assert "clean_unique_bundle_ids_pass=PASS" in uniq["evidence"]
    assert "duplicate_bundle_id_within_session_rejected=FAIL" in uniq["evidence"]
    assert "cross_sender_bundle_id_collision_rejected=FAIL" in uniq["evidence"]
    assert "bundle_id_truncation_collision_rejected=FAIL" in uniq["evidence"]
    assert "bundle_id_replayed_after_completion_rejected=FAIL" in uniq["evidence"]
    assert "dispatch_authorized=false" in uniq["evidence"]
    assert "live_providers_run=false" in uniq["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_bundle_content_type_allowlist_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    allow = by_id["134-check-remote-transfer-bundle-content-type-allowlist"]
    assert allow["live_provider"] is False
    assert allow["task_count"] == 0
    assert "docs/sdd/108-remote-transfer-bundle-content-type-allowlist.md" in allow["reads"]
    assert "scripts/check_remote_transfer_bundle_content_type_allowlist.py" in allow["reads"]
    assert allow["commands"] == [
        "python3 scripts/check_remote_transfer_bundle_content_type_allowlist.py --write-output --json"
    ]
    assert "Remote-transfer bundle content-type allowlist verdict PASS" in allow["evidence"]
    assert "case_count=5" in allow["evidence"]
    assert "mutation_case_count=4" in allow["evidence"]
    assert "clean_allowlisted_content_type_passes=PASS" in allow["evidence"]
    assert "unknown_content_type_silently_coerced_rejected=FAIL" in allow["evidence"]
    assert "mismatched_extension_to_content_type_rejected=FAIL" in allow["evidence"]
    assert "unknown_content_encoding_silently_decoded_rejected=FAIL" in allow["evidence"]
    assert "content_type_charset_parameter_smuggled_rejected=FAIL" in allow["evidence"]
    assert "dispatch_authorized=false" in allow["evidence"]
    assert "live_providers_run=false" in allow["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_per_tenant_quota_isolation_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    quota = by_id["135-check-remote-transfer-per-tenant-quota-isolation"]
    assert quota["live_provider"] is False
    assert quota["task_count"] == 0
    assert "docs/sdd/109-remote-transfer-per-tenant-quota-isolation.md" in quota["reads"]
    assert "scripts/check_remote_transfer_per_tenant_quota_isolation.py" in quota["reads"]
    assert quota["commands"] == [
        "python3 scripts/check_remote_transfer_per_tenant_quota_isolation.py --write-output --json"
    ]
    assert "Remote-transfer per-tenant quota isolation verdict PASS" in quota["evidence"]
    assert "case_count=5" in quota["evidence"]
    assert "mutation_case_count=4" in quota["evidence"]
    assert "clean_per_tenant_within_quota_passes=PASS" in quota["evidence"]
    assert "tenant_a_overflows_tenant_b_quota_slot_rejected=FAIL" in quota["evidence"]
    assert "aggregated_quota_across_tenants_merged_rejected=FAIL" in quota["evidence"]
    assert "tenant_identity_stripped_silently_coerced_to_default_rejected=FAIL" in quota["evidence"]
    assert "quota_refund_on_abort_double_credited_rejected=FAIL" in quota["evidence"]
    assert "dispatch_authorized=false" in quota["evidence"]
    assert "live_providers_run=false" in quota["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_wire_encryption_required_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    enc = by_id["136-check-remote-transfer-wire-encryption-required"]
    assert enc["live_provider"] is False
    assert enc["task_count"] == 0
    assert "docs/sdd/110-remote-transfer-wire-encryption-required.md" in enc["reads"]
    assert "scripts/check_remote_transfer_wire_encryption_required.py" in enc["reads"]
    assert enc["commands"] == [
        "python3 scripts/check_remote_transfer_wire_encryption_required.py --write-output --json"
    ]
    assert "Remote-transfer wire encryption required verdict PASS" in enc["evidence"]
    assert "case_count=5" in enc["evidence"]
    assert "mutation_case_count=4" in enc["evidence"]
    assert "clean_encrypted_bundle_accepted=PASS" in enc["evidence"]
    assert "cleartext_bundle_silently_accepted_rejected=FAIL" in enc["evidence"]
    assert "downgraded_tls_cipher_silently_accepted_rejected=FAIL" in enc["evidence"]
    assert "weak_null_cipher_suite_negotiated_rejected=FAIL" in enc["evidence"]
    assert "encryption_header_stripped_after_handshake_rejected=FAIL" in enc["evidence"]
    assert "dispatch_authorized=false" in enc["evidence"]
    assert "live_providers_run=false" in enc["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_sender_identity_rotation_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    rot = by_id["137-check-remote-transfer-sender-identity-rotation"]
    assert rot["live_provider"] is False
    assert rot["task_count"] == 0
    assert "docs/sdd/111-remote-transfer-sender-identity-rotation.md" in rot["reads"]
    assert "scripts/check_remote_transfer_sender_identity_rotation.py" in rot["reads"]
    assert rot["commands"] == [
        "python3 scripts/check_remote_transfer_sender_identity_rotation.py --write-output --json"
    ]
    assert "Remote-transfer sender identity rotation verdict PASS" in rot["evidence"]
    assert "case_count=5" in rot["evidence"]
    assert "mutation_case_count=4" in rot["evidence"]
    assert "clean_post_rotation_bundle_accepted=PASS" in rot["evidence"]
    assert "retired_identity_silently_accepted_rejected=FAIL" in rot["evidence"]
    assert "rotation_announcement_unsigned_silently_accepted_rejected=FAIL" in rot["evidence"]
    assert "future_rotation_effective_at_silently_accepted_rejected=FAIL" in rot["evidence"]
    assert "dual_acceptance_window_silently_left_open_rejected=FAIL" in rot["evidence"]
    assert "dispatch_authorized=false" in rot["evidence"]
    assert "live_providers_run=false" in rot["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_ai_agent_blast_radius_inventory_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    inv = by_id["138-check-ai-agent-blast-radius-inventory"]
    assert inv["live_provider"] is False
    assert inv["task_count"] == 0
    assert "docs/sdd/112-ai-agent-blast-radius-inventory.md" in inv["reads"]
    assert "scripts/check_ai_agent_blast_radius_inventory.py" in inv["reads"]
    assert inv["commands"] == [
        "python3 scripts/check_ai_agent_blast_radius_inventory.py --write-output --json"
    ]
    assert "AI agent blast-radius inventory verdict PASS" in inv["evidence"]
    assert "case_count=6" in inv["evidence"]
    assert "mutation_case_count=5" in inv["evidence"]
    assert "clean_inventory_classified_and_gated=PASS" in inv["evidence"]
    assert "unclassified_high_blast_radius_command_path_rejected=FAIL" in inv["evidence"]
    assert "destructive_action_without_approval_gate_rejected=FAIL" in inv["evidence"]
    assert "credential_path_reachable_from_untrusted_content_rejected=FAIL" in inv["evidence"]
    assert "provider_dispatch_without_approval_readiness_rejected=FAIL" in inv["evidence"]
    assert "release_artifact_includes_instruction_or_credentials_rejected=FAIL" in inv["evidence"]
    assert "dispatch_authorized=false" in inv["evidence"]
    assert "live_providers_run=false" in inv["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_ai_agent_destructive_action_approval_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    approval = by_id["139-check-ai-agent-destructive-action-approval"]
    assert approval["live_provider"] is False
    assert approval["task_count"] == 0
    assert "docs/sdd/113-ai-agent-destructive-action-approval.md" in approval["reads"]
    assert "scripts/check_ai_agent_destructive_action_approval.py" in approval["reads"]
    assert approval["commands"] == [
        "python3 scripts/check_ai_agent_destructive_action_approval.py --write-output --json"
    ]
    assert "AI agent destructive-action approval gate verdict PASS" in approval["evidence"]
    assert "case_count=6" in approval["evidence"]
    assert "mutation_case_count=5" in approval["evidence"]
    assert "clean_destructive_action_with_fresh_scoped_approval_executes=PASS" in approval["evidence"]
    assert "stale_approval_reused_after_expiry_rejected=FAIL" in approval["evidence"]
    assert "approval_scope_widened_at_exec_silently_accepted_rejected=FAIL" in approval["evidence"]
    assert "approval_consumed_twice_for_distinct_destructive_ops_rejected=FAIL" in approval["evidence"]
    assert "destructive_op_runs_with_policy_only_without_token_rejected=FAIL" in approval["evidence"]
    assert "parent_process_approval_inherited_by_child_without_reconfirm_rejected=FAIL" in approval["evidence"]
    assert "dispatch_authorized=false" in approval["evidence"]
    assert "live_providers_run=false" in approval["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_ai_agent_credential_reachability_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    cred = by_id["140-check-ai-agent-credential-reachability"]
    assert cred["live_provider"] is False
    assert cred["task_count"] == 0
    assert "docs/sdd/114-ai-agent-credential-reachability.md" in cred["reads"]
    assert "scripts/check_ai_agent_credential_reachability.py" in cred["reads"]
    assert cred["commands"] == [
        "python3 scripts/check_ai_agent_credential_reachability.py --write-output --json"
    ]
    assert "AI agent credential-reachability gate verdict PASS" in cred["evidence"]
    assert "case_count=6" in cred["evidence"]
    assert "mutation_case_count=5" in cred["evidence"]
    assert "clean_no_untrusted_to_credential_reachable_path=PASS" in cred["evidence"]
    assert "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected=FAIL" in cred["evidence"]
    assert "agent_tool_output_piped_to_shell_with_ssh_dir_rejected=FAIL" in cred["evidence"]
    assert "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected=FAIL" in cred["evidence"]
    assert "web_fetch_reflected_into_shell_resolving_env_rejected=FAIL" in cred["evidence"]
    assert "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected=FAIL" in cred["evidence"]
    assert "dispatch_authorized=false" in cred["evidence"]
    assert "live_providers_run=false" in cred["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_ai_agent_instruction_packaging_leak_detection_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    leak = by_id["141-check-ai-agent-instruction-packaging-leak-detection"]
    assert leak["live_provider"] is False
    assert leak["task_count"] == 0
    assert "docs/sdd/115-ai-agent-instruction-packaging-leak-detection.md" in leak["reads"]
    assert "scripts/check_ai_agent_instruction_packaging_leak_detection.py" in leak["reads"]
    assert leak["commands"] == [
        "python3 scripts/check_ai_agent_instruction_packaging_leak_detection.py --write-output --json"
    ]
    assert "AI agent instruction & release packaging leak detection gate verdict PASS" in leak["evidence"]
    assert "case_count=6" in leak["evidence"]
    assert "mutation_case_count=5" in leak["evidence"]
    assert "clean_no_instruction_or_packaging_leaks_in_public_artifacts=PASS" in leak["evidence"]
    assert "claude_md_directives_leaked_into_status_report_rejected=FAIL" in leak["evidence"]
    assert "agent_memory_snippet_copy_pasted_into_public_doc_rejected=FAIL" in leak["evidence"]
    assert "raw_user_prompt_logged_in_operator_slice_evidence_rejected=FAIL" in leak["evidence"]
    assert "anthropic_api_key_surfaced_in_evaluation_transcript_rejected=FAIL" in leak["evidence"]
    assert "tmp_diagnostic_path_included_in_public_artifact_rejected=FAIL" in leak["evidence"]
    assert "dispatch_authorized=false" in leak["evidence"]
    assert "live_providers_run=false" in leak["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_mcp_tool_poisoning_detection_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    poisoning = by_id["142-check-mcp-tool-poisoning-detection"]
    assert poisoning["live_provider"] is False
    assert poisoning["task_count"] == 0
    assert "docs/sdd/116-mcp-tool-poisoning-detection.md" in poisoning["reads"]
    assert "scripts/check_mcp_tool_poisoning_detection.py" in poisoning["reads"]
    assert poisoning["commands"] == [
        "python3 scripts/check_mcp_tool_poisoning_detection.py --write-output --json"
    ]
    assert "MCP / Tool poisoning detection gate verdict PASS" in poisoning["evidence"]
    assert "case_count=6" in poisoning["evidence"]
    assert "mutation_case_count=5" in poisoning["evidence"]
    assert "clean_no_mcp_or_tool_poisoning_indicators=PASS" in poisoning["evidence"]
    assert "hidden_imperative_in_mcp_description_rejected=FAIL" in poisoning["evidence"]
    assert "tool_result_schema_adds_destructive_default_arg_rejected=FAIL" in poisoning["evidence"]
    assert "mcp_returns_url_to_fetch_and_apply_rejected=FAIL" in poisoning["evidence"]
    assert "tool_name_shadowing_overrides_native_tool_rejected=FAIL" in poisoning["evidence"]
    assert "signed_descriptor_advertises_unallowed_privilege_rejected=FAIL" in poisoning["evidence"]
    assert "dispatch_authorized=false" in poisoning["evidence"]
    assert "live_providers_run=false" in poisoning["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_deepsec_diff_review_advisory_sast_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    sast = by_id["143-check-deepsec-diff-review-advisory-sast"]
    assert sast["live_provider"] is False
    assert sast["task_count"] == 0
    assert "docs/sdd/117-deepsec-diff-review-advisory-sast.md" in sast["reads"]
    assert "scripts/check_deepsec_diff_review_advisory_sast.py" in sast["reads"]
    assert sast["commands"] == [
        "python3 scripts/check_deepsec_diff_review_advisory_sast.py --write-output --json"
    ]
    assert "DeepSec diff-review advisory SAST gate verdict PASS" in sast["evidence"]
    assert "case_count=6" in sast["evidence"]
    assert "mutation_case_count=5" in sast["evidence"]
    assert "clean_no_untrusted_to_dangerous_sink_edges=PASS" in sast["evidence"]
    assert "untrusted_input_flows_into_shell_command_rejected=FAIL" in sast["evidence"]
    assert "untrusted_input_flows_into_fs_write_outside_workspace_rejected=FAIL" in sast["evidence"]
    assert "untrusted_input_flows_into_network_egress_rejected=FAIL" in sast["evidence"]
    assert "eval_or_exec_on_retrieved_content_rejected=FAIL" in sast["evidence"]
    assert "dynamic_import_from_agent_controlled_path_rejected=FAIL" in sast["evidence"]
    assert "dispatch_authorized=false" in sast["evidence"]
    assert "live_providers_run=false" in sast["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_supply_chain_integrity_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    integrity = by_id["144-check-agent-supply-chain-integrity"]
    assert integrity["live_provider"] is False
    assert integrity["task_count"] == 0
    assert "docs/sdd/118-agent-supply-chain-integrity.md" in integrity["reads"]
    assert "scripts/check_agent_supply_chain_integrity.py" in integrity["reads"]
    assert integrity["commands"] == [
        "python3 scripts/check_agent_supply_chain_integrity.py --write-output --json"
    ]
    assert "Agent supply-chain integrity gate verdict PASS" in integrity["evidence"]
    assert "case_count=6" in integrity["evidence"]
    assert "mutation_case_count=5" in integrity["evidence"]
    assert "clean_no_unauthorized_provenance_or_unsigned_package_edges=PASS" in integrity["evidence"]
    assert "unsigned_package_admitted_without_signature_rejected=FAIL" in integrity["evidence"]
    assert "lock_file_digest_mismatch_admitted_rejected=FAIL" in integrity["evidence"]
    assert "dependency_confusion_via_shadow_registry_rejected=FAIL" in integrity["evidence"]
    assert "post_install_script_with_network_egress_rejected=FAIL" in integrity["evidence"]
    assert "transitive_yank_without_repin_rejected=FAIL" in integrity["evidence"]
    assert "dispatch_authorized=false" in integrity["evidence"]
    assert "live_providers_run=false" in integrity["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_remote_transfer_resource_exhaustion_guard_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    guard = by_id["131-check-remote-transfer-resource-exhaustion-guard"]
    assert guard["live_provider"] is False
    assert guard["task_count"] == 0
    assert "docs/sdd/105-remote-transfer-resource-exhaustion-guard.md" in guard["reads"]
    assert "scripts/check_remote_transfer_resource_exhaustion_guard.py" in guard["reads"]
    assert guard["commands"] == [
        "python3 scripts/check_remote_transfer_resource_exhaustion_guard.py --write-output --json"
    ]
    assert "Remote-transfer resource exhaustion guard verdict PASS" in guard["evidence"]
    assert "case_count=5" in guard["evidence"]
    assert "mutation_case_count=4" in guard["evidence"]
    assert "clean_within_quota_passes=PASS" in guard["evidence"]
    assert "announced_chunk_count_exceeds_quota_rejected=FAIL" in guard["evidence"]
    assert "announced_total_size_exceeds_quota_rejected=FAIL" in guard["evidence"]
    assert "per_chunk_size_exceeds_max_rejected=FAIL" in guard["evidence"]
    assert "transfer_exceeds_announced_count_rejected=FAIL" in guard["evidence"]
    assert "dispatch_authorized=false" in guard["evidence"]
    assert "live_providers_run=false" in guard["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_uat_response_gate_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    gate = by_id["48-record-agent-os-uat-response-gate"]
    assert gate["live_provider"] is False
    assert gate["task_count"] == 0
    assert gate["commands"] == [
        "python3 scripts/agent_os_uat_response_gate.py --write-template --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_closure_gate_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    gate = by_id["49-record-agent-os-closure-gate"]
    assert gate["live_provider"] is False
    assert gate["task_count"] == 0
    assert gate["commands"] == [
        "python3 scripts/agent_os_closure_gate.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_renderer_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    renderer = by_id["50-record-agent-os-runspec-renderer"]
    assert renderer["live_provider"] is False
    assert renderer["task_count"] == 0
    assert renderer["commands"] == [
        "python3 scripts/agent_os_runspec_renderer.py --provider-profile .env.example --write-output --write-runspec --json"
    ]
    assert ".env.example" in renderer["reads"]
    assert "provider_profile_checked=true" in renderer["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_runspec_validation_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    validator = by_id["51-record-agent-os-runspec-validation"]
    assert validator["live_provider"] is False
    assert validator["task_count"] == 0
    assert validator["commands"] == [
        "python3 scripts/agent_os_runspec_validator.py --provider-profile .env.example --write-output --json"
    ]
    assert ".env.example" in validator["reads"]
    assert "provider_profile_matches=true" in validator["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_execution_prep_slices():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    assert by_id["52-record-agent-os-runspec-execution-approval-gate"]["commands"] == [
        "python3 scripts/check_agent_os_runspec_execution_approval_gate.py --write-output --json"
    ]
    assert "docs/sdd/61-agent-os-runspec-execution-plan-lock.md" in by_id["52-record-agent-os-runspec-execution-approval-gate"]["reads"]
    assert "runspec_sha256 recorded" in by_id["52-record-agent-os-runspec-execution-approval-gate"]["evidence"]
    assert "runspec_lock algorithm sha256" in by_id["52-record-agent-os-runspec-execution-approval-gate"]["evidence"]
    assert by_id["53-rehearse-agent-os-runspec-execution-no-provider"]["commands"] == [
        "python3 scripts/rehearse_agent_os_runspec_execution.py --write-output --json"
    ]
    assert by_id["54-route-agent-os-runspec-postrun"]["commands"] == [
        "python3 scripts/route_agent_os_runspec_postrun.py --write-output --json"
    ]
    assert "existing blocked execution report routes to BLOCKED" in by_id["54-route-agent-os-runspec-postrun"]["evidence"]
    assert "Stop if current blocked execution evidence is hidden or downgraded." in by_id["54-route-agent-os-runspec-postrun"]["stop_rules"]
    assert by_id["55-preserve-agent-os-runspec-diagnostics"]["commands"] == [
        "python3 scripts/preserve_agent_os_runspec_diagnostics.py --write-output --json"
    ]
    assert all(by_id[item]["live_provider"] is False for item in [
        "52-record-agent-os-runspec-execution-approval-gate",
        "53-rehearse-agent-os-runspec-execution-no-provider",
        "54-route-agent-os-runspec-postrun",
        "55-preserve-agent-os-runspec-diagnostics",
    ])
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_execution_readiness_slices():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    assert by_id["56-validate-agent-os-runspec-execution-approval"]["commands"] == [
        "python3 scripts/validate_agent_os_runspec_execution_approval.py --write-output --json"
    ]
    assert "docs/sdd/61-agent-os-runspec-execution-plan-lock.md" in by_id["56-validate-agent-os-runspec-execution-approval"]["reads"]
    assert "runspec_sha256 carried from approval gate" in by_id["56-validate-agent-os-runspec-execution-approval"]["evidence"]
    assert "provider_profile_matches=true" in by_id["56-validate-agent-os-runspec-execution-approval"]["evidence"]
    assert "Stop if provider-profile alignment is not carried through approval validation." in by_id["56-validate-agent-os-runspec-execution-approval"]["stop_rules"]
    assert by_id["57-record-agent-os-runspec-execution-blocked"]["expected_blocked"] is True
    assert by_id["57-record-agent-os-runspec-execution-blocked"]["expected_exit"] == 1
    assert "docs/sdd/68-agent-os-approval-lifecycle.md" in by_id["57-record-agent-os-runspec-execution-blocked"]["reads"]
    assert "launcher blocks when provider-profile alignment is absent or false" in by_id["57-record-agent-os-runspec-execution-blocked"]["evidence"]
    assert "launcher rechecks approval lifecycle at execution time" in by_id["57-record-agent-os-runspec-execution-blocked"]["evidence"]
    assert by_id["58-validate-agent-os-runspec-evaluator-closure"]["commands"] == [
        "python3 scripts/validate_agent_os_runspec_evaluator_closure.py --write-output --json"
    ]
    assert by_id["59-check-agent-os-role-output-schema"]["commands"] == [
        "python3 scripts/check_agent_os_role_output_schema.py --write-output --json"
    ]
    assert by_id["60-check-agent-os-execution-hygiene"]["commands"] == [
        "python3 scripts/check_agent_os_execution_hygiene.py --prompt ao/prompts/agent-os-phase/01-planner.md --prompt ao/prompts/agent-os-phase/02-plan-hardener.md --prompt ao/prompts/agent-os-phase/03-factory-manager.md --prompt ao/prompts/agent-os-phase/04-implementer.md --prompt ao/prompts/agent-os-phase/05-slice-reviewer.md --prompt ao/prompts/agent-os-phase/06-integrator.md --prompt ao/prompts/agent-os-phase/07-evaluator-closer.md --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_approved_execution_runner_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    runner = by_id["61-record-agent-os-approved-execution-runner"]
    assert runner["live_provider"] is False
    assert runner["expected_blocked"] is True
    assert runner["expected_exit"] == 1
    assert runner["commands"] == [
        "python3 scripts/run_agent_os_runspec_execution.py --write-output run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-execution-runner.json --json"
    ]
    assert "docs/sdd/61-agent-os-runspec-execution-plan-lock.md" in runner["reads"]
    assert "docs/sdd/68-agent-os-approval-lifecycle.md" in runner["reads"]
    assert "current_runspec_sha256 recorded when approval is valid" in runner["evidence"]
    assert "approval_lifecycle recorded before dispatch" in runner["evidence"]
    assert "provider-profile alignment remains required before dispatch" in runner["evidence"]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_agent_os_role_output_ingestion_slice():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    by_id = {item["id"]: item for item in slices if isinstance(item, dict)}
    ingestion = by_id["62-ingest-agent-os-role-outputs"]
    assert ingestion["live_provider"] is False
    assert ingestion["commands"] == [
        "python3 scripts/ingest_agent_os_role_outputs.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_default_manifest_includes_50_slice_live_approval_gate():
    manifest = Path("examples/remote-transfer-v2-stress/operator-slices.json")
    result = validate_operator_slices.validate_path(manifest)

    data = validate_operator_slices.load_manifest(manifest)
    slices = data["slices"]
    assert isinstance(slices, list)
    gate = next(item for item in slices if item["id"] == "28-check-50-slice-live-approval-gate")
    assert gate["live_provider"] is False
    assert gate["requires_override"] is True
    assert gate["approval_env"] == "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
    assert gate["task_count"] == 107
    assert gate["commands"] == [
        "python3 scripts/check_50_slice_live_approval_gate.py --write-output --json"
    ]
    assert result["verdict"] == "PASS"


def test_manifest_requires_expected_block_for_non_live_run_command():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    validation = slices[1]
    assert isinstance(validation, dict)
    validation["commands"] = ["python3 scripts/factory_run.py --run"]

    errors = validate_operator_slices.validate_manifest_data(data)

    assert any("--run is only allowed" in error for error in errors)


def test_manifest_allows_preflight_block_run_command():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    slices.append(
        {
            "order": 3,
            "id": "03-preflight-block",
            "mode": "preflight-block",
            "live_provider": False,
            "expected_blocked": True,
            "expected_exit": 1,
            "task_count": 2007,
            "objective": "Prove large live run blocks.",
            "reads": ["topology.yaml"],
            "writes": [],
            "commands": ["python3 scripts/factory_run.py --run"],
            "evidence": ["blocked before AO"],
            "stop_rules": ["Stop if AO starts."],
        }
    )

    errors = validate_operator_slices.validate_manifest_data(data)

    assert errors == []


def test_manifest_blocks_large_live_without_override():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    live = slices[2]
    assert isinstance(live, dict)
    live["task_count"] = 57

    errors = validate_operator_slices.validate_manifest_data(data)

    assert any("live task_count above 50 requires override" in error for error in errors)


def test_manifest_allows_large_live_with_explicit_override():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    live = slices[2]
    assert isinstance(live, dict)
    live.update(
        {
            "task_count": 57,
            "requires_override": True,
            "approval_env": "FACTORY_V3_ALLOW_LARGE_LIVE_RUN",
        }
    )

    errors = validate_operator_slices.validate_manifest_data(data)

    assert errors == []


def test_manifest_accepts_positive_timeout_seconds():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    live = slices[2]
    assert isinstance(live, dict)
    live["timeout_seconds"] = 1800

    errors = validate_operator_slices.validate_manifest_data(data)

    assert errors == []


def test_manifest_rejects_invalid_timeout_seconds():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    live = slices[2]
    assert isinstance(live, dict)
    live["timeout_seconds"] = 0

    errors = validate_operator_slices.validate_manifest_data(data)

    assert any("timeout_seconds" in error for error in errors)


def test_manifest_allows_string_env_and_path_prepend():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    local = slices[0]
    assert isinstance(local, dict)
    local["env"] = {
        "FACTORY_V3_AO_RUNTIME_PATH": "/tmp/runtime",
        "PATH_PREPEND": ["/tmp/runtime/target/release"],
    }

    errors = validate_operator_slices.validate_manifest_data(data)

    assert errors == []


def test_manifest_rejects_non_string_env_value():
    data = valid_manifest()
    slices = data["slices"]
    assert isinstance(slices, list)
    local = slices[0]
    assert isinstance(local, dict)
    local["env"] = {"FACTORY_V3_AO_RUNTIME_PATH": 123}

    errors = validate_operator_slices.validate_manifest_data(data)

    assert any("env.FACTORY_V3_AO_RUNTIME_PATH" in error for error in errors)


def test_cli_emits_json(tmp_path, capsys):
    manifest = tmp_path / "operator-slices.json"
    manifest.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    result = validate_operator_slices.main([str(manifest), "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "PASS"


def test_cli_lists_local_only_slices(tmp_path, capsys):
    manifest = tmp_path / "operator-slices.json"
    manifest.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    result = validate_operator_slices.main([str(manifest), "--list-slices", "--local-only", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in payload["slices"]] == ["00-diagnostics", "01-validation"]


def test_cli_prints_commands_for_slice(tmp_path, capsys):
    manifest = tmp_path / "operator-slices.json"
    manifest.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    result = validate_operator_slices.main([str(manifest), "--commands-for", "02-live", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["commands"] == ["python3 scripts/factory_run.py --brief brief.md --run"]
