from __future__ import annotations

import json
from pathlib import Path

import check_operator_guardrail_summary


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def seed_reports(root: Path) -> None:
    base = root / "run-artifacts/remote-transfer-v2-stress-live"
    write_json(
        base / "agent-os-operator-cockpit.json",
        {
            "schema": "ao-operator/agent-os-operator-cockpit/v1",
            "verdict": "PASS",
            "ship_ready": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "Execution is hash-locked and blocked until explicit approval is valid.",
        },
    )
    write_json(
        base / "remote-transfer-hardening.json",
        {
            "schema": "ao-operator/remote-transfer-hardening/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "public-release-security-surface.json",
        {
            "schema": "ao-operator/public-release-security/v1",
            "verdict": "PASS",
            "blocking_findings": 0,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "dast-readiness.json",
        {
            "schema": "ao-operator/dast-readiness/v1",
            "verdict": "PASS",
            "remote_dast_enabled": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "security-sdlc-roadmap.json",
        {
            "schema": "ao-operator/security-sdlc-roadmap/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "security-threat-model.json",
        {
            "schema": "ao-operator/security-threat-model/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "manual-pentest-gate.json",
        {
            "schema": "ao-operator/manual-pentest-gate/v1",
            "verdict": "PASS",
            "manual_pentest_authorized": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "host-key-evidence.json",
        {
            "schema": "ao-operator/host-key-evidence/v1",
            "verdict": "PASS",
            "host_key_evidence_required": True,
            "remote_dast_authorized": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "manual-pentest-report-classifier.json",
        {
            "schema": "ao-operator/manual-pentest-report-classifier/v1",
            "verdict": "PASS",
            "report_template_ready": True,
            "manual_pentest_authorized": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "supply-chain-gate.json",
        {
            "schema": "ao-operator/supply-chain-gate/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "resource-performance-gate.json",
        {
            "schema": "ao-operator/resource-performance-gate/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-execution-approval-bundle.json",
        {
            "schema": "ao-operator/agent-os-execution-approval-bundle/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "release-readiness-gate.json",
        {
            "schema": "ao-operator/release-readiness-gate/v1",
            "verdict": "PASS",
            "ship_ready": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-execution-rehearsal.json",
        {
            "schema": "ao-operator/agent-os-runspec-execution-rehearsal/v1",
            "verdict": "PASS",
            "refused_without_approval": True,
            "would_run_provider": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-lifecycle.json",
        {
            "schema": "ao-operator/agent-os-approval-lifecycle/v1",
            "verdict": "PASS",
            "approval_state": "ABSENT",
            "approval_usable": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
            "next_safe_command": "Keep Agent OS execution blocked until a fresh approval file is materialized.",
        },
    )
    write_json(
        base / "agent-os-approval-cleanup.json",
        {
            "schema": "ao-operator/agent-os-approval-cleanup/v1",
            "verdict": "PASS",
            "approval_state": "ABSENT",
            "removed": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approved-launch-proof.json",
        {
            "schema": "ao-operator/agent-os-approved-launch-proof/v1",
            "verdict": "PASS",
            "launcher_after_approval": {
                "verdict": "PLAN",
                "approval_state": "APPROVED_ACTIVE",
                "approval_usable": True,
                "would_run_provider": False,
            },
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-audit.json",
        {
            "schema": "ao-operator/agent-os-approval-audit-history/v1",
            "verdict": "PASS",
            "event_count": 1,
            "latest_event": "APPROVAL_CLEANUP_RECORDED",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-post-approval-cleanup-route.json",
        {
            "schema": "ao-operator/agent-os-post-approval-cleanup-route/v1",
            "verdict": "PASS",
            "postrun_route": {"route": "ACCEPTED"},
            "cleanup": {"removed": True},
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-runbook.json",
        {
            "schema": "ao-operator/agent-os-approval-runbook/v1",
            "verdict": "PASS",
            "required_item_count": 9,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-audit-retention.json",
        {
            "schema": "ao-operator/agent-os-approval-audit-retention/v1",
            "verdict": "PASS",
            "event_count": 1,
            "rotation_due": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-bundle-signature-report.json",
        {
            "schema": "ao-operator/agent-os-approval-bundle-signature/v1",
            "verdict": "PASS",
            "signature_matches": True,
            "identity_signature": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-revocation.json",
        {
            "schema": "ao-operator/agent-os-approval-revocation/v1",
            "verdict": "PASS",
            "revocation_applied": False,
            "approval_file_present_after": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-identity-signature.json",
        {
            "schema": "ao-operator/agent-os-approval-identity-signature/v1",
            "verdict": "PASS",
            "identity_signature": True,
            "signature_verified": True,
            "private_key_committed": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-revocation-apply-proof.json",
        {
            "schema": "ao-operator/agent-os-approval-revocation-apply-proof/v1",
            "verdict": "PASS",
            "materialization": {"approval_file_written": True},
            "revocation": {"revocation_applied": True, "approval_file_present_after": False},
            "revocation_log_sanitized": True,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-approval-audit-archive-restore.json",
        {
            "schema": "ao-operator/agent-os-approval-audit-archive-restore/v1",
            "verdict": "PASS",
            "archive_created": True,
            "restore_verified": True,
            "source_mutated": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-approval-artifact-parity.json",
        {
            "schema": "ao-operator/mac-ubuntu-approval-artifact-parity/v1",
            "verdict": "PASS",
            "artifact_parity": True,
            "remote_git_synced": True,
            "remote_checks_pass": True,
            "provider_dispatch": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-signed-approval-bundle-transfer.json",
        {
            "schema": "ao-operator/mac-ubuntu-signed-approval-bundle-transfer/v1",
            "verdict": "PASS",
            "artifact_parity": True,
            "remote_git_synced": True,
            "signature_verified": True,
            "identity_verified": True,
            "remote_cleanup_absent": True,
            "provider_dispatch": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-remote-approval-materialization-dry-run.json",
        {
            "schema": "ao-operator/mac-ubuntu-remote-approval-materialization-dry-run/v1",
            "verdict": "PASS",
            "remote_git_synced": True,
            "signed_bundle_verified": True,
            "signature_verified": True,
            "identity_verified": True,
            "materialization_dry_run_passed": True,
            "approval_file_written": False,
            "approval_valid": False,
            "approval_file_present_after": False,
            "remote_cleanup_absent": True,
            "provider_dispatch": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-remote-approval-revocation-rollback.json",
        {
            "schema": "ao-operator/mac-ubuntu-remote-approval-revocation-rollback/v1",
            "verdict": "PASS",
            "remote_git_synced": True,
            "signed_bundle_verified": True,
            "signature_verified": True,
            "identity_verified": True,
            "fixture_approval_written": True,
            "revocation_applied": True,
            "approval_file_present_after_revocation": False,
            "rollback_restore_verified": True,
            "approval_file_restored_after": True,
            "revocation_log_sanitized": True,
            "remote_cleanup_absent": True,
            "provider_dispatch": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-remote-approval-runbook.json",
        {
            "schema": "ao-operator/mac-ubuntu-remote-approval-runbook/v1",
            "verdict": "PASS",
            "required_item_count": 17,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mac-ubuntu-remote-approved-fixture.json",
        {
            "schema": "ao-operator/mac-ubuntu-remote-approved-fixture/v1",
            "verdict": "PASS",
            "remote_git_synced": True,
            "signed_bundle_verified": True,
            "signature_verified": True,
            "identity_verified": True,
            "fixture_approval_written": True,
            "approval_valid": True,
            "launcher_plan_verified": True,
            "would_run_provider": False,
            "approval_file_present_after": True,
            "remote_cleanup_absent": True,
            "provider_dispatch": False,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-architecture-implementation-gate.json",
        {
            "schema": "ao-operator/agent-os-architecture-implementation-gate/v1",
            "verdict": "PASS",
            "implementation_ready": True,
            "role_count": 7,
            "handoff_packet_count": 7,
            "runspec_task_count": 7,
            "checks": {"role_handoff_runspec_alignment": "PASS"},
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-router-transition-matrix.json",
        {
            "schema": "ao-operator/agent-os-router-transition-matrix/v1",
            "verdict": "PASS",
            "case_count": 9,
            "cases": [
                {"id": "live_provider_blocks_dispatch", "blocker_count": 1},
                {"id": "refactor_with_release_state_v2", "state_verdict": "PASS"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-failure-injection-matrix.json",
        {
            "schema": "ao-operator/agent-os-runspec-failure-injection-matrix/v1",
            "verdict": "PASS",
            "case_count": 7,
            "cases": [
                {"id": "baseline_validates", "observed_verdict": "PASS"},
                {"id": "stale_approval_hash_refused", "observed_verdict": "REFUSED"},
                {"id": "missing_prompt_refused", "observed_verdict": "FAIL"},
                {"id": "dispatch_flag_mutation_refused", "observed_verdict": "FAIL"},
                {"id": "bad_provider_profile_refused", "observed_verdict": "FAIL"},
                {"id": "invalid_provider_refused", "observed_verdict": "FAIL"},
                {"id": "missing_state_baseline_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-dag-edge-coverage.json",
        {
            "schema": "ao-operator/agent-os-runspec-dag-edge-coverage/v1",
            "verdict": "PASS",
            "task_count": 7,
            "edge_count": 6,
            "entry_task_ids": ["agent-os-planner"],
            "terminal_task_ids": ["agent-os-evaluator-closer"],
            "role_graph_alignment": True,
            "mutation_case_count": 5,
            "mutation_cases": [
                {"id": "cycle_refused", "observed_verdict": "FAIL"},
                {"id": "missing_role_edge_refused", "observed_verdict": "FAIL"},
                {"id": "unknown_dependency_refused", "observed_verdict": "FAIL"},
                {"id": "duplicate_entry_refused", "observed_verdict": "FAIL"},
                {"id": "terminal_fork_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-yaml-dag-parity.json",
        {
            "schema": "ao-operator/agent-os-runspec-yaml-dag-parity/v1",
            "verdict": "PASS",
            "task_count": 7,
            "yaml_edge_count": 6,
            "renderer_edge_count": 6,
            "role_graph_edge_count": 6,
            "entry_task_ids": ["agent-os-planner"],
            "terminal_task_ids": ["agent-os-evaluator-closer"],
            "yaml_renderer_alignment": True,
            "yaml_role_graph_alignment": True,
            "mutation_case_count": 4,
            "mutation_cases": [
                {"id": "yaml_cycle_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_renderer_edge_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_unknown_dependency_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_terminal_fork_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-yaml-semantic-parity.json",
        {
            "schema": "ao-operator/agent-os-runspec-yaml-semantic-parity/v1",
            "verdict": "PASS",
            "task_count": 7,
            "renderer_task_count": 7,
            "aligned_task_count": 7,
            "drifted_task_count": 0,
            "all_aligned": True,
            "fields_checked": [
                "provider",
                "promptFile",
                "workspace",
                "policyProfile",
                "kind",
                "dispatchAuthorized",
            ],
            "mutation_case_count": 6,
            "mutation_cases": [
                {"id": "yaml_provider_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_prompt_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_workspace_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_policy_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_kind_drift_refused", "observed_verdict": "FAIL"},
                {"id": "yaml_dispatch_authorized_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-yaml-schema-injection.json",
        {
            "schema": "ao-operator/agent-os-runspec-yaml-schema-injection/v1",
            "verdict": "PASS",
            "task_count": 7,
            "mutation_case_count": 6,
            "baseline_errors": [],
            "mutation_cases": [
                {"id": "malformed_yaml_refused", "observed_verdict": "FAIL"},
                {"id": "duplicate_task_ids_refused", "observed_verdict": "FAIL"},
                {"id": "missing_spec_block_refused", "observed_verdict": "FAIL"},
                {"id": "bad_deps_type_refused", "observed_verdict": "FAIL"},
                {"id": "unknown_task_field_refused", "observed_verdict": "FAIL"},
                {"id": "unsafe_dispatch_authorized_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-runspec-ao-preflight-compatibility.json",
        {
            "schema": "ao-operator/agent-os-runspec-ao-preflight-compatibility/v1",
            "verdict": "PASS",
            "task_count": 7,
            "mutation_case_count": 5,
            "baseline_errors": [],
            "ao_contract": {
                "api_versions": ["ao.dev/v1"],
                "runspec_kinds": ["Run"],
                "task_kinds": ["shell", "agent", "review", "test"],
            },
            "mutation_cases": [
                {"id": "wrong_api_version_refused", "observed_verdict": "FAIL"},
                {"id": "wrong_runspec_kind_refused", "observed_verdict": "FAIL"},
                {"id": "unknown_task_kind_refused", "observed_verdict": "FAIL"},
                {"id": "unknown_dependency_refused", "observed_verdict": "FAIL"},
                {"id": "dag_cycle_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-router-default-state-version.json",
        {
            "schema": "ao-operator/agent-os-router-default-state-version/v1",
            "verdict": "PASS",
            "argparse_default": "v2",
            "case_count": 3,
            "case_ids": [
                "default_emits_state_v2",
                "explicit_v1_remains_supported",
                "explicit_v2_matches_default",
            ],
            "cases": [
                {"id": "default_emits_state_v2", "observed_verdict": "PASS", "observed_schema": "ao-operator/agent-os-state/v2", "exit_code": 0, "dispatch_authorized": False, "live_providers_run": False},
                {"id": "explicit_v1_remains_supported", "observed_verdict": "PASS", "observed_schema": "ao-operator/agent-os-state/v1", "exit_code": 0, "dispatch_authorized": False, "live_providers_run": False},
                {"id": "explicit_v2_matches_default", "observed_verdict": "PASS", "observed_schema": "ao-operator/agent-os-state/v2", "exit_code": 0, "dispatch_authorized": False, "live_providers_run": False},
            ],
            "errors": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-role-graph-backward-compat.json",
        {
            "schema": "ao-operator/agent-os-role-graph-backward-compat/v1",
            "verdict": "PASS",
            "case_count": 6,
            "cases": [
                {"id": "legacy_v1_state_minimal_loadable", "observed_verdict": "PASS"},
                {"id": "legacy_v1_state_extra_unknown_fields_tolerated", "observed_verdict": "PASS"},
                {"id": "legacy_v1_state_no_role_graph_schema_injects_default", "observed_verdict": "PASS"},
                {"id": "legacy_v2_state_round_trip_preserves_previous_schema", "observed_verdict": "PASS"},
                {"id": "legacy_v1_role_graph_artifact_remains_loadable", "observed_verdict": "PASS"},
                {"id": "unknown_state_schema_refused", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-chunk-cleanup-invariants.json",
        {
            "schema": "ao-operator/remote-transfer-chunk-cleanup-invariants/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_upload_commit_passes", "observed_verdict": "PASS"},
                {"id": "orphaned_chunk_after_abort_detected", "observed_verdict": "FAIL"},
                {"id": "missing_finalize_detected", "observed_verdict": "FAIL"},
                {"id": "stale_partial_stage_dir_detected", "observed_verdict": "FAIL"},
                {"id": "double_commit_rejected", "observed_verdict": "FAIL"},
                {"id": "retry_index_drift_detected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-signed-bundle-tamper.json",
        {
            "schema": "ao-operator/remote-transfer-signed-bundle-tamper/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_signed_bundle_passes", "observed_verdict": "PASS"},
                {"id": "truncated_bundle_rejected", "observed_verdict": "FAIL"},
                {"id": "swapped_chunk_rejected", "observed_verdict": "FAIL"},
                {"id": "wrong_signing_key_rejected", "observed_verdict": "FAIL"},
                {"id": "replayed_bundle_rejected", "observed_verdict": "FAIL"},
                {"id": "manifest_digest_mismatch_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-approval-expiry-rotation.json",
        {
            "schema": "ao-operator/remote-transfer-approval-expiry-rotation/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_approval_passes", "observed_verdict": "PASS"},
                {"id": "expired_approval_rejected", "observed_verdict": "FAIL"},
                {"id": "approval_used_after_rotation_cutover_rejected", "observed_verdict": "FAIL"},
                {"id": "signing_key_rotated_midflight_without_grace_rejected", "observed_verdict": "FAIL"},
                {"id": "approval_reused_beyond_ttl_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-bundle-ordering-resume.json",
        {
            "schema": "ao-operator/remote-transfer-bundle-ordering-resume/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_ordered_delivery_passes", "observed_verdict": "PASS"},
                {"id": "out_of_order_chunk_rejected", "observed_verdict": "FAIL"},
                {"id": "partial_resume_drops_middle_chunk_rejected", "observed_verdict": "FAIL"},
                {"id": "resume_cursor_lies_about_high_water_rejected", "observed_verdict": "FAIL"},
                {"id": "duplicate_chunk_delivery_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-provider-redaction-round-trip.json",
        {
            "schema": "ao-operator/remote-transfer-provider-redaction-round-trip/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_round_trip_passes", "observed_verdict": "PASS"},
                {"id": "redaction_marker_stripped_before_transmit_rejected", "observed_verdict": "FAIL"},
                {"id": "sensitive_field_leaks_past_redaction_filter_rejected", "observed_verdict": "FAIL"},
                {"id": "double_redaction_corrupts_payload_rejected", "observed_verdict": "FAIL"},
                {"id": "provider_response_leaks_redacted_value_back_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-network-retry-idempotency.json",
        {
            "schema": "ao-operator/remote-transfer-network-retry-idempotency/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_retry_round_trip_passes", "observed_verdict": "PASS"},
                {"id": "retry_without_nonce_dedup_rejected", "observed_verdict": "FAIL"},
                {"id": "partial_flush_on_network_drop_rejected", "observed_verdict": "FAIL"},
                {"id": "ack_lost_causes_double_commit_rejected", "observed_verdict": "FAIL"},
                {"id": "timeout_shorter_than_response_causes_orphan_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-concurrent-transfer-collision.json",
        {
            "schema": "ao-operator/remote-transfer-concurrent-transfer-collision/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_serialized_concurrent_transfers_passes", "observed_verdict": "PASS"},
                {"id": "parallel_transfers_no_lock_corrupts_state_rejected", "observed_verdict": "FAIL"},
                {"id": "simultaneous_finalize_double_completes_bundle_rejected", "observed_verdict": "FAIL"},
                {"id": "lost_writer_overwrites_winner_bundle_rejected", "observed_verdict": "FAIL"},
                {"id": "stale_lock_holder_resumes_after_handoff_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-bundle-schema-version-skew.json",
        {
            "schema": "ao-operator/remote-transfer-bundle-schema-version-skew/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_matched_schema_version_passes", "observed_verdict": "PASS"},
                {"id": "receiver_below_min_version_rejected", "observed_verdict": "FAIL"},
                {"id": "receiver_above_max_silently_downgrades_rejected", "observed_verdict": "FAIL"},
                {"id": "bundle_advertises_unknown_extension_field_rejected", "observed_verdict": "FAIL"},
                {"id": "schema_version_field_missing_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-resource-exhaustion-guard.json",
        {
            "schema": "ao-operator/remote-transfer-resource-exhaustion-guard/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_within_quota_passes", "observed_verdict": "PASS"},
                {"id": "announced_chunk_count_exceeds_quota_rejected", "observed_verdict": "FAIL"},
                {"id": "announced_total_size_exceeds_quota_rejected", "observed_verdict": "FAIL"},
                {"id": "per_chunk_size_exceeds_max_rejected", "observed_verdict": "FAIL"},
                {"id": "transfer_exceeds_announced_count_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-clock-skew-tolerance.json",
        {
            "schema": "ao-operator/remote-transfer-clock-skew-tolerance/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_within_skew_tolerance_passes", "observed_verdict": "PASS"},
                {"id": "sender_clock_ahead_of_receiver_rejected", "observed_verdict": "FAIL"},
                {"id": "sender_clock_behind_receiver_rejected", "observed_verdict": "FAIL"},
                {"id": "future_dated_bundle_accepted_as_currently_valid_rejected", "observed_verdict": "FAIL"},
                {"id": "ttl_window_straddling_skew_silently_extended_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-bundle-id-uniqueness.json",
        {
            "schema": "ao-operator/remote-transfer-bundle-id-uniqueness/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_unique_bundle_ids_pass", "observed_verdict": "PASS"},
                {"id": "duplicate_bundle_id_within_session_rejected", "observed_verdict": "FAIL"},
                {"id": "cross_sender_bundle_id_collision_rejected", "observed_verdict": "FAIL"},
                {"id": "bundle_id_truncation_collision_rejected", "observed_verdict": "FAIL"},
                {"id": "bundle_id_replayed_after_completion_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-bundle-content-type-allowlist.json",
        {
            "schema": "ao-operator/remote-transfer-bundle-content-type-allowlist/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_allowlisted_content_type_passes", "observed_verdict": "PASS"},
                {"id": "unknown_content_type_silently_coerced_rejected", "observed_verdict": "FAIL"},
                {"id": "mismatched_extension_to_content_type_rejected", "observed_verdict": "FAIL"},
                {"id": "unknown_content_encoding_silently_decoded_rejected", "observed_verdict": "FAIL"},
                {"id": "content_type_charset_parameter_smuggled_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-per-tenant-quota-isolation.json",
        {
            "schema": "ao-operator/remote-transfer-per-tenant-quota-isolation/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_per_tenant_within_quota_passes", "observed_verdict": "PASS"},
                {"id": "tenant_a_overflows_tenant_b_quota_slot_rejected", "observed_verdict": "FAIL"},
                {"id": "aggregated_quota_across_tenants_merged_rejected", "observed_verdict": "FAIL"},
                {"id": "tenant_identity_stripped_silently_coerced_to_default_rejected", "observed_verdict": "FAIL"},
                {"id": "quota_refund_on_abort_double_credited_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-wire-encryption-required.json",
        {
            "schema": "ao-operator/remote-transfer-wire-encryption-required/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_encrypted_bundle_accepted", "observed_verdict": "PASS"},
                {"id": "cleartext_bundle_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "downgraded_tls_cipher_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "weak_null_cipher_suite_negotiated_rejected", "observed_verdict": "FAIL"},
                {"id": "encryption_header_stripped_after_handshake_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "remote-transfer-sender-identity-rotation.json",
        {
            "schema": "ao-operator/remote-transfer-sender-identity-rotation/v1",
            "verdict": "PASS",
            "case_count": 5,
            "mutation_case_count": 4,
            "cases": [
                {"id": "clean_post_rotation_bundle_accepted", "observed_verdict": "PASS"},
                {"id": "retired_identity_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "rotation_announcement_unsigned_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "future_rotation_effective_at_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "dual_acceptance_window_silently_left_open_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "ai-agent-blast-radius-inventory.json",
        {
            "schema": "ao-operator/ai-agent-blast-radius-inventory/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_inventory_classified_and_gated", "observed_verdict": "PASS"},
                {"id": "unclassified_high_blast_radius_command_path_rejected", "observed_verdict": "FAIL"},
                {"id": "destructive_action_without_approval_gate_rejected", "observed_verdict": "FAIL"},
                {"id": "credential_path_reachable_from_untrusted_content_rejected", "observed_verdict": "FAIL"},
                {"id": "provider_dispatch_without_approval_readiness_rejected", "observed_verdict": "FAIL"},
                {"id": "release_artifact_includes_instruction_or_credentials_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "ai-agent-destructive-action-approval.json",
        {
            "schema": "ao-operator/ai-agent-destructive-action-approval/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_destructive_action_with_fresh_scoped_approval_executes", "observed_verdict": "PASS"},
                {"id": "stale_approval_reused_after_expiry_rejected", "observed_verdict": "FAIL"},
                {"id": "approval_scope_widened_at_exec_silently_accepted_rejected", "observed_verdict": "FAIL"},
                {"id": "approval_consumed_twice_for_distinct_destructive_ops_rejected", "observed_verdict": "FAIL"},
                {"id": "destructive_op_runs_with_policy_only_without_token_rejected", "observed_verdict": "FAIL"},
                {"id": "parent_process_approval_inherited_by_child_without_reconfirm_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "ai-agent-credential-reachability.json",
        {
            "schema": "ao-operator/ai-agent-credential-reachability/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_untrusted_to_credential_reachable_path", "observed_verdict": "PASS"},
                {"id": "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected", "observed_verdict": "FAIL"},
                {"id": "agent_tool_output_piped_to_shell_with_ssh_dir_rejected", "observed_verdict": "FAIL"},
                {"id": "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected", "observed_verdict": "FAIL"},
                {"id": "web_fetch_reflected_into_shell_resolving_env_rejected", "observed_verdict": "FAIL"},
                {"id": "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "ai-agent-instruction-packaging-leak-detection.json",
        {
            "schema": "ao-operator/ai-agent-instruction-packaging-leak-detection/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_instruction_or_packaging_leaks_in_public_artifacts", "observed_verdict": "PASS"},
                {"id": "claude_md_directives_leaked_into_status_report_rejected", "observed_verdict": "FAIL"},
                {"id": "agent_memory_snippet_copy_pasted_into_public_doc_rejected", "observed_verdict": "FAIL"},
                {"id": "raw_user_prompt_logged_in_operator_slice_evidence_rejected", "observed_verdict": "FAIL"},
                {"id": "anthropic_api_key_surfaced_in_evaluation_transcript_rejected", "observed_verdict": "FAIL"},
                {"id": "tmp_diagnostic_path_included_in_public_artifact_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "mcp-tool-poisoning-detection.json",
        {
            "schema": "ao-operator/mcp-tool-poisoning-detection/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_mcp_or_tool_poisoning_indicators", "observed_verdict": "PASS"},
                {"id": "hidden_imperative_in_mcp_description_rejected", "observed_verdict": "FAIL"},
                {"id": "tool_result_schema_adds_destructive_default_arg_rejected", "observed_verdict": "FAIL"},
                {"id": "mcp_returns_url_to_fetch_and_apply_rejected", "observed_verdict": "FAIL"},
                {"id": "tool_name_shadowing_overrides_native_tool_rejected", "observed_verdict": "FAIL"},
                {"id": "signed_descriptor_advertises_unallowed_privilege_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "deepsec-diff-review-advisory-sast.json",
        {
            "schema": "ao-operator/deepsec-diff-review-advisory-sast/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_untrusted_to_dangerous_sink_edges", "observed_verdict": "PASS"},
                {"id": "untrusted_input_flows_into_shell_command_rejected", "observed_verdict": "FAIL"},
                {"id": "untrusted_input_flows_into_fs_write_outside_workspace_rejected", "observed_verdict": "FAIL"},
                {"id": "untrusted_input_flows_into_network_egress_rejected", "observed_verdict": "FAIL"},
                {"id": "eval_or_exec_on_retrieved_content_rejected", "observed_verdict": "FAIL"},
                {"id": "dynamic_import_from_agent_controlled_path_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-supply-chain-integrity.json",
        {
            "schema": "ao-operator/agent-supply-chain-integrity/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_unauthorized_provenance_or_unsigned_package_edges", "observed_verdict": "PASS"},
                {"id": "unsigned_package_admitted_without_signature_rejected", "observed_verdict": "FAIL"},
                {"id": "lock_file_digest_mismatch_admitted_rejected", "observed_verdict": "FAIL"},
                {"id": "dependency_confusion_via_shadow_registry_rejected", "observed_verdict": "FAIL"},
                {"id": "post_install_script_with_network_egress_rejected", "observed_verdict": "FAIL"},
                {"id": "transitive_yank_without_repin_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "prompt-injection-escape-boundary.json",
        {
            "schema": "ao-operator/prompt-injection-escape-boundary/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended", "observed_verdict": "PASS"},
                {"id": "attacker_role_spoofing_appended_after_user_content_rejected", "observed_verdict": "FAIL"},
                {"id": "fenced_block_escape_breaking_system_boundary_rejected", "observed_verdict": "FAIL"},
                {"id": "json_injection_replacing_operator_instructions_rejected", "observed_verdict": "FAIL"},
                {"id": "tool_name_shadowing_via_attacker_section_rejected", "observed_verdict": "FAIL"},
                {"id": "instruction_smuggling_via_unicode_homoglyph_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "approval-clock-skew-defense.json",
        {
            "schema": "ao-operator/approval-clock-skew-defense/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_clock_skew_or_replay_or_stale_freshness_edges", "observed_verdict": "PASS"},
                {"id": "ntp_rewind_admits_expired_approval_rejected", "observed_verdict": "FAIL"},
                {"id": "leap_second_jump_admits_expired_approval_rejected", "observed_verdict": "FAIL"},
                {"id": "tz_tagged_as_utc_admits_expired_approval_rejected", "observed_verdict": "FAIL"},
                {"id": "expired_but_cached_admits_replay_rejected", "observed_verdict": "FAIL"},
                {"id": "signed_token_replay_admits_reactivation_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-log-redaction-round-trip.json",
        {
            "schema": "ao-operator/agent-log-redaction-round-trip/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output", "observed_verdict": "PASS"},
                {"id": "partial_pattern_match_leaves_original_substring_rejected", "observed_verdict": "FAIL"},
                {"id": "base64_encoded_secret_unredacted_in_round_trip_rejected", "observed_verdict": "FAIL"},
                {"id": "path_normalization_alias_unredacted_in_round_trip_rejected", "observed_verdict": "FAIL"},
                {"id": "case_insensitive_token_unredacted_in_round_trip_rejected", "observed_verdict": "FAIL"},
                {"id": "json_string_escape_token_unredacted_in_round_trip_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "per-tenant-blast-radius-cap.json",
        {
            "schema": "ao-operator/per-tenant-blast-radius-cap/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges", "observed_verdict": "PASS"},
                {"id": "cross_tenant_fanout_to_unrelated_tenant_resource_rejected", "observed_verdict": "FAIL"},
                {"id": "missing_tenant_tag_admits_global_blast_radius_rejected", "observed_verdict": "FAIL"},
                {"id": "tenant_tag_spoof_admits_other_tenant_resource_rejected", "observed_verdict": "FAIL"},
                {"id": "allowlist_bypass_admits_unallowlisted_target_rejected", "observed_verdict": "FAIL"},
                {"id": "quota_overflow_leak_admits_post_window_action_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "sandbox-egress-allowlist.json",
        {
            "schema": "ao-operator/sandbox-egress-allowlist/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_unallowlisted_or_bypassed_egress_attempts", "observed_verdict": "PASS"},
                {"id": "unallowlisted_host_egress_admitted_rejected", "observed_verdict": "FAIL"},
                {"id": "ip_literal_bypass_admits_unallowlisted_target_rejected", "observed_verdict": "FAIL"},
                {"id": "dns_rebind_bypass_admits_unallowlisted_target_rejected", "observed_verdict": "FAIL"},
                {"id": "proxy_chain_bypass_admits_unallowlisted_target_rejected", "observed_verdict": "FAIL"},
                {"id": "raw_socket_bypass_admits_unallowlisted_target_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-tool-arg-injection-escape.json",
        {
            "schema": "ao-operator/agent-tool-arg-injection-escape/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion", "observed_verdict": "PASS"},
                {"id": "string_template_breakout_via_unescaped_quote_rejected", "observed_verdict": "FAIL"},
                {"id": "json_arg_breakout_via_nested_object_smuggling_rejected", "observed_verdict": "FAIL"},
                {"id": "polymorphic_argument_coercion_via_type_mismatch_rejected", "observed_verdict": "FAIL"},
                {"id": "shell_metachar_injection_via_unfiltered_string_arg_rejected", "observed_verdict": "FAIL"},
                {"id": "tool_name_spoof_via_arg_smuggled_alternate_tool_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-output-canary-leak-detection.json",
        {
            "schema": "ao-operator/agent-output-canary-leak-detection/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_canary_or_marked_secret_leak_in_output", "observed_verdict": "PASS"},
                {"id": "literal_canary_token_in_output_rejected", "observed_verdict": "FAIL"},
                {"id": "base64_encoded_canary_token_in_output_rejected", "observed_verdict": "FAIL"},
                {"id": "unicode_homoglyph_canary_substitution_in_output_rejected", "observed_verdict": "FAIL"},
                {"id": "partial_canary_fragment_concatenation_in_output_rejected", "observed_verdict": "FAIL"},
                {"id": "marked_secret_passthrough_via_field_label_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-os-execution-budget-enforcement.json",
        {
            "schema": "ao-operator/agent-os-execution-budget-enforcement/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_budget_overflow_or_reset_bypass", "observed_verdict": "PASS"},
                {"id": "token_budget_overflow_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "time_budget_overflow_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "tool_call_count_overflow_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "cost_ceiling_overflow_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "budget_reset_bypass_admit_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-system-prompt-tamper-detection.json",
        {
            "schema": "ao-operator/agent-system-prompt-tamper-detection/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_system_prompt_tamper", "observed_verdict": "PASS"},
                {"id": "system_prompt_substitution_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "system_prompt_appended_instruction_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "system_prompt_truncation_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "system_prompt_unicode_homoglyph_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "system_prompt_role_relabel_admit_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "tool-result-cache-poisoning-defense.json",
        {
            "schema": "ao-operator/tool-result-cache-poisoning-defense/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_tool_result_cache_poisoning", "observed_verdict": "PASS"},
                {"id": "cache_key_collision_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "stale_cache_serve_after_invalidation_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "ttl_extension_via_admin_replay_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "forged_response_signature_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "cross_tenant_cache_share_admit_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        base / "agent-credential-scope-narrowing.json",
        {
            "schema": "ao-operator/agent-credential-scope-narrowing/v1",
            "verdict": "PASS",
            "case_count": 6,
            "mutation_case_count": 5,
            "cases": [
                {"id": "clean_no_credential_scope_widening", "observed_verdict": "PASS"},
                {"id": "credential_scope_substitution_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "credential_scope_append_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "credential_audience_relabel_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "credential_expiry_extension_admit_rejected", "observed_verdict": "FAIL"},
                {"id": "credential_principal_mint_admit_rejected", "observed_verdict": "FAIL"},
            ],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def test_operator_guardrail_summary_passes_when_all_guardrails_pass(tmp_path):
    seed_reports(tmp_path)

    payload = check_operator_guardrail_summary.summarize(root=tmp_path)

    assert payload["schema"] == "ao-operator/operator-guardrail-summary/v1"
    assert payload["verdict"] == "PASS"
    assert payload["ship_ready"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["guardrails"]["operator_cockpit"]["verdict"] == "PASS"
    assert payload["guardrails"]["public_release_security"]["blocking_findings"] == 0
    assert payload["guardrails"]["dast_readiness"]["remote_dast_enabled"] is False
    assert payload["guardrails"]["manual_pentest_gate"]["manual_pentest_authorized"] is False
    assert payload["guardrails"]["host_key_evidence"]["host_key_evidence_required"] is True
    assert payload["guardrails"]["host_key_evidence"]["remote_dast_authorized"] is False
    assert payload["guardrails"]["manual_pentest_report_classifier"]["report_template_ready"] is True
    assert payload["guardrails"]["no_provider_rehearsal"]["refused_without_approval"] is True
    assert payload["approval_state"] == "ABSENT"
    assert payload["approval_usable"] is False
    assert payload["positive_approval_path"] == "PLAN_WITHOUT_DISPATCH"
    assert payload["guardrails"]["approval_cleanup"]["removed"] is False
    assert payload["guardrails"]["approved_launch_proof"]["launcher_verdict"] == "PLAN"
    assert payload["guardrails"]["approval_audit_history"]["event_count"] == 1
    assert payload["guardrails"]["post_approval_cleanup_route"]["route"] == "ACCEPTED"
    assert payload["guardrails"]["approval_runbook"]["required_item_count"] == 9
    assert payload["guardrails"]["approval_audit_retention"]["rotation_due"] is False
    assert payload["guardrails"]["approval_bundle_signature"]["signature_matches"] is True
    assert payload["guardrails"]["approval_revocation"]["revocation_applied"] is False
    assert payload["guardrails"]["approval_identity_signature"]["signature_verified"] is True
    assert payload["guardrails"]["approval_identity_signature"]["private_key_committed"] is False
    assert payload["guardrails"]["approval_revocation_apply_proof"]["revocation_applied"] is True
    assert payload["guardrails"]["approval_revocation_apply_proof"]["revocation_log_sanitized"] is True
    assert payload["guardrails"]["approval_audit_archive_restore"]["restore_verified"] is True
    assert payload["guardrails"]["approval_audit_archive_restore"]["source_mutated"] is False
    assert payload["guardrails"]["mac_ubuntu_approval_artifact_parity"]["artifact_parity"] is True
    assert payload["guardrails"]["mac_ubuntu_approval_artifact_parity"]["remote_git_synced"] is True
    assert payload["guardrails"]["mac_ubuntu_approval_artifact_parity"]["provider_dispatch"] is False
    assert payload["guardrails"]["mac_ubuntu_signed_approval_bundle_transfer"]["artifact_parity"] is True
    assert payload["guardrails"]["mac_ubuntu_signed_approval_bundle_transfer"]["signature_verified"] is True
    assert payload["guardrails"]["mac_ubuntu_signed_approval_bundle_transfer"]["identity_verified"] is True
    assert payload["guardrails"]["mac_ubuntu_signed_approval_bundle_transfer"]["remote_cleanup_absent"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_materialization_dry_run"]["signed_bundle_verified"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_materialization_dry_run"]["materialization_dry_run_passed"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_materialization_dry_run"]["approval_file_written"] is False
    assert payload["guardrails"]["mac_ubuntu_remote_approval_materialization_dry_run"]["approval_file_present_after"] is False
    assert payload["guardrails"]["mac_ubuntu_remote_approval_materialization_dry_run"]["remote_cleanup_absent"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_revocation_rollback"]["revocation_applied"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_revocation_rollback"]["rollback_restore_verified"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_revocation_rollback"]["approval_file_restored_after"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_revocation_rollback"]["remote_cleanup_absent"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approval_runbook"]["required_item_count"] == 17
    assert payload["guardrails"]["mac_ubuntu_remote_approved_fixture"]["approval_valid"] is True
    assert payload["guardrails"]["mac_ubuntu_remote_approved_fixture"]["launcher_plan_verified"] is True
    assert payload["guardrails"]["agent_os_architecture_implementation_gate"]["implementation_ready"] is True
    assert payload["guardrails"]["agent_os_architecture_implementation_gate"]["role_handoff_runspec_alignment"] == "PASS"
    assert payload["guardrails"]["agent_os_router_transition_matrix"]["case_count"] == 9
    assert payload["guardrails"]["agent_os_runspec_failure_injection_matrix"]["case_count"] == 7
    assert payload["guardrails"]["agent_os_runspec_dag_edge_coverage"]["edge_count"] == 6
    assert payload["guardrails"]["agent_os_runspec_dag_edge_coverage"]["role_graph_alignment"] is True
    assert payload["guardrails"]["agent_os_runspec_dag_edge_coverage"]["mutation_case_count"] == 5
    assert payload["guardrails"]["agent_os_runspec_yaml_dag_parity"]["yaml_edge_count"] == 6
    assert payload["guardrails"]["agent_os_runspec_yaml_dag_parity"]["yaml_renderer_alignment"] is True
    assert payload["guardrails"]["agent_os_runspec_yaml_dag_parity"]["yaml_role_graph_alignment"] is True
    assert payload["guardrails"]["agent_os_runspec_yaml_dag_parity"]["mutation_case_count"] == 4
    assert payload["guardrails"]["mac_ubuntu_remote_approved_fixture"]["would_run_provider"] is False
    assert payload["guardrails"]["remote_transfer_resource_exhaustion_guard"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_resource_exhaustion_guard"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_clock_skew_tolerance"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_clock_skew_tolerance"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_bundle_id_uniqueness"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_bundle_id_uniqueness"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_bundle_content_type_allowlist"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_bundle_content_type_allowlist"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_per_tenant_quota_isolation"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_per_tenant_quota_isolation"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_wire_encryption_required"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_wire_encryption_required"]["mutation_case_count"] == 4
    assert payload["guardrails"]["remote_transfer_sender_identity_rotation"]["case_count"] == 5
    assert payload["guardrails"]["remote_transfer_sender_identity_rotation"]["mutation_case_count"] == 4
    assert payload["guardrails"]["ai_agent_blast_radius_inventory"]["case_count"] == 6
    assert payload["guardrails"]["ai_agent_blast_radius_inventory"]["mutation_case_count"] == 5
    assert payload["next_safe_command"] == "All operator guardrails pass; keep Agent OS execution blocked without explicit approval."


def test_operator_guardrail_summary_blocks_live_or_dispatching_report(tmp_path):
    seed_reports(tmp_path)
    report = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/resource-performance-gate.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    data["dispatch_authorized"] = True
    write_json(report, data)

    payload = check_operator_guardrail_summary.summarize(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert "resource_performance" in payload["blockers"]
    assert "resource_performance dispatch_authorized must remain false" in payload["errors"]


def test_operator_guardrail_summary_cli_writes_report(tmp_path, capsys):
    seed_reports(tmp_path)
    output = tmp_path / "run-artifacts/summary.json"

    code = check_operator_guardrail_summary.main(["--root", str(tmp_path), "--write-output", str(output), "--json"])

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/operator-guardrail-summary/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
