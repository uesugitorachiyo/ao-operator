#!/usr/bin/env python3
"""Validate AO Operator implementation and generated artifacts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import factory_profiles


ROOT = Path(__file__).resolve().parents[1]
VALID_PROVIDERS = {"claude", "codex", "antigravity"}

SDD_FILES = [
    "docs/sdd/README.md",
    "docs/sdd/01-architecture.md",
    "docs/sdd/02-implementation-plan.md",
    "docs/sdd/03-interfaces-and-contracts.md",
    "docs/sdd/04-verification-plan.md",
    "docs/sdd/05-rollout-and-risks.md",
    "docs/sdd/06-implementation-checklist.md",
    "docs/sdd/10-stress-topology.md",
    "docs/sdd/11-operator-slices.md",
    "docs/sdd/12-bounded-live-acceptance.md",
    "docs/sdd/13-agent-os.md",
    "docs/sdd/14-agent-os-mission-router-state.md",
    "docs/sdd/15-agent-os-codebase-specialists.md",
    "docs/sdd/16-agent-os-capability-validation.md",
    "docs/sdd/17-agent-os-phase-compiler.md",
    "docs/sdd/18-agent-os-phase-handoff.md",
    "docs/sdd/19-agent-os-uat-state.md",
    "docs/sdd/20-agent-os-learning-extract.md",
    "docs/sdd/21-agent-os-operator-cockpit.md",
    "docs/sdd/22-agent-os-uat-response-gate.md",
    "docs/sdd/23-agent-os-closure-gate.md",
    "docs/sdd/24-agent-os-runspec-renderer.md",
    "docs/sdd/25-agent-os-runspec-validation.md",
    "docs/sdd/26-agent-os-runspec-execution-approval-gate.md",
    "docs/sdd/27-agent-os-runspec-no-provider-rehearsal.md",
    "docs/sdd/28-agent-os-runspec-postrun-router.md",
    "docs/sdd/29-agent-os-runspec-diagnostics-preservation.md",
    "docs/sdd/30-agent-os-execution-approval-contract.md",
    "docs/sdd/31-agent-os-approval-only-execution-launcher.md",
    "docs/sdd/32-agent-os-evaluator-closure-contract.md",
    "docs/sdd/33-agent-os-role-output-schema.md",
    "docs/sdd/34-agent-os-execution-hygiene.md",
    "docs/sdd/35-agent-os-approved-execution-runner.md",
    "docs/sdd/36-agent-os-role-output-ingestion.md",
    "docs/sdd/37-public-release-security-and-dast.md",
    "docs/sdd/38-security-sdlc-roadmap.md",
    "docs/sdd/39-security-threat-model-data-flow.md",
    "docs/sdd/40-manual-penetration-test-gate.md",
    "docs/sdd/41-host-key-evidence-gate.md",
    "docs/sdd/42-manual-pentest-report-classifier.md",
    "docs/sdd/43-supply-chain-audit-gate.md",
    "docs/sdd/44-agent-os-role-graph-state-versioning.md",
    "docs/sdd/45-agent-os-accepted-execution-commit-guard.md",
    "docs/sdd/46-agent-os-postrun-route-matrix.md",
    "docs/sdd/47-agent-os-state-v2-persistence.md",
    "docs/sdd/48-agent-os-runspec-compatibility-matrix.md",
    "docs/sdd/49-agent-os-architecture-readiness-summary.md",
    "docs/sdd/50-agent-os-router-v2-state.md",
    "docs/sdd/51-agent-os-state-evidence-hygiene.md",
    "docs/sdd/52-agent-os-approved-execution-fixture.md",
    "docs/sdd/53-agent-os-router-migration-matrix.md",
    "docs/sdd/54-agent-os-runspec-provider-boundary-matrix.md",
    "docs/sdd/55-agent-os-state-stale-cleanup.md",
    "docs/sdd/56-agent-os-failed-diagnostics-fixture.md",
    "docs/sdd/57-agent-os-approval-alignment-drift.md",
    "docs/sdd/58-repeated-run-hygiene-baseline.md",
    "docs/sdd/59-normalized-failure-diagnostics.md",
    "docs/sdd/60-agent-os-runspec-state-v2-bridge.md",
    "docs/sdd/61-agent-os-runspec-execution-plan-lock.md",
    "docs/sdd/62-remote-transfer-hardening-evidence-gate.md",
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
]

RUNTIME_FILES = [
    "scripts/factory_run.py",
    "scripts/validate_factory.py",
    "scripts/factory_doctor.py",
    "scripts/render_runspec.py",
    "scripts/validate_scaffold.py",
    "scripts/validate.py",
    "scripts/validate_intake.py",
    "scripts/verify_closure.py",
    "scripts/code_smell_analyzer.py",
    "scripts/install_global.py",
    "scripts/generate_stress_fixture.py",
    "scripts/validate_operator_slices.py",
    "scripts/run_operator_slice.py",
    "scripts/check_live_acceptance.py",
    "scripts/check_bounded_live_readiness.py",
    "scripts/prepare_live_profile_dry_run.py",
    "scripts/check_50_slice_live_approval_gate.py",
    "scripts/check_50_slice_provider_budget.py",
    "scripts/rehearse_50_slice_live_sequence.py",
    "scripts/run_50_slice_live.py",
    "scripts/route_50_slice_live_postrun.py",
    "scripts/summarize_50_slice_operator_state.py",
    "scripts/check_1000_slice_guardrail.py",
    "scripts/check_next_escalation_profile.py",
    "scripts/check_75_slice_live_approval_sdd.py",
    "scripts/check_agent_os_sdd.py",
    "scripts/agent_os_router.py",
    "scripts/agent_os_codebase_map.py",
    "scripts/agent_os_capability_validator.py",
    "scripts/agent_os_phase_compiler.py",
    "scripts/agent_os_phase_handoff.py",
    "scripts/agent_os_uat_state.py",
    "scripts/agent_os_learning_extract.py",
    "scripts/agent_os_operator_cockpit.py",
    "scripts/agent_os_uat_response_gate.py",
    "scripts/agent_os_closure_gate.py",
    "scripts/agent_os_runspec_renderer.py",
    "scripts/agent_os_runspec_validator.py",
    "scripts/check_agent_os_runspec_execution_approval_gate.py",
    "scripts/rehearse_agent_os_runspec_execution.py",
    "scripts/route_agent_os_runspec_postrun.py",
    "scripts/preserve_agent_os_runspec_diagnostics.py",
    "scripts/validate_agent_os_runspec_execution_approval.py",
    "scripts/run_agent_os_runspec_execution.py",
    "scripts/validate_agent_os_runspec_evaluator_closure.py",
    "scripts/check_agent_os_role_output_schema.py",
    "scripts/check_agent_os_execution_hygiene.py",
    "scripts/ingest_agent_os_role_outputs.py",
    "scripts/check_public_release_security.py",
    "scripts/redact_strict_public_artifacts.py",
    "scripts/check_status_json_integrity.py",
    "scripts/check_dast_readiness.py",
    "scripts/check_security_sdlc_roadmap.py",
    "scripts/check_security_threat_model.py",
    "scripts/check_pentest_gate.py",
    "scripts/check_host_key_evidence.py",
    "scripts/classify_pentest_report.py",
    "scripts/check_supply_chain_gate.py",
    "scripts/check_clean_clone_readiness.py",
    "scripts/agent_os_role_graph.py",
    "scripts/check_agent_os_accepted_execution_commit_guard.py",
    "scripts/check_agent_os_postrun_route_matrix.py",
    "scripts/agent_os_state_v2.py",
    "scripts/check_agent_os_runspec_compatibility_matrix.py",
    "scripts/summarize_agent_os_architecture_readiness.py",
    "scripts/check_agent_os_state_evidence_hygiene.py",
    "scripts/check_agent_os_approved_execution_fixture.py",
    "scripts/check_agent_os_approval_alignment_drift.py",
    "scripts/check_agent_os_failed_diagnostics_fixture.py",
    "scripts/check_agent_os_router_migration_matrix.py",
    "scripts/check_agent_os_runspec_provider_boundary_matrix.py",
    "scripts/cleanup_agent_os_state_artifacts.py",
    "scripts/check_repeated_run_hygiene.py",
    "scripts/check_normalized_failure_diagnostics.py",
    "scripts/check_remote_transfer_hardening.py",
    "scripts/check_resource_performance_gate.py",
    "scripts/generate_agent_os_approval_bundle.py",
    "scripts/check_operator_guardrail_summary.py",
    "scripts/materialize_agent_os_approval.py",
    "scripts/check_release_artifact_index.py",
    "scripts/check_agent_os_approval_lifecycle.py",
    "scripts/check_agent_os_approved_launch_proof.py",
    "scripts/cleanup_agent_os_approval.py",
    "scripts/check_agent_os_approval_audit_history.py",
    "scripts/check_agent_os_post_approval_cleanup_route.py",
    "scripts/check_agent_os_approval_runbook.py",
    "scripts/check_agent_os_approval_audit_retention.py",
    "scripts/check_agent_os_approval_bundle_signature.py",
    "scripts/check_agent_os_approval_revocation.py",
    "scripts/check_agent_os_approval_identity_signature.py",
    "scripts/check_agent_os_approval_revocation_apply_proof.py",
    "scripts/check_agent_os_approval_audit_archive_restore.py",
    "scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py",
    "scripts/check_mac_ubuntu_remote_approval_materialization_dry_run.py",
    "scripts/check_mac_ubuntu_remote_approval_revocation_rollback.py",
    "scripts/check_mac_ubuntu_remote_approval_runbook.py",
    "scripts/check_mac_ubuntu_remote_approved_fixture.py",
    "scripts/check_agent_os_architecture_implementation_gate.py",
    "scripts/check_agent_os_router_transition_matrix.py",
    "scripts/check_agent_os_runspec_failure_injection_matrix.py",
    "scripts/check_operator_safe_next_command.py",
    "scripts/check_agent_os_runspec_dag_edge_coverage.py",
    "scripts/check_agent_os_runspec_yaml_dag_parity.py",
    "scripts/check_agent_os_runspec_yaml_semantic_parity.py",
    "scripts/check_agent_os_runspec_yaml_schema_injection.py",
    "scripts/check_agent_os_runspec_ao_preflight_compatibility.py",
    "scripts/check_agent_os_router_default_state_version.py",
    "scripts/check_agent_os_role_graph_backward_compat.py",
    "scripts/check_remote_transfer_chunk_cleanup_invariants.py",
    "scripts/check_remote_transfer_signed_bundle_tamper.py",
    "scripts/check_remote_transfer_approval_expiry_rotation.py",
    "scripts/check_remote_transfer_bundle_ordering_resume.py",
    "scripts/check_remote_transfer_provider_redaction_round_trip.py",
    "scripts/check_remote_transfer_network_retry_idempotency.py",
    "scripts/check_remote_transfer_concurrent_transfer_collision.py",
    "scripts/check_remote_transfer_bundle_schema_version_skew.py",
    "scripts/check_remote_transfer_resource_exhaustion_guard.py",
    "scripts/check_remote_transfer_clock_skew_tolerance.py",
    "scripts/check_remote_transfer_bundle_id_uniqueness.py",
    "scripts/check_remote_transfer_bundle_content_type_allowlist.py",
    "scripts/check_remote_transfer_per_tenant_quota_isolation.py",
    "scripts/check_remote_transfer_wire_encryption_required.py",
    "scripts/check_remote_transfer_sender_identity_rotation.py",
    "scripts/check_ai_agent_blast_radius_inventory.py",
    "scripts/check_ai_agent_destructive_action_approval.py",
    "scripts/check_ai_agent_credential_reachability.py",
    "scripts/check_ai_agent_instruction_packaging_leak_detection.py",
    "scripts/check_mcp_tool_poisoning_detection.py",
    "scripts/check_deepsec_diff_review_advisory_sast.py",
    "scripts/check_agent_supply_chain_integrity.py",
    "scripts/check_prompt_injection_escape_boundary.py",
    "scripts/check_approval_clock_skew_defense.py",
    "scripts/check_agent_log_redaction_round_trip.py",
    "scripts/check_per_tenant_blast_radius_cap.py",
    "scripts/check_sandbox_egress_allowlist.py",
    "scripts/check_agent_tool_arg_injection_escape.py",
    "scripts/check_agent_output_canary_leak_detection.py",
    "scripts/check_agent_os_execution_budget_enforcement.py",
    "scripts/check_agent_system_prompt_tamper_detection.py",
    "scripts/check_tool_result_cache_poisoning_defense.py",
    "scripts/check_agent_credential_scope_narrowing.py",
]

SKILL_FILES = [
    "skills.toml",
    "skills/README.md",
    "skills/factory-intake/SKILL.md",
    "skills/context-offload/SKILL.md",
    "skills/closure-verification/SKILL.md",
    "skills/mission-monitor-ops/SKILL.md",
    "skills/spec-forge-contracting/SKILL.md",
    "skills/llm-wiki-lookup/SKILL.md",
]

TASK_IDS = [
    "planner-intake",
    "plan-hardener",
    "factory-manager",
    "implementer-slice",
    "reviewer-slice",
    "integrator",
    "evaluator-closer",
]


def parse_inline_list(value: str) -> list[str]:
    return re.findall(r'"([^"]+)"', value)


def parse_topology(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_absolute():
        path = ROOT / path
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [idx for idx, line in enumerate(lines) if re.match(r"\s{4}- id:\s*", line)]
    tasks: dict[str, dict[str, object]] = {}
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        block = lines[start:end]
        task_id = block[0].split(":", 1)[1].strip().strip('"')
        deps: list[str] = []
        spec: dict[str, str] = {}
        dep_idx = next((i for i, line in enumerate(block) if re.match(r"\s+deps:\s*", line)), None)
        spec_idx = next((i for i, line in enumerate(block) if re.match(r"\s+spec:\s*$", line)), len(block))
        if dep_idx is not None:
            after = block[dep_idx].split(":", 1)[1].strip()
            if after.startswith("["):
                deps = parse_inline_list(after)
            else:
                for line in block[dep_idx + 1 : spec_idx]:
                    match = re.match(r"\s+-\s+(.+?)\s*$", line)
                    if match:
                        deps.append(match.group(1).strip().strip('"'))
        for line in block[spec_idx + 1 :]:
            match = re.match(r"\s{8}([A-Za-z][A-Za-z0-9_]*):\s*(.+?)\s*$", line)
            if match:
                spec[match.group(1)] = match.group(2).strip().strip('"')
        tasks[task_id] = {"deps": deps, "spec": spec}
    return tasks


def check_contract(results: list[dict[str, str]], contract_path: Path | None) -> dict[str, object] | None:
    if not contract_path:
        return None
    if not contract_path.is_absolute():
        contract_path = ROOT / contract_path
    add(results, "contract.file", contract_path.is_file(), display_path(contract_path) if contract_path.is_file() else "missing")
    if not contract_path.is_file():
        return None
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        add(results, "contract.json", False, str(exc))
        return None
    required = ["shalls", "acceptance_criteria", "sensitive_fields", "negative_constraints", "slices"]
    for key in required:
        add(results, f"contract.field:{key}", bool(data.get(key)), key)
    slices = data.get("slices", [])
    inferred_slice_count = infer_expected_slice_count(data)
    actual_slice_count = len(slices) if isinstance(slices, list) else 0
    count_ok = actual_slice_count == inferred_slice_count if inferred_slice_count else actual_slice_count >= 5
    count_message = (
        f"{actual_slice_count} slice(s), expected {inferred_slice_count}"
        if inferred_slice_count
        else f"{actual_slice_count} slice(s)"
    )
    add(results, "contract.slices.count", isinstance(slices, list) and count_ok, count_message)
    if isinstance(slices, list):
        slice_ids: list[str] = []
        write_owners: dict[str, str] = {}
        duplicate_writes: list[str] = []
        for item in slices:
            if isinstance(item, dict):
                sid = str(item.get("id", "unknown"))
                slice_ids.append(sid)
                add(results, f"contract.slice:{sid}.reads", bool(item.get("reads")), "reads declared")
                add(results, f"contract.slice:{sid}.writes", bool(item.get("writes")), "writes declared")
                writes = item.get("writes", [])
                if isinstance(writes, list):
                    for write_path in [str(value) for value in writes]:
                        previous = write_owners.setdefault(write_path, sid)
                        if previous != sid:
                            duplicate_writes.append(f"{write_path} ({previous}, {sid})")
        duplicate_ids = sorted({sid for sid in slice_ids if slice_ids.count(sid) > 1})
        add(
            results,
            "contract.slices.unique_ids",
            not duplicate_ids,
            "unique slice ids" if not duplicate_ids else "duplicate ids: " + ", ".join(duplicate_ids),
        )
        add(
            results,
            "contract.slices.disjoint_writes",
            not duplicate_writes,
            "disjoint writes" if not duplicate_writes else "overlap: " + "; ".join(sorted(duplicate_writes)),
        )
    return data


def runspec_prompt_targets_slug(body: str, *, slug: str, task_id: str) -> tuple[bool, str]:
    expected_prompt = f"run-artifacts/{slug}/prompts/{task_id}.md"
    legacy_prompt = "/".join(["docs", "status", slug, "prompts", f"{task_id}.md"])
    public_prompt = f"run-artifacts/{slug}/prompts/{task_id}.md"
    normalized_body = body.replace("\\", "/")
    if (
        expected_prompt in normalized_body
        or legacy_prompt in normalized_body
        or public_prompt in normalized_body
    ):
        return True, expected_prompt

    task_marker = f"- id: {task_id}"
    start = body.find(task_marker)
    if start < 0:
        return False, "task missing from RunSpec"
    next_task = body.find("\n    - id: ", start + len(task_marker))
    task_block = body[start:] if next_task < 0 else body[start:next_task]
    prompt_candidates = [
        ROOT / "run-artifacts" / slug / "prompts" / f"{task_id}.md",
        ROOT / "run-artifacts" / slug / "prompts" / f"{task_id}.md",
    ]
    if "promptFile: [REDACTED_LOCAL_PATH]" in task_block and any(
        prompt.is_file() for prompt in prompt_candidates
    ):
        return True, "redacted promptFile with matching prompt artifact"
    return False, "promptFile does not target generated slug"


def check_topology(
    results: list[dict[str, str]],
    slug: str,
    topology_path: Path | None,
    contract: dict[str, object] | None = None,
) -> list[str]:
    if not topology_path:
        return TASK_IDS
    if not topology_path.is_absolute():
        topology_path = ROOT / topology_path
    add(results, "topology.file", topology_path.is_file(), display_path(topology_path) if topology_path.is_file() else "missing")
    if not topology_path.is_file():
        return TASK_IDS
    tasks = parse_topology(topology_path)
    task_ids = list(tasks)
    expected_factories = contract_factory_ids(contract)
    expected_task_count = (len(expected_factories) * 2) + 7 if expected_factories else None
    expected_chain = {
        "spec-forge-contract": ["planner-intake"],
        "ralph-loop": ["spec-forge-contract"],
        "plan-hardener": ["ralph-loop"],
        "factory-manager": ["plan-hardener"],
        "evaluator-closer": ["integrator"],
    }
    task_count_ok = len(tasks) == expected_task_count if expected_task_count else len(tasks) >= 7
    task_count_message = (
        f"{len(tasks)} task(s), expected {expected_task_count}"
        if expected_task_count
        else f"{len(tasks)} task(s)"
    )
    add(results, "topology.task_count", task_count_ok, task_count_message)
    for task_id in ["planner-intake", "spec-forge-contract", "ralph-loop", "plan-hardener", "factory-manager", "integrator", "evaluator-closer"]:
        add(results, f"topology.required:{task_id}", task_id in tasks, "present" if task_id in tasks else "missing")
    for task_id, deps in expected_chain.items():
        add(results, f"topology.deps:{task_id}", tasks.get(task_id, {}).get("deps") == deps, str(tasks.get(task_id, {}).get("deps")))
    factories = [task_id for task_id in tasks if task_id.endswith("-factory") and task_id != "factory-manager"]
    reviewers = [task_id for task_id in tasks if task_id.endswith("-reviewer")]
    factories_ok = len(factories) == len(expected_factories) if expected_factories else len(factories) >= 1
    factories_message = (
        f"{len(factories)} factor(y/ies), expected {len(expected_factories)}"
        if expected_factories
        else f"{len(factories)} factor(y/ies)"
    )
    add(results, "topology.factories.count", factories_ok, factories_message)
    add(results, "topology.reviewers.count", len(reviewers) == len(factories), f"{len(reviewers)} reviewer(s)")
    if expected_factories:
        missing_factories = sorted(set(expected_factories) - set(factories))
        extra_factories = sorted(set(factories) - set(expected_factories))
        add(
            results,
            "topology.factories.match_contract",
            not missing_factories and not extra_factories,
            "factories match contract slices"
            if not missing_factories and not extra_factories
            else "extra=" + ",".join(extra_factories) + " missing=" + ",".join(missing_factories),
        )
    for factory in factories:
        add(results, f"topology.factory_dep:{factory}", tasks[factory]["deps"] == ["factory-manager"], str(tasks[factory]["deps"]))
        expected_reviewer = factory.removesuffix("-factory") + "-reviewer"
        add(results, f"topology.factory_reviewer:{factory}", expected_reviewer in reviewers, expected_reviewer)
    for reviewer in reviewers:
        expected = [reviewer.removesuffix("-reviewer") + "-factory"]
        add(results, f"topology.reviewer_dep:{reviewer}", tasks[reviewer]["deps"] == expected, str(tasks[reviewer]["deps"]))
    integrator_deps = set(tasks.get("integrator", {}).get("deps", []))
    add(results, "topology.integrator_deps", set(reviewers).issubset(integrator_deps), ",".join(sorted(integrator_deps)))
    runspec = ROOT / "run-artifacts" / slug / f"{slug}.runspec.yaml"
    if runspec.is_file():
        body = runspec.read_text(encoding="utf-8")
        for task_id in task_ids:
            add(results, f"runspec.task:{task_id}", f"- id: {task_id}" in body, "present" if f"- id: {task_id}" in body else "missing")
            prompt_ok, prompt_message = runspec_prompt_targets_slug(body, slug=slug, task_id=task_id)
            add(
                results,
                f"runspec.prompt:{task_id}",
                prompt_ok,
                prompt_message,
            )
    return task_ids


def check_profile(results: list[dict[str, str]], profile: str) -> list[str]:
    try:
        data = factory_profiles.load_profile(profile, repo_root=ROOT)
    except (FileNotFoundError, factory_profiles.ProfileError, json.JSONDecodeError) as exc:
        add(results, f"profile.file:{profile}", False, str(exc))
        return TASK_IDS
    add(results, f"profile.file:{profile}", True, f"profile {profile!r} loaded")
    add(results, f"profile.schema:{profile}", data.get("schema") == "ao-operator/profile/v1", str(data.get("schema")))
    roles = data.get("roles", [])
    add(results, f"profile.roles:{profile}", isinstance(roles, list) and bool(roles), f"{len(roles) if isinstance(roles, list) else 0} role(s)")
    task_ids = [str(role.get("id")) for role in roles if isinstance(role, dict) and role.get("id")]
    add(results, f"profile.task_ids:{profile}", bool(task_ids), ",".join(task_ids) if task_ids else "missing")
    return task_ids or TASK_IDS


def infer_expected_slice_count(contract: dict[str, object]) -> int | None:
    text_fields: list[str] = []
    for key in ["objective", "problem"]:
        value = contract.get(key)
        if isinstance(value, str):
            text_fields.append(value)
    for key in ["success_criteria", "constraints", "negative_constraints"]:
        value = contract.get(key, [])
        if isinstance(value, list):
            text_fields.extend(str(item) for item in value)
    for key in ["shalls", "acceptance_criteria"]:
        value = contract.get(key, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text_fields.extend(str(v) for v in item.values())
                else:
                    text_fields.append(str(item))
    matches: list[int] = []
    for text in text_fields:
        matches.extend(int(match) for match in re.findall(r"\b(\d+)\s+(?:disjoint\s+)?(?:implementation\s+)?(?:remote transfer v2\s+)?slices?\b", text, flags=re.IGNORECASE))
    return max(matches) if matches else None


def contract_factory_ids(contract: dict[str, object] | None) -> list[str]:
    if not contract:
        return []
    slices = contract.get("slices", [])
    if not isinstance(slices, list):
        return []
    ids = [str(item.get("id", "")) for item in slices if isinstance(item, dict)]
    return ids if ids and all(item.endswith("-factory") for item in ids) else []


def contract_requires_dry_run_status(contract: dict[str, object] | None) -> bool:
    if not contract:
        return False
    criteria = contract.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        return False
    for item in criteria:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(value) for value in item.values()).lower()
        if "status" in text and "mode dry-run" in text:
            return True
    return False


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def add(results: list[dict[str, str]], check_id: str, ok: bool, message: str) -> None:
    results.append({"id": check_id, "status": "ok" if ok else "fail", "message": message})


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def git_tracking_available() -> bool:
    return (ROOT / ".git").exists()


def git_tracked(path: Path) -> bool:
    if not git_tracking_available():
        return True
    try:
        relpath = path.relative_to(ROOT)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(relpath)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_file_set(results: list[dict[str, str]], files: list[str], prefix: str) -> None:
    for rel in files:
        path = ROOT / rel
        add(results, f"{prefix}:{rel}", path.is_file(), "present" if path.is_file() else "missing")


def check_docs(results: list[dict[str, str]]) -> None:
    check_file_set(results, SDD_FILES, "sdd")
    readme = ROOT / "README.md"
    factory_doc = ROOT / "ao-operator.md"
    factory_doc_body = factory_doc.read_text(encoding="utf-8") if factory_doc.is_file() else ""
    add(
        results,
        "root.readme.sdd_link",
        readme.is_file() and "docs/sdd/" in readme.read_text(encoding="utf-8"),
        "README links docs/sdd/",
    )
    add(
        results,
        "root.factory_v3.source_of_truth",
        "docs/sdd/" in factory_doc_body
        and re.search(r"source\s+of\s+truth", factory_doc_body, re.IGNORECASE) is not None,
        "ao-operator.md names docs/sdd/ source of truth",
    )


def check_runtime(results: list[dict[str, str]]) -> None:
    check_file_set(results, RUNTIME_FILES, "runtime")
    check_file_set(results, SKILL_FILES, "skills")
    env = parse_env(ROOT / ".env.example")
    provider_keys = [key for key in env if key.startswith("FACTORY_V3_") and key.endswith("_PROVIDER")]
    provider_keys.append("FACTORY_V3_DEFAULT_PROVIDER")
    for key in sorted(set(provider_keys)):
        add(
            results,
            f"env.example:{key}",
            env.get(key) in VALID_PROVIDERS,
            f"{key}={env.get(key)}",
        )


def prompt_safe(path: Path) -> tuple[bool, str]:
    body = path.read_text(encoding="utf-8")
    required = [
        "Do not include full transcripts",
        "Do not include secret values",
        "Scoped Context",
        "Injected Artifact Contents",
        "Required STATUS Block",
    ]
    missing = [item for item in required if item not in body]
    if missing:
        return False, "missing " + ", ".join(missing)
    if re.search(r"(OPENAI_API_KEY|ANTHROPIC_API_KEY)\s*=", body):
        return False, "prompt contains secret-looking env assignment"
    return True, "scoped handoff prompt"


def prompt_skills_ok(path: Path) -> tuple[bool, str]:
    body = path.read_text(encoding="utf-8")
    if "## Relevant Skills" not in body:
        return False, "missing Relevant Skills section"
    if "skills/factory-intake/SKILL.md" not in body:
        return False, "missing factory-intake skill reference"
    return True, "skill references present"


def role_contract_ok(path: Path) -> tuple[bool, str]:
    body = path.read_text(encoding="utf-8")
    required = ["Result:", "Artifact:", "Evidence:", "Concerns:", "Blocker:"]
    missing = [item for item in required if item not in body]
    return (not missing, "role contract present" if not missing else "missing " + ", ".join(missing))


def role_result(path: Path) -> str | None:
    body = path.read_text(encoding="utf-8")
    before_captured_status = body.split("## Captured STATUS", 1)[0]
    match = re.search(r"(?m)^Result:\s*([A-Z_]+)\s*$", before_captured_status)
    return match.group(1) if match else None


def is_load_bearing_role(task_id: str) -> bool:
    return (
        task_id in {"implementer-slice", "reviewer-slice", "integrator", "evaluator-closer"}
        or bool(re.fullmatch(r"(implementer|reviewer)-slice-\d+", task_id))
        or (task_id.endswith("-factory") and task_id != "factory-manager")
        or task_id.endswith("-reviewer")
    )


def materialized_task_ids(task_ids: list[str], prompts_dir: Path, roles_dir: Path) -> list[str]:
    expanded: list[str] = []
    for task_id in task_ids:
        if (prompts_dir / f"{task_id}.md").is_file() or (roles_dir / f"{task_id}.md").is_file():
            expanded.append(task_id)
            continue
        suffixed = sorted(
            {
                path.stem
                for root in [prompts_dir, roles_dir]
                if root.is_dir()
                for path in root.glob(f"{task_id}-*.md")
                if re.fullmatch(rf"{re.escape(task_id)}-\d+", path.stem)
            },
            key=lambda value: int(value.rsplit("-", 1)[1]),
        )
        expanded.extend(suffixed or [task_id])
    return expanded


def check_slug(
    results: list[dict[str, str]],
    slug: str,
    task_ids: list[str],
    exact_prompts: bool = False,
    contract: dict[str, object] | None = None,
    require_tracked_roles: bool = True,
    allow_missing_evaluation: bool = False,
) -> None:
    spec = ROOT / "docs" / "specs" / f"{slug}-spec.md"
    plan = ROOT / "docs" / "plans" / f"{slug}-plan.md"
    status_dir = ROOT / "run-artifacts" / slug
    runspec = status_dir / f"{slug}.runspec.yaml"
    status = status_dir / f"{slug}-status.md"
    prompts_dir = status_dir / "prompts"
    roles_dir = status_dir / "roles"
    events = status_dir / f"{slug}-ao-events.md"
    evaluation = ROOT / "docs" / "evaluations" / f"{slug}-evaluation.md"

    for check_id, path in [
        ("artifact.spec", spec),
        ("artifact.plan", plan),
        ("artifact.runspec", runspec),
        ("artifact.status", status),
        ("artifact.prompts_dir", prompts_dir),
    ]:
        add(results, f"{check_id}:{slug}", path.exists(), str(path.relative_to(ROOT)) if path.exists() else "missing")
    if contract_requires_dry_run_status(contract) and status.is_file():
        status_body_text = status.read_text(encoding="utf-8")
        add(
            results,
            f"artifact.status_mode:{slug}",
            "Mode: dry-run" in status_body_text,
            "Mode: dry-run" if "Mode: dry-run" in status_body_text else "dry-run status mode missing",
        )

    task_ids = materialized_task_ids(task_ids, prompts_dir, roles_dir)
    runspec_body = runspec.read_text(encoding="utf-8") if runspec.is_file() else ""
    for task_id in task_ids:
        prompt = prompts_dir / f"{task_id}.md"
        add(results, f"artifact.prompt:{task_id}", prompt.is_file(), "present" if prompt.is_file() else "missing")
        if runspec_body and "- id:" in runspec_body:
            add(results, f"runspec.task:{task_id}", f"- id: {task_id}" in runspec_body, "present" if f"- id: {task_id}" in runspec_body else "missing")
            prompt_ok, prompt_message = runspec_prompt_targets_slug(runspec_body, slug=slug, task_id=task_id)
            add(results, f"runspec.prompt:{task_id}", prompt_ok, prompt_message)
        if prompt.is_file():
            ok, message = prompt_safe(prompt)
            add(results, f"handoff.prompt_safe:{task_id}", ok, message)
            ok, message = prompt_skills_ok(prompt)
            add(results, f"handoff.prompt_skills:{task_id}", ok, message)
    if exact_prompts and prompts_dir.is_dir():
        actual = {path.stem for path in prompts_dir.glob("*.md")}
        expected = set(task_ids)
        extras = sorted(actual - expected)
        missing = sorted(expected - actual)
        add(
            results,
            f"artifact.prompts_exact:{slug}",
            not extras and not missing,
            "prompt set matches topology" if not extras and not missing else "extra=" + ",".join(extras) + " missing=" + ",".join(missing),
        )

    live_artifacts_required = False
    evaluation_body = ""
    if evaluation.is_file():
        evaluation_body = evaluation.read_text(encoding="utf-8")
        live_artifacts_required = bool(re.search(r"AO Run:\s+r-", evaluation_body))
    elif allow_missing_evaluation and events.is_file():
        live_artifacts_required = True
    accepted_evaluation = "Verdict: ACCEPTED" in evaluation_body

    if events.is_file() or evaluation.is_file():
        if live_artifacts_required:
            add(results, f"artifact.events:{slug}", events.is_file(), "present" if events.is_file() else "missing")
        if evaluation.is_file() or not allow_missing_evaluation:
            add(results, f"artifact.evaluation:{slug}", evaluation.is_file(), "present" if evaluation.is_file() else "missing")
        if evaluation.is_file():
            body = evaluation_body
            has_verdict = (
                "Verdict: ACCEPTED" in body
                or "Verdict: REJECTED" in body
                or "Verdict: BLOCKED" in body
            )
            add(results, f"evaluation.verdict:{slug}", has_verdict, "verdict present" if has_verdict else "missing verdict")
            for needle in ["Spec:", "Plan:", "AO Run:", "Evidence:", "Blockers:"]:
                add(results, f"evaluation.field:{needle}", needle in body, needle)
        if live_artifacts_required:
            role_blockers: list[str] = []
            ignored_control_blockers: list[str] = []
            for task_id in task_ids:
                role = roles_dir / f"{task_id}.md"
                add(results, f"artifact.role:{task_id}", role.is_file(), "present" if role.is_file() else "missing")
                if role.is_file():
                    if require_tracked_roles:
                        tracked = git_tracked(role)
                        add(
                            results,
                            f"artifact.role_tracked:{task_id}",
                            tracked,
                            "tracked" if tracked else "untracked role artifact",
                        )
                    ok, message = role_contract_ok(role)
                    add(results, f"role.contract:{task_id}", ok, message)
                    result = role_result(role)
                    if result in {"BLOCKED", "REJECTED"}:
                        if is_load_bearing_role(task_id):
                            role_blockers.append(task_id)
                        else:
                            ignored_control_blockers.append(task_id)
            if accepted_evaluation:
                add(
                    results,
                    f"evaluation.accepted_roles_unblocked:{slug}",
                    not role_blockers,
                    "accepted evaluation has no blocked/rejected role artifacts"
                    + (
                        ""
                        if not ignored_control_blockers
                        else "; ignored non-load-bearing control blockers: " + ", ".join(ignored_control_blockers)
                    )
                    if not role_blockers
                    else "blocked/rejected roles: " + ", ".join(role_blockers),
                )


def run_checks(
    slug: str | None,
    topology: Path | None,
    contract: Path | None,
    profile: str | None = None,
    skip_repo_checks: bool = False,
    allow_untracked_artifacts: bool = False,
    allow_missing_evaluation: bool = False,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if not skip_repo_checks:
        check_docs(results)
        check_runtime(results)
    contract_data = check_contract(results, contract)
    if slug:
        if profile and profile != "default":
            task_ids = check_profile(results, profile)
            check_slug(
                results,
                slug,
                task_ids,
                exact_prompts=True,
                contract=contract_data,
                require_tracked_roles=not allow_untracked_artifacts,
                allow_missing_evaluation=allow_missing_evaluation,
            )
        else:
            task_ids = check_topology(results, slug, topology, contract_data)
            check_slug(
                results,
                slug,
                task_ids,
                exact_prompts=topology is not None,
                contract=contract_data,
                require_tracked_roles=not allow_untracked_artifacts,
                allow_missing_evaluation=allow_missing_evaluation,
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", help="Generated artifact slug to validate")
    parser.add_argument("--topology", help="Optional topology YAML to validate")
    parser.add_argument("--contract", help="Optional Spec Forge contract JSON to validate")
    parser.add_argument("--profile", help="Optional profile name under profiles/<NAME>.json")
    parser.add_argument("--skip-repo-checks", action="store_true", help="Validate only the requested slug/profile artifacts")
    parser.add_argument("--allow-untracked-artifacts", action="store_true", help="Do not require live role artifacts to already be git-tracked")
    parser.add_argument("--allow-missing-final-evaluation", action="store_true", help="Permit pre-evaluation live validation before the runner writes docs/evaluations/<slug>-evaluation.md")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    results = run_checks(
        args.slug,
        Path(args.topology) if args.topology else None,
        Path(args.contract) if args.contract else None,
        profile=args.profile,
        skip_repo_checks=args.skip_repo_checks,
        allow_untracked_artifacts=args.allow_untracked_artifacts,
        allow_missing_evaluation=args.allow_missing_final_evaluation,
    )
    ok = all(item["status"] == "ok" for item in results)
    payload = {"verdict": "PASS" if ok else "FAIL", "checks": results}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in results:
            print(f"{item['status'].upper():4} {item['id']} - {item['message']}")
        print(f"verdict={payload['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
