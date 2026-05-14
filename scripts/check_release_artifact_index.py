#!/usr/bin/env python3
"""Build a release artifact index for the latest SDD guardrail lanes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/release-artifact-index.json"

SDD_PATHS = {
    "remote_transfer_hardening": "docs/sdd/62-remote-transfer-hardening-evidence-gate.md",
    "public_release_security_and_dast": "docs/sdd/37-public-release-security-and-dast.md",
    "security_sdlc_roadmap": "docs/sdd/38-security-sdlc-roadmap.md",
    "security_threat_model": "docs/sdd/39-security-threat-model-data-flow.md",
    "manual_pentest_gate": "docs/sdd/40-manual-penetration-test-gate.md",
    "host_key_evidence": "docs/sdd/41-host-key-evidence-gate.md",
    "manual_pentest_report_classifier": "docs/sdd/42-manual-pentest-report-classifier.md",
    "supply_chain_gate": "docs/sdd/43-supply-chain-audit-gate.md",
    "resource_performance": "docs/sdd/63-resource-performance-guardrails.md",
    "approval_bundle": "docs/sdd/64-agent-os-execution-approval-bundle.md",
    "operator_guardrail_summary": "docs/sdd/65-operator-guardrail-summary.md",
    "approval_materialization": "docs/sdd/66-agent-os-approval-materialization.md",
    "release_artifact_index": "docs/sdd/67-release-artifact-index.md",
    "approval_lifecycle": "docs/sdd/68-agent-os-approval-lifecycle.md",
    "approved_launch_proof": "docs/sdd/69-agent-os-approved-launch-proof.md",
    "approval_cleanup": "docs/sdd/70-agent-os-approval-cleanup.md",
    "approval_audit_history": "docs/sdd/71-agent-os-approval-audit-history.md",
    "post_approval_cleanup_route": "docs/sdd/72-agent-os-post-approval-cleanup-route.md",
    "approval_runbook": "docs/sdd/73-agent-os-approval-materialization-runbook.md",
    "approval_audit_retention": "docs/sdd/74-agent-os-approval-audit-retention.md",
    "approval_bundle_signature": "docs/sdd/75-agent-os-approval-bundle-signature.md",
    "approval_revocation": "docs/sdd/76-agent-os-approval-revocation.md",
    "approval_identity_signature": "docs/sdd/77-agent-os-approval-identity-signature.md",
    "approval_revocation_apply_proof": "docs/sdd/78-agent-os-approval-revocation-apply-proof.md",
    "approval_audit_archive_restore": "docs/sdd/79-agent-os-approval-audit-archive-restore.md",
    "mac_ubuntu_approval_artifact_parity": "docs/sdd/80-mac-ubuntu-approval-artifact-parity.md",
    "mac_ubuntu_signed_approval_bundle_transfer": "docs/sdd/81-mac-ubuntu-signed-approval-bundle-transfer.md",
    "mac_ubuntu_remote_approval_materialization_dry_run": "docs/sdd/82-mac-ubuntu-remote-approval-materialization-dry-run.md",
    "mac_ubuntu_remote_approval_revocation_rollback": "docs/sdd/83-mac-ubuntu-remote-approval-revocation-rollback.md",
    "mac_ubuntu_remote_approval_runbook": "docs/sdd/84-mac-ubuntu-remote-approval-runbook.md",
    "mac_ubuntu_remote_approved_fixture": "docs/sdd/85-mac-ubuntu-remote-approved-fixture.md",
    "agent_os_architecture_implementation_gate": "docs/sdd/86-agent-os-architecture-implementation-gate.md",
    "agent_os_router_transition_matrix": "docs/sdd/87-agent-os-router-transition-matrix.md",
    "agent_os_runspec_failure_injection_matrix": "docs/sdd/88-agent-os-runspec-failure-injection-matrix.md",
    "operator_safe_next_command": "docs/sdd/89-operator-safe-next-command.md",
    "agent_os_runspec_dag_edge_coverage": "docs/sdd/90-agent-os-runspec-dag-edge-coverage.md",
    "agent_os_runspec_yaml_dag_parity": "docs/sdd/91-agent-os-runspec-yaml-dag-parity.md",
    "agent_os_runspec_yaml_semantic_parity": "docs/sdd/92-agent-os-runspec-yaml-semantic-parity.md",
    "agent_os_runspec_yaml_schema_injection": "docs/sdd/93-agent-os-runspec-yaml-schema-injection.md",
    "agent_os_runspec_ao_preflight_compatibility": "docs/sdd/94-agent-os-runspec-ao-preflight-compatibility.md",
    "agent_os_router_default_state_version": "docs/sdd/95-agent-os-router-default-state-version.md",
    "agent_os_role_graph_backward_compat": "docs/sdd/96-agent-os-role-graph-backward-compat.md",
    "remote_transfer_chunk_cleanup_invariants": "docs/sdd/97-remote-transfer-chunk-cleanup-invariants.md",
    "remote_transfer_signed_bundle_tamper": "docs/sdd/98-remote-transfer-signed-bundle-tamper.md",
    "remote_transfer_approval_expiry_rotation": "docs/sdd/99-remote-transfer-approval-expiry-rotation.md",
    "remote_transfer_bundle_ordering_resume": "docs/sdd/100-remote-transfer-bundle-ordering-resume.md",
    "remote_transfer_provider_redaction_round_trip": "docs/sdd/101-remote-transfer-provider-redaction-round-trip.md",
    "remote_transfer_network_retry_idempotency": "docs/sdd/102-remote-transfer-network-retry-idempotency.md",
    "remote_transfer_concurrent_transfer_collision": "docs/sdd/103-remote-transfer-concurrent-transfer-collision.md",
    "remote_transfer_bundle_schema_version_skew": "docs/sdd/104-remote-transfer-bundle-schema-version-skew.md",
    "remote_transfer_resource_exhaustion_guard": "docs/sdd/105-remote-transfer-resource-exhaustion-guard.md",
    "remote_transfer_clock_skew_tolerance": "docs/sdd/106-remote-transfer-clock-skew-tolerance.md",
    "remote_transfer_bundle_id_uniqueness": "docs/sdd/107-remote-transfer-bundle-id-uniqueness.md",
    "remote_transfer_bundle_content_type_allowlist": "docs/sdd/108-remote-transfer-bundle-content-type-allowlist.md",
    "remote_transfer_per_tenant_quota_isolation": "docs/sdd/109-remote-transfer-per-tenant-quota-isolation.md",
    "remote_transfer_wire_encryption_required": "docs/sdd/110-remote-transfer-wire-encryption-required.md",
    "remote_transfer_sender_identity_rotation": "docs/sdd/111-remote-transfer-sender-identity-rotation.md",
    "ai_agent_blast_radius_inventory": "docs/sdd/112-ai-agent-blast-radius-inventory.md",
    "ai_agent_destructive_action_approval": "docs/sdd/113-ai-agent-destructive-action-approval.md",
    "ai_agent_credential_reachability": "docs/sdd/114-ai-agent-credential-reachability.md",
    "ai_agent_instruction_packaging_leak_detection": "docs/sdd/115-ai-agent-instruction-packaging-leak-detection.md",
    "mcp_tool_poisoning_detection": "docs/sdd/116-mcp-tool-poisoning-detection.md",
    "deepsec_diff_review_advisory_sast": "docs/sdd/117-deepsec-diff-review-advisory-sast.md",
    "agent_supply_chain_integrity": "docs/sdd/118-agent-supply-chain-integrity.md",
    "prompt_injection_escape_boundary": "docs/sdd/119-prompt-injection-escape-boundary.md",
    "approval_clock_skew_defense": "docs/sdd/120-approval-clock-skew-defense.md",
    "agent_log_redaction_round_trip": "docs/sdd/121-agent-log-redaction-round-trip.md",
    "per_tenant_blast_radius_cap": "docs/sdd/122-per-tenant-blast-radius-cap.md",
    "sandbox_egress_allowlist": "docs/sdd/123-sandbox-egress-allowlist.md",
    "agent_tool_arg_injection_escape": "docs/sdd/124-agent-tool-arg-injection-escape.md",
    "agent_output_canary_leak_detection": "docs/sdd/125-agent-output-canary-leak-detection.md",
    "agent_os_execution_budget_enforcement": "docs/sdd/126-agent-os-execution-budget-enforcement.md",
    "agent_system_prompt_tamper_detection": "docs/sdd/127-agent-system-prompt-tamper-detection.md",
    "tool_result_cache_poisoning_defense": "docs/sdd/128-tool-result-cache-poisoning-defense.md",
    "agent_credential_scope_narrowing": "docs/sdd/129-agent-credential-scope-narrowing.md",
    "evidence_pack_v1": "docs/sdd/131-evidence-pack-v1.md",
}

ARTIFACTS = {
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
    "operator_guardrail_summary": {
        "path": f"{STATUS_ROOT}/operator-guardrail-summary.json",
        "schema": "ao-operator/operator-guardrail-summary/v1",
    },
    "approval_materialization": {
        "path": f"{STATUS_ROOT}/agent-os-approval-materialization.json",
        "schema": "ao-operator/agent-os-approval-materialization/v1",
    },
    "approval_lifecycle": {
        "path": f"{STATUS_ROOT}/agent-os-approval-lifecycle.json",
        "schema": "ao-operator/agent-os-approval-lifecycle/v1",
    },
    "approved_launch_proof": {
        "path": f"{STATUS_ROOT}/agent-os-approved-launch-proof.json",
        "schema": "ao-operator/agent-os-approved-launch-proof/v1",
    },
    "approval_cleanup": {
        "path": f"{STATUS_ROOT}/agent-os-approval-cleanup.json",
        "schema": "ao-operator/agent-os-approval-cleanup/v1",
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
    "operator_safe_next_command": {
        "path": f"{STATUS_ROOT}/operator-safe-next-command.json",
        "schema": "ao-operator/operator-safe-next-command/v1",
    },
    "live_evidence_pack_replay": {
        "path": f"{STATUS_ROOT}/live-evidence-pack-replay-gate.json",
        "schema": "ao-operator/live-evidence-pack-replay-gate/v1",
    },
    "provider_oauth_smoke": {
        "path": "run-artifacts/release-v0.7/provider-smoke/provider-oauth-smoke.json",
        "schema": "ao-operator/provider-oauth-smoke/v1",
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


def artifact_errors(artifact_id: str, payload: dict[str, Any], expected_schema: str) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != expected_schema:
        errors.append(f"{artifact_id} schema must be {expected_schema}")
    if payload.get("verdict") != "PASS":
        errors.append(f"{artifact_id} verdict must be PASS")
    if payload.get("dispatch_authorized") is not False:
        errors.append(f"{artifact_id} dispatch_authorized must remain false")
    if payload.get("live_providers_run") is not False:
        errors.append(f"{artifact_id} live_providers_run must remain false")
    if artifact_id == "public_release_security":
        if int(payload.get("blocking_findings") or 0) != 0:
            errors.append("public_release_security blocking_findings must be 0")
    if artifact_id == "dast_readiness":
        if payload.get("remote_dast_enabled") is not False:
            errors.append("dast_readiness remote_dast_enabled must remain false")
    if artifact_id == "manual_pentest_gate":
        if payload.get("manual_pentest_authorized") is not False:
            errors.append("manual_pentest_gate manual_pentest_authorized must remain false")
    if artifact_id == "host_key_evidence":
        if payload.get("host_key_evidence_required") is not True:
            errors.append("host_key_evidence host_key_evidence_required must be true")
        if payload.get("remote_dast_authorized") is not False:
            errors.append("host_key_evidence remote_dast_authorized must remain false")
    if artifact_id == "manual_pentest_report_classifier":
        if payload.get("report_template_ready") is not True:
            errors.append("manual_pentest_report_classifier report_template_ready must be true")
        if payload.get("manual_pentest_authorized") is not False:
            errors.append("manual_pentest_report_classifier manual_pentest_authorized must remain false")
    if artifact_id == "agent_os_runspec_dag_edge_coverage":
        if int(payload.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_dag_edge_coverage task_count must be 7")
        if int(payload.get("edge_count") or 0) != 6:
            errors.append("agent_os_runspec_dag_edge_coverage edge_count must be 6")
        if payload.get("role_graph_alignment") is not True:
            errors.append("agent_os_runspec_dag_edge_coverage role_graph_alignment must be true")
        if int(payload.get("mutation_case_count") or 0) != 5:
            errors.append("agent_os_runspec_dag_edge_coverage mutation_case_count must be 5")
    if artifact_id == "agent_os_runspec_yaml_dag_parity":
        if int(payload.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_dag_parity task_count must be 7")
        if int(payload.get("yaml_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_edge_count must be 6")
        if int(payload.get("renderer_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity renderer_edge_count must be 6")
        if int(payload.get("role_graph_edge_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_dag_parity role_graph_edge_count must be 6")
        if payload.get("yaml_renderer_alignment") is not True:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_renderer_alignment must be true")
        if payload.get("yaml_role_graph_alignment") is not True:
            errors.append("agent_os_runspec_yaml_dag_parity yaml_role_graph_alignment must be true")
        if int(payload.get("mutation_case_count") or 0) != 4:
            errors.append("agent_os_runspec_yaml_dag_parity mutation_case_count must be 4")
    if artifact_id == "agent_os_runspec_yaml_semantic_parity":
        if int(payload.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity task_count must be 7")
        if int(payload.get("renderer_task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity renderer_task_count must be 7")
        if int(payload.get("aligned_task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_semantic_parity aligned_task_count must be 7")
        if int(payload.get("drifted_task_count") or 0) != 0:
            errors.append("agent_os_runspec_yaml_semantic_parity drifted_task_count must be 0")
        if payload.get("all_aligned") is not True:
            errors.append("agent_os_runspec_yaml_semantic_parity all_aligned must be true")
        if int(payload.get("mutation_case_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_semantic_parity mutation_case_count must be 6")
    if artifact_id == "agent_os_runspec_yaml_schema_injection":
        if int(payload.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_yaml_schema_injection task_count must be 7")
        if int(payload.get("mutation_case_count") or 0) != 6:
            errors.append("agent_os_runspec_yaml_schema_injection mutation_case_count must be 6")
        baseline_errors = payload.get("baseline_errors")
        if not isinstance(baseline_errors, list) or baseline_errors:
            errors.append("agent_os_runspec_yaml_schema_injection baseline_errors must be empty")
        cases = payload.get("mutation_cases")
        if not isinstance(cases, list) or len(cases) != 6:
            errors.append("agent_os_runspec_yaml_schema_injection mutation_cases must list six cases")
        else:
            for case in cases:
                if not isinstance(case, dict):
                    errors.append("agent_os_runspec_yaml_schema_injection mutation_cases entries must be objects")
                    continue
                if case.get("observed_verdict") != "FAIL":
                    errors.append(
                        f"agent_os_runspec_yaml_schema_injection {case.get('id')} must observe FAIL"
                    )
    if artifact_id == "agent_os_runspec_ao_preflight_compatibility":
        if int(payload.get("task_count") or 0) != 7:
            errors.append("agent_os_runspec_ao_preflight_compatibility task_count must be 7")
        if int(payload.get("mutation_case_count") or 0) != 5:
            errors.append("agent_os_runspec_ao_preflight_compatibility mutation_case_count must be 5")
        baseline_errors = payload.get("baseline_errors")
        if not isinstance(baseline_errors, list) or baseline_errors:
            errors.append("agent_os_runspec_ao_preflight_compatibility baseline_errors must be empty")
        cases = payload.get("mutation_cases")
        if not isinstance(cases, list) or len(cases) != 5:
            errors.append("agent_os_runspec_ao_preflight_compatibility mutation_cases must list five cases")
        else:
            for case in cases:
                if not isinstance(case, dict):
                    errors.append("agent_os_runspec_ao_preflight_compatibility mutation_cases entries must be objects")
                    continue
                if case.get("observed_verdict") != "FAIL":
                    errors.append(
                        f"agent_os_runspec_ao_preflight_compatibility {case.get('id')} must observe FAIL"
                    )
        contract = payload.get("ao_contract")
        if not isinstance(contract, dict):
            errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract must be an object")
        else:
            if contract.get("api_versions") != ["ao.dev/v1"]:
                errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract.api_versions must be ['ao.dev/v1']")
            if contract.get("runspec_kinds") != ["Run"]:
                errors.append("agent_os_runspec_ao_preflight_compatibility ao_contract.runspec_kinds must be ['Run']")
            if contract.get("task_kinds") != ["shell", "agent", "review", "test"]:
                errors.append(
                    "agent_os_runspec_ao_preflight_compatibility ao_contract.task_kinds must be ['shell', 'agent', 'review', 'test']"
                )
    if artifact_id == "live_evidence_pack_replay":
        summaries = payload.get("summaries")
        if not isinstance(summaries, list):
            errors.append("live_evidence_pack_replay summaries must be a list")
        else:
            evidence_profile_summary = [
                item
                for item in summaries
                if isinstance(item, dict)
                and "run-artifacts/evidence-profile-live-proof/evidence-packs/" in str(item.get("path", ""))
                and item.get("verify_verdict") == "PASS"
                and item.get("replay_verdict") == "PASS"
                and int(item.get("deterministic_task_count") or 0) > 0
                and item.get("deterministic_command_execution") == "PASS"
                and item.get("verdict") == "PASS"
            ]
            if not evidence_profile_summary:
                errors.append(
                    "live_evidence_pack_replay must include evidence-profile-live-proof deterministic replay summary"
                )
    return errors


def build_index(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    blockers: list[str] = []
    errors: list[str] = []
    sdd: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}

    for sdd_id, value in SDD_PATHS.items():
        path = resolve_path(root, value)
        exists = path.is_file()
        if not exists:
            blockers.append(sdd_id)
            errors.append(f"{sdd_id} SDD file is missing")
        sdd[sdd_id] = {"path": relpath(root, path), "exists": exists}

    for artifact_id, config in ARTIFACTS.items():
        path = resolve_path(root, config["path"])
        payload = load_json(path)
        current_errors = artifact_errors(artifact_id, payload, config["schema"])
        if current_errors:
            blockers.append(artifact_id)
            errors.extend(current_errors)
        artifacts[artifact_id] = {
            "path": relpath(root, path),
            "schema": payload.get("schema", ""),
            "verdict": payload.get("verdict", "MISSING"),
            "dispatch_authorized": payload.get("dispatch_authorized"),
            "live_providers_run": payload.get("live_providers_run"),
        }
        if "approval_file_written" in payload:
            artifacts[artifact_id]["approval_file_written"] = payload["approval_file_written"]

    return {
        "schema": "ao-operator/release-artifact-index/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "sdd": sdd,
        "artifacts": artifacts,
        "sdd_count": len(sdd),
        "artifact_count": len(artifacts),
        "blockers": sorted(set(blockers)),
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Release artifact index is complete; continue with the next gated SDD lane."
            if not errors
            else "Fix missing or failing release artifacts before continuing."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build release artifact index")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_index(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
