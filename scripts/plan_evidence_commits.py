#!/usr/bin/env python3
"""Plan commit-ready evidence bundles without staging or committing files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress"
STAGING_SEQUENCE = [
    "runtime-guardrails-and-tests",
    "operator-sdd-and-manifest",
    "bounded-live-profile-dry-run",
    "large-dry-run-materialization",
    "operator-run-reports",
    "failed-live-diagnostics",
]


@dataclass(frozen=True)
class StatusEntry:
    status: str
    path: str


@dataclass(frozen=True)
class EvidenceGroup:
    group_id: str
    title: str
    intent: str
    commit_message: str
    commit_allowed: bool = True


GROUPS = {
    "runtime-guardrails-and-tests": EvidenceGroup(
        group_id="runtime-guardrails-and-tests",
        title="Runtime guardrails and tests",
        intent="Runtime changes that make stress operation bounded, hygienic, and testable.",
        commit_message="Harden remote transfer stress runtime guardrails",
    ),
    "operator-sdd-and-manifest": EvidenceGroup(
        group_id="operator-sdd-and-manifest",
        title="Operator SDD and manifest",
        intent="Machine-checkable operator slice queue and accompanying SDD documentation.",
        commit_message="Add remote transfer stress operator slices",
    ),
    "large-dry-run-materialization": EvidenceGroup(
        group_id="large-dry-run-materialization",
        title="Large dry-run materialization evidence",
        intent="1000-slice stress topology artifacts; dry-run only, not successful live evidence.",
        commit_message="Refresh remote transfer stress dry-run evidence",
    ),
    "bounded-live-profile-dry-run": EvidenceGroup(
        group_id="bounded-live-profile-dry-run",
        title="Bounded live profile dry-run evidence",
        intent="10-slice bounded live profile contract, topology, prompts, RunSpec, and dry-run artifacts.",
        commit_message="Add bounded remote transfer live profile",
    ),
    "failed-live-diagnostics": EvidenceGroup(
        group_id="failed-live-diagnostics",
        title="Failed live provider diagnostics",
        intent="Provider-limit diagnostics and partial role artifacts preserved for analysis only.",
        commit_message="Preserve remote transfer provider-limit diagnostics",
    ),
    "operator-run-reports": EvidenceGroup(
        group_id="operator-run-reports",
        title="Operator run reports",
        intent="Durable reports from local operator slice execution.",
        commit_message="Record remote transfer operator run reports",
    ),
    "scratch-excluded": EvidenceGroup(
        group_id="scratch-excluded",
        title="Scratch outputs excluded from commits",
        intent="Transient outputs from tests or local probes that should not be committed.",
        commit_message="do-not-commit scratch outputs",
        commit_allowed=False,
    ),
}


RUNTIME_PATHS = {
    "scripts/factory_run.py",
    "scripts/generate_stress_fixture.py",
    "scripts/plan_evidence_commits.py",
    "scripts/run_operator_slice.py",
    "scripts/summarize_ao_failure.py",
    "scripts/validate_factory.py",
    "scripts/validate_operator_slices.py",
    "tests/test_agent_manifest_sync.py",
    "tests/test_factory_run_preflight.py",
    "tests/test_plan_evidence_commits.py",
    "tests/test_run_operator_slice.py",
    "tests/test_summarize_ao_failure.py",
    "tests/test_validate_factory_topology.py",
    "tests/test_validate_operator_slices.py",
}

OPERATOR_SDD_PATHS = {
    "docs/sdd/10-stress-topology.md",
    "docs/sdd/11-operator-slices.md",
    "docs/sdd/README.md",
    "examples/remote-transfer-v2-stress/README.md",
    "examples/remote-transfer-v2-stress/operator-slices.json",
}

BOUNDED_LIVE_EXAMPLE_PATHS = {
    "examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml",
    "examples/remote-transfer-v2-stress/expected-throughput-live.md",
    "examples/remote-transfer-v2-stress/spec-forge.live.contract.json",
    "examples/remote-transfer-v2-stress/task-brief-live.md",
    "docs/plans/remote-transfer-v2-stress-live-plan.md",
    "docs/specs/remote-transfer-v2-stress-live-spec.md",
}

LARGE_DRY_RUN_EXACT = {
    "docs/specs/remote-transfer-v2-stress-spec.md",
    "docs/plans/remote-transfer-v2-stress-plan.md",
    "run-artifacts/remote-transfer-v2-stress/remote-transfer-v2-stress-status.md",
    "run-artifacts/remote-transfer-v2-stress/remote-transfer-v2-stress.runspec.yaml",
}

FAILED_LIVE_EXACT = {
    "docs/evaluations/remote-transfer-v2-stress-evaluation.md",
    "run-artifacts/remote-transfer-v2-stress/remote-transfer-v2-stress-ao-events.md",
}


def git_status(root: Path = ROOT) -> list[StatusEntry]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    parts = result.stdout.decode("utf-8", errors="replace").split("\0")
    entries: list[StatusEntry] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if not record:
            continue
        status = record[:2]
        path = record[3:]
        if "R" in status or "C" in status:
            index += 1
        entries.append(StatusEntry(status=status, path=path))
    return entries


def classify_path(path: str) -> str:
    if path in RUNTIME_PATHS:
        return "runtime-guardrails-and-tests"
    if path in OPERATOR_SDD_PATHS:
        return "operator-sdd-and-manifest"
    if path in BOUNDED_LIVE_EXAMPLE_PATHS or path.startswith("run-artifacts/remote-transfer-v2-stress-live/"):
        return "bounded-live-profile-dry-run"
    if path in LARGE_DRY_RUN_EXACT or path.startswith("run-artifacts/remote-transfer-v2-stress/prompts/"):
        return "large-dry-run-materialization"
    if (
        path in FAILED_LIVE_EXACT
        or path.startswith("run-artifacts/remote-transfer-v2-stress/failure-snapshots/")
        or path.startswith("run-artifacts/remote-transfer-v2-stress/patches/")
        or path.startswith("docs/remote-transfer-v2/")
    ):
        return "failed-live-diagnostics"
    if (
        path.startswith("run-artifacts/remote-transfer-v2-stress/operator-runs/")
        or path.startswith("run-artifacts/remote-transfer-v2-stress/commit-readiness/")
        or path.startswith("run-artifacts/remote-transfer-v2-stress/staging-plans/")
    ):
        return "operator-run-reports"
    if path.startswith("run-artifacts/test-operator/"):
        return "scratch-excluded"
    return "unclassified"


def build_plan(entries: list[StatusEntry], *, slug: str = DEFAULT_SLUG, generated_at: str | None = None) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    grouped: dict[str, list[dict[str, str]]] = {group_id: [] for group_id in GROUPS}
    unclassified: list[dict[str, str]] = []
    for entry in sorted(entries, key=lambda item: item.path):
        group_id = classify_path(entry.path)
        payload = {"status": entry.status, "path": entry.path}
        if group_id == "unclassified":
            unclassified.append(payload)
        else:
            grouped[group_id].append(payload)

    groups: list[dict[str, Any]] = []
    for group_id, spec in GROUPS.items():
        paths = grouped[group_id]
        if not paths:
            continue
        groups.append(
            {
                "id": spec.group_id,
                "title": spec.title,
                "intent": spec.intent,
                "commit_allowed": spec.commit_allowed,
                "commit_message": spec.commit_message,
                "count": len(paths),
                "paths": paths,
            }
        )

    errors = [f"unclassified path: {item['path']}" for item in unclassified]
    warnings = [
        "failed-live-diagnostics must not be committed as successful live evidence",
        "scratch-excluded paths should be deleted or ignored before committing",
    ]
    warnings = [
        warning
        for warning in warnings
        if (
            warning.startswith("failed-live")
            and grouped["failed-live-diagnostics"]
            or warning.startswith("scratch")
            and grouped["scratch-excluded"]
        )
    ]
    return {
        "schema": "ao-operator/commit-readiness/v1",
        "slug": slug,
        "generated_at": generated,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "total_paths": len(entries),
        "groups": groups,
        "unclassified": unclassified,
        "negative_constraints": [
            "Do not commit failed provider-limit evidence as successful live evidence.",
            "Do not stage provider OAuth credentials or CLI session files.",
            "Do not run live providers from commit-readiness planning.",
        ],
        "sensitive_fields": [
            "provider OAuth credentials",
            "provider CLI session files",
            "AO_HOME run transcripts",
            "full provider transcripts",
        ],
    }


def write_plan(plan: dict[str, Any], *, slug: str, root: Path = ROOT) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = root / "run-artifacts" / slug / "commit-readiness" / f"{timestamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def build_staging_plan(
    readiness: dict[str, Any],
    *,
    slug: str = DEFAULT_SLUG,
    generated_at: str | None = None,
    plan_dir: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    groups = {group["id"]: group for group in readiness.get("groups", []) if isinstance(group, dict)}
    batches: list[dict[str, Any]] = []
    for group_id in STAGING_SEQUENCE:
        group = groups.get(group_id)
        if not group or group.get("commit_allowed") is not True:
            continue
        paths = [item["path"] for item in group.get("paths", []) if isinstance(item, dict) and isinstance(item.get("path"), str)]
        pathspec_file = (
            f"{plan_dir}/{len(batches) + 1:02d}-{group_id}.pathspec"
            if plan_dir
            else f"<staging-plan-dir>/{len(batches) + 1:02d}-{group_id}.pathspec"
        )
        notes: list[str] = []
        success_evidence = group_id != "failed-live-diagnostics"
        if group_id == "failed-live-diagnostics":
            notes.append("diagnostic-only: do not present as successful live evidence")
        if group_id == "operator-run-reports":
            notes.append("records local operator execution only")
        batches.append(
            {
                "order": len(batches) + 1,
                "group_id": group_id,
                "title": group.get("title"),
                "path_count": len(paths),
                "commit_message": group.get("commit_message"),
                "success_evidence": success_evidence,
                "pathspec_file": pathspec_file,
                "stage_command": f"git add --pathspec-from-file={pathspec_file}",
                "commit_command": f"git commit -m {json.dumps(str(group.get('commit_message') or group_id))}",
                "notes": notes,
                "paths": paths,
            }
        )

    errors = list(readiness.get("errors", []))
    if readiness.get("verdict") != "PASS":
        errors.append("readiness verdict must be PASS before staging")
    missing = [
        group_id
        for group_id in ("runtime-guardrails-and-tests", "operator-sdd-and-manifest")
        if group_id not in groups
    ]
    errors.extend(f"required staging group missing: {group_id}" for group_id in missing)
    return {
        "schema": "ao-operator/staged-commit-plan/v1",
        "slug": slug,
        "generated_at": generated,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": readiness.get("warnings", []),
        "source_readiness_generated_at": readiness.get("generated_at"),
        "negative_constraints": [
            "This plan must not stage or commit files by itself.",
            "Failed live diagnostics must stay diagnostic-only.",
            "Run git diff --cached and deterministic checks after each staged batch.",
        ],
        "batches": batches,
    }


def write_staging_plan(staging_plan: dict[str, Any], *, slug: str, root: Path = ROOT) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    plan_dir = root / "run-artifacts" / slug / "staging-plans" / timestamp
    rel_plan_dir = rel(plan_dir.relative_to(root) if plan_dir.is_absolute() else plan_dir)
    refreshed = build_staging_plan(
        {
            **staging_plan,
            "groups": [
                {
                    "id": batch["group_id"],
                    "title": batch["title"],
                    "commit_allowed": True,
                    "commit_message": batch["commit_message"],
                    "paths": [{"path": path} for path in batch["paths"]],
                }
                for batch in staging_plan.get("batches", [])
            ],
            "warnings": staging_plan.get("warnings", []),
            "errors": staging_plan.get("errors", []),
            "verdict": "PASS" if not staging_plan.get("errors") else "FAIL",
            "generated_at": staging_plan.get("source_readiness_generated_at"),
        },
        slug=slug,
        generated_at=staging_plan.get("generated_at"),
        plan_dir=rel_plan_dir,
    )
    plan_dir.mkdir(parents=True, exist_ok=True)
    for batch in refreshed["batches"]:
        pathspec = root / batch["pathspec_file"]
        pathspec.write_text("\n".join(batch["paths"]) + "\n", encoding="utf-8")
    summary = plan_dir / "staging-plan.json"
    refreshed["report"] = rel(summary)
    summary.write_text(json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def latest_staging_plan(*, slug: str = DEFAULT_SLUG, root: Path = ROOT) -> Path | None:
    plans = sorted((root / "run-artifacts" / slug / "staging-plans").glob("*/staging-plan.json"))
    return plans[-1] if plans else None


def verify_staging_plan(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": "ao-operator/staged-commit-verification/v1", "verdict": "FAIL", "errors": [f"missing: {path}"]}
    except json.JSONDecodeError as exc:
        return {
            "schema": "ao-operator/staged-commit-verification/v1",
            "verdict": "FAIL",
            "errors": [f"invalid JSON: {exc}"],
        }
    if not isinstance(data, dict):
        return {"schema": "ao-operator/staged-commit-verification/v1", "verdict": "FAIL", "errors": ["plan must be a JSON object"]}

    if data.get("schema") != "ao-operator/staged-commit-plan/v1":
        errors.append("schema must be ao-operator/staged-commit-plan/v1")
    if data.get("verdict") != "PASS":
        errors.append("staging plan verdict must be PASS")

    batches = data.get("batches", [])
    if not isinstance(batches, list) or not batches:
        errors.append("batches must be a non-empty list")
        batches = []

    expected_first = ["runtime-guardrails-and-tests", "operator-sdd-and-manifest"]
    actual_first = [batch.get("group_id") for batch in batches[:2] if isinstance(batch, dict)]
    if actual_first != expected_first:
        errors.append("first batches must be runtime-guardrails-and-tests then operator-sdd-and-manifest")

    batch_results: list[dict[str, Any]] = []
    seen_failed_diagnostics_batch = False
    for index, batch in enumerate(batches):
        if not isinstance(batch, dict):
            errors.append(f"batches[{index}] must be an object")
            continue
        group_id = str(batch.get("group_id") or "")
        success_evidence = batch.get("success_evidence") is True
        pathspec_file = str(batch.get("pathspec_file") or "")
        plan_paths = [path for path in batch.get("paths", []) if isinstance(path, str)]
        pathspec_paths: list[str] = []

        if not pathspec_file:
            errors.append(f"{group_id}: pathspec_file is required")
        else:
            pathspec_path = root / pathspec_file
            if not pathspec_path.is_file():
                errors.append(f"{group_id}: missing pathspec {pathspec_file}")
            else:
                pathspec_paths = [
                    line.strip()
                    for line in pathspec_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if pathspec_paths != plan_paths:
                    errors.append(f"{group_id}: pathspec entries do not match staging-plan paths")

        if batch.get("path_count") != len(plan_paths):
            errors.append(f"{group_id}: path_count does not match paths length")

        paths_to_check = pathspec_paths or plan_paths
        classifications = {path_item: classify_path(path_item) for path_item in paths_to_check}
        mismatched = [path_item for path_item, classified in classifications.items() if classified != group_id]
        if mismatched:
            errors.append(f"{group_id}: path classification mismatch: {', '.join(mismatched[:5])}")

        failed_diag_paths = [
            path_item
            for path_item, classified in classifications.items()
            if classified == "failed-live-diagnostics"
        ]
        if success_evidence and failed_diag_paths:
            errors.append(f"{group_id}: success batch includes failed-live diagnostics")
        if group_id == "failed-live-diagnostics":
            seen_failed_diagnostics_batch = True
            if success_evidence:
                errors.append("failed-live-diagnostics batch must have success_evidence=false")

        batch_results.append(
            {
                "group_id": group_id,
                "success_evidence": success_evidence,
                "pathspec_file": pathspec_file,
                "path_count": len(plan_paths),
                "pathspec_count": len(pathspec_paths),
                "failed_live_diagnostic_paths": len(failed_diag_paths),
                "classification_mismatches": len(mismatched),
            }
        )

    if not seen_failed_diagnostics_batch:
        errors.append("failed-live-diagnostics batch is required when diagnostics are present")

    return {
        "schema": "ao-operator/staged-commit-verification/v1",
        "plan": str(path),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "batch_results": batch_results,
        "negative_constraints": [
            "Success batches must not include failed-live diagnostics.",
            "failed-live-diagnostics must remain success_evidence=false.",
            "Verifier must not stage or commit files.",
        ],
    }


def git_output(args: list[str], *, root: Path = ROOT, env: dict[str, str] | None = None) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def selected_rehearsal_batches(staging_plan: dict[str, Any], group_ids: list[str]) -> list[dict[str, Any]]:
    batches = staging_plan.get("batches", [])
    if not isinstance(batches, list):
        return []
    selected: list[dict[str, Any]] = []
    for group_id in group_ids:
        batch = next(
            (item for item in batches if isinstance(item, dict) and item.get("group_id") == group_id),
            None,
        )
        if isinstance(batch, dict):
            selected.append(batch)
    return selected


def rehearse_staging_plan(
    path: Path,
    *,
    group_ids: list[str],
    root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    verification = verify_staging_plan(path, root=root)
    if verification["verdict"] != "PASS":
        errors.extend(f"staging-plan verification: {error}" for error in verification.get("errors", []))

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": "ao-operator/staging-rehearsal/v1",
            "plan": str(path),
            "verdict": "FAIL",
            "errors": [f"cannot read staging plan: {exc}"],
        }

    selected = selected_rehearsal_batches(data, group_ids)
    missing_groups = [group_id for group_id in group_ids if group_id not in {batch.get("group_id") for batch in selected}]
    errors.extend(f"selected group missing: {group_id}" for group_id in missing_groups)

    real_cached_before = git_output(["diff", "--cached", "--name-only"], root=root)
    expected_paths = [
        path_item
        for batch in selected
        for path_item in batch.get("paths", [])
        if isinstance(path_item, str)
    ]
    expected_set = set(expected_paths)
    rehearsal_cached: list[str] = []
    batch_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="ao-operator-rehearsal-") as temp_dir:
        temp_index = Path(temp_dir) / "index"
        git_index_path = git_output(["rev-parse", "--git-path", "index"], root=root)[0]
        source_index = root / git_index_path
        if source_index.is_file():
            shutil.copy2(source_index, temp_index)
        env = {**dict(os.environ), "GIT_INDEX_FILE": str(temp_index)}

        for batch in selected:
            group_id = str(batch.get("group_id") or "")
            pathspec_file = str(batch.get("pathspec_file") or "")
            success_evidence = batch.get("success_evidence") is True
            if not pathspec_file:
                errors.append(f"{group_id}: pathspec_file is required")
                continue
            if not success_evidence:
                errors.append(f"{group_id}: rehearsal refuses non-success evidence batches")
                continue
            before = set(git_output(["diff", "--cached", "--name-only"], root=root, env=env))
            subprocess.run(
                ["git", "add", f"--pathspec-from-file={pathspec_file}"],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            after = set(git_output(["diff", "--cached", "--name-only"], root=root, env=env))
            staged_now = sorted(after - before)
            batch_paths = [path_item for path_item in batch.get("paths", []) if isinstance(path_item, str)]
            unexpected = [path_item for path_item in staged_now if path_item not in batch_paths]
            missing = [path_item for path_item in batch_paths if path_item not in after]
            if unexpected:
                errors.append(f"{group_id}: unexpected staged paths: {', '.join(unexpected[:5])}")
            if missing:
                errors.append(f"{group_id}: expected paths not staged: {', '.join(missing[:5])}")
            batch_results.append(
                {
                    "group_id": group_id,
                    "pathspec_file": pathspec_file,
                    "expected_count": len(batch_paths),
                    "staged_now_count": len(staged_now),
                    "missing_count": len(missing),
                    "unexpected_count": len(unexpected),
                }
            )
        rehearsal_cached = git_output(["diff", "--cached", "--name-only"], root=root, env=env)

    real_cached_after = git_output(["diff", "--cached", "--name-only"], root=root)
    if real_cached_after != real_cached_before:
        errors.append("real git index changed during rehearsal")

    rehearsal_set = set(rehearsal_cached)
    unexpected_final = sorted(rehearsal_set - expected_set)
    missing_final = sorted(expected_set - rehearsal_set)
    if unexpected_final:
        errors.append("rehearsal staged unexpected paths: " + ", ".join(unexpected_final[:5]))
    if missing_final:
        errors.append("rehearsal did not stage expected paths: " + ", ".join(missing_final[:5]))

    failed_diag_paths = [path_item for path_item in rehearsal_cached if classify_path(path_item) == "failed-live-diagnostics"]
    if failed_diag_paths:
        errors.append("rehearsal staged failed-live diagnostics: " + ", ".join(failed_diag_paths[:5]))

    return {
        "schema": "ao-operator/staging-rehearsal/v1",
        "plan": str(path),
        "selected_groups": group_ids,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "real_index_untouched": real_cached_after == real_cached_before,
        "expected_path_count": len(expected_paths),
        "rehearsed_staged_count": len(rehearsal_cached),
        "failed_live_diagnostic_paths": len(failed_diag_paths),
        "batch_results": batch_results,
        "negative_constraints": [
            "Use a temporary GIT_INDEX_FILE only.",
            "Do not stage failed-live diagnostics in success-batch rehearsal.",
            "Do not alter the real git index.",
        ],
    }


def review_staging_batch(path: Path, *, group_id: str, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    verification = verify_staging_plan(path, root=root)
    if verification["verdict"] != "PASS":
        errors.extend(f"staging-plan verification: {error}" for error in verification.get("errors", []))

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": "ao-operator/staging-batch-review/v1",
            "plan": str(path),
            "group_id": group_id,
            "verdict": "FAIL",
            "errors": [f"cannot read staging plan: {exc}"],
        }

    batches = data.get("batches", [])
    batch = next(
        (item for item in batches if isinstance(item, dict) and item.get("group_id") == group_id),
        None,
    )
    if not isinstance(batch, dict):
        return {
            "schema": "ao-operator/staging-batch-review/v1",
            "plan": str(path),
            "group_id": group_id,
            "verdict": "FAIL",
            "errors": [*errors, f"selected group missing: {group_id}"],
        }

    success_evidence = batch.get("success_evidence") is True
    if not success_evidence:
        errors.append(f"{group_id}: review refuses non-success evidence batches")

    pathspec_file = str(batch.get("pathspec_file") or "")
    pathspec_entries: list[str] = []
    pathspec_sha256 = ""
    if not pathspec_file:
        errors.append(f"{group_id}: pathspec_file is required")
    else:
        pathspec_path = root / pathspec_file
        try:
            pathspec_body = pathspec_path.read_bytes()
        except OSError as exc:
            errors.append(f"{group_id}: cannot read pathspec: {exc}")
        else:
            pathspec_sha256 = hashlib.sha256(pathspec_body).hexdigest()
            pathspec_entries = [
                line.strip()
                for line in pathspec_body.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            ]

    plan_paths = [path_item for path_item in batch.get("paths", []) if isinstance(path_item, str)]
    if pathspec_entries != plan_paths:
        errors.append(f"{group_id}: pathspec entries do not match staging-plan paths")

    failed_diag_paths = [path_item for path_item in pathspec_entries if classify_path(path_item) == "failed-live-diagnostics"]
    if failed_diag_paths:
        errors.append(f"{group_id}: pathspec includes failed-live diagnostics")

    return {
        "schema": "ao-operator/staging-batch-review/v1",
        "plan": str(path),
        "group_id": group_id,
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "title": batch.get("title"),
        "success_evidence": success_evidence,
        "path_count": len(plan_paths),
        "pathspec_file": pathspec_file,
        "pathspec_sha256": pathspec_sha256,
        "pathspec_entries": pathspec_entries,
        "stage_command": batch.get("stage_command"),
        "commit_command": batch.get("commit_command"),
        "verification_commands": [
            "git diff --cached --name-only",
            "git diff --check --cached",
            "python3 -m pytest -q tests/test_plan_evidence_commits.py tests/test_factory_run_preflight.py tests/test_validate_factory_topology.py tests/test_agent_manifest_sync.py",
            "FACTORY_V3_AO_RUNTIME_PATH=${FACTORY_V3_AO_RUNTIME_PATH} PATH=\"${FACTORY_V3_AO_RUNTIME_PATH}/target/release:$PATH\" python3 ${FACTORY_V3_FACTORY_SKILLS_PATH}/scripts/verify_closure.py --repo . --with-pytest --json",
        ],
        "negative_constraints": [
            "Review only; do not stage or commit from this command.",
            "Pathspec entries must exactly match the staging-plan batch paths.",
            "Do not include failed-live diagnostics in success-batch review.",
        ],
    }


def rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan AO Operator evidence commit bundles without staging files")
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--write", action="store_true", help="Write report under run-artifacts/<slug>/commit-readiness/")
    parser.add_argument("--write-staging-plan", action="store_true", help="Write staged-commit plan and pathspec files")
    parser.add_argument("--verify-staging-plan", help="Verify a staged-commit plan and its pathspec files")
    parser.add_argument("--verify-latest-staging-plan", action="store_true", help="Verify latest staged-commit plan for --slug")
    parser.add_argument("--rehearse-staging-plan", help="Rehearse selected staging batches using a temporary git index")
    parser.add_argument("--rehearse-latest-staging-plan", action="store_true", help="Rehearse latest staged-commit plan for --slug")
    parser.add_argument("--review-staging-plan", help="Review one staged-commit batch without staging files")
    parser.add_argument("--review-latest-staging-plan", action="store_true", help="Review latest staged-commit plan for --slug")
    parser.add_argument("--review-group", default="runtime-guardrails-and-tests", help="Staging group to review")
    parser.add_argument(
        "--rehearse-groups",
        default="runtime-guardrails-and-tests,operator-sdd-and-manifest",
        help="Comma-separated staging groups to rehearse",
    )
    parser.add_argument("--allow-unclassified", action="store_true", help="Return success even when unclassified paths exist")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    if args.review_staging_plan or args.review_latest_staging_plan:
        if args.review_latest_staging_plan:
            target = latest_staging_plan(slug=args.slug, root=ROOT)
            if target is None:
                result = {
                    "schema": "ao-operator/staging-batch-review/v1",
                    "verdict": "FAIL",
                    "errors": [f"no staging plan found for {args.slug}"],
                    "group_id": args.review_group,
                }
            else:
                result = review_staging_batch(target, group_id=args.review_group, root=ROOT)
        else:
            target = Path(str(args.review_staging_plan))
            if not target.is_absolute():
                target = ROOT / target
            result = review_staging_batch(target, group_id=args.review_group, root=ROOT)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"verdict={result['verdict']} group={result.get('group_id')}")
            print(f"pathspec={result.get('pathspec_file', '')}")
            print(f"stage={result.get('stage_command', '')}")
            print(f"commit={result.get('commit_command', '')}")
            for entry in result.get("pathspec_entries", []):
                print(entry)
            for error in result.get("errors", []):
                print(f"error: {error}")
        return 0 if result["verdict"] == "PASS" else 1

    if args.rehearse_staging_plan or args.rehearse_latest_staging_plan:
        group_ids = [group.strip() for group in args.rehearse_groups.split(",") if group.strip()]
        if args.rehearse_latest_staging_plan:
            target = latest_staging_plan(slug=args.slug, root=ROOT)
            if target is None:
                result = {
                    "schema": "ao-operator/staging-rehearsal/v1",
                    "verdict": "FAIL",
                    "errors": [f"no staging plan found for {args.slug}"],
                }
            else:
                result = rehearse_staging_plan(target, group_ids=group_ids, root=ROOT)
        else:
            target = Path(str(args.rehearse_staging_plan))
            if not target.is_absolute():
                target = ROOT / target
            result = rehearse_staging_plan(target, group_ids=group_ids, root=ROOT)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"verdict={result['verdict']}")
            for error in result.get("errors", []):
                print(f"error: {error}")
        return 0 if result["verdict"] == "PASS" else 1

    if args.verify_staging_plan or args.verify_latest_staging_plan:
        if args.verify_latest_staging_plan:
            target = latest_staging_plan(slug=args.slug, root=ROOT)
            if target is None:
                result = {
                    "schema": "ao-operator/staged-commit-verification/v1",
                    "verdict": "FAIL",
                    "errors": [f"no staging plan found for {args.slug}"],
                }
            else:
                result = verify_staging_plan(target, root=ROOT)
        else:
            target = Path(str(args.verify_staging_plan))
            if not target.is_absolute():
                target = ROOT / target
            result = verify_staging_plan(target, root=ROOT)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"verdict={result['verdict']}")
            for error in result.get("errors", []):
                print(f"error: {error}")
        return 0 if result["verdict"] == "PASS" else 1

    plan = build_plan(git_status(ROOT), slug=args.slug)
    if args.write:
        plan["report"] = str(write_plan(plan, slug=args.slug, root=ROOT))
    if args.write_staging_plan:
        staging_plan = build_staging_plan(plan, slug=args.slug)
        plan["staging_plan"] = str(write_staging_plan(staging_plan, slug=args.slug, root=ROOT))
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(f"verdict={plan['verdict']} total_paths={plan['total_paths']}")
        for group in plan["groups"]:
            print(f"{group['id']}: {group['count']} path(s)")
        for warning in plan["warnings"]:
            print(f"warning: {warning}")
        for error in plan["errors"]:
            print(f"error: {error}")
    return 0 if plan["verdict"] == "PASS" or args.allow_unclassified else 1


if __name__ == "__main__":
    raise SystemExit(main())
