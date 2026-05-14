from __future__ import annotations

import json
import subprocess

import check_clean_clone_readiness


def test_command_plan_covers_architecture_prerequisites():
    commands = check_clean_clone_readiness.command_plan(include_closure=True)

    assert ["python3", "scripts/summarize_50_slice_operator_state.py", "--json"] in commands
    assert ["python3", "scripts/check_live_acceptance.py", "--slug", "remote-transfer-v2-stress-live", "--json"] in commands
    assert ["python3", "scripts/validate_factory.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_router_migration_matrix.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_provider_boundary_matrix.py", "--json"] in commands
    assert ["python3", "scripts/agent_os_runspec_validator.py", "--provider-profile", ".env.example", "--json"] in commands
    assert ["python3", "scripts/cleanup_agent_os_state_artifacts.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approved_launch_proof.py", "--json"] in commands
    assert ["python3", "scripts/cleanup_agent_os_approval.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_audit_history.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_post_approval_cleanup_route.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_runbook.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_audit_retention.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_bundle_signature.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_revocation.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_identity_signature.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_revocation_apply_proof.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_approval_audit_archive_restore.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_approval_artifact_parity.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_remote_approval_runbook.py", "--json"] in commands
    assert ["python3", "scripts/check_mac_ubuntu_remote_approved_fixture.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_architecture_implementation_gate.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_router_transition_matrix.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_failure_injection_matrix.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_dag_edge_coverage.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_yaml_dag_parity.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_yaml_semantic_parity.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_yaml_schema_injection.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_runspec_ao_preflight_compatibility.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_router_default_state_version.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_role_graph_backward_compat.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_chunk_cleanup_invariants.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_signed_bundle_tamper.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_approval_expiry_rotation.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_bundle_ordering_resume.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_provider_redaction_round_trip.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_network_retry_idempotency.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_concurrent_transfer_collision.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_bundle_schema_version_skew.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_resource_exhaustion_guard.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_clock_skew_tolerance.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_bundle_id_uniqueness.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_bundle_content_type_allowlist.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_per_tenant_quota_isolation.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_wire_encryption_required.py", "--json"] in commands
    assert ["python3", "scripts/check_remote_transfer_sender_identity_rotation.py", "--json"] in commands
    assert ["python3", "scripts/check_ai_agent_blast_radius_inventory.py", "--json"] in commands
    assert ["python3", "scripts/check_ai_agent_destructive_action_approval.py", "--json"] in commands
    assert ["python3", "scripts/check_ai_agent_credential_reachability.py", "--json"] in commands
    assert ["python3", "scripts/check_ai_agent_instruction_packaging_leak_detection.py", "--json"] in commands
    assert ["python3", "scripts/check_mcp_tool_poisoning_detection.py", "--json"] in commands
    assert ["python3", "scripts/check_deepsec_diff_review_advisory_sast.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_supply_chain_integrity.py", "--json"] in commands
    assert ["python3", "scripts/check_prompt_injection_escape_boundary.py", "--json"] in commands
    assert ["python3", "scripts/check_approval_clock_skew_defense.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_log_redaction_round_trip.py", "--json"] in commands
    assert ["python3", "scripts/check_per_tenant_blast_radius_cap.py", "--json"] in commands
    assert ["python3", "scripts/check_sandbox_egress_allowlist.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_tool_arg_injection_escape.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_output_canary_leak_detection.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_os_execution_budget_enforcement.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_system_prompt_tamper_detection.py", "--json"] in commands
    assert ["python3", "scripts/check_tool_result_cache_poisoning_defense.py", "--json"] in commands
    assert ["python3", "scripts/check_agent_credential_scope_narrowing.py", "--json"] in commands
    assert ["python3", "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] in commands
    assert ["python3", "scripts/redact_strict_public_artifacts.py", "--fail-on-changes", "--json"] in commands
    assert ["python3", "scripts/check_status_json_integrity.py", "--json"] in commands


def test_summarize_blocks_non_accepted_50_slice_state(tmp_path, monkeypatch):
    clone = tmp_path / "clone"

    monkeypatch.setattr(check_clean_clone_readiness.tempfile, "TemporaryDirectory", lambda prefix: _TempDir(clone))
    monkeypatch.setattr(
        check_clean_clone_readiness,
        "run_command",
        lambda command, cwd, timeout, env=None: _result(command, stdout='{"current_state":"READY_FOR_APPROVAL_NOT_DISPATCH"}'),
    )

    payload = check_clean_clone_readiness.summarize(root=tmp_path, include_closure=False)

    assert payload["verdict"] == "FAIL"
    assert "50_slice.accepted_terminal_state" in payload["blockers"]


def test_summarize_records_agent_os_architecture_baseline_verdicts(tmp_path, monkeypatch):
    clone = tmp_path / "clone"

    def fake_run(command, cwd, timeout, env=None):
        if command == ["python3", "scripts/summarize_50_slice_operator_state.py", "--json"]:
            return _result(command, stdout='{"current_state":"ACCEPTED_50_SLICE_LIVE"}')
        if command == ["python3", "scripts/check_agent_os_router_migration_matrix.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-router-migration-matrix/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_runspec_provider_boundary_matrix.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-provider-boundary-matrix/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/agent_os_runspec_validator.py", "--provider-profile", ".env.example", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-validation/v1","verdict":"PASS","provider_profile_matches":true}')
        if command == ["python3", "scripts/cleanup_agent_os_state_artifacts.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-state-stale-cleanup/v1","verdict":"PASS","candidate_count":0}')
        if command == ["python3", "scripts/check_agent_os_architecture_implementation_gate.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-architecture-implementation-gate/v1","verdict":"PASS","implementation_ready":true}')
        if command == ["python3", "scripts/check_agent_os_router_transition_matrix.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-router-transition-matrix/v1","verdict":"PASS","case_count":9}')
        if command == ["python3", "scripts/check_agent_os_runspec_failure_injection_matrix.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-failure-injection-matrix/v1","verdict":"PASS","case_count":7}')
        if command == ["python3", "scripts/check_agent_os_runspec_dag_edge_coverage.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-dag-edge-coverage/v1","verdict":"PASS","mutation_case_count":5,"role_graph_alignment":true}')
        if command == ["python3", "scripts/check_agent_os_runspec_yaml_dag_parity.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-yaml-dag-parity/v1","verdict":"PASS","mutation_case_count":4,"yaml_renderer_alignment":true,"yaml_role_graph_alignment":true}')
        if command == ["python3", "scripts/check_agent_os_runspec_yaml_semantic_parity.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-yaml-semantic-parity/v1","verdict":"PASS","mutation_case_count":6,"all_aligned":true}')
        if command == ["python3", "scripts/check_agent_os_runspec_yaml_schema_injection.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-yaml-schema-injection/v1","verdict":"PASS","task_count":7,"mutation_case_count":6,"mutation_cases":[{"id":"malformed_yaml_refused","observed_verdict":"FAIL"},{"id":"duplicate_task_ids_refused","observed_verdict":"FAIL"},{"id":"missing_spec_block_refused","observed_verdict":"FAIL"},{"id":"bad_deps_type_refused","observed_verdict":"FAIL"},{"id":"unknown_task_field_refused","observed_verdict":"FAIL"},{"id":"unsafe_dispatch_authorized_refused","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_os_runspec_ao_preflight_compatibility.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-runspec-ao-preflight-compatibility/v1","verdict":"PASS","task_count":7,"mutation_case_count":5,"mutation_cases":[{"id":"wrong_api_version_refused","observed_verdict":"FAIL"},{"id":"wrong_runspec_kind_refused","observed_verdict":"FAIL"},{"id":"unknown_task_kind_refused","observed_verdict":"FAIL"},{"id":"unknown_dependency_refused","observed_verdict":"FAIL"},{"id":"dag_cycle_refused","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_os_router_default_state_version.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-router-default-state-version/v1","verdict":"PASS","argparse_default":"v2","case_count":3,"cases":[{"id":"default_emits_state_v2","observed_verdict":"PASS"},{"id":"explicit_v1_remains_supported","observed_verdict":"PASS"},{"id":"explicit_v2_matches_default","observed_verdict":"PASS"}]}')
        if command == ["python3", "scripts/check_agent_os_role_graph_backward_compat.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-role-graph-backward-compat/v1","verdict":"PASS","case_count":6,"cases":[{"id":"legacy_v1_state_minimal_loadable","observed_verdict":"PASS"},{"id":"legacy_v1_state_extra_unknown_fields_tolerated","observed_verdict":"PASS"},{"id":"legacy_v1_state_no_role_graph_schema_injects_default","observed_verdict":"PASS"},{"id":"legacy_v2_state_round_trip_preserves_previous_schema","observed_verdict":"PASS"},{"id":"legacy_v1_role_graph_artifact_remains_loadable","observed_verdict":"PASS"},{"id":"unknown_state_schema_refused","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_chunk_cleanup_invariants.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-chunk-cleanup-invariants/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_upload_commit_passes","observed_verdict":"PASS"},{"id":"orphaned_chunk_after_abort_detected","observed_verdict":"FAIL"},{"id":"missing_finalize_detected","observed_verdict":"FAIL"},{"id":"stale_partial_stage_dir_detected","observed_verdict":"FAIL"},{"id":"double_commit_rejected","observed_verdict":"FAIL"},{"id":"retry_index_drift_detected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_signed_bundle_tamper.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-signed-bundle-tamper/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_signed_bundle_passes","observed_verdict":"PASS"},{"id":"truncated_bundle_rejected","observed_verdict":"FAIL"},{"id":"swapped_chunk_rejected","observed_verdict":"FAIL"},{"id":"wrong_signing_key_rejected","observed_verdict":"FAIL"},{"id":"replayed_bundle_rejected","observed_verdict":"FAIL"},{"id":"manifest_digest_mismatch_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_approval_expiry_rotation.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-approval-expiry-rotation/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_approval_passes","observed_verdict":"PASS"},{"id":"expired_approval_rejected","observed_verdict":"FAIL"},{"id":"approval_used_after_rotation_cutover_rejected","observed_verdict":"FAIL"},{"id":"signing_key_rotated_midflight_without_grace_rejected","observed_verdict":"FAIL"},{"id":"approval_reused_beyond_ttl_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_bundle_ordering_resume.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-bundle-ordering-resume/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_ordered_delivery_passes","observed_verdict":"PASS"},{"id":"out_of_order_chunk_rejected","observed_verdict":"FAIL"},{"id":"partial_resume_drops_middle_chunk_rejected","observed_verdict":"FAIL"},{"id":"resume_cursor_lies_about_high_water_rejected","observed_verdict":"FAIL"},{"id":"duplicate_chunk_delivery_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_provider_redaction_round_trip.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-provider-redaction-round-trip/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_round_trip_passes","observed_verdict":"PASS"},{"id":"redaction_marker_stripped_before_transmit_rejected","observed_verdict":"FAIL"},{"id":"sensitive_field_leaks_past_redaction_filter_rejected","observed_verdict":"FAIL"},{"id":"double_redaction_corrupts_payload_rejected","observed_verdict":"FAIL"},{"id":"provider_response_leaks_redacted_value_back_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_network_retry_idempotency.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-network-retry-idempotency/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_retry_round_trip_passes","observed_verdict":"PASS"},{"id":"retry_without_nonce_dedup_rejected","observed_verdict":"FAIL"},{"id":"partial_flush_on_network_drop_rejected","observed_verdict":"FAIL"},{"id":"ack_lost_causes_double_commit_rejected","observed_verdict":"FAIL"},{"id":"timeout_shorter_than_response_causes_orphan_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_concurrent_transfer_collision.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-concurrent-transfer-collision/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_serialized_concurrent_transfers_passes","observed_verdict":"PASS"},{"id":"parallel_transfers_no_lock_corrupts_state_rejected","observed_verdict":"FAIL"},{"id":"simultaneous_finalize_double_completes_bundle_rejected","observed_verdict":"FAIL"},{"id":"lost_writer_overwrites_winner_bundle_rejected","observed_verdict":"FAIL"},{"id":"stale_lock_holder_resumes_after_handoff_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_bundle_schema_version_skew.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-bundle-schema-version-skew/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_matched_schema_version_passes","observed_verdict":"PASS"},{"id":"receiver_below_min_version_rejected","observed_verdict":"FAIL"},{"id":"receiver_above_max_silently_downgrades_rejected","observed_verdict":"FAIL"},{"id":"bundle_advertises_unknown_extension_field_rejected","observed_verdict":"FAIL"},{"id":"schema_version_field_missing_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_resource_exhaustion_guard.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-resource-exhaustion-guard/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_within_quota_passes","observed_verdict":"PASS"},{"id":"announced_chunk_count_exceeds_quota_rejected","observed_verdict":"FAIL"},{"id":"announced_total_size_exceeds_quota_rejected","observed_verdict":"FAIL"},{"id":"per_chunk_size_exceeds_max_rejected","observed_verdict":"FAIL"},{"id":"transfer_exceeds_announced_count_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_clock_skew_tolerance.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-clock-skew-tolerance/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_within_skew_tolerance_passes","observed_verdict":"PASS"},{"id":"sender_clock_ahead_of_receiver_rejected","observed_verdict":"FAIL"},{"id":"sender_clock_behind_receiver_rejected","observed_verdict":"FAIL"},{"id":"future_dated_bundle_accepted_as_currently_valid_rejected","observed_verdict":"FAIL"},{"id":"ttl_window_straddling_skew_silently_extended_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_bundle_id_uniqueness.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-bundle-id-uniqueness/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_unique_bundle_ids_pass","observed_verdict":"PASS"},{"id":"duplicate_bundle_id_within_session_rejected","observed_verdict":"FAIL"},{"id":"cross_sender_bundle_id_collision_rejected","observed_verdict":"FAIL"},{"id":"bundle_id_truncation_collision_rejected","observed_verdict":"FAIL"},{"id":"bundle_id_replayed_after_completion_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_bundle_content_type_allowlist.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-bundle-content-type-allowlist/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_allowlisted_content_type_passes","observed_verdict":"PASS"},{"id":"unknown_content_type_silently_coerced_rejected","observed_verdict":"FAIL"},{"id":"mismatched_extension_to_content_type_rejected","observed_verdict":"FAIL"},{"id":"unknown_content_encoding_silently_decoded_rejected","observed_verdict":"FAIL"},{"id":"content_type_charset_parameter_smuggled_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_per_tenant_quota_isolation.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-per-tenant-quota-isolation/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_per_tenant_within_quota_passes","observed_verdict":"PASS"},{"id":"tenant_a_overflows_tenant_b_quota_slot_rejected","observed_verdict":"FAIL"},{"id":"aggregated_quota_across_tenants_merged_rejected","observed_verdict":"FAIL"},{"id":"tenant_identity_stripped_silently_coerced_to_default_rejected","observed_verdict":"FAIL"},{"id":"quota_refund_on_abort_double_credited_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_wire_encryption_required.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-wire-encryption-required/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_encrypted_bundle_accepted","observed_verdict":"PASS"},{"id":"cleartext_bundle_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"downgraded_tls_cipher_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"weak_null_cipher_suite_negotiated_rejected","observed_verdict":"FAIL"},{"id":"encryption_header_stripped_after_handshake_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_remote_transfer_sender_identity_rotation.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/remote-transfer-sender-identity-rotation/v1","verdict":"PASS","case_count":5,"mutation_case_count":4,"cases":[{"id":"clean_post_rotation_bundle_accepted","observed_verdict":"PASS"},{"id":"retired_identity_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"rotation_announcement_unsigned_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"future_rotation_effective_at_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"dual_acceptance_window_silently_left_open_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_ai_agent_blast_radius_inventory.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/ai-agent-blast-radius-inventory/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_inventory_classified_and_gated","observed_verdict":"PASS"},{"id":"unclassified_high_blast_radius_command_path_rejected","observed_verdict":"FAIL"},{"id":"destructive_action_without_approval_gate_rejected","observed_verdict":"FAIL"},{"id":"credential_path_reachable_from_untrusted_content_rejected","observed_verdict":"FAIL"},{"id":"provider_dispatch_without_approval_readiness_rejected","observed_verdict":"FAIL"},{"id":"release_artifact_includes_instruction_or_credentials_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_ai_agent_destructive_action_approval.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/ai-agent-destructive-action-approval/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_destructive_action_with_fresh_scoped_approval_executes","observed_verdict":"PASS"},{"id":"stale_approval_reused_after_expiry_rejected","observed_verdict":"FAIL"},{"id":"approval_scope_widened_at_exec_silently_accepted_rejected","observed_verdict":"FAIL"},{"id":"approval_consumed_twice_for_distinct_destructive_ops_rejected","observed_verdict":"FAIL"},{"id":"destructive_op_runs_with_policy_only_without_token_rejected","observed_verdict":"FAIL"},{"id":"parent_process_approval_inherited_by_child_without_reconfirm_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_ai_agent_credential_reachability.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/ai-agent-credential-reachability/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_untrusted_to_credential_reachable_path","observed_verdict":"PASS"},{"id":"untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected","observed_verdict":"FAIL"},{"id":"agent_tool_output_piped_to_shell_with_ssh_dir_rejected","observed_verdict":"FAIL"},{"id":"mcp_tool_result_included_in_role_handoff_with_session_paths_rejected","observed_verdict":"FAIL"},{"id":"web_fetch_reflected_into_shell_resolving_env_rejected","observed_verdict":"FAIL"},{"id":"prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_ai_agent_instruction_packaging_leak_detection.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/ai-agent-instruction-packaging-leak-detection/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_instruction_or_packaging_leaks_in_public_artifacts","observed_verdict":"PASS"},{"id":"claude_md_directives_leaked_into_status_report_rejected","observed_verdict":"FAIL"},{"id":"agent_memory_snippet_copy_pasted_into_public_doc_rejected","observed_verdict":"FAIL"},{"id":"raw_user_prompt_logged_in_operator_slice_evidence_rejected","observed_verdict":"FAIL"},{"id":"anthropic_api_key_surfaced_in_evaluation_transcript_rejected","observed_verdict":"FAIL"},{"id":"tmp_diagnostic_path_included_in_public_artifact_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_mcp_tool_poisoning_detection.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/mcp-tool-poisoning-detection/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_mcp_or_tool_poisoning_indicators","observed_verdict":"PASS"},{"id":"hidden_imperative_in_mcp_description_rejected","observed_verdict":"FAIL"},{"id":"tool_result_schema_adds_destructive_default_arg_rejected","observed_verdict":"FAIL"},{"id":"mcp_returns_url_to_fetch_and_apply_rejected","observed_verdict":"FAIL"},{"id":"tool_name_shadowing_overrides_native_tool_rejected","observed_verdict":"FAIL"},{"id":"signed_descriptor_advertises_unallowed_privilege_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_deepsec_diff_review_advisory_sast.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/deepsec-diff-review-advisory-sast/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_untrusted_to_dangerous_sink_edges","observed_verdict":"PASS"},{"id":"untrusted_input_flows_into_shell_command_rejected","observed_verdict":"FAIL"},{"id":"untrusted_input_flows_into_fs_write_outside_workspace_rejected","observed_verdict":"FAIL"},{"id":"untrusted_input_flows_into_network_egress_rejected","observed_verdict":"FAIL"},{"id":"eval_or_exec_on_retrieved_content_rejected","observed_verdict":"FAIL"},{"id":"dynamic_import_from_agent_controlled_path_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_supply_chain_integrity.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-supply-chain-integrity/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_unauthorized_provenance_or_unsigned_package_edges","observed_verdict":"PASS"},{"id":"unsigned_package_admitted_without_signature_rejected","observed_verdict":"FAIL"},{"id":"lock_file_digest_mismatch_admitted_rejected","observed_verdict":"FAIL"},{"id":"dependency_confusion_via_shadow_registry_rejected","observed_verdict":"FAIL"},{"id":"post_install_script_with_network_egress_rejected","observed_verdict":"FAIL"},{"id":"transitive_yank_without_repin_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_prompt_injection_escape_boundary.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/prompt-injection-escape-boundary/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_role_spoofing_or_attacker_controlled_system_prompt_appended","observed_verdict":"PASS"},{"id":"attacker_role_spoofing_appended_after_user_content_rejected","observed_verdict":"FAIL"},{"id":"fenced_block_escape_breaking_system_boundary_rejected","observed_verdict":"FAIL"},{"id":"json_injection_replacing_operator_instructions_rejected","observed_verdict":"FAIL"},{"id":"tool_name_shadowing_via_attacker_section_rejected","observed_verdict":"FAIL"},{"id":"instruction_smuggling_via_unicode_homoglyph_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_approval_clock_skew_defense.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/approval-clock-skew-defense/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_clock_skew_or_replay_or_stale_freshness_edges","observed_verdict":"PASS"},{"id":"ntp_rewind_admits_expired_approval_rejected","observed_verdict":"FAIL"},{"id":"leap_second_jump_admits_expired_approval_rejected","observed_verdict":"FAIL"},{"id":"tz_tagged_as_utc_admits_expired_approval_rejected","observed_verdict":"FAIL"},{"id":"expired_but_cached_admits_replay_rejected","observed_verdict":"FAIL"},{"id":"signed_token_replay_admits_reactivation_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_log_redaction_round_trip.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-log-redaction-round-trip/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_round_trip_recoverable_secret_or_personal_path_in_redacted_output","observed_verdict":"PASS"},{"id":"partial_pattern_match_leaves_original_substring_rejected","observed_verdict":"FAIL"},{"id":"base64_encoded_secret_unredacted_in_round_trip_rejected","observed_verdict":"FAIL"},{"id":"path_normalization_alias_unredacted_in_round_trip_rejected","observed_verdict":"FAIL"},{"id":"case_insensitive_token_unredacted_in_round_trip_rejected","observed_verdict":"FAIL"},{"id":"json_string_escape_token_unredacted_in_round_trip_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_per_tenant_blast_radius_cap.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/per-tenant-blast-radius-cap/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_cross_tenant_or_unallowlisted_or_quota_overflow_action_edges","observed_verdict":"PASS"},{"id":"cross_tenant_fanout_to_unrelated_tenant_resource_rejected","observed_verdict":"FAIL"},{"id":"missing_tenant_tag_admits_global_blast_radius_rejected","observed_verdict":"FAIL"},{"id":"tenant_tag_spoof_admits_other_tenant_resource_rejected","observed_verdict":"FAIL"},{"id":"allowlist_bypass_admits_unallowlisted_target_rejected","observed_verdict":"FAIL"},{"id":"quota_overflow_leak_admits_post_window_action_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_sandbox_egress_allowlist.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/sandbox-egress-allowlist/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_unallowlisted_or_bypassed_egress_attempts","observed_verdict":"PASS"},{"id":"unallowlisted_host_egress_admitted_rejected","observed_verdict":"FAIL"},{"id":"ip_literal_bypass_admits_unallowlisted_target_rejected","observed_verdict":"FAIL"},{"id":"dns_rebind_bypass_admits_unallowlisted_target_rejected","observed_verdict":"FAIL"},{"id":"proxy_chain_bypass_admits_unallowlisted_target_rejected","observed_verdict":"FAIL"},{"id":"raw_socket_bypass_admits_unallowlisted_target_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_tool_arg_injection_escape.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-tool-arg-injection-escape/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_tool_arg_injection_or_breakout_or_polymorphic_coercion","observed_verdict":"PASS"},{"id":"string_template_breakout_via_unescaped_quote_rejected","observed_verdict":"FAIL"},{"id":"json_arg_breakout_via_nested_object_smuggling_rejected","observed_verdict":"FAIL"},{"id":"polymorphic_argument_coercion_via_type_mismatch_rejected","observed_verdict":"FAIL"},{"id":"shell_metachar_injection_via_unfiltered_string_arg_rejected","observed_verdict":"FAIL"},{"id":"tool_name_spoof_via_arg_smuggled_alternate_tool_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_output_canary_leak_detection.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-output-canary-leak-detection/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_canary_or_marked_secret_leak_in_output","observed_verdict":"PASS"},{"id":"literal_canary_token_in_output_rejected","observed_verdict":"FAIL"},{"id":"base64_encoded_canary_token_in_output_rejected","observed_verdict":"FAIL"},{"id":"unicode_homoglyph_canary_substitution_in_output_rejected","observed_verdict":"FAIL"},{"id":"partial_canary_fragment_concatenation_in_output_rejected","observed_verdict":"FAIL"},{"id":"marked_secret_passthrough_via_field_label_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_os_execution_budget_enforcement.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-execution-budget-enforcement/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_budget_overflow_or_reset_bypass","observed_verdict":"PASS"},{"id":"token_budget_overflow_admit_rejected","observed_verdict":"FAIL"},{"id":"time_budget_overflow_admit_rejected","observed_verdict":"FAIL"},{"id":"tool_call_count_overflow_admit_rejected","observed_verdict":"FAIL"},{"id":"cost_ceiling_overflow_admit_rejected","observed_verdict":"FAIL"},{"id":"budget_reset_bypass_admit_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_system_prompt_tamper_detection.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-system-prompt-tamper-detection/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_system_prompt_tamper","observed_verdict":"PASS"},{"id":"system_prompt_substitution_admit_rejected","observed_verdict":"FAIL"},{"id":"system_prompt_appended_instruction_admit_rejected","observed_verdict":"FAIL"},{"id":"system_prompt_truncation_admit_rejected","observed_verdict":"FAIL"},{"id":"system_prompt_unicode_homoglyph_admit_rejected","observed_verdict":"FAIL"},{"id":"system_prompt_role_relabel_admit_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_tool_result_cache_poisoning_defense.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/tool-result-cache-poisoning-defense/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_tool_result_cache_poisoning","observed_verdict":"PASS"},{"id":"cache_key_collision_admit_rejected","observed_verdict":"FAIL"},{"id":"stale_cache_serve_after_invalidation_admit_rejected","observed_verdict":"FAIL"},{"id":"ttl_extension_via_admin_replay_admit_rejected","observed_verdict":"FAIL"},{"id":"forged_response_signature_admit_rejected","observed_verdict":"FAIL"},{"id":"cross_tenant_cache_share_admit_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_credential_scope_narrowing.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-credential-scope-narrowing/v1","verdict":"PASS","case_count":6,"mutation_case_count":5,"cases":[{"id":"clean_no_credential_scope_widening","observed_verdict":"PASS"},{"id":"credential_scope_substitution_admit_rejected","observed_verdict":"FAIL"},{"id":"credential_scope_append_admit_rejected","observed_verdict":"FAIL"},{"id":"credential_audience_relabel_admit_rejected","observed_verdict":"FAIL"},{"id":"credential_expiry_extension_admit_rejected","observed_verdict":"FAIL"},{"id":"credential_principal_mint_admit_rejected","observed_verdict":"FAIL"}]}')
        if command == ["python3", "scripts/check_agent_os_approved_launch_proof.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approved-launch-proof/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/cleanup_agent_os_approval.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-cleanup/v1","verdict":"PASS","approval_state":"ABSENT"}')
        if command == ["python3", "scripts/check_agent_os_approval_audit_history.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-audit-history/v1","verdict":"PASS","event_count":1}')
        if command == ["python3", "scripts/check_agent_os_post_approval_cleanup_route.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-post-approval-cleanup-route/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_runbook.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-runbook/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_audit_retention.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-audit-retention/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_bundle_signature.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-bundle-signature/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_revocation.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-revocation/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_identity_signature.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-identity-signature/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_revocation_apply_proof.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-revocation-apply-proof/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_agent_os_approval_audit_archive_restore.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/agent-os-approval-audit-archive-restore/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_mac_ubuntu_approval_artifact_parity.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/mac-ubuntu-approval-artifact-parity-validation/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/mac-ubuntu-signed-approval-bundle-transfer-validation/v1","verdict":"PASS"}')
        if command == ["python3", "scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py", "--json"]:
            return _result(command, stdout='{"schema":"ao-operator/mac-ubuntu-remote-approval-materialization-dry-run-validation/v1","verdict":"PASS"}')
        return _result(command)

    monkeypatch.setattr(check_clean_clone_readiness.tempfile, "TemporaryDirectory", lambda prefix: _TempDir(clone))
    monkeypatch.setattr(check_clean_clone_readiness, "run_command", fake_run)

    payload = check_clean_clone_readiness.summarize(root=tmp_path, include_closure=False)

    assert payload["verdict"] == "PASS"
    assert payload["architecture_baselines"] == {
        "agent_os_router_migration_matrix": "PASS",
        "agent_os_runspec_provider_boundary_matrix": "PASS",
        "agent_os_runspec_provider_profile_validation": "PASS",
        "agent_os_state_stale_cleanup": "PASS",
        "agent_os_architecture_implementation_gate": "PASS",
        "agent_os_router_transition_matrix": "PASS",
        "agent_os_runspec_failure_injection_matrix": "PASS",
        "agent_os_runspec_dag_edge_coverage": "PASS",
        "agent_os_runspec_yaml_dag_parity": "PASS",
        "agent_os_runspec_yaml_semantic_parity": "PASS",
        "agent_os_runspec_yaml_schema_injection": "PASS",
        "agent_os_runspec_ao_preflight_compatibility": "PASS",
        "agent_os_router_default_state_version": "PASS",
        "agent_os_role_graph_backward_compat": "PASS",
        "remote_transfer_chunk_cleanup_invariants": "PASS",
        "remote_transfer_signed_bundle_tamper": "PASS",
        "remote_transfer_approval_expiry_rotation": "PASS",
        "remote_transfer_bundle_ordering_resume": "PASS",
        "remote_transfer_provider_redaction_round_trip": "PASS",
        "remote_transfer_network_retry_idempotency": "PASS",
        "remote_transfer_concurrent_transfer_collision": "PASS",
        "remote_transfer_bundle_schema_version_skew": "PASS",
        "remote_transfer_resource_exhaustion_guard": "PASS",
        "remote_transfer_clock_skew_tolerance": "PASS",
        "remote_transfer_bundle_id_uniqueness": "PASS",
        "remote_transfer_bundle_content_type_allowlist": "PASS",
        "remote_transfer_per_tenant_quota_isolation": "PASS",
        "remote_transfer_wire_encryption_required": "PASS",
        "remote_transfer_sender_identity_rotation": "PASS",
        "ai_agent_blast_radius_inventory": "PASS",
        "ai_agent_destructive_action_approval": "PASS",
        "ai_agent_credential_reachability": "PASS",
        "ai_agent_instruction_packaging_leak_detection": "PASS",
        "mcp_tool_poisoning_detection": "PASS",
        "deepsec_diff_review_advisory_sast": "PASS",
        "agent_supply_chain_integrity": "PASS",
        "prompt_injection_escape_boundary": "PASS",
        "approval_clock_skew_defense": "PASS",
        "agent_log_redaction_round_trip": "PASS",
        "per_tenant_blast_radius_cap": "PASS",
        "sandbox_egress_allowlist": "PASS",
        "agent_tool_arg_injection_escape": "PASS",
        "agent_output_canary_leak_detection": "PASS",
        "agent_os_execution_budget_enforcement": "PASS",
        "agent_system_prompt_tamper_detection": "PASS",
        "tool_result_cache_poisoning_defense": "PASS",
        "agent_credential_scope_narrowing": "PASS",
    }


def test_parse_stdout_json_prefers_structured_fields_when_tail_is_truncated():
    result = {
        "stdout_tail": '{"verdict":"PASS"}',
        "stdout_fields": {
            "schema": "ao-operator/agent-os-router-transition-matrix/v1",
            "verdict": "PASS",
            "case_count": 9,
        },
    }

    payload = check_clean_clone_readiness.parse_stdout_json(result)

    assert payload["case_count"] == 9


def test_main_writes_sanitized_report(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"

    monkeypatch.setattr(
        check_clean_clone_readiness,
        "summarize",
        lambda **kwargs: {
            "schema": "ao-operator/clean-clone-readiness/v1",
            "verdict": "PASS",
            "blockers": [],
            "repo": str(tmp_path),
            "clone_path": str(tmp_path / "ao-operator-clean-clone-abc" / "ao-operator"),
        },
    )

    code = check_clean_clone_readiness.main(["--root", str(tmp_path), "--write-output", str(report), "--json"])

    assert code == 0
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["repo"] == "${FACTORY_V3_ROOT}"
    assert written["clone_path"] == "${FACTORY_V3_ROOT}/ao-operator-clean-clone-abc/ao-operator"
    printed = json.loads(capsys.readouterr().out)
    assert printed["output"] == str(report)


class _TempDir:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.path.mkdir(parents=True, exist_ok=True)
        return str(self.path)

    def __exit__(self, exc_type, exc, tb):
        return False


def _result(command, *, stdout: str = "{}"):
    return {
        "command": command,
        "duration_seconds": 0.001,
        "returncode": 0,
        "stdout_tail": stdout,
        "stderr_tail": "",
        "verdict": "PASS",
    }
