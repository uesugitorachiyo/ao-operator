#!/usr/bin/env python3
"""Gate R: post-execution role artifact validation for AO Operator."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/gate-r/v1"
FAILED_RESULTS = {"BLOCKED", "REJECTED"}
SUCCESS_RESULTS = {"DONE", "DONE_WITH_CONCERNS"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def status_result(text: str) -> str:
    match = re.search(r"(?m)^Result:\s*([A-Z_]+)\s*$", text)
    return match.group(1) if match else ""


def status_artifact(text: str) -> str:
    match = re.search(r"(?m)^Artifact:\s*(.+?)\s*$", text)
    return match.group(1).strip().strip("`") if match else ""


def artifact_is_concrete_path(value: str) -> bool:
    if not value or "/" not in value:
        return False
    if value.lower().startswith(("event", "ao event", "run event")):
        return False
    if value.startswith(("http://", "https://")):
        return False
    return True


def expected_role_artifacts(gate_b: dict[str, Any], slug: str) -> dict[str, str]:
    spec = gate_b.get("spec")
    if isinstance(spec, dict) and isinstance(spec.get("role_artifacts"), dict):
        return {
            str(role_id): str(path)
            for role_id, path in spec["role_artifacts"].items()
            if role_id and path
        }

    outputs: dict[str, str] = {}
    contracts = gate_b.get("role_contracts")
    if not isinstance(contracts, list):
        return outputs
    for item in contracts:
        if not isinstance(item, dict):
            continue
        role_id = str(item.get("id") or "")
        if role_id:
            outputs[role_id] = f"run-artifacts/{slug}/roles/{role_id}.md"
    return outputs


def allowed_artifacts(gate_b: dict[str, Any], slug: str) -> dict[str, set[str]]:
    spec = gate_b.get("spec")
    if isinstance(spec, dict) and isinstance(spec.get("roles"), list):
        out: dict[str, set[str]] = {}
        for item in spec["roles"]:
            if not isinstance(item, dict):
                continue
            role_id = str(item.get("id") or "")
            allowed = item.get("allowed_artifacts")
            if role_id and isinstance(allowed, list):
                out[role_id] = {str(value) for value in allowed if isinstance(value, str)}
        return out

    return {
        role_id: {path}
        for role_id, path in expected_role_artifacts(gate_b, slug).items()
    }


def partition_slices(gate_b: dict[str, Any]) -> list[dict[str, Any]]:
    spec = gate_b.get("spec")
    if isinstance(spec, dict) and isinstance(spec.get("partition_slices"), list):
        return [item for item in spec["partition_slices"] if isinstance(item, dict)]
    partition = gate_b.get("partition")
    if isinstance(partition, dict) and isinstance(partition.get("slices"), list):
        return [item for item in partition["slices"] if isinstance(item, dict)]
    return []


def slice_role_id(base: str, slice_item: dict[str, Any], outputs: dict[str, str], slice_count: int) -> str:
    raw_id = slice_item.get("slice_id")
    numbered = f"{base}-{raw_id}"
    if raw_id is not None and (numbered in outputs or slice_count > 1):
        return numbered
    if base in outputs:
        return base
    slice_name = str(slice_item.get("id") or "")
    match = re.search(r"(\d+)$", slice_name)
    if match:
        return f"{base}-{match.group(1)}"
    return numbered


def read_role_body(repo: Path, slug: str, role_id: str) -> tuple[str, str]:
    path = repo / "run-artifacts" / slug / "roles" / f"{role_id}.md"
    if not path.is_file():
        return "", ""
    body = path.read_text(encoding="utf-8", errors="replace")
    return body, status_result(body)


def text_mentions(text: str, value: str) -> bool:
    return bool(value) and value in text


def validate_slice_integrator_contract(
    *,
    repo: Path,
    slug: str,
    gate_b: dict[str, Any],
    outputs: dict[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    slices = partition_slices(gate_b)
    if not slices:
        return [], []

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    integrator_body, integrator_result = read_role_body(repo, slug, "integrator")
    if not integrator_body:
        checks.append({"id": "slice_integrator:integrator", "status": "FAIL", "message": "missing integrator role artifact"})
        errors.append("slice fan-in: missing integrator role artifact")
    elif integrator_result not in SUCCESS_RESULTS:
        checks.append(
            {
                "id": "slice_integrator:integrator",
                "status": "FAIL",
                "result": integrator_result,
                "message": "integrator did not return a successful result",
            }
        )
        errors.append(f"slice fan-in: integrator did not return a successful result ({integrator_result or 'missing'})")
    else:
        checks.append({"id": "slice_integrator:integrator", "status": "PASS", "result": integrator_result})

    for item in slices:
        slice_name = str(item.get("id") or item.get("slice_id") or "slice")
        implementer_id = slice_role_id("implementer-slice", item, outputs, len(slices))
        reviewer_id = slice_role_id("reviewer-slice", item, outputs, len(slices))
        patch_meta = repo / "run-artifacts" / slug / "patches" / f"{implementer_id}.json"
        patch_file = repo / "run-artifacts" / slug / "patches" / f"{implementer_id}.patch"

        patch_check: dict[str, Any] = {
            "id": f"slice_patch_bundle:{slice_name}",
            "task": implementer_id,
            "path": rel(repo, patch_meta),
        }
        if not patch_meta.is_file() or not patch_file.is_file():
            patch_check["status"] = "FAIL"
            patch_check["message"] = "missing implementer patch bundle metadata or patch file"
            errors.append(f"{slice_name}: missing patch bundle for {implementer_id}")
        else:
            try:
                meta = load_json(patch_meta)
            except json.JSONDecodeError as exc:
                meta = {}
                patch_check["status"] = "FAIL"
                patch_check["message"] = f"patch bundle metadata is invalid JSON: {exc}"
                errors.append(f"{slice_name}: invalid patch bundle metadata for {implementer_id}: {exc}")
            if patch_check.get("status") != "FAIL":
                patch_check["status"] = "PASS"
                patch_check["patch"] = rel(repo, patch_file)
                patch_check["diff_bytes"] = meta.get("diff_bytes")
        checks.append(patch_check)

        reviewer_body, reviewer_result = read_role_body(repo, slug, reviewer_id)
        reviewer_check: dict[str, Any] = {
            "id": f"slice_reviewer_result:{slice_name}",
            "task": reviewer_id,
        }
        if reviewer_result not in SUCCESS_RESULTS:
            reviewer_check["status"] = "FAIL"
            reviewer_check["result"] = reviewer_result
            reviewer_check["message"] = "reviewer result is missing or unsuccessful"
            errors.append(f"{slice_name}: reviewer {reviewer_id} result is missing or unsuccessful")
        else:
            reviewer_check["status"] = "PASS"
            reviewer_check["result"] = reviewer_result
        checks.append(reviewer_check)

        disposition_terms = [implementer_id, reviewer_id, slice_name]
        writes = [str(value) for value in item.get("writes", []) if isinstance(value, str)]
        disposition_missing = [
            value for value in [*disposition_terms, *writes]
            if not text_mentions(integrator_body, value)
        ]
        disposition_check: dict[str, Any] = {
            "id": f"slice_integrator_disposition:{slice_name}",
            "task": "integrator",
            "slice": slice_name,
            "writes": writes,
        }
        if disposition_missing:
            disposition_check["status"] = "FAIL"
            disposition_check["missing"] = disposition_missing
            disposition_check["message"] = "integrator artifact does not disposition every slice handoff and final write"
            errors.append(f"{slice_name}: integrator disposition missing {', '.join(disposition_missing)}")
        else:
            disposition_check["status"] = "PASS"
        checks.append(disposition_check)

        if writes:
            checks.append(
                {
                    "id": f"slice_final_artifact_mapping:{slice_name}",
                    "status": "PASS",
                    "slice": slice_name,
                    "task": implementer_id,
                    "final_artifacts": writes,
                    "rejoin_artifact": item.get("rejoin_artifact", ""),
                }
            )
        else:
            checks.append(
                {
                    "id": f"slice_final_artifact_mapping:{slice_name}",
                    "status": "FAIL",
                    "slice": slice_name,
                    "task": implementer_id,
                    "message": "slice has no final artifact mapping",
                }
            )
            errors.append(f"{slice_name}: slice has no final artifact mapping")

    return checks, errors


def run_gate(*, repo: Path, slug: str, gate_b_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    gate_b = load_json(gate_b_path)
    outputs = expected_role_artifacts(gate_b, slug)
    allowed_by_role = allowed_artifacts(gate_b, slug)
    if not outputs:
        errors.append("Gate B report does not contain role_contracts")

    for role_id, output in outputs.items():
        path = repo / output
        check: dict[str, Any] = {"id": f"role_output:{role_id}", "path": output}
        if not path.is_file():
            check["status"] = "FAIL"
            check["message"] = "missing declared role output"
            errors.append(f"{role_id}: missing declared role output {output}")
        else:
            body = path.read_text(encoding="utf-8", errors="replace")
            result = status_result(body)
            artifact = status_artifact(body)
            check["result"] = result
            check["artifact"] = artifact
            if not result:
                check["status"] = "FAIL"
                check["message"] = "missing STATUS Result line"
                errors.append(f"{role_id}: missing STATUS Result line in {output}")
            elif result in FAILED_RESULTS:
                check["status"] = "FAIL"
                check["message"] = f"role returned {result}"
                errors.append(f"{role_id}: role returned {result}")
            elif not artifact:
                check["status"] = "FAIL"
                check["message"] = "missing STATUS Artifact line"
                errors.append(f"{role_id}: missing STATUS Artifact line in {output}")
            elif artifact_is_concrete_path(artifact) and artifact not in allowed_by_role.get(role_id, set()):
                check["status"] = "FAIL"
                check["message"] = f"artifact drift outside Gate B contract: {artifact}"
                errors.append(f"{role_id}: artifact drift outside Gate B contract: {artifact}")
            else:
                check["status"] = "PASS"
                check["message"] = "declared role output is complete"
        checks.append(check)

    roles_dir = repo / "run-artifacts" / slug / "roles"
    expected_role_paths = {f"run-artifacts/{slug}/roles/{role_id}.md" for role_id in outputs}
    if roles_dir.is_dir():
        for path in sorted(roles_dir.glob("*.md")):
            relative = rel(repo, path)
            if relative not in expected_role_paths:
                checks.append({"id": "unexpected_role_artifact", "path": relative, "status": "FAIL"})
                errors.append(f"unexpected role artifact outside Gate B contract: {relative}")

    slice_checks, slice_errors = validate_slice_integrator_contract(
        repo=repo,
        slug=slug,
        gate_b=gate_b,
        outputs=outputs,
    )
    checks.extend(slice_checks)
    errors.extend(slice_errors)

    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "dispatch_authorized": False,
        "live_providers_run": False,
        "slug": slug,
        "gate_b": rel(repo, gate_b_path),
        "checks": checks,
        "errors": errors,
        "verdict": "PASS" if not errors else "FAIL",
        "next_safe_command": (
            "Gate R passed; Factory evaluation may be trusted."
            if not errors
            else "Fix Gate R role-output drift before closure."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AO Operator Gate R.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--slug", required=True)
    parser.add_argument("--gate-b", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_gate(repo=args.repo, slug=args.slug, gate_b_path=args.gate_b)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"verdict={report['verdict']}")
        for error in report["errors"]:
            print(f"error={error}", file=sys.stderr)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
