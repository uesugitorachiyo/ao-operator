#!/usr/bin/env python3
"""Generate the Remote Transfer v2 AO Operator stress fixture."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
SLUG = "remote-transfer-v2-stress"
LIVE_SLUG = "remote-transfer-v2-stress-live"
EXAMPLE_DIR = ROOT / "examples" / SLUG
DEFAULT_SLICE_COUNT = 1000
DEFAULT_LIVE_SLICE_COUNT = 10
VALIDATED_PROBE_SLICE_COUNT = 25000
COUNT_ONLY_CEILING_SLICE_COUNT = 100000
MAX_SYNTHETIC_SLICE_COUNT = COUNT_ONLY_CEILING_SLICE_COUNT

BASE_DOMAINS = [
    ("identity", ["docs/ao-operator-remote-transfer-v2-sdd-roadmap.md", "crates/ao-node/src/registry.rs"], "identity status projection acceptance documented"),
    ("heartbeat", ["crates/ao-node/src/registry.rs", "crates/ao-node/src/coordinator.rs"], "ready busy offline heartbeat states documented"),
    ("stale-timeout", ["crates/ao-node/src/registry.rs"], "timeout behavior keeps task state durable"),
    ("enrollment", ["crates/ao-node/src/enrollment.rs", "crates/ao-node/tests/distributed_worker_grpc_codes.rs"], "enrollment failure modes remain typed"),
    ("grpc-errors", ["proto/ao/v1/runtime.proto", "crates/ao-node/tests/distributed_worker_grpc_codes.rs"], "connection errors are structured"),
    ("bundle-small", ["docs/remote-worker-workspace-transfer-spec.md", "crates/ao-node/tests/remote_workspace.rs"], "small bundles keep existing single-message path"),
    ("bundle-chunk", ["docs/remote-worker-workspace-transfer-spec.md", "crates/ao-workspace/src/bundle.rs"], "large bundles use begin chunk commit semantics"),
    ("chunk-retry", ["docs/remote-worker-workspace-transfer-spec.md"], "retry resends only failed chunk index"),
    ("staging-cleanup", ["docs/remote-worker-workspace-transfer-spec.md", "docs/remote-worker-tar-bomb-defense.md"], "failed uploads clean partial staging files"),
    ("manifest-canonical", ["docs/remote-worker-manifest-verify-spec.md", "crates/ao-workspace/src/bundle.rs"], "canonical manifest fields are named"),
    ("manifest-signing", ["docs/remote-worker-manifest-verify-spec.md"], "missing and invalid signatures reject before metadata trust"),
    ("key-rotation", ["docs/remote-worker-manifest-verify-spec.md"], "key rotation grace period documented"),
    ("deterministic-smoke", ["docs/ao-operator-remote-transfer-v2-execution-plan.md", "crates/ao-node/tests/remote_workspace.rs"], "provider-free marker smoke documented"),
    ("artifact-return", ["crates/ao-node/tests/distributed_worker_artifact_payload.rs"], "artifact name size sha256 content return metadata documented"),
    ("temp-cleanup", ["docs/remote-worker-workspace-transfer-spec.md", "crates/ao-workspace/tests/workspace.rs"], "temp workspace cleanup behavior documented"),
    ("codex-preflight", ["docs/remote-worker-codex-smoke-spec.md", "docs/ao-operator-remote-transfer-v2-mac-ubuntu-plan.md"], "Ubuntu local Codex auth preflight documented with workspace-provider-auth-material failure reason named"),
    (
        "codex-smoke",
        ["docs/remote-worker-codex-smoke-spec.md", "scripts/remote_codex_smoke_preflight.sh", "prompts/remote-codex-smoke.md"],
        "remote Codex smoke declared single write",
    ),
    ("observability-events", ["docs/ao-operator-remote-transfer-v2-sdd-roadmap.md", "crates/ao-daemon/tests/event_store_engine_integration.rs"], "task started artifact completed failed run terminal events and normalized reason documented without claiming provider progress persistence coverage"),
    ("operator-runbook", ["docs/ao-operator-remote-transfer-v2-task-board.md"], "operator loop and stop rules documented"),
    ("failure-recovery", ["docs/ao-operator-remote-transfer-v2-execution-plan.md"], "failure recovery handling documented"),
    ("worker-discovery", ["crates/ao-node/src/registry.rs"], "worker discovery states and TTL boundaries documented"),
    ("capability-advertisement", ["proto/ao/v1/runtime.proto"], "capability advertisements remain typed and versioned"),
    ("queue-lease", ["crates/ao-policy/src/queue.rs"], "remote queue lease ownership acquire observe resolve double resolution and current no lease expiry behavior documented"),
    ("task-claim", ["crates/ao-node/src/coordinator.rs"], "remote task claim behavior documented"),
    ("task-cancel", ["crates/ao-node/src/coordinator.rs"], "remote task cancellation state transitions documented"),
    ("backpressure", ["crates/ao-node/src/registry.rs", "crates/ao-scheduler/src/lib.rs"], "backpressure states prevent overload"),
    ("bundle-compression", ["crates/ao-workspace/src/bundle.rs"], "compression settings preserve deterministic hashes"),
    ("bundle-delta", ["crates/ao-workspace/src/bundle.rs"], "delta bundle selection baseline mismatch apply retry and security behavior documented"),
    ("chunk-integrity", ["docs/remote-worker-workspace-transfer-spec.md"], "chunk hash validation rejects corrupt uploads"),
    ("resumable-upload", ["docs/remote-worker-workspace-transfer-spec.md"], "resumable upload checkpoints documented"),
    ("staging-quota", ["docs/remote-worker-workspace-transfer-spec.md"], "staging quota exhaustion behavior documented"),
    ("manifest-schema", ["docs/remote-worker-manifest-verify-spec.md"], "manifest fields signing payload verification order compatibility and failure codes documented"),
    ("manifest-compat", ["docs/remote-worker-manifest-verify-spec.md"], "manifest compatibility fallback documented with verifier key compatibility signature rejection auth exclusion and preserved hash or missing file failures"),
    ("signer-policy", ["docs/remote-worker-manifest-verify-spec.md"], "signer policy allowlist behavior documented"),
    ("trust-store", ["docs/remote-worker-manifest-verify-spec.md"], "trust store lookup and missing-key failure documented"),
    ("audit-log", ["crates/ao-daemon/tests/event_store_engine_integration.rs"], "audit log event coverage documented"),
    ("artifact-download", ["crates/ao-node/tests/distributed_worker_artifact_payload.rs"], "artifact download metadata and ordering documented"),
    ("artifact-dedup", ["crates/ao-node/tests/distributed_worker_artifact_payload.rs"], "artifact deduplication by digest documented"),
    ("result-metadata", ["crates/ao-node/tests/distributed_worker_artifact_payload.rs"], "result metadata schema documented"),
    ("cleanup-sweeper", ["crates/ao-workspace/tests/workspace.rs"], "cleanup sweeper failure handling documented"),
    ("codex-env-probe", ["docs/remote-worker-codex-smoke-spec.md"], "Codex environment probe remains local to Ubuntu"),
    ("codex-token-redaction", ["docs/remote-worker-codex-smoke-spec.md"], "Codex transcript redaction policy documented"),
    ("codex-timeout", ["docs/remote-worker-codex-smoke-spec.md"], "Codex provider timeout terminal state run id and API key boundary documented with no retry smoke-output or event-closure claim"),
    ("event-heartbeat", ["crates/ao-daemon/tests/event_store_engine_integration.rs"], "heartbeat event cadence documented"),
    ("event-replay", ["crates/ao-daemon/tests/event_store_engine_integration.rs"], "event replay idempotency documented"),
    ("operator-dashboard", ["docs/ao-operator-remote-transfer-v2-task-board.md"], "operator dashboard source signals documented"),
    ("recovery-resume", ["docs/ao-operator-remote-transfer-v2-execution-plan.md"], "resume recovery path documented"),
    ("recovery-rollback", ["docs/ao-operator-remote-transfer-v2-execution-plan.md"], "rollback recovery path documented"),
    ("security-tar-sanitize", ["docs/remote-worker-tar-bomb-defense.md"], "tar sanitization checks documented"),
    ("security-path-normalize", ["docs/remote-worker-tar-bomb-defense.md"], "path normalization policy documented"),
]


def selected_domains(slice_count: int) -> list[tuple[str, list[str], str]]:
    if slice_count < 1 or slice_count > MAX_SYNTHETIC_SLICE_COUNT:
        raise ValueError(f"slice count must be between 1 and {MAX_SYNTHETIC_SLICE_COUNT}")
    domains = list(BASE_DOMAINS[:slice_count])
    for index in range(len(domains) + 1, slice_count + 1):
        domain = f"synthetic-transfer-{index:03d}"
        domains.append(
            (
                domain,
                [
                    "docs/ao-operator-remote-transfer-v2-execution-plan.md",
                    "docs/ao-operator-remote-transfer-v2-task-board.md",
                ],
                f"synthetic transfer slice {index:03d} scoped evidence documented",
            )
        )
    return domains


def task_count(slice_count: int) -> int:
    return (slice_count * 2) + 7


def factory_id(domain: str) -> str:
    return f"{domain}-factory"


def reviewer_id(domain: str) -> str:
    return f"{domain}-reviewer"


def contract(
    slice_count: int,
    *,
    slug: str = SLUG,
    topology_file: str | None = None,
    contract_file: str | None = None,
    live_profile: bool = False,
) -> dict[str, object]:
    total = task_count(slice_count)
    domains = selected_domains(slice_count)
    topology_file = topology_file or f"examples/{SLUG}/ao-stress-topology.yaml"
    contract_file = contract_file or f"examples/{SLUG}/spec-forge.contract.json"
    profile_label = "bounded live" if live_profile else "maximum fan-out planning"
    problem = (
        "AO Operator needs a conductable stress lane that exercises Remote Transfer v2 planning without exhausting live provider limits or exposing network endpoints."
        if live_profile
        else "AO Operator needs a conductable, high-task-count stress lane that exercises Remote Transfer v2 planning without spending live provider cycles or exposing network endpoints."
    )
    live_constraints = [
        "Keep live provider fan-out bounded to a small first-wave profile.",
        "Use the maximum 1000-slice topology only for dry-run materialization.",
    ] if live_profile else ["Keep the stress lane dry-run by default."]
    live_negative_constraints = [
        "MUST NOT run the 1000-slice dry-run topology as a live provider workload",
        "MUST NOT exceed the bounded live slice count without an explicit operator approval",
    ] if live_profile else ["MUST NOT run remote Codex from this dry-run stress lane"]
    success_criteria = [
        f"AO Operator materializes a {total}-task RunSpec and exact prompt set.",
        f"The contract declares {slice_count} disjoint implementation slices.",
    ]
    if live_profile:
        success_criteria.extend(
            [
                "The generated RunSpec contains every bounded live factory and reviewer task.",
                "The prompt directory exactly matches the bounded topology task IDs.",
                "AO events capture a real run id, command exit, completion state, and provider failure evidence when failures occur.",
            ]
        )
    success_criteria.extend(
        [
            "The topology validator accepts topology sizes above the original 17-task demo.",
            "The bounded live profile is small enough to run before escalating provider concurrency."
            if live_profile
            else "The dry-run completes without live provider execution.",
        ]
    )
    constraints = [
        "Use OAuth CLI providers only.",
        *live_constraints,
        "Keep branch context bounded to scoped reads, writes, and durable artifacts.",
        "Fan out only after Spec Forge and Ralph Loop gates pass.",
    ]
    if live_profile:
        constraints.append("Require validate_factory.py and validate_intake.py PASS before live provider dispatch.")
    negative_constraints = [
        "MUST NOT configure OPENAI_API_KEY or ANTHROPIC_API_KEY",
        *(
            [
                "MUST NOT read provider auth files or provider CLI session files",
            ]
            if live_profile
            else []
        ),
        "MUST NOT transfer provider auth files between machines",
        *(["MUST NOT emit raw environment dumps"] if live_profile else []),
        "MUST NOT bind anonymous write-capable endpoints",
        *live_negative_constraints,
        "MUST NOT pass full transcripts between branches",
        "MUST NOT accept closure when any branch returns BLOCKED or REJECTED",
    ]
    shalls = [
        {
            "id": "SHALL-001",
            "text": f"The stress topology SHALL contain planner-intake, Spec Forge, Ralph Loop, plan-hardener, factory-manager, {slice_count} implementation factories, {slice_count} reviewers, integrator, and evaluator-closer.",
        },
        {"id": "SHALL-002", "text": "Every implementation factory SHALL declare disjoint read and write ownership."},
        {"id": "SHALL-003", "text": "Every reviewer SHALL depend only on its paired implementation factory."},
        {"id": "SHALL-004", "text": f"The integrator SHALL fan in all {slice_count} reviewer artifacts."},
    ]
    if live_profile:
        shalls.extend(
            [
                {
                    "id": "SHALL-005",
                    "text": "The bounded live run SHALL use OAuth CLI providers only and SHALL NOT require provider API keys.",
                },
                {
                    "id": "SHALL-006",
                    "text": "Every role artifact SHALL return Result, Artifact, Evidence, Concerns, and Blocker.",
                },
                {
                    "id": "SHALL-007",
                    "text": "The prompt directory SHALL exactly match the bounded topology task IDs before live provider dispatch.",
                },
                {
                    "id": "SHALL-008",
                    "text": "AO event capture SHALL include a real run id, command exit, completion state, and provider failure evidence when provider failures occur.",
                },
                {
                    "id": "SHALL-009",
                    "text": "Live provider dispatch SHALL be blocked unless validate_factory.py and validate_intake.py both return PASS.",
                },
            ]
        )
    else:
        shalls.append({"id": "SHALL-005", "text": "The dry-run SHALL not require live provider execution or network endpoint exposure."})
    acceptance_criteria = [
        {
            "id": "AC-001",
            "description": f"The stress topology contains exactly {total} tasks.",
            "oracle": "RunSpec and topology validation report every task present.",
            "verification": f"python3 scripts/validate_factory.py --slug {slug} --topology {topology_file} --contract {contract_file} --json",
        },
        {
            "id": "AC-002",
            "description": f"The contract carries all {slice_count} Remote Transfer v2 slices.",
            "oracle": "Intake validation passes with reads, writes, verification, sensitive fields, trigger hints, and negative constraints.",
            "verification": f"python3 scripts/validate_intake.py {contract_file} --json",
        },
    ]
    if live_profile:
        acceptance_criteria.extend(
            [
                {
                    "id": "AC-003",
                    "description": "The profile materializes prompts and RunSpec before live provider dispatch.",
                    "oracle": "Factory render command uses the bounded topology and generated status/evaluation names the bounded slug without launching AO.",
                    "verification": (
                        f"python3 scripts/factory_run.py --brief examples/{SLUG}/task-brief-live.md "
                        f"--slug {slug} --provider-env examples/{SLUG}/provider.env "
                        f"--topology {topology_file} --contract {contract_file} --render-only --overwrite-artifacts --scrub-root-context"
                    ),
                },
                {
                    "id": "AC-004",
                    "description": "The live prompt directory exactly matches the bounded topology task IDs.",
                    "oracle": "Validation reports no missing or extra prompt files for the bounded topology.",
                    "verification": f"python3 scripts/validate_factory.py --slug {slug} --topology {topology_file} --contract {contract_file} --json",
                },
                {
                    "id": "AC-005",
                    "description": "AO events capture live execution closure evidence.",
                    "oracle": "Post-run evidence contains a real AO run id, command exit status, completion state, and provider failure evidence when failures occur.",
                    "verification": (
                        f"python3 scripts/factory_run.py --brief examples/{SLUG}/task-brief-live.md "
                        f"--slug {slug} --provider-env examples/{SLUG}/provider.env "
                        f"--topology {topology_file} --contract {contract_file} --run --overwrite-artifacts --scrub-root-context "
                        f"&& python3 scripts/validate_factory.py --slug {slug} --topology {topology_file} --contract {contract_file} --json"
                    ),
                },
            ]
        )
    else:
        acceptance_criteria.append(
            {
                "id": "AC-003",
                "description": "The dry-run materializes prompts and RunSpec without live provider dispatch.",
                "oracle": "Factory run dry-run command exits 0 and generated status says mode dry-run.",
                "verification": f"python3 scripts/factory_run.py --brief examples/{SLUG}/task-brief.md --slug {slug} --provider-env examples/{SLUG}/provider.env --topology {topology_file} --dry-run --overwrite-artifacts",
            }
        )
    return {
        "schema": "spec-forge/v2",
        "slug": slug,
        "title": f"Remote Transfer v2 {profile_label} stress test",
        "shape": "greenfield",
        "classification": "COMPLEX",
        "problem": problem,
        "objective": f"Materialize a {total}-task AO Operator topology with {slice_count} Remote Transfer v2 implementation factories, {slice_count} reviewers, and durable SDD-style closure artifacts.",
        "success_criteria": success_criteria,
        "constraints": constraints,
        "sensitive_fields": [
            "provider OAuth credentials",
            "provider CLI session files",
            "enrollment tokens",
            "worker endpoint URLs",
            "local machine labels",
            "full provider transcripts",
        ],
        "trigger_hints": ["security", "build", "docs", "provider-runtime", "performance"],
        "negative_constraints": negative_constraints,
        "shalls": shalls,
        "acceptance_criteria": acceptance_criteria,
        "slices": [
            {
                "id": factory_id(domain),
                "reads": reads,
                "writes": [f"docs/remote-transfer-v2/{domain}.md"],
                "verification": [verification],
            }
            for domain, reads, verification in domains
        ],
    }


def task_block(task_id: str, deps: list[str], *, slug: str = SLUG, extra: dict[str, str] | None = None) -> list[str]:
    prompt_file = f"run-artifacts/{slug}/prompts/{task_id}.md"
    lines = [
        f"    - id: {task_id}",
        "      kind: agent",
        f"      deps: {json.dumps(deps)}",
        "      spec:",
        "        provider: codex",
        "        agent: codex-default",
        f"        promptFile: {prompt_file}",
        "        workspace: .",
        "        policyProfile: ao/policy/local-dev.yaml",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"        {key}: {value}")
    return lines


def topology(
    slice_count: int,
    *,
    slug: str = SLUG,
    contract_file: str | None = None,
    live_profile: bool = False,
) -> str:
    total = task_count(slice_count)
    domains = selected_domains(slice_count)
    contract_file = contract_file or f"examples/{SLUG}/spec-forge.contract.json"
    profile = "bounded live" if live_profile else "stress"
    lines = [
        "apiVersion: ao.dev/v1",
        "kind: Run",
        "metadata:",
        f"  name: {slug}",
        "  description: >",
        f"    AO Operator Remote Transfer v2 {profile} topology. Materializes {total} tasks:",
        f"    five control-gate tasks, {slice_count} implementation factories, {slice_count} reviewers,",
        "    integrator, and evaluator-closer.",
        "spec:",
        "  tasks:",
    ]
    control_tasks = [
        ("planner-intake", [], None),
        ("spec-forge-contract", ["planner-intake"], {"contractFile": contract_file}),
        ("ralph-loop", ["spec-forge-contract"], {"gate": "greenfield-readiness"}),
        ("plan-hardener", ["ralph-loop"], None),
        ("factory-manager", ["plan-hardener"], {"dispatchMode": "fan-out"}),
    ]
    for task_id, deps, extra in control_tasks:
        lines.extend(task_block(task_id, deps, slug=slug, extra=extra))
        lines.append("")
    for domain, _, _ in domains:
        lines.extend(task_block(factory_id(domain), ["factory-manager"], slug=slug))
        lines.append("")
    for domain, _, _ in domains:
        lines.extend(task_block(reviewer_id(domain), [factory_id(domain)], slug=slug))
        lines.append("")
    lines.extend(task_block("integrator", [reviewer_id(domain) for domain, _, _ in domains], slug=slug))
    lines.append("")
    lines.extend(task_block("evaluator-closer", ["integrator"], slug=slug))
    return "\n".join(lines) + "\n"


def readme(slice_count: int) -> str:
    total = task_count(slice_count)
    return dedent(
        f"""\
        # Remote Transfer v2 Stress Topology

        This fixture stress-tests AO Operator with a {total}-task Remote Transfer v2
        factory-of-factories topology.

        It is a dry-run/materialization lane by default. It does not run live providers,
        does not transfer credentials, and does not expose network endpoints.

        Current operator handoff:
        `run-artifacts/remote-transfer-v2-stress/operator-handoff-20260506.md`

        Bounded live acceptance runbook:
        `run-artifacts/remote-transfer-v2-stress-live/live-acceptance-runbook-20260506.md`

        ## Commands

        ```bash
        python3 scripts/factory_run.py \\
          --brief examples/{SLUG}/task-brief.md \\
          --slug {SLUG} \\
          --provider-env examples/{SLUG}/provider.env \\
          --topology examples/{SLUG}/ao-stress-topology.yaml \\
          --dry-run \\
          --overwrite-artifacts

        python3 scripts/validate_factory.py \\
          --slug {SLUG} \\
          --topology examples/{SLUG}/ao-stress-topology.yaml \\
          --contract examples/{SLUG}/spec-forge.contract.json \\
          --json

        python3 scripts/validate_intake.py \\
          examples/{SLUG}/spec-forge.contract.json \\
          --json

        python3 scripts/generate_stress_fixture.py --slices 25000 --check-only --validate-topology

        python3 scripts/generate_stress_fixture.py --slices 100000 --check-only

        FACTORY_V3_RUN_STRESS_TESTS=1 python3 -m pytest -q tests/test_validate_factory_topology.py

        python3 scripts/validate_operator_slices.py \\
          examples/remote-transfer-v2-stress/operator-slices.json \\
          --json

        python3 scripts/validate_operator_slices.py \\
          examples/remote-transfer-v2-stress/operator-slices.json \\
          --list-slices \\
          --local-only \\
          --json

        python3 scripts/run_operator_slice.py \\
          examples/remote-transfer-v2-stress/operator-slices.json \\
          --from 01-ao-runtime-doctor \\
          --through 11-review-runtime-guardrail-batch \\
          --local-only \\
          --json

        python3 scripts/run_operator_slice.py \\
          examples/remote-transfer-v2-stress/operator-slices.json \\
          --slice 02-validate-bounded-live-profile \\
          --execute \\
          --json

        python3 scripts/check_bounded_live_readiness.py --json

        python3 scripts/check_bounded_live_readiness.py --write-summary --json

        python3 scripts/build_live_dispatch_packet.py --write-packet --json

        python3 scripts/verify_live_dispatch_packet.py --json

        python3 scripts/check_live_dispatch_gate.py --ao-runtime-path ${FACTORY_V3_AO_RUNTIME_PATH} --write-gate --json

        python3 scripts/classify_live_outcome.py --write-output --json

        python3 scripts/plan_live_failure_diagnostics.py --write-plan --json

        python3 scripts/preserve_live_failure_diagnostics.py --write-report --json

        python3 scripts/route_live_postrun.py --write-output --json

        python3 scripts/check_live_success_commit_guard.py --write-output --json

        python3 scripts/check_live_operator_sequence.py --write-output --json

        python3 scripts/check_live_approval_readiness.py --write-output --json

        python3 scripts/check_live_acceptance.py \\
          --slug remote-transfer-v2-stress-live \\
          --json

        # Failure diagnostics after a blocked or provider-limited live attempt.
        python3 scripts/summarize_ao_failure.py \\
          /tmp/ao-operator-ao-remote-transfer-v2-stress \\
          --json

        # Bounded live provider profile. Start here for live AO runs.
        python3 scripts/factory_run.py \\
          --brief examples/remote-transfer-v2-stress/task-brief-live.md \\
          --slug remote-transfer-v2-stress-live \\
          --provider-env examples/remote-transfer-v2-stress/provider.env \\
          --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \\
          --run \\
          --overwrite-artifacts \\
          --scrub-root-context
        ```

        ## Scale

        - {total} topology tasks.
        - {slice_count} implementation factories.
        - {slice_count} reviewer tasks.
        - 1 integrator fan-in.
        - 1 evaluator closure.
        - 27-task bounded live profile available as `remote-transfer-v2-stress-live`.
        - 34 ordered operator slices in `operator-slices.json`.
        - 50007-task topology validator probe available with `--check-only --validate-topology`.
        - 200007-task count-only ceiling probe available with `--check-only`.

        ## Safety

        - OAuth CLI providers only.
        - No provider API-key env vars.
        - No live Mac-to-Ubuntu endpoint exposure.
        - No provider credential transfer.
        - No full transcript handoffs.
        - Operator-run reports redact provider auth paths, token/API-key shaped values,
          and raw AO home paths before they are written.
        - Do not run the 1000-slice topology with live providers; use the bounded live
          profile first.
        - Live runs above `FACTORY_V3_MAX_LIVE_TASKS` (default: 50) are blocked unless
          `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1` is set with documented provider-limit
          evidence.
        """
    )


def task_brief(slice_count: int) -> str:
    total = task_count(slice_count)
    return dedent(
        f"""\
        # Remote Transfer v2 Stress Task Brief

        Use AO Operator to create a maximum-pressure complex dry-run plan for AO
        Runtime Remote Transfer v2.

        Shape it as greenfield.

        ## Goal

        Materialize a very large AO Operator topology for Remote Transfer v2 planning:
        {slice_count} implementation factories, {slice_count} reviewer branches, and
        standard Spec Forge, Ralph Loop, integrator, and evaluator gates.

        This is a AO Operator stress test. The run should push task count, prompt
        materialization, provider resolution, RunSpec generation, exact prompt
        validation, and contract validation. It should not run live provider work.

        ## Product Scope

        The generated plan covers Remote Transfer v2 from connection identity through
        remote Codex smoke, operator telemetry, failure recovery, and transfer security.

        ## Factory Shape

        Shape: greenfield.

        The topology must include one factory and one reviewer for each Remote Transfer
        v2 work domain. Every factory owns disjoint documentation or source-path scopes
        declared in `spec-forge.contract.json`.

        ## Constraints

        - Use OAuth CLI providers only.
        - Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
        - Do not read or transfer provider auth files.
        - Do not bind anonymous write-capable endpoints.
        - Do not execute live Mac-to-Ubuntu provider work from this dry-run lane.
        - Do not pass full provider transcripts between roles.
        - Every role must return Result, Artifact, Evidence, Concerns, and Blocker.

        ## Acceptance Criteria

        - AO Operator materializes all {total} topology tasks.
        - The generated RunSpec contains every stress factory and reviewer task.
        - Prompt directory exactly matches the topology task IDs.
        - Spec Forge contract declares all {slice_count} slices with reads, writes, and
          verification commands.
        - Validator accepts topology sizes above the original 17-task demo.
        - `validate_factory.py` and `validate_intake.py` both return PASS.
        """
    )


def live_task_brief(slice_count: int) -> str:
    total = task_count(slice_count)
    return dedent(
        f"""\
        # Remote Transfer v2 Bounded Live Stress Task Brief

        Use AO Operator to run a complex bounded live AO-backed provider stress
        profile for Remote Transfer v2.

        Shape it as greenfield.

        ## Goal

        Materialize and run a small live AO Operator topology before attempting any
        wider provider fan-out: {slice_count} implementation factories,
        {slice_count} reviewer branches, and the standard Spec Forge, Ralph Loop,
        integrator, and evaluator gates.

        This is the live counterpart to the 1000-slice dry-run stress fixture. It
        exists to prove AO Runtime provider execution, role artifacts, event
        capture, and closure behavior without exceeding provider limits.

        ## Product Scope

        The generated plan covers the first {slice_count} Remote Transfer v2 work
        domains from the stress contract.

        ## Constraints

        - Use OAuth CLI providers only.
        - Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
        - Do not read or transfer provider auth files.
        - Do not run the 1000-slice stress topology in live mode.
        - Do not raise the live slice count without operator approval.
        - Every role must return Result, Artifact, Evidence, Concerns, and Blocker.

        ## Acceptance Criteria

        - AO Operator materializes all {total} bounded live topology tasks.
        - The generated RunSpec contains every bounded live factory and reviewer task.
        - Prompt directory exactly matches the bounded topology task IDs.
        - AO events capture a real run id, command exit, completion state, and
          provider failure evidence when failures occur.
        - `validate_factory.py` and `validate_intake.py` both return PASS before
          live dispatch.
        """
    )


def expected_throughput(slice_count: int) -> str:
    total = task_count(slice_count)
    return dedent(
        f"""\
        # Expected Throughput

        The stress topology is a dry-run lane, so throughput is measured by generated
        AO Operator artifacts rather than live provider completions.

        - Total AO tasks: {total}
        - Parallel implementation factories after `factory-manager`: {slice_count}
        - Parallel reviewers after implementation: {slice_count}
        - Required generated prompts: {total}
        - Live provider calls by default: 0
        - Topology validator probe: 50007 AO tasks from 25000 slices
        - Count-only ceiling probe: 200007 AO tasks from 100000 slices
        - Ceiling probe generated prompts: 0

        Passing validation means AO Operator can materialize, index, and validate the
        large topology without dispatching live provider work.
        """
    )


def live_expected_throughput(slice_count: int) -> str:
    total = task_count(slice_count)
    return dedent(
        f"""\
        # Bounded Live Expected Throughput

        This is the provider-safe live profile for Remote Transfer v2 stress work.
        It is intentionally much smaller than the 1000-slice dry-run topology.

        - Total AO tasks: {total}
        - Live implementation factories after `factory-manager`: {slice_count}
        - Live reviewers after implementation: {slice_count}
        - Required generated prompts: {total}
        - Live provider calls are bounded to the generated topology size.
        - Escalate to 25 pairs only after this profile completes without provider
          limit, auth, network, or closure blockers.

        The 1000-slice topology remains the materialization-only stress lane.
        """
    )


def provider_env() -> str:
    keys = [
        "FACTORY_V3_DEFAULT_PROVIDER",
        "FACTORY_V3_PLANNER_PROVIDER",
        "FACTORY_V3_SPEC_FORGE_PROVIDER",
        "FACTORY_V3_RALPH_LOOP_PROVIDER",
        "FACTORY_V3_PLAN_HARDENER_PROVIDER",
        "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
        "FACTORY_V3_IMPLEMENTER_PROVIDER",
        "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
        "FACTORY_V3_INTEGRATOR_PROVIDER",
        "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
    ]
    return "\n".join(f"{key}=codex" for key in keys) + "\n"


def write_fixture(slice_count: int) -> None:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    (EXAMPLE_DIR / "spec-forge.contract.json").write_text(json.dumps(contract(slice_count), indent=2) + "\n", encoding="utf-8")
    (EXAMPLE_DIR / "ao-stress-topology.yaml").write_text(topology(slice_count), encoding="utf-8")
    (EXAMPLE_DIR / "README.md").write_text(readme(slice_count), encoding="utf-8")
    (EXAMPLE_DIR / "task-brief.md").write_text(task_brief(slice_count), encoding="utf-8")
    (EXAMPLE_DIR / "expected-throughput.md").write_text(expected_throughput(slice_count), encoding="utf-8")
    (EXAMPLE_DIR / "provider.env").write_text(provider_env(), encoding="utf-8")


def write_live_profile(slice_count: int = DEFAULT_LIVE_SLICE_COUNT) -> None:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    topology_file = f"examples/{SLUG}/ao-live-stress-topology.yaml"
    contract_file = f"examples/{SLUG}/spec-forge.live.contract.json"
    (EXAMPLE_DIR / "spec-forge.live.contract.json").write_text(
        json.dumps(
            contract(
                slice_count,
                slug=LIVE_SLUG,
                topology_file=topology_file,
                contract_file=contract_file,
                live_profile=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EXAMPLE_DIR / "ao-live-stress-topology.yaml").write_text(
        topology(
            slice_count,
            slug=LIVE_SLUG,
            contract_file=contract_file,
            live_profile=True,
        ),
        encoding="utf-8",
    )
    (EXAMPLE_DIR / "task-brief-live.md").write_text(live_task_brief(slice_count), encoding="utf-8")
    (EXAMPLE_DIR / "expected-throughput-live.md").write_text(live_expected_throughput(slice_count), encoding="utf-8")


def check_only_summary(slice_count: int) -> dict[str, object]:
    domains = selected_domains(slice_count)
    return {
        "slug": SLUG,
        "mode": "check-only",
        "slices": slice_count,
        "tasks": task_count(slice_count),
        "first_slice": factory_id(domains[0][0]),
        "last_slice": factory_id(domains[-1][0]),
        "writes_artifacts": False,
    }


def topology_validation_summary(slice_count: int) -> dict[str, object]:
    import validate_factory

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"{SLUG}-") as tmp:
        topology_path = Path(tmp) / "ao-stress-topology.yaml"
        topology_path.write_text(topology(slice_count), encoding="utf-8")
        results: list[dict[str, str]] = []
        task_ids = validate_factory.check_topology(results, f"{SLUG}-probe", topology_path, contract(slice_count))
    duration = time.perf_counter() - started

    failed = [item for item in results if item["status"] != "ok"]
    checks = {
        item["id"]: {
            "status": item["status"],
            "message": (
                f"{slice_count} reviewer deps present"
                if item["id"] == "topology.integrator_deps" and item["status"] == "ok"
                else item["message"]
            ),
        }
        for item in results
        if item["id"]
        in {
            "topology.task_count",
            "topology.factories.count",
            "topology.reviewers.count",
            "topology.factories.match_contract",
            "topology.integrator_deps",
        }
    }
    return {
        "verdict": "PASS" if not failed else "FAIL",
        "checked_tasks": len(task_ids),
        "duration_seconds": round(duration, 3),
        "checks": checks,
        "failure_count": len(failed),
        "failures": failed[:10],
        "writes_artifacts": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slices", type=int, default=DEFAULT_SLICE_COUNT)
    parser.add_argument("--live-slices", type=int, default=DEFAULT_LIVE_SLICE_COUNT)
    parser.add_argument(
        "--write-live-profile",
        action="store_true",
        help="write the bounded live provider profile alongside the dry-run stress fixture",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate and print generated counts without writing fixture files",
    )
    parser.add_argument(
        "--validate-topology",
        action="store_true",
        help="with --check-only, run validate_factory against a temporary generated topology",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.write_live_profile:
        write_live_profile(args.live_slices)
        print(f"generated {LIVE_SLUG}: slices={args.live_slices} tasks={task_count(args.live_slices)}")
        return 0
    if args.check_only:
        summary = check_only_summary(args.slices)
        if args.validate_topology:
            summary["topology_validation"] = topology_validation_summary(args.slices)
        print(json.dumps(summary, indent=2))
        validation = summary.get("topology_validation")
        if isinstance(validation, dict) and validation.get("verdict") != "PASS":
            return 1
        return 0
    if args.validate_topology:
        print("generate_stress_fixture.py: --validate-topology requires --check-only", flush=True)
        return 2
    write_fixture(args.slices)
    print(f"generated {SLUG}: slices={args.slices} tasks={task_count(args.slices)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
