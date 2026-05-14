from __future__ import annotations

import json
from pathlib import Path

import check_release_artifact_index


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def seed_artifacts(root: Path) -> None:
    for path in [
        "docs/sdd/62-remote-transfer-hardening-evidence-gate.md",
        "docs/sdd/37-public-release-security-and-dast.md",
        "docs/sdd/38-security-sdlc-roadmap.md",
        "docs/sdd/39-security-threat-model-data-flow.md",
        "docs/sdd/40-manual-penetration-test-gate.md",
        "docs/sdd/41-host-key-evidence-gate.md",
        "docs/sdd/42-manual-pentest-report-classifier.md",
        "docs/sdd/43-supply-chain-audit-gate.md",
        "docs/sdd/63-resource-performance-guardrails.md",
        "docs/sdd/64-agent-os-execution-approval-bundle.md",
        "docs/sdd/65-operator-guardrail-summary.md",
        "docs/sdd/66-agent-os-approval-materialization.md",
        "docs/sdd/67-release-artifact-index.md",
        "docs/sdd/68-agent-os-approval-lifecycle.md",
        "docs/sdd/69-agent-os-approved-launch-proof.md",
        "docs/sdd/70-agent-os-approval-cleanup.md",
        "docs/sdd/71-agent-os-approval-audit-history.md",
        "docs/sdd/72-agent-os-post-approval-cleanup-route.md",
        "docs/sdd/73-agent-os-approval-materialization-runbook.md",
        "docs/sdd/74-agent-os-approval-audit-retention.md",
        "docs/sdd/75-agent-os-approval-bundle-signature.md",
        "docs/sdd/76-agent-os-approval-revocation.md",
        "docs/sdd/77-agent-os-approval-identity-signature.md",
        "docs/sdd/78-agent-os-approval-revocation-apply-proof.md",
        "docs/sdd/79-agent-os-approval-audit-archive-restore.md",
        "docs/sdd/80-mac-ubuntu-approval-artifact-parity.md",
        "docs/sdd/81-mac-ubuntu-signed-approval-bundle-transfer.md",
        "docs/sdd/82-mac-ubuntu-remote-approval-materialization-dry-run.md",
        "docs/sdd/83-mac-ubuntu-remote-approval-revocation-rollback.md",
        "docs/sdd/84-mac-ubuntu-remote-approval-runbook.md",
        "docs/sdd/85-mac-ubuntu-remote-approved-fixture.md",
        "docs/sdd/86-agent-os-architecture-implementation-gate.md",
        "docs/sdd/87-agent-os-router-transition-matrix.md",
        "docs/sdd/88-agent-os-runspec-failure-injection-matrix.md",
        "docs/sdd/89-operator-safe-next-command.md",
        "docs/sdd/90-agent-os-runspec-dag-edge-coverage.md",
        "docs/sdd/91-agent-os-runspec-yaml-dag-parity.md",
        "docs/sdd/92-agent-os-runspec-yaml-semantic-parity.md",
        "docs/sdd/93-agent-os-runspec-yaml-schema-injection.md",
        "docs/sdd/94-agent-os-runspec-ao-preflight-compatibility.md",
        "docs/sdd/95-agent-os-router-default-state-version.md",
        "docs/sdd/96-agent-os-role-graph-backward-compat.md",
        "docs/sdd/97-remote-transfer-chunk-cleanup-invariants.md",
        "docs/sdd/98-remote-transfer-signed-bundle-tamper.md",
        "docs/sdd/99-remote-transfer-approval-expiry-rotation.md",
        "docs/sdd/100-remote-transfer-bundle-ordering-resume.md",
        "docs/sdd/101-remote-transfer-provider-redaction-round-trip.md",
        "docs/sdd/102-remote-transfer-network-retry-idempotency.md",
        "docs/sdd/103-remote-transfer-concurrent-transfer-collision.md",
        "docs/sdd/104-remote-transfer-bundle-schema-version-skew.md",
        "docs/sdd/105-remote-transfer-resource-exhaustion-guard.md",
        "docs/sdd/106-remote-transfer-clock-skew-tolerance.md",
        "docs/sdd/107-remote-transfer-bundle-id-uniqueness.md",
        "docs/sdd/108-remote-transfer-bundle-content-type-allowlist.md",
        "docs/sdd/109-remote-transfer-per-tenant-quota-isolation.md",
        "docs/sdd/110-remote-transfer-wire-encryption-required.md",
        "docs/sdd/111-remote-transfer-sender-identity-rotation.md",
        "docs/sdd/112-ai-agent-blast-radius-inventory.md",
        "docs/sdd/113-ai-agent-destructive-action-approval.md",
        "docs/sdd/114-ai-agent-credential-reachability.md",
        "docs/sdd/115-ai-agent-instruction-packaging-leak-detection.md",
        "docs/sdd/116-mcp-tool-poisoning-detection.md",
        "docs/sdd/117-deepsec-diff-review-advisory-sast.md",
        "docs/sdd/118-agent-supply-chain-integrity.md",
        "docs/sdd/119-prompt-injection-escape-boundary.md",
        "docs/sdd/120-approval-clock-skew-defense.md",
        "docs/sdd/121-agent-log-redaction-round-trip.md",
        "docs/sdd/122-per-tenant-blast-radius-cap.md",
        "docs/sdd/123-sandbox-egress-allowlist.md",
        "docs/sdd/124-agent-tool-arg-injection-escape.md",
        "docs/sdd/125-agent-output-canary-leak-detection.md",
        "docs/sdd/126-agent-os-execution-budget-enforcement.md",
        "docs/sdd/127-agent-system-prompt-tamper-detection.md",
        "docs/sdd/128-tool-result-cache-poisoning-defense.md",
        "docs/sdd/129-agent-credential-scope-narrowing.md",
        "docs/sdd/131-evidence-pack-v1.md",
    ]:
        write_text(root / path, "# SDD\n\n## Verification\n")
    base = root / "run-artifacts/remote-transfer-v2-stress-live"
    write_json(base / "remote-transfer-hardening.json", {"schema": "ao-operator/remote-transfer-hardening/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "public-release-security-surface.json", {"schema": "ao-operator/public-release-security/v1", "verdict": "PASS", "blocking_findings": 0, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "dast-readiness.json", {"schema": "ao-operator/dast-readiness/v1", "verdict": "PASS", "remote_dast_enabled": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "security-sdlc-roadmap.json", {"schema": "ao-operator/security-sdlc-roadmap/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "security-threat-model.json", {"schema": "ao-operator/security-threat-model/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "manual-pentest-gate.json", {"schema": "ao-operator/manual-pentest-gate/v1", "verdict": "PASS", "manual_pentest_authorized": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "host-key-evidence.json", {"schema": "ao-operator/host-key-evidence/v1", "verdict": "PASS", "host_key_evidence_required": True, "remote_dast_authorized": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "manual-pentest-report-classifier.json", {"schema": "ao-operator/manual-pentest-report-classifier/v1", "verdict": "PASS", "report_template_ready": True, "manual_pentest_authorized": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "supply-chain-gate.json", {"schema": "ao-operator/supply-chain-gate/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "resource-performance-gate.json", {"schema": "ao-operator/resource-performance-gate/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-runspec-execution-approval-bundle.json", {"schema": "ao-operator/agent-os-execution-approval-bundle/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "operator-guardrail-summary.json", {"schema": "ao-operator/operator-guardrail-summary/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-materialization.json", {"schema": "ao-operator/agent-os-approval-materialization/v1", "verdict": "PASS", "approval_file_written": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-lifecycle.json", {"schema": "ao-operator/agent-os-approval-lifecycle/v1", "verdict": "PASS", "approval_file_present": False, "approval_usable": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approved-launch-proof.json", {"schema": "ao-operator/agent-os-approved-launch-proof/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-cleanup.json", {"schema": "ao-operator/agent-os-approval-cleanup/v1", "verdict": "PASS", "removed": False, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-audit.json", {"schema": "ao-operator/agent-os-approval-audit-history/v1", "verdict": "PASS", "event_count": 1, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-post-approval-cleanup-route.json", {"schema": "ao-operator/agent-os-post-approval-cleanup-route/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-runbook.json", {"schema": "ao-operator/agent-os-approval-runbook/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-audit-retention.json", {"schema": "ao-operator/agent-os-approval-audit-retention/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-bundle-signature-report.json", {"schema": "ao-operator/agent-os-approval-bundle-signature/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-revocation.json", {"schema": "ao-operator/agent-os-approval-revocation/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-identity-signature.json", {"schema": "ao-operator/agent-os-approval-identity-signature/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-revocation-apply-proof.json", {"schema": "ao-operator/agent-os-approval-revocation-apply-proof/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-approval-audit-archive-restore.json", {"schema": "ao-operator/agent-os-approval-audit-archive-restore/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-approval-artifact-parity.json", {"schema": "ao-operator/mac-ubuntu-approval-artifact-parity/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-signed-approval-bundle-transfer.json", {"schema": "ao-operator/mac-ubuntu-signed-approval-bundle-transfer/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-remote-approval-materialization-dry-run.json", {"schema": "ao-operator/mac-ubuntu-remote-approval-materialization-dry-run/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-remote-approval-revocation-rollback.json", {"schema": "ao-operator/mac-ubuntu-remote-approval-revocation-rollback/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-remote-approval-runbook.json", {"schema": "ao-operator/mac-ubuntu-remote-approval-runbook/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "mac-ubuntu-remote-approved-fixture.json", {"schema": "ao-operator/mac-ubuntu-remote-approved-fixture/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-architecture-implementation-gate.json", {"schema": "ao-operator/agent-os-architecture-implementation-gate/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-router-transition-matrix.json", {"schema": "ao-operator/agent-os-router-transition-matrix/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-runspec-failure-injection-matrix.json", {"schema": "ao-operator/agent-os-runspec-failure-injection-matrix/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "operator-safe-next-command.json", {"schema": "ao-operator/operator-safe-next-command/v1", "verdict": "PASS", "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-runspec-dag-edge-coverage.json", {"schema": "ao-operator/agent-os-runspec-dag-edge-coverage/v1", "verdict": "PASS", "task_count": 7, "edge_count": 6, "role_graph_alignment": True, "mutation_case_count": 5, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-runspec-yaml-dag-parity.json", {"schema": "ao-operator/agent-os-runspec-yaml-dag-parity/v1", "verdict": "PASS", "task_count": 7, "yaml_edge_count": 6, "renderer_edge_count": 6, "role_graph_edge_count": 6, "yaml_renderer_alignment": True, "yaml_role_graph_alignment": True, "mutation_case_count": 4, "dispatch_authorized": False, "live_providers_run": False})
    write_json(base / "agent-os-runspec-yaml-semantic-parity.json", {"schema": "ao-operator/agent-os-runspec-yaml-semantic-parity/v1", "verdict": "PASS", "task_count": 7, "renderer_task_count": 7, "aligned_task_count": 7, "drifted_task_count": 0, "all_aligned": True, "mutation_case_count": 6, "dispatch_authorized": False, "live_providers_run": False})
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
    write_json(
        base / "live-evidence-pack-replay-gate.json",
        {
            "schema": "ao-operator/live-evidence-pack-replay-gate/v1",
            "verdict": "PASS",
            "summary_count": 1,
            "summaries": [
                {
                    "path": "run-artifacts/evidence-profile-live-proof/evidence-packs/evidence-pack-r-evidence-profile-live-proof-summary.json",
                    "run_id": "r-evidence-profile-live-proof",
                    "verify_verdict": "PASS",
                    "replay_verdict": "PASS",
                    "deterministic_task_count": 1,
                    "deterministic_command_execution": "PASS",
                    "verdict": "PASS",
                }
            ],
            "errors": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )
    write_json(
        root / "run-artifacts/release-v0.7/provider-smoke/provider-oauth-smoke.json",
        {
            "schema": "ao-operator/provider-oauth-smoke/v1",
            "verdict": "PASS",
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def test_release_artifact_index_links_sdd_and_status_reports(tmp_path):
    seed_artifacts(tmp_path)

    payload = check_release_artifact_index.build_index(root=tmp_path)

    assert payload["schema"] == "ao-operator/release-artifact-index/v1"
    assert payload["verdict"] == "PASS"
    assert payload["artifact_count"] == 77
    assert payload["sdd_count"] == 76
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["artifacts"]["operator_guardrail_summary"]["verdict"] == "PASS"
    assert payload["artifacts"]["public_release_security"]["verdict"] == "PASS"
    assert payload["artifacts"]["dast_readiness"]["verdict"] == "PASS"
    assert payload["artifacts"]["manual_pentest_gate"]["verdict"] == "PASS"
    assert payload["artifacts"]["host_key_evidence"]["verdict"] == "PASS"
    assert payload["artifacts"]["manual_pentest_report_classifier"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_lifecycle"]["verdict"] == "PASS"
    assert payload["artifacts"]["approved_launch_proof"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_cleanup"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_audit_history"]["verdict"] == "PASS"
    assert payload["artifacts"]["post_approval_cleanup_route"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_runbook"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_audit_retention"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_bundle_signature"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_revocation"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_identity_signature"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_revocation_apply_proof"]["verdict"] == "PASS"
    assert payload["artifacts"]["approval_audit_archive_restore"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_approval_artifact_parity"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_signed_approval_bundle_transfer"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_remote_approval_materialization_dry_run"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_remote_approval_revocation_rollback"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_remote_approval_runbook"]["verdict"] == "PASS"
    assert payload["artifacts"]["mac_ubuntu_remote_approved_fixture"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_architecture_implementation_gate"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_router_transition_matrix"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_failure_injection_matrix"]["verdict"] == "PASS"
    assert payload["artifacts"]["operator_safe_next_command"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_dag_edge_coverage"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_yaml_dag_parity"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_yaml_semantic_parity"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_yaml_schema_injection"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_runspec_ao_preflight_compatibility"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_router_default_state_version"]["verdict"] == "PASS"
    assert payload["artifacts"]["agent_os_role_graph_backward_compat"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_chunk_cleanup_invariants"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_signed_bundle_tamper"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_approval_expiry_rotation"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_bundle_ordering_resume"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_provider_redaction_round_trip"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_network_retry_idempotency"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_concurrent_transfer_collision"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_bundle_schema_version_skew"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_resource_exhaustion_guard"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_clock_skew_tolerance"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_bundle_id_uniqueness"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_bundle_content_type_allowlist"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_per_tenant_quota_isolation"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_wire_encryption_required"]["verdict"] == "PASS"
    assert payload["artifacts"]["remote_transfer_sender_identity_rotation"]["verdict"] == "PASS"
    assert payload["artifacts"]["ai_agent_blast_radius_inventory"]["verdict"] == "PASS"
    assert payload["artifacts"]["live_evidence_pack_replay"]["verdict"] == "PASS"
    assert payload["artifacts"]["provider_oauth_smoke"]["verdict"] == "PASS"


def test_release_artifact_index_blocks_missing_or_failing_report(tmp_path):
    seed_artifacts(tmp_path)
    report = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    data["verdict"] = "FAIL"
    write_json(report, data)

    payload = check_release_artifact_index.build_index(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert "operator_guardrail_summary" in payload["blockers"]


def test_release_artifact_index_requires_evidence_profile_replay_proof(tmp_path):
    seed_artifacts(tmp_path)
    report = tmp_path / "run-artifacts/remote-transfer-v2-stress-live/live-evidence-pack-replay-gate.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    data["summaries"] = [
        {
            "path": "run-artifacts/deterministic-replay-live-proof/evidence-packs/evidence-pack-deterministicreplay01-summary.json",
            "run_id": "deterministicreplay01",
            "verify_verdict": "PASS",
            "replay_verdict": "PASS",
            "deterministic_task_count": 1,
            "deterministic_command_execution": "PASS",
            "verdict": "PASS",
        }
    ]
    write_json(report, data)

    payload = check_release_artifact_index.build_index(root=tmp_path)

    assert payload["verdict"] == "FAIL"
    assert "live_evidence_pack_replay" in payload["blockers"]
    assert "live_evidence_pack_replay must include evidence-profile-live-proof deterministic replay summary" in payload["errors"]


def test_release_artifact_index_cli_writes_output(tmp_path, capsys):
    seed_artifacts(tmp_path)
    output = tmp_path / "run-artifacts/index.json"

    code = check_release_artifact_index.main(["--root", str(tmp_path), "--write-output", str(output), "--json"])

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/release-artifact-index/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
