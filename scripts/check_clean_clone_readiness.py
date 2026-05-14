#!/usr/bin/env python3
"""Verify accepted 50-slice evidence from a clean clone."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redact_strict_public_artifacts import redact_text


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/clean-clone-readiness.json"


def command_plan(*, slug: str = DEFAULT_SLUG, include_closure: bool = True) -> list[list[str]]:
    commands = [
        ["python3", "scripts/summarize_50_slice_operator_state.py", "--json"],
        ["python3", "scripts/check_live_acceptance.py", "--slug", slug, "--json"],
        ["python3", "scripts/validate_factory.py", "--json"],
        ["python3", "scripts/check_agent_os_router_migration_matrix.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_provider_boundary_matrix.py", "--json"],
        ["python3", "scripts/agent_os_runspec_validator.py", "--provider-profile", ".env.example", "--json"],
        ["python3", "scripts/cleanup_agent_os_state_artifacts.py", "--json"],
        ["python3", "scripts/check_agent_os_approved_launch_proof.py", "--json"],
        ["python3", "scripts/cleanup_agent_os_approval.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_audit_history.py", "--json"],
        ["python3", "scripts/check_agent_os_post_approval_cleanup_route.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_runbook.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_audit_retention.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_bundle_signature.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_revocation.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_identity_signature.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_revocation_apply_proof.py", "--json"],
        ["python3", "scripts/check_agent_os_approval_audit_archive_restore.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_approval_artifact_parity.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_remote_approval_runbook.py", "--json"],
        ["python3", "scripts/check_mac_ubuntu_remote_approved_fixture.py", "--json"],
        ["python3", "scripts/check_agent_os_architecture_implementation_gate.py", "--json"],
        ["python3", "scripts/check_agent_os_router_transition_matrix.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_failure_injection_matrix.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_dag_edge_coverage.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_yaml_dag_parity.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_yaml_semantic_parity.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_yaml_schema_injection.py", "--json"],
        ["python3", "scripts/check_agent_os_runspec_ao_preflight_compatibility.py", "--json"],
        ["python3", "scripts/check_agent_os_router_default_state_version.py", "--json"],
        ["python3", "scripts/check_agent_os_role_graph_backward_compat.py", "--json"],
        ["python3", "scripts/check_remote_transfer_chunk_cleanup_invariants.py", "--json"],
        ["python3", "scripts/check_remote_transfer_signed_bundle_tamper.py", "--json"],
        ["python3", "scripts/check_remote_transfer_approval_expiry_rotation.py", "--json"],
        ["python3", "scripts/check_remote_transfer_bundle_ordering_resume.py", "--json"],
        ["python3", "scripts/check_remote_transfer_provider_redaction_round_trip.py", "--json"],
        ["python3", "scripts/check_remote_transfer_network_retry_idempotency.py", "--json"],
        ["python3", "scripts/check_remote_transfer_concurrent_transfer_collision.py", "--json"],
        ["python3", "scripts/check_remote_transfer_bundle_schema_version_skew.py", "--json"],
        ["python3", "scripts/check_remote_transfer_resource_exhaustion_guard.py", "--json"],
        ["python3", "scripts/check_remote_transfer_clock_skew_tolerance.py", "--json"],
        ["python3", "scripts/check_remote_transfer_bundle_id_uniqueness.py", "--json"],
        ["python3", "scripts/check_remote_transfer_bundle_content_type_allowlist.py", "--json"],
        ["python3", "scripts/check_remote_transfer_per_tenant_quota_isolation.py", "--json"],
        ["python3", "scripts/check_remote_transfer_wire_encryption_required.py", "--json"],
        ["python3", "scripts/check_remote_transfer_sender_identity_rotation.py", "--json"],
        ["python3", "scripts/check_ai_agent_blast_radius_inventory.py", "--json"],
        ["python3", "scripts/check_ai_agent_destructive_action_approval.py", "--json"],
        ["python3", "scripts/check_ai_agent_credential_reachability.py", "--json"],
        ["python3", "scripts/check_ai_agent_instruction_packaging_leak_detection.py", "--json"],
        ["python3", "scripts/check_mcp_tool_poisoning_detection.py", "--json"],
        ["python3", "scripts/check_deepsec_diff_review_advisory_sast.py", "--json"],
        ["python3", "scripts/check_agent_supply_chain_integrity.py", "--json"],
        ["python3", "scripts/check_prompt_injection_escape_boundary.py", "--json"],
        ["python3", "scripts/check_approval_clock_skew_defense.py", "--json"],
        ["python3", "scripts/check_agent_log_redaction_round_trip.py", "--json"],
        ["python3", "scripts/check_per_tenant_blast_radius_cap.py", "--json"],
        ["python3", "scripts/check_sandbox_egress_allowlist.py", "--json"],
        ["python3", "scripts/check_agent_tool_arg_injection_escape.py", "--json"],
        ["python3", "scripts/check_agent_output_canary_leak_detection.py", "--json"],
        ["python3", "scripts/check_agent_os_execution_budget_enforcement.py", "--json"],
        ["python3", "scripts/check_agent_system_prompt_tamper_detection.py", "--json"],
        ["python3", "scripts/check_tool_result_cache_poisoning_defense.py", "--json"],
        ["python3", "scripts/check_agent_credential_scope_narrowing.py", "--json"],
    ]
    if include_closure:
        commands.append(["python3", "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"])
    commands.extend(
        [
            ["python3", "scripts/redact_strict_public_artifacts.py", "--fail-on-changes", "--json"],
            ["python3", "scripts/check_status_json_integrity.py", "--json"],
        ]
    )
    return commands


_BACKSLASH_TAIL_AFTER_PLACEHOLDER = re.compile(
    r"(\${FACTORY_V3_(?:ROOT|CLEAN_CLONE)})((?:\\[A-Za-z0-9._\-]+)+)"
)


def sanitize(value: Any, *, root: Path | None = None, clone: Path | None = None) -> Any:
    if isinstance(value, str):
        text = value
        # Match both OS-native and POSIX-form path variants so the
        # placeholder substitution lands regardless of which form
        # callers stored. F6f: normalize backslash path tails that
        # follow the placeholder so cross-OS consumers parse the same
        # bytes.
        if root is not None:
            native = str(root)
            for variant in {native, Path(root).as_posix(), native.replace("/", "\\")}:
                text = text.replace(variant, "${FACTORY_V3_ROOT}")
        if clone is not None:
            native = str(clone)
            for variant in {native, Path(clone).as_posix(), native.replace("/", "\\")}:
                text = text.replace(variant, "${FACTORY_V3_CLEAN_CLONE}")
        text = _BACKSLASH_TAIL_AFTER_PLACEHOLDER.sub(
            lambda m: m.group(1) + m.group(2).replace("\\", "/"),
            text,
        )
        return redact_text(text)[0]
    if isinstance(value, list):
        return [sanitize(item, root=root, clone=clone) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item, root=root, clone=clone) for key, item in value.items()}
    return value


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
            check=False,
        )
        stdout_fields: dict[str, Any] = {}
        try:
            parsed_stdout = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed_stdout = {}
        if isinstance(parsed_stdout, dict):
            for key in [
                "schema",
                "verdict",
                "current_state",
                "case_count",
                "provider_profile_matches",
                "candidate_count",
                "implementation_ready",
                "mutation_case_count",
                "role_graph_alignment",
                "yaml_renderer_alignment",
                "yaml_role_graph_alignment",
                "all_aligned",
                "task_count",
                "mutation_cases",
                "argparse_default",
                "cases",
            ]:
                if key in parsed_stdout:
                    stdout_fields[key] = parsed_stdout[key]
        return {
            "command": command,
            "duration_seconds": round(time.monotonic() - start, 3),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "verdict": "PASS" if completed.returncode == 0 else "FAIL",
            "stdout_fields": stdout_fields,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "duration_seconds": round(time.monotonic() - start, 3),
            "returncode": None,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "verdict": "FAIL",
            "error": f"timed out after {timeout}s",
        }


def parse_stdout_json(result: dict[str, Any]) -> dict[str, Any]:
    fields = result.get("stdout_fields")
    if isinstance(fields, dict) and fields:
        return fields
    try:
        data = json.loads(str(result.get("stdout_tail") or "{}"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def result_for(command_results: list[dict[str, Any]], command: list[str]) -> dict[str, Any]:
    return next((result for result in command_results if result.get("command") == command), {})


def architecture_baselines(command_results: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    commands = {
        "agent_os_router_migration_matrix": ["python3", "scripts/check_agent_os_router_migration_matrix.py", "--json"],
        "agent_os_runspec_provider_boundary_matrix": [
            "python3",
            "scripts/check_agent_os_runspec_provider_boundary_matrix.py",
            "--json",
        ],
        "agent_os_runspec_provider_profile_validation": [
            "python3",
            "scripts/agent_os_runspec_validator.py",
            "--provider-profile",
            ".env.example",
            "--json",
        ],
        "agent_os_state_stale_cleanup": ["python3", "scripts/cleanup_agent_os_state_artifacts.py", "--json"],
        "agent_os_architecture_implementation_gate": [
            "python3",
            "scripts/check_agent_os_architecture_implementation_gate.py",
            "--json",
        ],
        "agent_os_router_transition_matrix": [
            "python3",
            "scripts/check_agent_os_router_transition_matrix.py",
            "--json",
        ],
        "agent_os_runspec_failure_injection_matrix": [
            "python3",
            "scripts/check_agent_os_runspec_failure_injection_matrix.py",
            "--json",
        ],
        "agent_os_runspec_dag_edge_coverage": [
            "python3",
            "scripts/check_agent_os_runspec_dag_edge_coverage.py",
            "--json",
        ],
        "agent_os_runspec_yaml_dag_parity": [
            "python3",
            "scripts/check_agent_os_runspec_yaml_dag_parity.py",
            "--json",
        ],
        "agent_os_runspec_yaml_semantic_parity": [
            "python3",
            "scripts/check_agent_os_runspec_yaml_semantic_parity.py",
            "--json",
        ],
        "agent_os_runspec_yaml_schema_injection": [
            "python3",
            "scripts/check_agent_os_runspec_yaml_schema_injection.py",
            "--json",
        ],
        "agent_os_runspec_ao_preflight_compatibility": [
            "python3",
            "scripts/check_agent_os_runspec_ao_preflight_compatibility.py",
            "--json",
        ],
        "agent_os_router_default_state_version": [
            "python3",
            "scripts/check_agent_os_router_default_state_version.py",
            "--json",
        ],
        "agent_os_role_graph_backward_compat": [
            "python3",
            "scripts/check_agent_os_role_graph_backward_compat.py",
            "--json",
        ],
        "remote_transfer_chunk_cleanup_invariants": [
            "python3",
            "scripts/check_remote_transfer_chunk_cleanup_invariants.py",
            "--json",
        ],
        "remote_transfer_signed_bundle_tamper": [
            "python3",
            "scripts/check_remote_transfer_signed_bundle_tamper.py",
            "--json",
        ],
        "remote_transfer_approval_expiry_rotation": [
            "python3",
            "scripts/check_remote_transfer_approval_expiry_rotation.py",
            "--json",
        ],
        "remote_transfer_bundle_ordering_resume": [
            "python3",
            "scripts/check_remote_transfer_bundle_ordering_resume.py",
            "--json",
        ],
        "remote_transfer_provider_redaction_round_trip": [
            "python3",
            "scripts/check_remote_transfer_provider_redaction_round_trip.py",
            "--json",
        ],
        "remote_transfer_network_retry_idempotency": [
            "python3",
            "scripts/check_remote_transfer_network_retry_idempotency.py",
            "--json",
        ],
        "remote_transfer_concurrent_transfer_collision": [
            "python3",
            "scripts/check_remote_transfer_concurrent_transfer_collision.py",
            "--json",
        ],
        "remote_transfer_bundle_schema_version_skew": [
            "python3",
            "scripts/check_remote_transfer_bundle_schema_version_skew.py",
            "--json",
        ],
        "remote_transfer_resource_exhaustion_guard": [
            "python3",
            "scripts/check_remote_transfer_resource_exhaustion_guard.py",
            "--json",
        ],
        "remote_transfer_clock_skew_tolerance": [
            "python3",
            "scripts/check_remote_transfer_clock_skew_tolerance.py",
            "--json",
        ],
        "remote_transfer_bundle_id_uniqueness": [
            "python3",
            "scripts/check_remote_transfer_bundle_id_uniqueness.py",
            "--json",
        ],
        "remote_transfer_bundle_content_type_allowlist": [
            "python3",
            "scripts/check_remote_transfer_bundle_content_type_allowlist.py",
            "--json",
        ],
        "remote_transfer_per_tenant_quota_isolation": [
            "python3",
            "scripts/check_remote_transfer_per_tenant_quota_isolation.py",
            "--json",
        ],
        "remote_transfer_wire_encryption_required": [
            "python3",
            "scripts/check_remote_transfer_wire_encryption_required.py",
            "--json",
        ],
        "remote_transfer_sender_identity_rotation": [
            "python3",
            "scripts/check_remote_transfer_sender_identity_rotation.py",
            "--json",
        ],
        "ai_agent_blast_radius_inventory": [
            "python3",
            "scripts/check_ai_agent_blast_radius_inventory.py",
            "--json",
        ],
        "ai_agent_destructive_action_approval": [
            "python3",
            "scripts/check_ai_agent_destructive_action_approval.py",
            "--json",
        ],
        "ai_agent_credential_reachability": [
            "python3",
            "scripts/check_ai_agent_credential_reachability.py",
            "--json",
        ],
        "ai_agent_instruction_packaging_leak_detection": [
            "python3",
            "scripts/check_ai_agent_instruction_packaging_leak_detection.py",
            "--json",
        ],
        "mcp_tool_poisoning_detection": [
            "python3",
            "scripts/check_mcp_tool_poisoning_detection.py",
            "--json",
        ],
        "deepsec_diff_review_advisory_sast": [
            "python3",
            "scripts/check_deepsec_diff_review_advisory_sast.py",
            "--json",
        ],
        "agent_supply_chain_integrity": [
            "python3",
            "scripts/check_agent_supply_chain_integrity.py",
            "--json",
        ],
        "prompt_injection_escape_boundary": [
            "python3",
            "scripts/check_prompt_injection_escape_boundary.py",
            "--json",
        ],
        "approval_clock_skew_defense": [
            "python3",
            "scripts/check_approval_clock_skew_defense.py",
            "--json",
        ],
        "agent_log_redaction_round_trip": [
            "python3",
            "scripts/check_agent_log_redaction_round_trip.py",
            "--json",
        ],
        "per_tenant_blast_radius_cap": [
            "python3",
            "scripts/check_per_tenant_blast_radius_cap.py",
            "--json",
        ],
        "sandbox_egress_allowlist": [
            "python3",
            "scripts/check_sandbox_egress_allowlist.py",
            "--json",
        ],
        "agent_tool_arg_injection_escape": [
            "python3",
            "scripts/check_agent_tool_arg_injection_escape.py",
            "--json",
        ],
        "agent_output_canary_leak_detection": [
            "python3",
            "scripts/check_agent_output_canary_leak_detection.py",
            "--json",
        ],
        "agent_os_execution_budget_enforcement": [
            "python3",
            "scripts/check_agent_os_execution_budget_enforcement.py",
            "--json",
        ],
        "agent_system_prompt_tamper_detection": [
            "python3",
            "scripts/check_agent_system_prompt_tamper_detection.py",
            "--json",
        ],
        "tool_result_cache_poisoning_defense": [
            "python3",
            "scripts/check_tool_result_cache_poisoning_defense.py",
            "--json",
        ],
        "agent_credential_scope_narrowing": [
            "python3",
            "scripts/check_agent_credential_scope_narrowing.py",
            "--json",
        ],
    }
    baselines: dict[str, str] = {}
    blockers: list[str] = []
    for baseline_id, command in commands.items():
        result = result_for(command_results, command)
        payload = parse_stdout_json(result)
        verdict = str(payload.get("verdict") or result.get("verdict") or "UNKNOWN")
        baselines[baseline_id] = verdict
        if verdict != "PASS":
            blockers.append(f"architecture_baseline:{baseline_id}")
        if baseline_id == "agent_os_runspec_provider_profile_validation" and payload.get("provider_profile_matches") is not True:
            blockers.append("architecture_baseline:agent_os_runspec_provider_profile_validation.profile_mismatch")
        if baseline_id == "agent_os_state_stale_cleanup" and payload.get("candidate_count") not in (0, None):
            blockers.append("architecture_baseline:agent_os_state_stale_cleanup.candidates_present")
        if baseline_id == "agent_os_architecture_implementation_gate" and payload.get("implementation_ready") is not True:
            blockers.append("architecture_baseline:agent_os_architecture_implementation_gate.not_ready")
        if baseline_id == "agent_os_router_transition_matrix" and int(payload.get("case_count") or 0) != 9:
            blockers.append("architecture_baseline:agent_os_router_transition_matrix.case_count")
        if baseline_id == "agent_os_runspec_failure_injection_matrix" and int(payload.get("case_count") or 0) != 7:
            blockers.append("architecture_baseline:agent_os_runspec_failure_injection_matrix.case_count")
        if baseline_id == "agent_os_runspec_dag_edge_coverage":
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_os_runspec_dag_edge_coverage.mutation_case_count")
            if payload.get("role_graph_alignment") is not True:
                blockers.append("architecture_baseline:agent_os_runspec_dag_edge_coverage.role_graph_alignment")
        if baseline_id == "agent_os_runspec_yaml_dag_parity":
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_dag_parity.mutation_case_count")
            if payload.get("yaml_renderer_alignment") is not True:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_dag_parity.yaml_renderer_alignment")
            if payload.get("yaml_role_graph_alignment") is not True:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_dag_parity.yaml_role_graph_alignment")
        if baseline_id == "agent_os_runspec_yaml_semantic_parity":
            if int(payload.get("mutation_case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_semantic_parity.mutation_case_count")
            if payload.get("all_aligned") is not True:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_semantic_parity.all_aligned")
        if baseline_id == "agent_os_runspec_yaml_schema_injection":
            if int(payload.get("mutation_case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_schema_injection.mutation_case_count")
            if int(payload.get("task_count") or 0) != 7:
                blockers.append("architecture_baseline:agent_os_runspec_yaml_schema_injection.task_count")
            cases = payload.get("mutation_cases")
            if isinstance(cases, list):
                if any(case.get("observed_verdict") != "FAIL" for case in cases if isinstance(case, dict)):
                    blockers.append("architecture_baseline:agent_os_runspec_yaml_schema_injection.mutation_case_verdict")
        if baseline_id == "agent_os_runspec_ao_preflight_compatibility":
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_os_runspec_ao_preflight_compatibility.mutation_case_count")
            if int(payload.get("task_count") or 0) != 7:
                blockers.append("architecture_baseline:agent_os_runspec_ao_preflight_compatibility.task_count")
            cases = payload.get("mutation_cases")
            if isinstance(cases, list):
                if any(case.get("observed_verdict") != "FAIL" for case in cases if isinstance(case, dict)):
                    blockers.append("architecture_baseline:agent_os_runspec_ao_preflight_compatibility.mutation_case_verdict")
        if baseline_id == "agent_os_router_default_state_version":
            if str(payload.get("argparse_default") or "") != "v2":
                blockers.append("architecture_baseline:agent_os_router_default_state_version.argparse_default")
            if int(payload.get("case_count") or 0) != 3:
                blockers.append("architecture_baseline:agent_os_router_default_state_version.case_count")
            cases = payload.get("cases")
            if isinstance(cases, list):
                if any(case.get("observed_verdict") != "PASS" for case in cases if isinstance(case, dict)):
                    blockers.append("architecture_baseline:agent_os_router_default_state_version.case_verdict")
        if baseline_id == "agent_os_role_graph_backward_compat":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_os_role_graph_backward_compat.case_count")
            expected_case_verdicts = {
                "legacy_v1_state_minimal_loadable": "PASS",
                "legacy_v1_state_extra_unknown_fields_tolerated": "PASS",
                "legacy_v1_state_no_role_graph_schema_injects_default": "PASS",
                "legacy_v2_state_round_trip_preserves_previous_schema": "PASS",
                "legacy_v1_role_graph_artifact_remains_loadable": "PASS",
                "unknown_state_schema_refused": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_case_verdicts:
                    blockers.append("architecture_baseline:agent_os_role_graph_backward_compat.case_verdict")
        if baseline_id == "remote_transfer_chunk_cleanup_invariants":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:remote_transfer_chunk_cleanup_invariants.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_chunk_cleanup_invariants.mutation_case_count")
            expected_chunk_verdicts = {
                "clean_upload_commit_passes": "PASS",
                "orphaned_chunk_after_abort_detected": "FAIL",
                "missing_finalize_detected": "FAIL",
                "stale_partial_stage_dir_detected": "FAIL",
                "double_commit_rejected": "FAIL",
                "retry_index_drift_detected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_chunk_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_chunk_cleanup_invariants.case_verdict")
        if baseline_id == "remote_transfer_signed_bundle_tamper":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:remote_transfer_signed_bundle_tamper.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_signed_bundle_tamper.mutation_case_count")
            expected_tamper_verdicts = {
                "clean_signed_bundle_passes": "PASS",
                "truncated_bundle_rejected": "FAIL",
                "swapped_chunk_rejected": "FAIL",
                "wrong_signing_key_rejected": "FAIL",
                "replayed_bundle_rejected": "FAIL",
                "manifest_digest_mismatch_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_tamper_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_signed_bundle_tamper.case_verdict")
        if baseline_id == "remote_transfer_approval_expiry_rotation":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_approval_expiry_rotation.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_approval_expiry_rotation.mutation_case_count")
            expected_lifecycle_verdicts = {
                "clean_approval_passes": "PASS",
                "expired_approval_rejected": "FAIL",
                "approval_used_after_rotation_cutover_rejected": "FAIL",
                "signing_key_rotated_midflight_without_grace_rejected": "FAIL",
                "approval_reused_beyond_ttl_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_lifecycle_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_approval_expiry_rotation.case_verdict")
        if baseline_id == "remote_transfer_bundle_ordering_resume":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_bundle_ordering_resume.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_bundle_ordering_resume.mutation_case_count")
            expected_ordering_verdicts = {
                "clean_ordered_delivery_passes": "PASS",
                "out_of_order_chunk_rejected": "FAIL",
                "partial_resume_drops_middle_chunk_rejected": "FAIL",
                "resume_cursor_lies_about_high_water_rejected": "FAIL",
                "duplicate_chunk_delivery_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_ordering_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_bundle_ordering_resume.case_verdict")
        if baseline_id == "remote_transfer_provider_redaction_round_trip":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_provider_redaction_round_trip.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_provider_redaction_round_trip.mutation_case_count")
            expected_redaction_verdicts = {
                "clean_round_trip_passes": "PASS",
                "redaction_marker_stripped_before_transmit_rejected": "FAIL",
                "sensitive_field_leaks_past_redaction_filter_rejected": "FAIL",
                "double_redaction_corrupts_payload_rejected": "FAIL",
                "provider_response_leaks_redacted_value_back_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_redaction_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_provider_redaction_round_trip.case_verdict")
        if baseline_id == "remote_transfer_network_retry_idempotency":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_network_retry_idempotency.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_network_retry_idempotency.mutation_case_count")
            expected_retry_verdicts = {
                "clean_retry_round_trip_passes": "PASS",
                "retry_without_nonce_dedup_rejected": "FAIL",
                "partial_flush_on_network_drop_rejected": "FAIL",
                "ack_lost_causes_double_commit_rejected": "FAIL",
                "timeout_shorter_than_response_causes_orphan_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_retry_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_network_retry_idempotency.case_verdict")
        if baseline_id == "remote_transfer_concurrent_transfer_collision":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_concurrent_transfer_collision.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_concurrent_transfer_collision.mutation_case_count")
            expected_collision_verdicts = {
                "clean_serialized_concurrent_transfers_passes": "PASS",
                "parallel_transfers_no_lock_corrupts_state_rejected": "FAIL",
                "simultaneous_finalize_double_completes_bundle_rejected": "FAIL",
                "lost_writer_overwrites_winner_bundle_rejected": "FAIL",
                "stale_lock_holder_resumes_after_handoff_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_collision_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_concurrent_transfer_collision.case_verdict")
        if baseline_id == "remote_transfer_bundle_schema_version_skew":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_bundle_schema_version_skew.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_bundle_schema_version_skew.mutation_case_count")
            expected_skew_verdicts = {
                "clean_matched_schema_version_passes": "PASS",
                "receiver_below_min_version_rejected": "FAIL",
                "receiver_above_max_silently_downgrades_rejected": "FAIL",
                "bundle_advertises_unknown_extension_field_rejected": "FAIL",
                "schema_version_field_missing_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_skew_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_bundle_schema_version_skew.case_verdict")
        if baseline_id == "remote_transfer_resource_exhaustion_guard":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_resource_exhaustion_guard.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_resource_exhaustion_guard.mutation_case_count")
            expected_quota_verdicts = {
                "clean_within_quota_passes": "PASS",
                "announced_chunk_count_exceeds_quota_rejected": "FAIL",
                "announced_total_size_exceeds_quota_rejected": "FAIL",
                "per_chunk_size_exceeds_max_rejected": "FAIL",
                "transfer_exceeds_announced_count_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_quota_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_resource_exhaustion_guard.case_verdict")
        if baseline_id == "remote_transfer_clock_skew_tolerance":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_clock_skew_tolerance.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_clock_skew_tolerance.mutation_case_count")
            expected_clock_skew_verdicts = {
                "clean_within_skew_tolerance_passes": "PASS",
                "sender_clock_ahead_of_receiver_rejected": "FAIL",
                "sender_clock_behind_receiver_rejected": "FAIL",
                "future_dated_bundle_accepted_as_currently_valid_rejected": "FAIL",
                "ttl_window_straddling_skew_silently_extended_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_clock_skew_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_clock_skew_tolerance.case_verdict")
        if baseline_id == "remote_transfer_bundle_id_uniqueness":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_bundle_id_uniqueness.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_bundle_id_uniqueness.mutation_case_count")
            expected_bundle_id_verdicts = {
                "clean_unique_bundle_ids_pass": "PASS",
                "duplicate_bundle_id_within_session_rejected": "FAIL",
                "cross_sender_bundle_id_collision_rejected": "FAIL",
                "bundle_id_truncation_collision_rejected": "FAIL",
                "bundle_id_replayed_after_completion_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_bundle_id_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_bundle_id_uniqueness.case_verdict")
        if baseline_id == "remote_transfer_bundle_content_type_allowlist":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_bundle_content_type_allowlist.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_bundle_content_type_allowlist.mutation_case_count")
            expected_content_type_verdicts = {
                "clean_allowlisted_content_type_passes": "PASS",
                "unknown_content_type_silently_coerced_rejected": "FAIL",
                "mismatched_extension_to_content_type_rejected": "FAIL",
                "unknown_content_encoding_silently_decoded_rejected": "FAIL",
                "content_type_charset_parameter_smuggled_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_content_type_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_bundle_content_type_allowlist.case_verdict")
        if baseline_id == "remote_transfer_per_tenant_quota_isolation":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_per_tenant_quota_isolation.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_per_tenant_quota_isolation.mutation_case_count")
            expected_per_tenant_quota_verdicts = {
                "clean_per_tenant_within_quota_passes": "PASS",
                "tenant_a_overflows_tenant_b_quota_slot_rejected": "FAIL",
                "aggregated_quota_across_tenants_merged_rejected": "FAIL",
                "tenant_identity_stripped_silently_coerced_to_default_rejected": "FAIL",
                "quota_refund_on_abort_double_credited_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_per_tenant_quota_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_per_tenant_quota_isolation.case_verdict")
        if baseline_id == "remote_transfer_wire_encryption_required":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_wire_encryption_required.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_wire_encryption_required.mutation_case_count")
            expected_wire_encryption_verdicts = {
                "clean_encrypted_bundle_accepted": "PASS",
                "cleartext_bundle_silently_accepted_rejected": "FAIL",
                "downgraded_tls_cipher_silently_accepted_rejected": "FAIL",
                "weak_null_cipher_suite_negotiated_rejected": "FAIL",
                "encryption_header_stripped_after_handshake_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_wire_encryption_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_wire_encryption_required.case_verdict")
        if baseline_id == "remote_transfer_sender_identity_rotation":
            if int(payload.get("case_count") or 0) != 5:
                blockers.append("architecture_baseline:remote_transfer_sender_identity_rotation.case_count")
            if int(payload.get("mutation_case_count") or 0) != 4:
                blockers.append("architecture_baseline:remote_transfer_sender_identity_rotation.mutation_case_count")
            expected_sender_identity_rotation_verdicts = {
                "clean_post_rotation_bundle_accepted": "PASS",
                "retired_identity_silently_accepted_rejected": "FAIL",
                "rotation_announcement_unsigned_silently_accepted_rejected": "FAIL",
                "future_rotation_effective_at_silently_accepted_rejected": "FAIL",
                "dual_acceptance_window_silently_left_open_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_sender_identity_rotation_verdicts:
                    blockers.append("architecture_baseline:remote_transfer_sender_identity_rotation.case_verdict")
        if baseline_id == "ai_agent_blast_radius_inventory":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:ai_agent_blast_radius_inventory.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:ai_agent_blast_radius_inventory.mutation_case_count")
            expected_blast_radius_verdicts = {
                "clean_inventory_classified_and_gated": "PASS",
                "unclassified_high_blast_radius_command_path_rejected": "FAIL",
                "destructive_action_without_approval_gate_rejected": "FAIL",
                "credential_path_reachable_from_untrusted_content_rejected": "FAIL",
                "provider_dispatch_without_approval_readiness_rejected": "FAIL",
                "release_artifact_includes_instruction_or_credentials_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_blast_radius_verdicts:
                    blockers.append("architecture_baseline:ai_agent_blast_radius_inventory.case_verdict")
        if baseline_id == "ai_agent_destructive_action_approval":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:ai_agent_destructive_action_approval.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:ai_agent_destructive_action_approval.mutation_case_count")
            expected_destructive_action_approval_verdicts = {
                "clean_destructive_action_with_fresh_scoped_approval_executes": "PASS",
                "stale_approval_reused_after_expiry_rejected": "FAIL",
                "approval_scope_widened_at_exec_silently_accepted_rejected": "FAIL",
                "approval_consumed_twice_for_distinct_destructive_ops_rejected": "FAIL",
                "destructive_op_runs_with_policy_only_without_token_rejected": "FAIL",
                "parent_process_approval_inherited_by_child_without_reconfirm_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_destructive_action_approval_verdicts:
                    blockers.append("architecture_baseline:ai_agent_destructive_action_approval.case_verdict")
        if baseline_id == "ai_agent_credential_reachability":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:ai_agent_credential_reachability.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:ai_agent_credential_reachability.mutation_case_count")
            expected_credential_reachability_verdicts = {
                "clean_no_untrusted_to_credential_reachable_path": "PASS",
                "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected": "FAIL",
                "agent_tool_output_piped_to_shell_with_ssh_dir_rejected": "FAIL",
                "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected": "FAIL",
                "web_fetch_reflected_into_shell_resolving_env_rejected": "FAIL",
                "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_credential_reachability_verdicts:
                    blockers.append("architecture_baseline:ai_agent_credential_reachability.case_verdict")
        if baseline_id == "ai_agent_instruction_packaging_leak_detection":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:ai_agent_instruction_packaging_leak_detection.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:ai_agent_instruction_packaging_leak_detection.mutation_case_count")
            expected_instruction_packaging_leak_verdicts = {
                "clean_no_instruction_or_packaging_leaks_in_public_artifacts": "PASS",
                "claude_md_directives_leaked_into_status_report_rejected": "FAIL",
                "agent_memory_snippet_copy_pasted_into_public_doc_rejected": "FAIL",
                "raw_user_prompt_logged_in_operator_slice_evidence_rejected": "FAIL",
                "anthropic_api_key_surfaced_in_evaluation_transcript_rejected": "FAIL",
                "tmp_diagnostic_path_included_in_public_artifact_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_instruction_packaging_leak_verdicts:
                    blockers.append("architecture_baseline:ai_agent_instruction_packaging_leak_detection.case_verdict")
        if baseline_id == "mcp_tool_poisoning_detection":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:mcp_tool_poisoning_detection.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:mcp_tool_poisoning_detection.mutation_case_count")
            expected_mcp_tool_poisoning_verdicts = {
                "clean_no_mcp_or_tool_poisoning_indicators": "PASS",
                "hidden_imperative_in_mcp_description_rejected": "FAIL",
                "tool_result_schema_adds_destructive_default_arg_rejected": "FAIL",
                "mcp_returns_url_to_fetch_and_apply_rejected": "FAIL",
                "tool_name_shadowing_overrides_native_tool_rejected": "FAIL",
                "signed_descriptor_advertises_unallowed_privilege_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_mcp_tool_poisoning_verdicts:
                    blockers.append("architecture_baseline:mcp_tool_poisoning_detection.case_verdict")
        if baseline_id == "deepsec_diff_review_advisory_sast":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:deepsec_diff_review_advisory_sast.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:deepsec_diff_review_advisory_sast.mutation_case_count")
            expected_deepsec_diff_review_advisory_sast_verdicts = {
                "clean_no_untrusted_to_dangerous_sink_edges": "PASS",
                "untrusted_input_flows_into_shell_command_rejected": "FAIL",
                "untrusted_input_flows_into_fs_write_outside_workspace_rejected": "FAIL",
                "untrusted_input_flows_into_network_egress_rejected": "FAIL",
                "eval_or_exec_on_retrieved_content_rejected": "FAIL",
                "dynamic_import_from_agent_controlled_path_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_deepsec_diff_review_advisory_sast_verdicts:
                    blockers.append("architecture_baseline:deepsec_diff_review_advisory_sast.case_verdict")
        if baseline_id == "agent_supply_chain_integrity":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_supply_chain_integrity.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_supply_chain_integrity.mutation_case_count")
            expected_agent_supply_chain_integrity_verdicts = {
                "clean_no_unauthorized_provenance_or_unsigned_package_edges": "PASS",
                "unsigned_package_admitted_without_signature_rejected": "FAIL",
                "lock_file_digest_mismatch_admitted_rejected": "FAIL",
                "dependency_confusion_via_shadow_registry_rejected": "FAIL",
                "post_install_script_with_network_egress_rejected": "FAIL",
                "transitive_yank_without_repin_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_supply_chain_integrity_verdicts:
                    blockers.append("architecture_baseline:agent_supply_chain_integrity.case_verdict")
        if baseline_id == "prompt_injection_escape_boundary":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:prompt_injection_escape_boundary.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:prompt_injection_escape_boundary.mutation_case_count")
            expected_prompt_injection_escape_boundary_verdicts = {
                "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended": "PASS",
                "attacker_role_spoofing_appended_after_user_content_rejected": "FAIL",
                "fenced_block_escape_breaking_system_boundary_rejected": "FAIL",
                "json_injection_replacing_operator_instructions_rejected": "FAIL",
                "tool_name_shadowing_via_attacker_section_rejected": "FAIL",
                "instruction_smuggling_via_unicode_homoglyph_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_prompt_injection_escape_boundary_verdicts:
                    blockers.append("architecture_baseline:prompt_injection_escape_boundary.case_verdict")
        if baseline_id == "approval_clock_skew_defense":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:approval_clock_skew_defense.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:approval_clock_skew_defense.mutation_case_count")
            expected_approval_clock_skew_defense_verdicts = {
                "clean_no_clock_skew_or_replay_or_stale_freshness_edges": "PASS",
                "ntp_rewind_admits_expired_approval_rejected": "FAIL",
                "leap_second_jump_admits_expired_approval_rejected": "FAIL",
                "tz_tagged_as_utc_admits_expired_approval_rejected": "FAIL",
                "expired_but_cached_admits_replay_rejected": "FAIL",
                "signed_token_replay_admits_reactivation_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_approval_clock_skew_defense_verdicts:
                    blockers.append("architecture_baseline:approval_clock_skew_defense.case_verdict")
        if baseline_id == "agent_log_redaction_round_trip":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_log_redaction_round_trip.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_log_redaction_round_trip.mutation_case_count")
            expected_agent_log_redaction_round_trip_verdicts = {
                "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output": "PASS",
                "partial_pattern_match_leaves_original_substring_rejected": "FAIL",
                "base64_encoded_secret_unredacted_in_round_trip_rejected": "FAIL",
                "path_normalization_alias_unredacted_in_round_trip_rejected": "FAIL",
                "case_insensitive_token_unredacted_in_round_trip_rejected": "FAIL",
                "json_string_escape_token_unredacted_in_round_trip_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_log_redaction_round_trip_verdicts:
                    blockers.append("architecture_baseline:agent_log_redaction_round_trip.case_verdict")
        if baseline_id == "per_tenant_blast_radius_cap":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:per_tenant_blast_radius_cap.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:per_tenant_blast_radius_cap.mutation_case_count")
            expected_per_tenant_blast_radius_cap_verdicts = {
                "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges": "PASS",
                "cross_tenant_fanout_to_unrelated_tenant_resource_rejected": "FAIL",
                "missing_tenant_tag_admits_global_blast_radius_rejected": "FAIL",
                "tenant_tag_spoof_admits_other_tenant_resource_rejected": "FAIL",
                "allowlist_bypass_admits_unallowlisted_target_rejected": "FAIL",
                "quota_overflow_leak_admits_post_window_action_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_per_tenant_blast_radius_cap_verdicts:
                    blockers.append("architecture_baseline:per_tenant_blast_radius_cap.case_verdict")
        if baseline_id == "sandbox_egress_allowlist":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:sandbox_egress_allowlist.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:sandbox_egress_allowlist.mutation_case_count")
            expected_sandbox_egress_allowlist_verdicts = {
                "clean_no_unallowlisted_or_bypassed_egress_attempts": "PASS",
                "unallowlisted_host_egress_admitted_rejected": "FAIL",
                "ip_literal_bypass_admits_unallowlisted_target_rejected": "FAIL",
                "dns_rebind_bypass_admits_unallowlisted_target_rejected": "FAIL",
                "proxy_chain_bypass_admits_unallowlisted_target_rejected": "FAIL",
                "raw_socket_bypass_admits_unallowlisted_target_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_sandbox_egress_allowlist_verdicts:
                    blockers.append("architecture_baseline:sandbox_egress_allowlist.case_verdict")
        if baseline_id == "agent_tool_arg_injection_escape":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_tool_arg_injection_escape.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_tool_arg_injection_escape.mutation_case_count")
            expected_agent_tool_arg_injection_escape_verdicts = {
                "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion": "PASS",
                "string_template_breakout_via_unescaped_quote_rejected": "FAIL",
                "json_arg_breakout_via_nested_object_smuggling_rejected": "FAIL",
                "polymorphic_argument_coercion_via_type_mismatch_rejected": "FAIL",
                "shell_metachar_injection_via_unfiltered_string_arg_rejected": "FAIL",
                "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_tool_arg_injection_escape_verdicts:
                    blockers.append("architecture_baseline:agent_tool_arg_injection_escape.case_verdict")
        if baseline_id == "agent_output_canary_leak_detection":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_output_canary_leak_detection.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_output_canary_leak_detection.mutation_case_count")
            expected_agent_output_canary_leak_detection_verdicts = {
                "clean_no_canary_or_marked_secret_leak_in_output": "PASS",
                "literal_canary_token_in_output_rejected": "FAIL",
                "base64_encoded_canary_token_in_output_rejected": "FAIL",
                "unicode_homoglyph_canary_substitution_in_output_rejected": "FAIL",
                "partial_canary_fragment_concatenation_in_output_rejected": "FAIL",
                "marked_secret_passthrough_via_field_label_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_output_canary_leak_detection_verdicts:
                    blockers.append("architecture_baseline:agent_output_canary_leak_detection.case_verdict")
        if baseline_id == "agent_os_execution_budget_enforcement":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_os_execution_budget_enforcement.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_os_execution_budget_enforcement.mutation_case_count")
            expected_agent_os_execution_budget_enforcement_verdicts = {
                "clean_no_budget_overflow_or_reset_bypass": "PASS",
                "token_budget_overflow_admit_rejected": "FAIL",
                "time_budget_overflow_admit_rejected": "FAIL",
                "tool_call_count_overflow_admit_rejected": "FAIL",
                "cost_ceiling_overflow_admit_rejected": "FAIL",
                "budget_reset_bypass_admit_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_os_execution_budget_enforcement_verdicts:
                    blockers.append("architecture_baseline:agent_os_execution_budget_enforcement.case_verdict")
        if baseline_id == "agent_system_prompt_tamper_detection":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_system_prompt_tamper_detection.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_system_prompt_tamper_detection.mutation_case_count")
            expected_agent_system_prompt_tamper_detection_verdicts = {
                "clean_no_system_prompt_tamper": "PASS",
                "system_prompt_substitution_admit_rejected": "FAIL",
                "system_prompt_appended_instruction_admit_rejected": "FAIL",
                "system_prompt_truncation_admit_rejected": "FAIL",
                "system_prompt_unicode_homoglyph_admit_rejected": "FAIL",
                "system_prompt_role_relabel_admit_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_system_prompt_tamper_detection_verdicts:
                    blockers.append("architecture_baseline:agent_system_prompt_tamper_detection.case_verdict")
        if baseline_id == "tool_result_cache_poisoning_defense":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:tool_result_cache_poisoning_defense.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:tool_result_cache_poisoning_defense.mutation_case_count")
            expected_tool_result_cache_poisoning_defense_verdicts = {
                "clean_no_tool_result_cache_poisoning": "PASS",
                "cache_key_collision_admit_rejected": "FAIL",
                "stale_cache_serve_after_invalidation_admit_rejected": "FAIL",
                "ttl_extension_via_admin_replay_admit_rejected": "FAIL",
                "forged_response_signature_admit_rejected": "FAIL",
                "cross_tenant_cache_share_admit_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_tool_result_cache_poisoning_defense_verdicts:
                    blockers.append("architecture_baseline:tool_result_cache_poisoning_defense.case_verdict")
        if baseline_id == "agent_credential_scope_narrowing":
            if int(payload.get("case_count") or 0) != 6:
                blockers.append("architecture_baseline:agent_credential_scope_narrowing.case_count")
            if int(payload.get("mutation_case_count") or 0) != 5:
                blockers.append("architecture_baseline:agent_credential_scope_narrowing.mutation_case_count")
            expected_agent_credential_scope_narrowing_verdicts = {
                "clean_no_credential_scope_widening": "PASS",
                "credential_scope_substitution_admit_rejected": "FAIL",
                "credential_scope_append_admit_rejected": "FAIL",
                "credential_audience_relabel_admit_rejected": "FAIL",
                "credential_expiry_extension_admit_rejected": "FAIL",
                "credential_principal_mint_admit_rejected": "FAIL",
            }
            cases = payload.get("cases")
            if isinstance(cases, list):
                observed_verdicts = {
                    case.get("id"): case.get("observed_verdict")
                    for case in cases
                    if isinstance(case, dict)
                }
                if observed_verdicts != expected_agent_credential_scope_narrowing_verdicts:
                    blockers.append("architecture_baseline:agent_credential_scope_narrowing.case_verdict")
    return baselines, blockers


def summarize(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    include_closure: bool = True,
    timeout: int = 240,
) -> dict[str, Any]:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="ao-operator-clean-clone-") as temp_dir:
        temp_root = Path(temp_dir).resolve()
        clone = (temp_root / "ao-operator").resolve()
        ao_runtime = Path(os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", str(root.parent / "ao-runtime"))).resolve()
        command_env = os.environ.copy()
        command_env["FACTORY_V3_AO_RUNTIME_PATH"] = str(ao_runtime)
        release_bin = ao_runtime / "target" / "release"
        command_env["PATH"] = f"{release_bin}{os.pathsep}{command_env.get('PATH', '')}"
        clone_result = run_command(
            ["git", "clone", "--quiet", "--no-local", str(root), str(clone)],
            cwd=temp_root,
            timeout=timeout,
            env=command_env,
        )
        command_results = [clone_result]
        if clone_result["verdict"] == "PASS":
            command_results.extend(
                run_command(command, cwd=clone, timeout=timeout, env=command_env)
                for command in command_plan(slug=slug, include_closure=include_closure)
            )

        blockers = [
            "command:" + " ".join(result["command"])
            for result in command_results
            if result.get("verdict") != "PASS"
        ]
        summary_result = next(
            (
                result
                for result in command_results
                if result.get("command") == ["python3", "scripts/summarize_50_slice_operator_state.py", "--json"]
            ),
            {},
        )
        summary_payload = parse_stdout_json(summary_result)
        if summary_result and summary_payload.get("current_state") != "ACCEPTED_50_SLICE_LIVE":
            blockers.append("50_slice.accepted_terminal_state")
        baselines, baseline_blockers = architecture_baselines(command_results)
        blockers.extend(baseline_blockers)

        payload = {
            "schema": "ao-operator/clean-clone-readiness/v1",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "repo": str(root),
            "clone_path": str(clone),
            "slug": slug,
            "verdict": "PASS" if not blockers else "FAIL",
            "dispatch_authorized": False,
            "live_providers_run": False,
            "blockers": blockers,
            "commands": command_results,
            "accepted_50_current_state": summary_payload.get("current_state", "UNKNOWN"),
            "architecture_baselines": baselines,
            "next_safe_command": (
                "Clean-clone readiness passes; architecture SDD can proceed."
                if not blockers
                else "Fix clean-clone blockers before architecture implementation."
            ),
        }
        return sanitize(payload, root=root, clone=clone)


def resolve_output(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run clean-clone readiness validation")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--skip-closure", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(
        root=args.root,
        slug=args.slug,
        include_closure=not args.skip_closure,
        timeout=args.timeout,
    )
    payload = sanitize(payload, root=args.root.resolve())
    if args.write_output is not None:
        output = resolve_output(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        print(f"accepted_50_current_state={payload['accepted_50_current_state']}")
        for blocker in payload["blockers"]:
            print(f"blocker={blocker}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
