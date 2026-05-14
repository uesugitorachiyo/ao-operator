#!/usr/bin/env python3
"""Summarize operator cockpit and guardrail reports in one non-dispatching view."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/operator-guardrail-summary.json"

REPORTS = {
    "operator_cockpit": {
        "path": f"{STATUS_ROOT}/agent-os-operator-cockpit.json",
        "schema": "ao-operator/agent-os-operator-cockpit/v1",
    },
    "remote_transfer_hardening": {
        "path": f"{STATUS_ROOT}/remote-transfer-hardening.json",
        "schema": "ao-operator/remote-transfer-hardening/v1",
    },
    "public_release_security": {
        "path": f"{STATUS_ROOT}/public-release-security-surface.json",
        "schema": "ao-operator/public-release-security/v1",
    },
    "dast_readiness": {
        "path": f"{STATUS_ROOT}/dast-readiness.json",
        "schema": "ao-operator/dast-readiness/v1",
    },
    "security_sdlc_roadmap": {
        "path": f"{STATUS_ROOT}/security-sdlc-roadmap.json",
        "schema": "ao-operator/security-sdlc-roadmap/v1",
    },
    "security_threat_model": {
        "path": f"{STATUS_ROOT}/security-threat-model.json",
        "schema": "ao-operator/security-threat-model/v1",
    },
    "manual_pentest_gate": {
        "path": f"{STATUS_ROOT}/manual-pentest-gate.json",
        "schema": "ao-operator/manual-pentest-gate/v1",
    },
    "host_key_evidence": {
        "path": f"{STATUS_ROOT}/host-key-evidence.json",
        "schema": "ao-operator/host-key-evidence/v1",
    },
    "manual_pentest_report_classifier": {
        "path": f"{STATUS_ROOT}/manual-pentest-report-classifier.json",
        "schema": "ao-operator/manual-pentest-report-classifier/v1",
    },
    "supply_chain_gate": {
        "path": f"{STATUS_ROOT}/supply-chain-gate.json",
        "schema": "ao-operator/supply-chain-gate/v1",
    },
    "resource_performance": {
        "path": f"{STATUS_ROOT}/resource-performance-gate.json",
        "schema": "ao-operator/resource-performance-gate/v1",
    },
    "approval_bundle": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-execution-approval-bundle.json",
        "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
    },
    "release_readiness": {
        "path": f"{STATUS_ROOT}/release-readiness-gate.json",
        "schema": "ao-operator/release-readiness-gate/v1",
    },
    "no_provider_rehearsal": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-execution-rehearsal.json",
        "schema": "ao-operator/agent-os-runspec-execution-rehearsal/v1",
    },
    "approval_lifecycle": {
        "path": f"{STATUS_ROOT}/agent-os-approval-lifecycle.json",
        "schema": "ao-operator/agent-os-approval-lifecycle/v1",
    },
    "approval_cleanup": {
        "path": f"{STATUS_ROOT}/agent-os-approval-cleanup.json",
        "schema": "ao-operator/agent-os-approval-cleanup/v1",
    },
    "approved_launch_proof": {
        "path": f"{STATUS_ROOT}/agent-os-approved-launch-proof.json",
        "schema": "ao-operator/agent-os-approved-launch-proof/v1",
    },
    "approval_audit_history": {
        "path": f"{STATUS_ROOT}/agent-os-approval-audit.json",
        "schema": "ao-operator/agent-os-approval-audit-history/v1",
    },
    "post_approval_cleanup_route": {
        "path": f"{STATUS_ROOT}/agent-os-post-approval-cleanup-route.json",
        "schema": "ao-operator/agent-os-post-approval-cleanup-route/v1",
    },
    "approval_runbook": {
        "path": f"{STATUS_ROOT}/agent-os-approval-runbook.json",
        "schema": "ao-operator/agent-os-approval-runbook/v1",
    },
    "approval_audit_retention": {
        "path": f"{STATUS_ROOT}/agent-os-approval-audit-retention.json",
        "schema": "ao-operator/agent-os-approval-audit-retention/v1",
    },
    "approval_bundle_signature": {
        "path": f"{STATUS_ROOT}/agent-os-approval-bundle-signature-report.json",
        "schema": "ao-operator/agent-os-approval-bundle-signature/v1",
    },
    "approval_revocation": {
        "path": f"{STATUS_ROOT}/agent-os-approval-revocation.json",
        "schema": "ao-operator/agent-os-approval-revocation/v1",
    },
    "approval_identity_signature": {
        "path": f"{STATUS_ROOT}/agent-os-approval-identity-signature.json",
        "schema": "ao-operator/agent-os-approval-identity-signature/v1",
    },
    "approval_revocation_apply_proof": {
        "path": f"{STATUS_ROOT}/agent-os-approval-revocation-apply-proof.json",
        "schema": "ao-operator/agent-os-approval-revocation-apply-proof/v1",
    },
    "approval_audit_archive_restore": {
        "path": f"{STATUS_ROOT}/agent-os-approval-audit-archive-restore.json",
        "schema": "ao-operator/agent-os-approval-audit-archive-restore/v1",
    },
    "mac_ubuntu_approval_artifact_parity": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-approval-artifact-parity.json",
        "schema": "ao-operator/mac-ubuntu-approval-artifact-parity/v1",
    },
    "mac_ubuntu_signed_approval_bundle_transfer": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-signed-approval-bundle-transfer.json",
        "schema": "ao-operator/mac-ubuntu-signed-approval-bundle-transfer/v1",
    },
    "mac_ubuntu_remote_approval_materialization_dry_run": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-remote-approval-materialization-dry-run.json",
        "schema": "ao-operator/mac-ubuntu-remote-approval-materialization-dry-run/v1",
    },
    "mac_ubuntu_remote_approval_revocation_rollback": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-remote-approval-revocation-rollback.json",
        "schema": "ao-operator/mac-ubuntu-remote-approval-revocation-rollback/v1",
    },
    "mac_ubuntu_remote_approval_runbook": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-remote-approval-runbook.json",
        "schema": "ao-operator/mac-ubuntu-remote-approval-runbook/v1",
    },
    "mac_ubuntu_remote_approved_fixture": {
        "path": f"{STATUS_ROOT}/mac-ubuntu-remote-approved-fixture.json",
        "schema": "ao-operator/mac-ubuntu-remote-approved-fixture/v1",
    },
    "agent_os_architecture_implementation_gate": {
        "path": f"{STATUS_ROOT}/agent-os-architecture-implementation-gate.json",
        "schema": "ao-operator/agent-os-architecture-implementation-gate/v1",
    },
    "agent_os_router_transition_matrix": {
        "path": f"{STATUS_ROOT}/agent-os-router-transition-matrix.json",
        "schema": "ao-operator/agent-os-router-transition-matrix/v1",
    },
    "agent_os_runspec_failure_injection_matrix": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-failure-injection-matrix.json",
        "schema": "ao-operator/agent-os-runspec-failure-injection-matrix/v1",
    },
    "agent_os_runspec_dag_edge_coverage": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-dag-edge-coverage.json",
        "schema": "ao-operator/agent-os-runspec-dag-edge-coverage/v1",
    },
    "agent_os_runspec_yaml_dag_parity": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-yaml-dag-parity.json",
        "schema": "ao-operator/agent-os-runspec-yaml-dag-parity/v1",
    },
    "agent_os_runspec_yaml_semantic_parity": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-yaml-semantic-parity.json",
        "schema": "ao-operator/agent-os-runspec-yaml-semantic-parity/v1",
    },
    "agent_os_runspec_yaml_schema_injection": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-yaml-schema-injection.json",
        "schema": "ao-operator/agent-os-runspec-yaml-schema-injection/v1",
    },
    "agent_os_runspec_ao_preflight_compatibility": {
        "path": f"{STATUS_ROOT}/agent-os-runspec-ao-preflight-compatibility.json",
        "schema": "ao-operator/agent-os-runspec-ao-preflight-compatibility/v1",
    },
    "agent_os_router_default_state_version": {
        "path": f"{STATUS_ROOT}/agent-os-router-default-state-version.json",
        "schema": "ao-operator/agent-os-router-default-state-version/v1",
    },
    "agent_os_role_graph_backward_compat": {
        "path": f"{STATUS_ROOT}/agent-os-role-graph-backward-compat.json",
        "schema": "ao-operator/agent-os-role-graph-backward-compat/v1",
    },
    "remote_transfer_chunk_cleanup_invariants": {
        "path": f"{STATUS_ROOT}/remote-transfer-chunk-cleanup-invariants.json",
        "schema": "ao-operator/remote-transfer-chunk-cleanup-invariants/v1",
    },
    "remote_transfer_signed_bundle_tamper": {
        "path": f"{STATUS_ROOT}/remote-transfer-signed-bundle-tamper.json",
        "schema": "ao-operator/remote-transfer-signed-bundle-tamper/v1",
    },
    "remote_transfer_approval_expiry_rotation": {
        "path": f"{STATUS_ROOT}/remote-transfer-approval-expiry-rotation.json",
        "schema": "ao-operator/remote-transfer-approval-expiry-rotation/v1",
    },
    "remote_transfer_bundle_ordering_resume": {
        "path": f"{STATUS_ROOT}/remote-transfer-bundle-ordering-resume.json",
        "schema": "ao-operator/remote-transfer-bundle-ordering-resume/v1",
    },
    "remote_transfer_provider_redaction_round_trip": {
        "path": f"{STATUS_ROOT}/remote-transfer-provider-redaction-round-trip.json",
        "schema": "ao-operator/remote-transfer-provider-redaction-round-trip/v1",
    },
    "remote_transfer_network_retry_idempotency": {
        "path": f"{STATUS_ROOT}/remote-transfer-network-retry-idempotency.json",
        "schema": "ao-operator/remote-transfer-network-retry-idempotency/v1",
    },
    "remote_transfer_concurrent_transfer_collision": {
        "path": f"{STATUS_ROOT}/remote-transfer-concurrent-transfer-collision.json",
        "schema": "ao-operator/remote-transfer-concurrent-transfer-collision/v1",
    },
    "remote_transfer_bundle_schema_version_skew": {
        "path": f"{STATUS_ROOT}/remote-transfer-bundle-schema-version-skew.json",
        "schema": "ao-operator/remote-transfer-bundle-schema-version-skew/v1",
    },
    "remote_transfer_resource_exhaustion_guard": {
        "path": f"{STATUS_ROOT}/remote-transfer-resource-exhaustion-guard.json",
        "schema": "ao-operator/remote-transfer-resource-exhaustion-guard/v1",
    },
    "remote_transfer_clock_skew_tolerance": {
        "path": f"{STATUS_ROOT}/remote-transfer-clock-skew-tolerance.json",
        "schema": "ao-operator/remote-transfer-clock-skew-tolerance/v1",
    },
    "remote_transfer_bundle_id_uniqueness": {
        "path": f"{STATUS_ROOT}/remote-transfer-bundle-id-uniqueness.json",
        "schema": "ao-operator/remote-transfer-bundle-id-uniqueness/v1",
    },
    "remote_transfer_bundle_content_type_allowlist": {
        "path": f"{STATUS_ROOT}/remote-transfer-bundle-content-type-allowlist.json",
        "schema": "ao-operator/remote-transfer-bundle-content-type-allowlist/v1",
    },
    "remote_transfer_per_tenant_quota_isolation": {
        "path": f"{STATUS_ROOT}/remote-transfer-per-tenant-quota-isolation.json",
        "schema": "ao-operator/remote-transfer-per-tenant-quota-isolation/v1",
    },
    "remote_transfer_wire_encryption_required": {
        "path": f"{STATUS_ROOT}/remote-transfer-wire-encryption-required.json",
        "schema": "ao-operator/remote-transfer-wire-encryption-required/v1",
    },
    "remote_transfer_sender_identity_rotation": {
        "path": f"{STATUS_ROOT}/remote-transfer-sender-identity-rotation.json",
        "schema": "ao-operator/remote-transfer-sender-identity-rotation/v1",
    },
    "ai_agent_blast_radius_inventory": {
        "path": f"{STATUS_ROOT}/ai-agent-blast-radius-inventory.json",
        "schema": "ao-operator/ai-agent-blast-radius-inventory/v1",
    },
    "ai_agent_destructive_action_approval": {
        "path": f"{STATUS_ROOT}/ai-agent-destructive-action-approval.json",
        "schema": "ao-operator/ai-agent-destructive-action-approval/v1",
    },
    "ai_agent_credential_reachability": {
        "path": f"{STATUS_ROOT}/ai-agent-credential-reachability.json",
        "schema": "ao-operator/ai-agent-credential-reachability/v1",
    },
    "ai_agent_instruction_packaging_leak_detection": {
        "path": f"{STATUS_ROOT}/ai-agent-instruction-packaging-leak-detection.json",
        "schema": "ao-operator/ai-agent-instruction-packaging-leak-detection/v1",
    },
    "mcp_tool_poisoning_detection": {
        "path": f"{STATUS_ROOT}/mcp-tool-poisoning-detection.json",
        "schema": "ao-operator/mcp-tool-poisoning-detection/v1",
    },
    "deepsec_diff_review_advisory_sast": {
        "path": f"{STATUS_ROOT}/deepsec-diff-review-advisory-sast.json",
        "schema": "ao-operator/deepsec-diff-review-advisory-sast/v1",
    },
    "agent_supply_chain_integrity": {
        "path": f"{STATUS_ROOT}/agent-supply-chain-integrity.json",
        "schema": "ao-operator/agent-supply-chain-integrity/v1",
    },
    "prompt_injection_escape_boundary": {
        "path": f"{STATUS_ROOT}/prompt-injection-escape-boundary.json",
        "schema": "ao-operator/prompt-injection-escape-boundary/v1",
    },
    "approval_clock_skew_defense": {
        "path": f"{STATUS_ROOT}/approval-clock-skew-defense.json",
        "schema": "ao-operator/approval-clock-skew-defense/v1",
    },
    "agent_log_redaction_round_trip": {
        "path": f"{STATUS_ROOT}/agent-log-redaction-round-trip.json",
        "schema": "ao-operator/agent-log-redaction-round-trip/v1",
    },
    "per_tenant_blast_radius_cap": {
        "path": f"{STATUS_ROOT}/per-tenant-blast-radius-cap.json",
        "schema": "ao-operator/per-tenant-blast-radius-cap/v1",
    },
    "sandbox_egress_allowlist": {
        "path": f"{STATUS_ROOT}/sandbox-egress-allowlist.json",
        "schema": "ao-operator/sandbox-egress-allowlist/v1",
    },
    "agent_tool_arg_injection_escape": {
        "path": f"{STATUS_ROOT}/agent-tool-arg-injection-escape.json",
        "schema": "ao-operator/agent-tool-arg-injection-escape/v1",
    },
    "agent_output_canary_leak_detection": {
        "path": f"{STATUS_ROOT}/agent-output-canary-leak-detection.json",
        "schema": "ao-operator/agent-output-canary-leak-detection/v1",
    },
    "agent_os_execution_budget_enforcement": {
        "path": f"{STATUS_ROOT}/agent-os-execution-budget-enforcement.json",
        "schema": "ao-operator/agent-os-execution-budget-enforcement/v1",
    },
    "agent_system_prompt_tamper_detection": {
        "path": f"{STATUS_ROOT}/agent-system-prompt-tamper-detection.json",
        "schema": "ao-operator/agent-system-prompt-tamper-detection/v1",
    },
    "tool_result_cache_poisoning_defense": {
        "path": f"{STATUS_ROOT}/tool-result-cache-poisoning-defense.json",
        "schema": "ao-operator/tool-result-cache-poisoning-defense/v1",
    },
    "agent_credential_scope_narrowing": {
        "path": f"{STATUS_ROOT}/agent-credential-scope-narrowing.json",
        "schema": "ao-operator/agent-credential-scope-narrowing/v1",
    },
}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def report_errors(report_id: str, report: dict[str, Any], expected_schema: str) -> list[str]:
    errors: list[str] = []
    if report.get("schema") != expected_schema:
        errors.append(f"{report_id} schema must be {expected_schema}")
    if report.get("verdict") != "PASS":
        errors.append(f"{report_id} verdict must be PASS")
    if report.get("dispatch_authorized") is not False:
        errors.append(f"{report_id} dispatch_authorized must remain false")
    if report.get("live_providers_run") is not False:
        errors.append(f"{report_id} live_providers_run must remain false")
    if report_id == "release_readiness" and report.get("ship_ready") is not True:
        errors.append("release_readiness ship_ready must be true")
    if report_id == "public_release_security":
        if int(report.get("blocking_findings") or 0) != 0:
            errors.append("public_release_security blocking_findings must be 0")
    if report_id == "dast_readiness":
        if report.get("remote_dast_enabled") is not False:
            errors.append("dast_readiness remote_dast_enabled must remain false")
    if report_id == "manual_pentest_gate":
        if report.get("manual_pentest_authorized") is not False:
            errors.append("manual_pentest_gate manual_pentest_authorized must remain false")
    if report_id == "host_key_evidence":
        if report.get("host_key_evidence_required") is not True:
            errors.append("host_key_evidence host_key_evidence_required must be true")
        if report.get("remote_dast_authorized") is not False:
            errors.append("host_key_evidence remote_dast_authorized must remain false")
    if report_id == "manual_pentest_report_classifier":
        if report.get("report_template_ready") is not True:
            errors.append("manual_pentest_report_classifier report_template_ready must be true")
        if report.get("manual_pentest_authorized") is not False:
            errors.append("manual_pentest_report_classifier manual_pentest_authorized must remain false")
    if report_id == "no_provider_rehearsal":
        if report.get("refused_without_approval") is not True:
            errors.append("no_provider_rehearsal refused_without_approval must be true")
        if report.get("would_run_provider") is not False:
            errors.append("no_provider_rehearsal would_run_provider must remain false")
    if report_id == "approval_lifecycle":
        if report.get("approval_usable") is True and report.get("approval_state") != "APPROVED_ACTIVE":
            errors.append("approval_lifecycle usable approvals must be APPROVED_ACTIVE")
    if report_id == "approval_cleanup":
        if report.get("removed") is True and report.get("mode") != "apply":
            errors.append("approval_cleanup removed=true requires apply mode")
    if report_id == "approved_launch_proof":
        launcher = report.get("launcher_after_approval") if isinstance(report.get("launcher_after_approval"), dict) else {}
        if launcher.get("verdict") != "PLAN":
            errors.append("approved_launch_proof launcher_after_approval verdict must be PLAN")
        if launcher.get("would_run_provider") is not False:
            errors.append("approved_launch_proof must not run providers")
    if report_id == "approval_audit_history":
        if int(report.get("event_count") or 0) < 1:
            errors.append("approval_audit_history event_count must be at least 1")
    if report_id == "post_approval_cleanup_route":
        route = report.get("postrun_route") if isinstance(report.get("postrun_route"), dict) else {}
        cleanup = report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {}
        if route.get("route") != "ACCEPTED":
            errors.append("post_approval_cleanup_route route must be ACCEPTED")
        if cleanup.get("removed") is not True:
            errors.append("post_approval_cleanup_route cleanup removed must be true")
    if report_id == "approval_runbook":
        if int(report.get("required_item_count") or 0) < 9:
            errors.append("approval_runbook required_item_count must be at least 9")
    if report_id == "mac_ubuntu_remote_approval_runbook":
        if int(report.get("required_item_count") or 0) < 17:
            errors.append("mac_ubuntu_remote_approval_runbook required_item_count must be at least 17")
    if report_id == "mac_ubuntu_remote_approved_fixture":
        if report.get("remote_git_synced") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture remote_git_synced must be true")
        if report.get("signed_bundle_verified") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture signed_bundle_verified must be true")
        if report.get("signature_verified") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture signature_verified must be true")
        if report.get("identity_verified") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture identity_verified must be true")
        if report.get("fixture_approval_written") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture fixture_approval_written must be true")
        if report.get("approval_valid") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture approval_valid must be true")
        if report.get("launcher_plan_verified") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture launcher_plan_verified must be true")
        if report.get("would_run_provider") is not False:
            errors.append("mac_ubuntu_remote_approved_fixture would_run_provider must be false")
        if report.get("approval_file_present_after") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture approval_file_present_after must be true")
        if report.get("remote_cleanup_absent") is not True:
            errors.append("mac_ubuntu_remote_approved_fixture remote_cleanup_absent must be true")
        if report.get("provider_dispatch") is not False:
            errors.append("mac_ubuntu_remote_approved_fixture provider_dispatch must be false")
    if report_id == "agent_os_architecture_implementation_gate":
        checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
        if report.get("implementation_ready") is not True:
            errors.append("agent_os_architecture_implementation_gate implementation_ready must be true")
        if int(report.get("role_count") or 0) != 7:
            errors.append("agent_os_architecture_implementation_gate role_count must be 7")
        if int(report.get("handoff_packet_count") or 0) != 7:
            errors.append("agent_os_architecture_implementation_gate handoff_packet_count must be 7")
        if int(report.get("runspec_task_count") or 0) != 7:
            errors.append("agent_os_architecture_implementation_gate runspec_task_count must be 7")
        if checks.get("role_handoff_runspec_alignment") != "PASS":
            errors.append("agent_os_architecture_implementation_gate role_handoff_runspec_alignment must be PASS")
    if report_id == "agent_os_router_transition_matrix":
        if int(report.get("case_count") or 0) != 9:
            errors.append("agent_os_router_transition_matrix case_count must be 9")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("live_provider_blocks_dispatch", {}).get("blocker_count", 0) < 1:
            errors.append("agent_os_router_transition_matrix live provider case must preserve a blocker")
        if by_id.get("refactor_with_release_state_v2", {}).get("state_verdict") != "PASS":
            errors.append("agent_os_router_transition_matrix release state v2 case must pass")
    if report_id == "agent_os_runspec_failure_injection_matrix":
        if int(report.get("case_count") or 0) != 7:
            errors.append("agent_os_runspec_failure_injection_matrix case_count must be 7")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        expected = {
            "baseline_validates": "PASS",
            "stale_approval_hash_refused": "REFUSED",
            "missing_prompt_refused": "FAIL",
            "dispatch_flag_mutation_refused": "FAIL",
            "bad_provider_profile_refused": "FAIL",
            "invalid_provider_refused": "FAIL",
            "missing_state_baseline_refused": "FAIL",
        }
        for case_id, verdict in expected.items():
            if by_id.get(case_id, {}).get("observed_verdict") != verdict:
                errors.append(f"agent_os_runspec_failure_injection_matrix {case_id} must be {verdict}")
    if report_id == "agent_os_runspec_dag_edge_coverage":
        if int(report.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_dag_edge_coverage task_count must be 7")
        if int(report.get("edge_count") or 0) != 6:
            errors.append("agent_os_runspec_dag_edge_coverage edge_count must be 6")
        if report.get("role_graph_alignment") is not True:
            errors.append("agent_os_runspec_dag_edge_coverage role_graph_alignment must be true")
        if report.get("entry_task_ids") != ["agent-os-planner"]:
            errors.append("agent_os_runspec_dag_edge_coverage entry_task_ids must be agent-os-planner")
        if report.get("terminal_task_ids") != ["agent-os-evaluator-closer"]:
            errors.append("agent_os_runspec_dag_edge_coverage terminal_task_ids must be agent-os-evaluator-closer")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_os_runspec_dag_edge_coverage mutation_case_count must be 5")
        cases = report.get("mutation_cases") if isinstance(report.get("mutation_cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "cycle_refused",
            "missing_role_edge_refused",
            "unknown_dependency_refused",
            "duplicate_entry_refused",
            "terminal_fork_refused",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_runspec_dag_edge_coverage {case_id} must be FAIL")
    if report_id == "agent_os_runspec_yaml_dag_parity":
        if int(report.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_dag_parity task_count must be 7")
        if int(report.get("yaml_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_edge_count must be 6")
        if int(report.get("renderer_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity renderer_edge_count must be 6")
        if int(report.get("role_graph_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity role_graph_edge_count must be 6")
        if report.get("yaml_renderer_alignment") is not True:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_renderer_alignment must be true")
        if report.get("yaml_role_graph_alignment") is not True:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_role_graph_alignment must be true")
        if report.get("entry_task_ids") != ["agent-os-planner"]:
            errors.append("agent_os_runspec_yaml_dag_parity entry_task_ids must be agent-os-planner")
        if report.get("terminal_task_ids") != ["agent-os-evaluator-closer"]:
            errors.append("agent_os_runspec_yaml_dag_parity terminal_task_ids must be agent-os-evaluator-closer")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("agent_os_runspec_yaml_dag_parity mutation_case_count must be 4")
        cases = report.get("mutation_cases") if isinstance(report.get("mutation_cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "yaml_cycle_refused",
            "yaml_renderer_edge_drift_refused",
            "yaml_unknown_dependency_refused",
            "yaml_terminal_fork_refused",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_runspec_yaml_dag_parity {case_id} must be FAIL")
    if report_id == "agent_os_runspec_yaml_semantic_parity":
        if int(report.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity task_count must be 7")
        if int(report.get("renderer_task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity renderer_task_count must be 7")
        if int(report.get("aligned_task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity aligned_task_count must be 7")
        if int(report.get("drifted_task_count") or 0) != 0:
            errors.append("agent_os_runspec_yaml_semantic_parity drifted_task_count must be 0")
        if report.get("all_aligned") is not True:
            errors.append("agent_os_runspec_yaml_semantic_parity all_aligned must be true")
        if report.get("fields_checked") != [
            "provider",
            "promptFile",
            "workspace",
            "policyProfile",
            "kind",
            "dispatchAuthorized",
        ]:
            errors.append("agent_os_runspec_yaml_semantic_parity fields_checked must list all six fields")
        if int(report.get("mutation_case_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_semantic_parity mutation_case_count must be 6")
        cases = report.get("mutation_cases") if isinstance(report.get("mutation_cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "yaml_provider_drift_refused",
            "yaml_prompt_drift_refused",
            "yaml_workspace_drift_refused",
            "yaml_policy_drift_refused",
            "yaml_kind_drift_refused",
            "yaml_dispatch_authorized_refused",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_runspec_yaml_semantic_parity {case_id} must be FAIL")
    if report_id == "agent_os_runspec_yaml_schema_injection":
        if int(report.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_schema_injection task_count must be 7")
        if int(report.get("mutation_case_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_schema_injection mutation_case_count must be 6")
        baseline_errors_value = report.get("baseline_errors")
        if not isinstance(baseline_errors_value, list) or baseline_errors_value:
            errors.append("agent_os_runspec_yaml_schema_injection baseline_errors must be empty")
        cases = report.get("mutation_cases") if isinstance(report.get("mutation_cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "malformed_yaml_refused",
            "duplicate_task_ids_refused",
            "missing_spec_block_refused",
            "bad_deps_type_refused",
            "unknown_task_field_refused",
            "unsafe_dispatch_authorized_refused",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_runspec_yaml_schema_injection {case_id} must be FAIL")
    if report_id == "agent_os_runspec_ao_preflight_compatibility":
        if int(report.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_ao_preflight_compatibility task_count must be 7")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_os_runspec_ao_preflight_compatibility mutation_case_count must be 5")
        baseline_errors_value = report.get("baseline_errors")
        if not isinstance(baseline_errors_value, list) or baseline_errors_value:
            errors.append("agent_os_runspec_ao_preflight_compatibility baseline_errors must be empty")
        contract = report.get("ao_contract")
        if not isinstance(contract, dict):
            errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract must be an object")
        else:
            if contract.get("api_versions") != ["ao.dev/v1"]:
                errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract.api_versions must be ['ao.dev/v1']")
            if contract.get("runspec_kinds") != ["Run"]:
                errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract.runspec_kinds must be ['Run']")
            if contract.get("task_kinds") != ["shell", "agent", "review", "test"]:
                errors.append(
                    "agent_os_runspec_ao_preflight_compatibility ao_contract.task_kinds must list AO TaskKind variants"
                )
        cases = report.get("mutation_cases") if isinstance(report.get("mutation_cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "wrong_api_version_refused",
            "wrong_runspec_kind_refused",
            "unknown_task_kind_refused",
            "unknown_dependency_refused",
            "dag_cycle_refused",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_runspec_ao_preflight_compatibility {case_id} must be FAIL")
    if report_id == "agent_os_router_default_state_version":
        if report.get("argparse_default") != "v2":
            errors.append("agent_os_router_default_state_version argparse_default must be v2")
        if int(report.get("case_count") or 0) != 3:
            errors.append("agent_os_router_default_state_version case_count must be 3")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "default_emits_state_v2",
            "explicit_v1_remains_supported",
            "explicit_v2_matches_default",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "PASS":
                errors.append(f"agent_os_router_default_state_version {case_id} must be PASS")
    if report_id == "agent_os_role_graph_backward_compat":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_os_role_graph_backward_compat case_count must be 6")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        for case_id in {
            "legacy_v1_state_minimal_loadable",
            "legacy_v1_state_extra_unknown_fields_tolerated",
            "legacy_v1_state_no_role_graph_schema_injects_default",
            "legacy_v2_state_round_trip_preserves_previous_schema",
            "legacy_v1_role_graph_artifact_remains_loadable",
        }:
            if by_id.get(case_id, {}).get("observed_verdict") != "PASS":
                errors.append(f"agent_os_role_graph_backward_compat {case_id} must be PASS")
        if by_id.get("unknown_state_schema_refused", {}).get("observed_verdict") != "FAIL":
            errors.append("agent_os_role_graph_backward_compat unknown_state_schema_refused must be FAIL")
    if report_id == "remote_transfer_chunk_cleanup_invariants":
        if int(report.get("case_count") or 0) != 6:
            errors.append("remote_transfer_chunk_cleanup_invariants case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("remote_transfer_chunk_cleanup_invariants mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_upload_commit_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_chunk_cleanup_invariants clean_upload_commit_passes must be PASS")
        for case_id in (
            "orphaned_chunk_after_abort_detected",
            "missing_finalize_detected",
            "stale_partial_stage_dir_detected",
            "double_commit_rejected",
            "retry_index_drift_detected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_chunk_cleanup_invariants {case_id} must be FAIL")
    if report_id == "remote_transfer_signed_bundle_tamper":
        if int(report.get("case_count") or 0) != 6:
            errors.append("remote_transfer_signed_bundle_tamper case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("remote_transfer_signed_bundle_tamper mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_signed_bundle_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_signed_bundle_tamper clean_signed_bundle_passes must be PASS")
        for case_id in (
            "truncated_bundle_rejected",
            "swapped_chunk_rejected",
            "wrong_signing_key_rejected",
            "replayed_bundle_rejected",
            "manifest_digest_mismatch_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_signed_bundle_tamper {case_id} must be FAIL")
    if report_id == "remote_transfer_approval_expiry_rotation":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_approval_expiry_rotation case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_approval_expiry_rotation mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_approval_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_approval_expiry_rotation clean_approval_passes must be PASS")
        for case_id in (
            "expired_approval_rejected",
            "approval_used_after_rotation_cutover_rejected",
            "signing_key_rotated_midflight_without_grace_rejected",
            "approval_reused_beyond_ttl_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_approval_expiry_rotation {case_id} must be FAIL")
    if report_id == "remote_transfer_bundle_ordering_resume":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_bundle_ordering_resume case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_bundle_ordering_resume mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_ordered_delivery_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_bundle_ordering_resume clean_ordered_delivery_passes must be PASS")
        for case_id in (
            "out_of_order_chunk_rejected",
            "partial_resume_drops_middle_chunk_rejected",
            "resume_cursor_lies_about_high_water_rejected",
            "duplicate_chunk_delivery_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_bundle_ordering_resume {case_id} must be FAIL")
    if report_id == "remote_transfer_provider_redaction_round_trip":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_provider_redaction_round_trip case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_provider_redaction_round_trip mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_round_trip_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_provider_redaction_round_trip clean_round_trip_passes must be PASS")
        for case_id in (
            "redaction_marker_stripped_before_transmit_rejected",
            "sensitive_field_leaks_past_redaction_filter_rejected",
            "double_redaction_corrupts_payload_rejected",
            "provider_response_leaks_redacted_value_back_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_provider_redaction_round_trip {case_id} must be FAIL")
    if report_id == "remote_transfer_network_retry_idempotency":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_network_retry_idempotency case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_network_retry_idempotency mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_retry_round_trip_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_network_retry_idempotency clean_retry_round_trip_passes must be PASS")
        for case_id in (
            "retry_without_nonce_dedup_rejected",
            "partial_flush_on_network_drop_rejected",
            "ack_lost_causes_double_commit_rejected",
            "timeout_shorter_than_response_causes_orphan_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_network_retry_idempotency {case_id} must be FAIL")
    if report_id == "remote_transfer_concurrent_transfer_collision":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_concurrent_transfer_collision case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_concurrent_transfer_collision mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_serialized_concurrent_transfers_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_concurrent_transfer_collision clean_serialized_concurrent_transfers_passes must be PASS")
        for case_id in (
            "parallel_transfers_no_lock_corrupts_state_rejected",
            "simultaneous_finalize_double_completes_bundle_rejected",
            "lost_writer_overwrites_winner_bundle_rejected",
            "stale_lock_holder_resumes_after_handoff_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_concurrent_transfer_collision {case_id} must be FAIL")
    if report_id == "remote_transfer_bundle_schema_version_skew":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_bundle_schema_version_skew case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_bundle_schema_version_skew mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_matched_schema_version_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_bundle_schema_version_skew clean_matched_schema_version_passes must be PASS")
        for case_id in (
            "receiver_below_min_version_rejected",
            "receiver_above_max_silently_downgrades_rejected",
            "bundle_advertises_unknown_extension_field_rejected",
            "schema_version_field_missing_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_bundle_schema_version_skew {case_id} must be FAIL")
    if report_id == "remote_transfer_resource_exhaustion_guard":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_resource_exhaustion_guard case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_resource_exhaustion_guard mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_within_quota_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_resource_exhaustion_guard clean_within_quota_passes must be PASS")
        for case_id in (
            "announced_chunk_count_exceeds_quota_rejected",
            "announced_total_size_exceeds_quota_rejected",
            "per_chunk_size_exceeds_max_rejected",
            "transfer_exceeds_announced_count_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_resource_exhaustion_guard {case_id} must be FAIL")
    if report_id == "remote_transfer_clock_skew_tolerance":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_clock_skew_tolerance case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_clock_skew_tolerance mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_within_skew_tolerance_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_clock_skew_tolerance clean_within_skew_tolerance_passes must be PASS")
        for case_id in (
            "sender_clock_ahead_of_receiver_rejected",
            "sender_clock_behind_receiver_rejected",
            "future_dated_bundle_accepted_as_currently_valid_rejected",
            "ttl_window_straddling_skew_silently_extended_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_clock_skew_tolerance {case_id} must be FAIL")
    if report_id == "remote_transfer_bundle_id_uniqueness":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_bundle_id_uniqueness case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_bundle_id_uniqueness mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_unique_bundle_ids_pass", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_bundle_id_uniqueness clean_unique_bundle_ids_pass must be PASS")
        for case_id in (
            "duplicate_bundle_id_within_session_rejected",
            "cross_sender_bundle_id_collision_rejected",
            "bundle_id_truncation_collision_rejected",
            "bundle_id_replayed_after_completion_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_bundle_id_uniqueness {case_id} must be FAIL")
    if report_id == "remote_transfer_bundle_content_type_allowlist":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_bundle_content_type_allowlist case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_bundle_content_type_allowlist mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_allowlisted_content_type_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_bundle_content_type_allowlist clean_allowlisted_content_type_passes must be PASS")
        for case_id in (
            "unknown_content_type_silently_coerced_rejected",
            "mismatched_extension_to_content_type_rejected",
            "unknown_content_encoding_silently_decoded_rejected",
            "content_type_charset_parameter_smuggled_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_bundle_content_type_allowlist {case_id} must be FAIL")
    if report_id == "remote_transfer_per_tenant_quota_isolation":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_per_tenant_quota_isolation case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_per_tenant_quota_isolation mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_per_tenant_within_quota_passes", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_per_tenant_quota_isolation clean_per_tenant_within_quota_passes must be PASS")
        for case_id in (
            "tenant_a_overflows_tenant_b_quota_slot_rejected",
            "aggregated_quota_across_tenants_merged_rejected",
            "tenant_identity_stripped_silently_coerced_to_default_rejected",
            "quota_refund_on_abort_double_credited_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_per_tenant_quota_isolation {case_id} must be FAIL")
    if report_id == "remote_transfer_wire_encryption_required":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_wire_encryption_required case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_wire_encryption_required mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_encrypted_bundle_accepted", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_wire_encryption_required clean_encrypted_bundle_accepted must be PASS")
        for case_id in (
            "cleartext_bundle_silently_accepted_rejected",
            "downgraded_tls_cipher_silently_accepted_rejected",
            "weak_null_cipher_suite_negotiated_rejected",
            "encryption_header_stripped_after_handshake_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_wire_encryption_required {case_id} must be FAIL")
    if report_id == "remote_transfer_sender_identity_rotation":
        if int(report.get("case_count") or 0) != 5:
            errors.append("remote_transfer_sender_identity_rotation case_count must be 5")
        if int(report.get("mutation_case_count") or 0) != 4:
            errors.append("remote_transfer_sender_identity_rotation mutation_case_count must be 4")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_post_rotation_bundle_accepted", {}).get("observed_verdict") != "PASS":
            errors.append("remote_transfer_sender_identity_rotation clean_post_rotation_bundle_accepted must be PASS")
        for case_id in (
            "retired_identity_silently_accepted_rejected",
            "rotation_announcement_unsigned_silently_accepted_rejected",
            "future_rotation_effective_at_silently_accepted_rejected",
            "dual_acceptance_window_silently_left_open_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"remote_transfer_sender_identity_rotation {case_id} must be FAIL")
    if report_id == "ai_agent_blast_radius_inventory":
        if int(report.get("case_count") or 0) != 6:
            errors.append("ai_agent_blast_radius_inventory case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("ai_agent_blast_radius_inventory mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_inventory_classified_and_gated", {}).get("observed_verdict") != "PASS":
            errors.append("ai_agent_blast_radius_inventory clean_inventory_classified_and_gated must be PASS")
        for case_id in (
            "unclassified_high_blast_radius_command_path_rejected",
            "destructive_action_without_approval_gate_rejected",
            "credential_path_reachable_from_untrusted_content_rejected",
            "provider_dispatch_without_approval_readiness_rejected",
            "release_artifact_includes_instruction_or_credentials_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"ai_agent_blast_radius_inventory {case_id} must be FAIL")
    if report_id == "ai_agent_destructive_action_approval":
        if int(report.get("case_count") or 0) != 6:
            errors.append("ai_agent_destructive_action_approval case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("ai_agent_destructive_action_approval mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_destructive_action_with_fresh_scoped_approval_executes", {}).get("observed_verdict") != "PASS":
            errors.append("ai_agent_destructive_action_approval clean_destructive_action_with_fresh_scoped_approval_executes must be PASS")
        for case_id in (
            "stale_approval_reused_after_expiry_rejected",
            "approval_scope_widened_at_exec_silently_accepted_rejected",
            "approval_consumed_twice_for_distinct_destructive_ops_rejected",
            "destructive_op_runs_with_policy_only_without_token_rejected",
            "parent_process_approval_inherited_by_child_without_reconfirm_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"ai_agent_destructive_action_approval {case_id} must be FAIL")
    if report_id == "ai_agent_credential_reachability":
        if int(report.get("case_count") or 0) != 6:
            errors.append("ai_agent_credential_reachability case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("ai_agent_credential_reachability mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_untrusted_to_credential_reachable_path", {}).get("observed_verdict") != "PASS":
            errors.append("ai_agent_credential_reachability clean_no_untrusted_to_credential_reachable_path must be PASS")
        for case_id in (
            "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected",
            "agent_tool_output_piped_to_shell_with_ssh_dir_rejected",
            "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected",
            "web_fetch_reflected_into_shell_resolving_env_rejected",
            "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"ai_agent_credential_reachability {case_id} must be FAIL")
    if report_id == "ai_agent_instruction_packaging_leak_detection":
        if int(report.get("case_count") or 0) != 6:
            errors.append("ai_agent_instruction_packaging_leak_detection case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("ai_agent_instruction_packaging_leak_detection mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_instruction_or_packaging_leaks_in_public_artifacts", {}).get("observed_verdict") != "PASS":
            errors.append("ai_agent_instruction_packaging_leak_detection clean_no_instruction_or_packaging_leaks_in_public_artifacts must be PASS")
        for case_id in (
            "claude_md_directives_leaked_into_status_report_rejected",
            "agent_memory_snippet_copy_pasted_into_public_doc_rejected",
            "raw_user_prompt_logged_in_operator_slice_evidence_rejected",
            "anthropic_api_key_surfaced_in_evaluation_transcript_rejected",
            "tmp_diagnostic_path_included_in_public_artifact_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"ai_agent_instruction_packaging_leak_detection {case_id} must be FAIL")
    if report_id == "mcp_tool_poisoning_detection":
        if int(report.get("case_count") or 0) != 6:
            errors.append("mcp_tool_poisoning_detection case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("mcp_tool_poisoning_detection mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_mcp_or_tool_poisoning_indicators", {}).get("observed_verdict") != "PASS":
            errors.append("mcp_tool_poisoning_detection clean_no_mcp_or_tool_poisoning_indicators must be PASS")
        for case_id in (
            "hidden_imperative_in_mcp_description_rejected",
            "tool_result_schema_adds_destructive_default_arg_rejected",
            "mcp_returns_url_to_fetch_and_apply_rejected",
            "tool_name_shadowing_overrides_native_tool_rejected",
            "signed_descriptor_advertises_unallowed_privilege_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"mcp_tool_poisoning_detection {case_id} must be FAIL")
    if report_id == "deepsec_diff_review_advisory_sast":
        if int(report.get("case_count") or 0) != 6:
            errors.append("deepsec_diff_review_advisory_sast case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("deepsec_diff_review_advisory_sast mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_untrusted_to_dangerous_sink_edges", {}).get("observed_verdict") != "PASS":
            errors.append("deepsec_diff_review_advisory_sast clean_no_untrusted_to_dangerous_sink_edges must be PASS")
        for case_id in (
            "untrusted_input_flows_into_shell_command_rejected",
            "untrusted_input_flows_into_fs_write_outside_workspace_rejected",
            "untrusted_input_flows_into_network_egress_rejected",
            "eval_or_exec_on_retrieved_content_rejected",
            "dynamic_import_from_agent_controlled_path_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"deepsec_diff_review_advisory_sast {case_id} must be FAIL")
    if report_id == "agent_supply_chain_integrity":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_supply_chain_integrity case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_supply_chain_integrity mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_unauthorized_provenance_or_unsigned_package_edges", {}).get("observed_verdict") != "PASS":
            errors.append("agent_supply_chain_integrity clean_no_unauthorized_provenance_or_unsigned_package_edges must be PASS")
        for case_id in (
            "unsigned_package_admitted_without_signature_rejected",
            "lock_file_digest_mismatch_admitted_rejected",
            "dependency_confusion_via_shadow_registry_rejected",
            "post_install_script_with_network_egress_rejected",
            "transitive_yank_without_repin_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_supply_chain_integrity {case_id} must be FAIL")
    if report_id == "prompt_injection_escape_boundary":
        if int(report.get("case_count") or 0) != 6:
            errors.append("prompt_injection_escape_boundary case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("prompt_injection_escape_boundary mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended", {}).get("observed_verdict") != "PASS":
            errors.append("prompt_injection_escape_boundary clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended must be PASS")
        for case_id in (
            "attacker_role_spoofing_appended_after_user_content_rejected",
            "fenced_block_escape_breaking_system_boundary_rejected",
            "json_injection_replacing_operator_instructions_rejected",
            "tool_name_shadowing_via_attacker_section_rejected",
            "instruction_smuggling_via_unicode_homoglyph_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"prompt_injection_escape_boundary {case_id} must be FAIL")
    if report_id == "approval_clock_skew_defense":
        if int(report.get("case_count") or 0) != 6:
            errors.append("approval_clock_skew_defense case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("approval_clock_skew_defense mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_clock_skew_or_replay_or_stale_freshness_edges", {}).get("observed_verdict") != "PASS":
            errors.append("approval_clock_skew_defense clean_no_clock_skew_or_replay_or_stale_freshness_edges must be PASS")
        for case_id in (
            "ntp_rewind_admits_expired_approval_rejected",
            "leap_second_jump_admits_expired_approval_rejected",
            "tz_tagged_as_utc_admits_expired_approval_rejected",
            "expired_but_cached_admits_replay_rejected",
            "signed_token_replay_admits_reactivation_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"approval_clock_skew_defense {case_id} must be FAIL")
    if report_id == "agent_log_redaction_round_trip":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_log_redaction_round_trip case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_log_redaction_round_trip mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output", {}).get("observed_verdict") != "PASS":
            errors.append("agent_log_redaction_round_trip clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output must be PASS")
        for case_id in (
            "partial_pattern_match_leaves_original_substring_rejected",
            "base64_encoded_secret_unredacted_in_round_trip_rejected",
            "path_normalization_alias_unredacted_in_round_trip_rejected",
            "case_insensitive_token_unredacted_in_round_trip_rejected",
            "json_string_escape_token_unredacted_in_round_trip_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_log_redaction_round_trip {case_id} must be FAIL")
    if report_id == "per_tenant_blast_radius_cap":
        if int(report.get("case_count") or 0) != 6:
            errors.append("per_tenant_blast_radius_cap case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("per_tenant_blast_radius_cap mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges", {}).get("observed_verdict") != "PASS":
            errors.append("per_tenant_blast_radius_cap clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges must be PASS")
        for case_id in (
            "cross_tenant_fanout_to_unrelated_tenant_resource_rejected",
            "missing_tenant_tag_admits_global_blast_radius_rejected",
            "tenant_tag_spoof_admits_other_tenant_resource_rejected",
            "allowlist_bypass_admits_unallowlisted_target_rejected",
            "quota_overflow_leak_admits_post_window_action_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"per_tenant_blast_radius_cap {case_id} must be FAIL")
    if report_id == "sandbox_egress_allowlist":
        if int(report.get("case_count") or 0) != 6:
            errors.append("sandbox_egress_allowlist case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("sandbox_egress_allowlist mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_unallowlisted_or_bypassed_egress_attempts", {}).get("observed_verdict") != "PASS":
            errors.append("sandbox_egress_allowlist clean_no_unallowlisted_or_bypassed_egress_attempts must be PASS")
        for case_id in (
            "unallowlisted_host_egress_admitted_rejected",
            "ip_literal_bypass_admits_unallowlisted_target_rejected",
            "dns_rebind_bypass_admits_unallowlisted_target_rejected",
            "proxy_chain_bypass_admits_unallowlisted_target_rejected",
            "raw_socket_bypass_admits_unallowlisted_target_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"sandbox_egress_allowlist {case_id} must be FAIL")
    if report_id == "agent_tool_arg_injection_escape":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_tool_arg_injection_escape case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_tool_arg_injection_escape mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion", {}).get("observed_verdict") != "PASS":
            errors.append("agent_tool_arg_injection_escape clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion must be PASS")
        for case_id in (
            "string_template_breakout_via_unescaped_quote_rejected",
            "json_arg_breakout_via_nested_object_smuggling_rejected",
            "polymorphic_argument_coercion_via_type_mismatch_rejected",
            "shell_metachar_injection_via_unfiltered_string_arg_rejected",
            "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_tool_arg_injection_escape {case_id} must be FAIL")
    if report_id == "agent_output_canary_leak_detection":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_output_canary_leak_detection case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_output_canary_leak_detection mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_canary_or_marked_secret_leak_in_output", {}).get("observed_verdict") != "PASS":
            errors.append("agent_output_canary_leak_detection clean_no_canary_or_marked_secret_leak_in_output must be PASS")
        for case_id in (
            "literal_canary_token_in_output_rejected",
            "base64_encoded_canary_token_in_output_rejected",
            "unicode_homoglyph_canary_substitution_in_output_rejected",
            "partial_canary_fragment_concatenation_in_output_rejected",
            "marked_secret_passthrough_via_field_label_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_output_canary_leak_detection {case_id} must be FAIL")
    if report_id == "agent_os_execution_budget_enforcement":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_os_execution_budget_enforcement case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_os_execution_budget_enforcement mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_budget_overflow_or_reset_bypass", {}).get("observed_verdict") != "PASS":
            errors.append("agent_os_execution_budget_enforcement clean_no_budget_overflow_or_reset_bypass must be PASS")
        for case_id in (
            "token_budget_overflow_admit_rejected",
            "time_budget_overflow_admit_rejected",
            "tool_call_count_overflow_admit_rejected",
            "cost_ceiling_overflow_admit_rejected",
            "budget_reset_bypass_admit_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_os_execution_budget_enforcement {case_id} must be FAIL")
    if report_id == "agent_system_prompt_tamper_detection":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_system_prompt_tamper_detection case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_system_prompt_tamper_detection mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_system_prompt_tamper", {}).get("observed_verdict") != "PASS":
            errors.append("agent_system_prompt_tamper_detection clean_no_system_prompt_tamper must be PASS")
        for case_id in (
            "system_prompt_substitution_admit_rejected",
            "system_prompt_appended_instruction_admit_rejected",
            "system_prompt_truncation_admit_rejected",
            "system_prompt_unicode_homoglyph_admit_rejected",
            "system_prompt_role_relabel_admit_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_system_prompt_tamper_detection {case_id} must be FAIL")
    if report_id == "tool_result_cache_poisoning_defense":
        if int(report.get("case_count") or 0) != 6:
            errors.append("tool_result_cache_poisoning_defense case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("tool_result_cache_poisoning_defense mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_tool_result_cache_poisoning", {}).get("observed_verdict") != "PASS":
            errors.append("tool_result_cache_poisoning_defense clean_no_tool_result_cache_poisoning must be PASS")
        for case_id in (
            "cache_key_collision_admit_rejected",
            "stale_cache_serve_after_invalidation_admit_rejected",
            "ttl_extension_via_admin_replay_admit_rejected",
            "forged_response_signature_admit_rejected",
            "cross_tenant_cache_share_admit_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"tool_result_cache_poisoning_defense {case_id} must be FAIL")
    if report_id == "agent_credential_scope_narrowing":
        if int(report.get("case_count") or 0) != 6:
            errors.append("agent_credential_scope_narrowing case_count must be 6")
        if int(report.get("mutation_case_count") or 0) != 5:
            errors.append("agent_credential_scope_narrowing mutation_case_count must be 5")
        cases = report.get("cases") if isinstance(report.get("cases"), list) else []
        by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
        if by_id.get("clean_no_credential_scope_widening", {}).get("observed_verdict") != "PASS":
            errors.append("agent_credential_scope_narrowing clean_no_credential_scope_widening must be PASS")
        for case_id in (
            "credential_scope_substitution_admit_rejected",
            "credential_scope_append_admit_rejected",
            "credential_audience_relabel_admit_rejected",
            "credential_expiry_extension_admit_rejected",
            "credential_principal_mint_admit_rejected",
        ):
            if by_id.get(case_id, {}).get("observed_verdict") != "FAIL":
                errors.append(f"agent_credential_scope_narrowing {case_id} must be FAIL")
    if report_id == "approval_audit_retention":
        if report.get("rotation_due") is not False:
            errors.append("approval_audit_retention rotation_due must be false for committed baseline")
    if report_id == "approval_bundle_signature":
        if report.get("signature_matches") is not True:
            errors.append("approval_bundle_signature signature_matches must be true")
    if report_id == "approval_revocation":
        if report.get("revocation_applied") is not False:
            errors.append("approval_revocation default report must be non-mutating")
    if report_id == "approval_identity_signature":
        if report.get("identity_signature") is not True:
            errors.append("approval_identity_signature identity_signature must be true")
        if report.get("signature_verified") is not True:
            errors.append("approval_identity_signature signature_verified must be true")
        if report.get("private_key_committed") is not False:
            errors.append("approval_identity_signature private_key_committed must be false")
    if report_id == "approval_revocation_apply_proof":
        materialization = report.get("materialization") if isinstance(report.get("materialization"), dict) else {}
        revocation = report.get("revocation") if isinstance(report.get("revocation"), dict) else {}
        if materialization.get("approval_file_written") is not True:
            errors.append("approval_revocation_apply_proof materialization approval_file_written must be true")
        if revocation.get("revocation_applied") is not True:
            errors.append("approval_revocation_apply_proof revocation_applied must be true")
        if revocation.get("approval_file_present_after") is not False:
            errors.append("approval_revocation_apply_proof approval_file_present_after must be false")
        if report.get("revocation_log_sanitized") is not True:
            errors.append("approval_revocation_apply_proof revocation_log_sanitized must be true")
    if report_id == "approval_audit_archive_restore":
        if report.get("archive_created") is not True:
            errors.append("approval_audit_archive_restore archive_created must be true")
        if report.get("restore_verified") is not True:
            errors.append("approval_audit_archive_restore restore_verified must be true")
        if report.get("source_mutated") is not False:
            errors.append("approval_audit_archive_restore source_mutated must be false")
    if report_id == "mac_ubuntu_approval_artifact_parity":
        if report.get("artifact_parity") is not True:
            errors.append("mac_ubuntu_approval_artifact_parity artifact_parity must be true")
        if report.get("remote_git_synced") is not True:
            errors.append("mac_ubuntu_approval_artifact_parity remote_git_synced must be true")
        if report.get("remote_checks_pass") is not True:
            errors.append("mac_ubuntu_approval_artifact_parity remote_checks_pass must be true")
        if report.get("provider_dispatch") is not False:
            errors.append("mac_ubuntu_approval_artifact_parity provider_dispatch must be false")
    if report_id == "mac_ubuntu_signed_approval_bundle_transfer":
        if report.get("artifact_parity") is not True:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer artifact_parity must be true")
        if report.get("remote_git_synced") is not True:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer remote_git_synced must be true")
        if report.get("signature_verified") is not True:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer signature_verified must be true")
        if report.get("identity_verified") is not True:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer identity_verified must be true")
        if report.get("remote_cleanup_absent") is not True:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer remote_cleanup_absent must be true")
        if report.get("provider_dispatch") is not False:
            errors.append("mac_ubuntu_signed_approval_bundle_transfer provider_dispatch must be false")
    if report_id == "mac_ubuntu_remote_approval_materialization_dry_run":
        if report.get("remote_git_synced") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run remote_git_synced must be true")
        if report.get("signed_bundle_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run signed_bundle_verified must be true")
        if report.get("signature_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run signature_verified must be true")
        if report.get("identity_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run identity_verified must be true")
        if report.get("materialization_dry_run_passed") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run materialization_dry_run_passed must be true")
        if report.get("approval_file_written") is not False:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run approval_file_written must be false")
        if report.get("approval_valid") is not False:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run approval_valid must be false")
        if report.get("approval_file_present_after") is not False:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run approval_file_present_after must be false")
        if report.get("remote_cleanup_absent") is not True:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run remote_cleanup_absent must be true")
        if report.get("provider_dispatch") is not False:
            errors.append("mac_ubuntu_remote_approval_materialization_dry_run provider_dispatch must be false")
    if report_id == "mac_ubuntu_remote_approval_revocation_rollback":
        if report.get("remote_git_synced") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback remote_git_synced must be true")
        if report.get("signed_bundle_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback signed_bundle_verified must be true")
        if report.get("signature_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback signature_verified must be true")
        if report.get("identity_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback identity_verified must be true")
        if report.get("fixture_approval_written") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback fixture_approval_written must be true")
        if report.get("revocation_applied") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback revocation_applied must be true")
        if report.get("approval_file_present_after_revocation") is not False:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback approval_file_present_after_revocation must be false")
        if report.get("rollback_restore_verified") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback rollback_restore_verified must be true")
        if report.get("approval_file_restored_after") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback approval_file_restored_after must be true")
        if report.get("revocation_log_sanitized") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback revocation_log_sanitized must be true")
        if report.get("remote_cleanup_absent") is not True:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback remote_cleanup_absent must be true")
        if report.get("provider_dispatch") is not False:
            errors.append("mac_ubuntu_remote_approval_revocation_rollback provider_dispatch must be false")
    return errors


def summarize(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    guardrails: dict[str, Any] = {}
    errors: list[str] = []
    blockers: list[str] = []
    for report_id, config in REPORTS.items():
        path = resolve_path(root, config["path"])
        report = load_json(path)
        current_errors = report_errors(report_id, report, config["schema"])
        if current_errors:
            blockers.append(report_id)
            errors.extend(current_errors)
        guardrails[report_id] = {
            "path": relpath(root, path),
            "schema": report.get("schema", ""),
            "verdict": report.get("verdict", "MISSING"),
            "dispatch_authorized": report.get("dispatch_authorized"),
            "live_providers_run": report.get("live_providers_run"),
        }
        for optional_key in ("ship_ready", "refused_without_approval", "would_run_provider", "next_safe_command"):
            if optional_key in report:
                guardrails[report_id][optional_key] = report[optional_key]
        for optional_key in ("approval_state", "approval_usable", "removed"):
            if optional_key in report:
                guardrails[report_id][optional_key] = report[optional_key]
        if report_id == "approved_launch_proof":
            launcher = report.get("launcher_after_approval") if isinstance(report.get("launcher_after_approval"), dict) else {}
            guardrails[report_id]["launcher_verdict"] = launcher.get("verdict", "")
            guardrails[report_id]["launcher_would_run_provider"] = launcher.get("would_run_provider", False)
        if report_id == "approval_audit_history":
            guardrails[report_id]["event_count"] = report.get("event_count", 0)
            guardrails[report_id]["latest_event"] = report.get("latest_event", "")
        if report_id == "post_approval_cleanup_route":
            route = report.get("postrun_route") if isinstance(report.get("postrun_route"), dict) else {}
            cleanup = report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {}
            guardrails[report_id]["route"] = route.get("route", "")
            guardrails[report_id]["cleanup_removed"] = cleanup.get("removed", False)
        if report_id == "approval_runbook":
            guardrails[report_id]["required_item_count"] = report.get("required_item_count", 0)
        if report_id == "mac_ubuntu_remote_approval_runbook":
            guardrails[report_id]["required_item_count"] = report.get("required_item_count", 0)
        if report_id == "mac_ubuntu_remote_approved_fixture":
            guardrails[report_id]["remote_git_synced"] = report.get("remote_git_synced", False)
            guardrails[report_id]["signed_bundle_verified"] = report.get("signed_bundle_verified", False)
            guardrails[report_id]["signature_verified"] = report.get("signature_verified", False)
            guardrails[report_id]["identity_verified"] = report.get("identity_verified", False)
            guardrails[report_id]["fixture_approval_written"] = report.get("fixture_approval_written", False)
            guardrails[report_id]["approval_valid"] = report.get("approval_valid", False)
            guardrails[report_id]["launcher_plan_verified"] = report.get("launcher_plan_verified", False)
            guardrails[report_id]["would_run_provider"] = report.get("would_run_provider", True)
            guardrails[report_id]["approval_file_present_after"] = report.get("approval_file_present_after", False)
            guardrails[report_id]["remote_cleanup_absent"] = report.get("remote_cleanup_absent", False)
            guardrails[report_id]["provider_dispatch"] = report.get("provider_dispatch", True)
        if report_id == "agent_os_architecture_implementation_gate":
            checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
            guardrails[report_id]["implementation_ready"] = report.get("implementation_ready", False)
            guardrails[report_id]["role_count"] = report.get("role_count", 0)
            guardrails[report_id]["handoff_packet_count"] = report.get("handoff_packet_count", 0)
            guardrails[report_id]["runspec_task_count"] = report.get("runspec_task_count", 0)
            guardrails[report_id]["role_handoff_runspec_alignment"] = checks.get("role_handoff_runspec_alignment", "")
        if report_id in {"agent_os_router_transition_matrix", "agent_os_runspec_failure_injection_matrix"}:
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
        if report_id == "agent_os_runspec_dag_edge_coverage":
            guardrails[report_id]["task_count"] = report.get("task_count", 0)
            guardrails[report_id]["edge_count"] = report.get("edge_count", 0)
            guardrails[report_id]["role_graph_alignment"] = report.get("role_graph_alignment", False)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_os_runspec_yaml_dag_parity":
            guardrails[report_id]["task_count"] = report.get("task_count", 0)
            guardrails[report_id]["yaml_edge_count"] = report.get("yaml_edge_count", 0)
            guardrails[report_id]["renderer_edge_count"] = report.get("renderer_edge_count", 0)
            guardrails[report_id]["role_graph_edge_count"] = report.get("role_graph_edge_count", 0)
            guardrails[report_id]["yaml_renderer_alignment"] = report.get("yaml_renderer_alignment", False)
            guardrails[report_id]["yaml_role_graph_alignment"] = report.get("yaml_role_graph_alignment", False)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_os_runspec_yaml_semantic_parity":
            guardrails[report_id]["task_count"] = report.get("task_count", 0)
            guardrails[report_id]["renderer_task_count"] = report.get("renderer_task_count", 0)
            guardrails[report_id]["aligned_task_count"] = report.get("aligned_task_count", 0)
            guardrails[report_id]["drifted_task_count"] = report.get("drifted_task_count", 0)
            guardrails[report_id]["all_aligned"] = report.get("all_aligned", False)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_os_runspec_yaml_schema_injection":
            guardrails[report_id]["task_count"] = report.get("task_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
            baseline_errors_value = report.get("baseline_errors")
            guardrails[report_id]["baseline_errors_count"] = (
                len(baseline_errors_value) if isinstance(baseline_errors_value, list) else 0
            )
        if report_id == "agent_os_runspec_ao_preflight_compatibility":
            guardrails[report_id]["task_count"] = report.get("task_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
            baseline_errors_value = report.get("baseline_errors")
            guardrails[report_id]["baseline_errors_count"] = (
                len(baseline_errors_value) if isinstance(baseline_errors_value, list) else 0
            )
        if report_id == "agent_os_router_default_state_version":
            guardrails[report_id]["argparse_default"] = report.get("argparse_default", "")
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
        if report_id == "agent_os_role_graph_backward_compat":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
        if report_id == "remote_transfer_chunk_cleanup_invariants":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_signed_bundle_tamper":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_approval_expiry_rotation":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_bundle_ordering_resume":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_provider_redaction_round_trip":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_network_retry_idempotency":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_concurrent_transfer_collision":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_bundle_schema_version_skew":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_resource_exhaustion_guard":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_clock_skew_tolerance":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_bundle_id_uniqueness":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_bundle_content_type_allowlist":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_per_tenant_quota_isolation":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_wire_encryption_required":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "remote_transfer_sender_identity_rotation":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "ai_agent_blast_radius_inventory":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "ai_agent_destructive_action_approval":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "ai_agent_credential_reachability":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "ai_agent_instruction_packaging_leak_detection":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "mcp_tool_poisoning_detection":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "deepsec_diff_review_advisory_sast":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_supply_chain_integrity":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "prompt_injection_escape_boundary":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "approval_clock_skew_defense":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_log_redaction_round_trip":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "per_tenant_blast_radius_cap":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "sandbox_egress_allowlist":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_tool_arg_injection_escape":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_output_canary_leak_detection":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_os_execution_budget_enforcement":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_system_prompt_tamper_detection":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "tool_result_cache_poisoning_defense":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "agent_credential_scope_narrowing":
            guardrails[report_id]["case_count"] = report.get("case_count", 0)
            guardrails[report_id]["mutation_case_count"] = report.get("mutation_case_count", 0)
        if report_id == "public_release_security":
            guardrails[report_id]["blocking_findings"] = report.get("blocking_findings", 0)
            guardrails[report_id]["mode"] = report.get("mode", "")
        if report_id == "dast_readiness":
            guardrails[report_id]["remote_dast_enabled"] = report.get("remote_dast_enabled", True)
        if report_id == "manual_pentest_gate":
            guardrails[report_id]["manual_pentest_authorized"] = report.get("manual_pentest_authorized", True)
            guardrails[report_id]["approval_env_present"] = report.get("approval_env_present", True)
        if report_id == "host_key_evidence":
            guardrails[report_id]["host_key_evidence_required"] = report.get("host_key_evidence_required", False)
            guardrails[report_id]["remote_dast_authorized"] = report.get("remote_dast_authorized", True)
        if report_id == "manual_pentest_report_classifier":
            guardrails[report_id]["report_template_ready"] = report.get("report_template_ready", False)
            guardrails[report_id]["manual_pentest_authorized"] = report.get("manual_pentest_authorized", True)
        if report_id == "approval_audit_retention":
            guardrails[report_id]["rotation_due"] = report.get("rotation_due", False)
            guardrails[report_id]["event_count"] = report.get("event_count", 0)
        if report_id == "approval_bundle_signature":
            guardrails[report_id]["signature_matches"] = report.get("signature_matches", False)
            guardrails[report_id]["identity_signature"] = report.get("identity_signature", False)
        if report_id == "approval_revocation":
            guardrails[report_id]["revocation_applied"] = report.get("revocation_applied", False)
            guardrails[report_id]["approval_file_present_after"] = report.get("approval_file_present_after", False)
        if report_id == "approval_identity_signature":
            guardrails[report_id]["identity_signature"] = report.get("identity_signature", False)
            guardrails[report_id]["signature_verified"] = report.get("signature_verified", False)
            guardrails[report_id]["private_key_committed"] = report.get("private_key_committed", True)
        if report_id == "approval_revocation_apply_proof":
            materialization = report.get("materialization") if isinstance(report.get("materialization"), dict) else {}
            revocation = report.get("revocation") if isinstance(report.get("revocation"), dict) else {}
            guardrails[report_id]["approval_file_written"] = materialization.get("approval_file_written", False)
            guardrails[report_id]["revocation_applied"] = revocation.get("revocation_applied", False)
            guardrails[report_id]["approval_file_present_after"] = revocation.get("approval_file_present_after", True)
            guardrails[report_id]["revocation_log_sanitized"] = report.get("revocation_log_sanitized", False)
        if report_id == "approval_audit_archive_restore":
            guardrails[report_id]["archive_created"] = report.get("archive_created", False)
            guardrails[report_id]["restore_verified"] = report.get("restore_verified", False)
            guardrails[report_id]["source_mutated"] = report.get("source_mutated", True)
        if report_id == "mac_ubuntu_approval_artifact_parity":
            guardrails[report_id]["artifact_parity"] = report.get("artifact_parity", False)
            guardrails[report_id]["remote_git_synced"] = report.get("remote_git_synced", False)
            guardrails[report_id]["remote_checks_pass"] = report.get("remote_checks_pass", False)
            guardrails[report_id]["provider_dispatch"] = report.get("provider_dispatch", True)
        if report_id == "mac_ubuntu_signed_approval_bundle_transfer":
            guardrails[report_id]["artifact_parity"] = report.get("artifact_parity", False)
            guardrails[report_id]["remote_git_synced"] = report.get("remote_git_synced", False)
            guardrails[report_id]["signature_verified"] = report.get("signature_verified", False)
            guardrails[report_id]["identity_verified"] = report.get("identity_verified", False)
            guardrails[report_id]["remote_cleanup_absent"] = report.get("remote_cleanup_absent", False)
            guardrails[report_id]["provider_dispatch"] = report.get("provider_dispatch", True)
        if report_id == "mac_ubuntu_remote_approval_materialization_dry_run":
            guardrails[report_id]["remote_git_synced"] = report.get("remote_git_synced", False)
            guardrails[report_id]["signed_bundle_verified"] = report.get("signed_bundle_verified", False)
            guardrails[report_id]["signature_verified"] = report.get("signature_verified", False)
            guardrails[report_id]["identity_verified"] = report.get("identity_verified", False)
            guardrails[report_id]["materialization_dry_run_passed"] = report.get("materialization_dry_run_passed", False)
            guardrails[report_id]["approval_file_written"] = report.get("approval_file_written", True)
            guardrails[report_id]["approval_valid"] = report.get("approval_valid", True)
            guardrails[report_id]["approval_file_present_after"] = report.get("approval_file_present_after", True)
            guardrails[report_id]["remote_cleanup_absent"] = report.get("remote_cleanup_absent", False)
            guardrails[report_id]["provider_dispatch"] = report.get("provider_dispatch", True)
        if report_id == "mac_ubuntu_remote_approval_revocation_rollback":
            guardrails[report_id]["remote_git_synced"] = report.get("remote_git_synced", False)
            guardrails[report_id]["signed_bundle_verified"] = report.get("signed_bundle_verified", False)
            guardrails[report_id]["signature_verified"] = report.get("signature_verified", False)
            guardrails[report_id]["identity_verified"] = report.get("identity_verified", False)
            guardrails[report_id]["fixture_approval_written"] = report.get("fixture_approval_written", False)
            guardrails[report_id]["revocation_applied"] = report.get("revocation_applied", False)
            guardrails[report_id]["approval_file_present_after_revocation"] = report.get("approval_file_present_after_revocation", True)
            guardrails[report_id]["rollback_restore_verified"] = report.get("rollback_restore_verified", False)
            guardrails[report_id]["approval_file_restored_after"] = report.get("approval_file_restored_after", False)
            guardrails[report_id]["revocation_log_sanitized"] = report.get("revocation_log_sanitized", False)
            guardrails[report_id]["remote_cleanup_absent"] = report.get("remote_cleanup_absent", False)
            guardrails[report_id]["provider_dispatch"] = report.get("provider_dispatch", True)

    ship_ready = guardrails.get("release_readiness", {}).get("ship_ready") is True
    approval_state = str(guardrails.get("approval_lifecycle", {}).get("approval_state") or "UNKNOWN")
    approval_usable = guardrails.get("approval_lifecycle", {}).get("approval_usable") is True
    launcher_guardrail = guardrails.get("approved_launch_proof", {})
    positive_approval_path = (
        "PLAN_WITHOUT_DISPATCH"
        if launcher_guardrail.get("launcher_verdict") == "PLAN"
        and launcher_guardrail.get("launcher_would_run_provider") is False
        else "UNPROVEN"
    )
    return {
        "schema": "ao-operator/operator-guardrail-summary/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "ship_ready": ship_ready,
        "approval_state": approval_state,
        "approval_usable": approval_usable,
        "positive_approval_path": positive_approval_path,
        "guardrails": guardrails,
        "blockers": blockers,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "All operator guardrails pass; keep Agent OS execution blocked without explicit approval."
            if not errors
            else "Fix failing operator guardrails before starting the next execution lane."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize operator cockpit and guardrail reports")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
