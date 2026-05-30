#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/ao2-release-evaluator-decision/v1"
READINESS_BRIDGE_SCHEMA = "ao-operator/hermes-ao-bridge/v1"
READINESS_SCHEMA = "ao2.cp-release-readiness.v1"
HANDOFF_CHECKLIST_SCHEMA = "ao-operator/ao2-release-handoff-checklist/v1"
SUPPORT_BUNDLE_BRIDGE_ACTION = "release-support-bundle-status"
SUPPORT_BUNDLE_SCHEMA = "ao2.cp-release-support-bundle.v1"
RELEASE_ASSEMBLY_SCHEMA = "ao2.cp-release-assembly.v1"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected json object in {path}")
    return value


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def as_str(value: Any, default: str = "missing") -> str:
    return value if isinstance(value, str) and value else default


def as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def extract_readiness(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version") == READINESS_SCHEMA:
        return payload
    if (
        payload.get("schema") == READINESS_BRIDGE_SCHEMA
        and payload.get("action") == "release-readiness-status"
        and isinstance(payload.get("readiness_snapshot"), dict)
    ):
        snapshot = payload["readiness_snapshot"]
        if snapshot.get("schema_version") == READINESS_SCHEMA:
            return snapshot
    return None


def extract_support_bundle(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version") == SUPPORT_BUNDLE_SCHEMA:
        return payload
    if (
        payload.get("schema") == READINESS_BRIDGE_SCHEMA
        and payload.get("action") == SUPPORT_BUNDLE_BRIDGE_ACTION
        and isinstance(payload.get("support_bundle_snapshot"), dict)
    ):
        snapshot = payload["support_bundle_snapshot"]
        if snapshot.get("schema_version") == SUPPORT_BUNDLE_SCHEMA:
            return snapshot
    return None


def release_from(readiness: dict[str, Any] | None, checklist: dict[str, Any]) -> dict[str, Any]:
    release = readiness.get("release", {}) if isinstance(readiness, dict) else {}
    if not isinstance(release, dict) or not release:
        release = checklist.get("release", {})
    return release if isinstance(release, dict) else {}


def check_status(
    check_id: str,
    label: str,
    observed: str,
    expected: str,
    blockers: list[str],
    *,
    allow_pending_self_reference: bool = False,
) -> dict[str, str]:
    status = "passed" if observed == expected else "blocked"
    if status == "blocked" and allow_pending_self_reference:
        status = "passed_pending_self_reference"
    if status == "blocked":
        blockers.append(f"{check_id}: expected {expected}, observed {observed}")
    return {
        "id": check_id,
        "label": label,
        "observed": observed,
        "expected": expected,
        "status": status,
    }


def is_missing_evaluator_blocker(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value in {
        "release_evaluator_decision: expected accepted, observed missing",
        "candidate_correlation: expected matched, observed mismatched",
        "handoff_status: expected ready, observed attention",
    } or value.startswith("release_evaluator_version unknown does not match ") or value.startswith(
        "release_evaluator_tag unknown does not match "
    )


def only_missing_evaluator_blockers(values: Any) -> bool:
    if not isinstance(values, list) or not values:
        return False
    return all(is_missing_evaluator_blocker(value) for value in values)


def candidate_correlation_is_only_missing_evaluator(
    release_assembly: dict[str, Any],
    support_frontend: dict[str, Any],
    release: dict[str, Any],
) -> bool:
    if as_str(release_assembly.get("candidate_correlation") or support_frontend.get("candidate_correlation")) != "mismatched":
        return False
    detail = release_assembly.get("candidate_correlation_detail")
    if not isinstance(detail, dict):
        return False
    blockers = detail.get("blockers")
    if not only_missing_evaluator_blockers(blockers):
        return False
    release_version = as_str(release.get("version"))
    release_tag = as_str(release.get("release_tag"))
    return (
        as_str(detail.get("release_version")) == release_version
        and as_str(detail.get("release_tag")) == release_tag
        and as_str(detail.get("codex_acceptance_version")) == release_version
        and as_str(detail.get("claude_acceptance_version")) == release_version
        and as_str(detail.get("three_os_version")) == release_version
        and as_str(detail.get("release_evaluator_version")) == "unknown"
        and as_str(detail.get("release_evaluator_tag")) == "unknown"
    )


def should_apply_missing_evaluator_self_reference_exception(
    *,
    readiness: dict[str, Any] | None,
    readiness_frontend: dict[str, Any],
    readiness_blockers: Any,
    checklist: dict[str, Any],
    checklist_blockers: Any,
    support_frontend: dict[str, Any],
    release_assembly: dict[str, Any],
    release: dict[str, Any],
) -> bool:
    readiness_status = as_str(readiness.get("status") if readiness else readiness_frontend.get("status"))
    handoff_status = as_str(checklist.get("status"))
    assembly_status = as_str(release_assembly.get("status") or support_frontend.get("status"))
    missing_count = str(support_frontend.get("missing_artifact_count", "missing"))
    return (
        readiness_status == "attention"
        and handoff_status == "blocked"
        and assembly_status == "attention"
        and missing_count == "0"
        and only_missing_evaluator_blockers(readiness_blockers)
        and only_missing_evaluator_blockers(checklist_blockers)
        and candidate_correlation_is_only_missing_evaluator(
            release_assembly, support_frontend, release
        )
    )


def build_decision(
    *,
    readiness_path: Path,
    readiness_source: dict[str, Any],
    checklist_path: Path,
    checklist: dict[str, Any],
    support_bundle_path: Path,
    support_bundle_source: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    readiness = extract_readiness(readiness_source)
    readiness_frontend = readiness_source.get("frontend_status", {})
    if not isinstance(readiness_frontend, dict):
        readiness_frontend = {}
    support_bundle = extract_support_bundle(support_bundle_source)
    support_frontend = support_bundle_source.get("frontend_status", {})
    if not isinstance(support_frontend, dict):
        support_frontend = {}
    release_assembly = (
        support_bundle.get("release_assembly")
        if isinstance(support_bundle, dict)
        and isinstance(support_bundle.get("release_assembly"), dict)
        else {}
    )
    release = release_from(readiness, checklist)
    readiness_blockers = readiness.get("blockers", []) if isinstance(readiness, dict) else []
    checklist_blockers = checklist.get("blockers", [])
    self_reference_exception_applied = should_apply_missing_evaluator_self_reference_exception(
        readiness=readiness,
        readiness_frontend=readiness_frontend,
        readiness_blockers=readiness_blockers,
        checklist=checklist,
        checklist_blockers=checklist_blockers,
        support_frontend=support_frontend,
        release_assembly=release_assembly,
        release=release,
    )

    checks: list[dict[str, str]] = []
    checks.append(
        check_status(
            "readiness_schema",
            "Readiness schema",
            as_str(readiness.get("schema_version") if readiness else None),
            READINESS_SCHEMA,
            blockers,
        )
    )
    checks.append(
        check_status(
            "readiness_status",
            "Release readiness status",
            as_str(readiness.get("status") if readiness else readiness_frontend.get("status")),
            "ready",
            blockers,
            allow_pending_self_reference=self_reference_exception_applied,
        )
    )
    checks.append(
        check_status(
            "handoff_checklist_schema",
            "Handoff checklist schema",
            as_str(checklist.get("schema")),
            HANDOFF_CHECKLIST_SCHEMA,
            blockers,
        )
    )
    checks.append(
        check_status(
            "handoff_checklist_status",
            "Handoff checklist status",
            as_str(checklist.get("status")),
            "ready_for_evaluator_closer",
            blockers,
            allow_pending_self_reference=self_reference_exception_applied,
        )
    )
    checks.append(
        check_status(
            "support_bundle_schema",
            "Support bundle schema",
            as_str(support_bundle.get("schema_version") if support_bundle else None),
            SUPPORT_BUNDLE_SCHEMA,
            blockers,
        )
    )
    checks.append(
        check_status(
            "release_assembly_schema",
            "Release assembly schema",
            as_str(release_assembly.get("schema_version")),
            RELEASE_ASSEMBLY_SCHEMA,
            blockers,
        )
    )
    checks.append(
        check_status(
            "release_assembly_status",
            "Release assembly status",
            as_str(release_assembly.get("status") or support_frontend.get("status")),
            "assembled",
            blockers,
            allow_pending_self_reference=self_reference_exception_applied,
        )
    )
    checks.append(
        check_status(
            "release_assembly_candidate_correlation",
            "Release assembly candidate correlation",
            as_str(
                release_assembly.get("candidate_correlation")
                or support_frontend.get("candidate_correlation")
            ),
            "matched",
            blockers,
            allow_pending_self_reference=self_reference_exception_applied,
        )
    )
    checks.append(
        check_status(
            "release_assembly_missing_artifacts",
            "Release assembly missing artifacts",
            str(support_frontend.get("missing_artifact_count", "missing")),
            "0",
            blockers,
        )
    )

    if isinstance(readiness_blockers, list):
        for blocker in readiness_blockers:
            if self_reference_exception_applied and is_missing_evaluator_blocker(blocker):
                continue
            blockers.append(f"readiness_blocker: {blocker}")
    if isinstance(checklist_blockers, list):
        for blocker in checklist_blockers:
            if self_reference_exception_applied and is_missing_evaluator_blocker(blocker):
                continue
            blockers.append(f"handoff_checklist_blocker: {blocker}")

    readiness_control_plane_approves = as_bool(
        nested(readiness or {}, "operator_decision", "control_plane_approves_release"),
        default=as_bool(readiness_frontend.get("control_plane_approves_release")),
    )
    checklist_control_plane_approves = as_bool(
        nested(checklist, "operator_decision", "control_plane_approves_release")
    )
    support_control_plane_approves = as_bool(
        release_assembly.get("control_plane_approves_release"),
        default=as_bool(support_frontend.get("control_plane_approves_release")),
    )
    if (
        readiness_control_plane_approves
        or checklist_control_plane_approves
        or support_control_plane_approves
    ):
        blockers.append("trust_boundary: control plane must not approve release")

    release_version = as_str(release.get("version") if isinstance(release, dict) else None)
    assembly_version = as_str(
        release_assembly.get("release_candidate_version")
        or support_frontend.get("release_candidate_version")
    )
    if release_version != "missing" and assembly_version != release_version:
        blockers.append(
            f"release_assembly_version: expected {release_version}, observed {assembly_version}"
        )
    accepted = not blockers
    decision = "accept_phase1_release_candidate" if accepted else "reject_phase1_release_candidate"
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "decision": decision,
        "release": release,
        "checks": checks,
        "blockers": blockers,
        "self_reference_exception": {
            "status": "applied" if self_reference_exception_applied else "not_applicable",
            "reason": (
                "control-plane readiness was waiting only for the ao-operator evaluator decision currently being produced"
                if self_reference_exception_applied
                else "no evaluator self-reference gap was detected"
            ),
        },
        "evidence": {
            "release_readiness_status": str(readiness_path),
            "release_handoff_checklist": str(checklist_path),
            "release_support_bundle_status": str(support_bundle_path),
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
        "next_action": (
            "release candidate is accepted by ao-operator evaluator-closer for release-line handoff"
            if accepted
            else "resolve blockers before release-line handoff"
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release", {})
    lines = [
        "# AO2 Release Evaluator Decision",
        "",
        f"- status: `{payload.get('status', 'missing')}`",
        f"- decision: `{payload.get('decision', 'missing')}`",
        f"- release_tag: `{release.get('release_tag', 'missing') if isinstance(release, dict) else 'missing'}`",
        "- release_acceptance_owner: `ao-operator evaluator-closer`",
        "- control_plane_approves_release: `False`",
        "",
        "## Checks",
        "",
        "| Check | Status | Observed | Expected |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload.get("checks", []):
        lines.append(
            f"| {item['label']} | `{item['status']}` | `{item['observed']}` | `{item['expected']}` |"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    self_reference_exception = payload.get("self_reference_exception", {})
    if isinstance(self_reference_exception, dict) and self_reference_exception.get("status") == "applied":
        lines.extend(
            [
                "",
                "## Self Reference Exception",
                "",
                f"- self_reference_exception: `{self_reference_exception.get('status')}`",
                f"- reason: `{self_reference_exception.get('reason')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- release_readiness_status: `{payload['evidence']['release_readiness_status']}`",
            f"- release_handoff_checklist: `{payload['evidence']['release_handoff_checklist']}`",
            f"- release_support_bundle_status: `{payload['evidence']['release_support_bundle_status']}`",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--handoff-checklist", type=Path, required=True)
    parser.add_argument("--support-bundle-status", type=Path, required=True)
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = build_decision(
        readiness_path=args.readiness,
        readiness_source=read_json(args.readiness),
        checklist_path=args.handoff_checklist,
        checklist=read_json(args.handoff_checklist),
        support_bundle_path=args.support_bundle_status,
        support_bundle_source=read_json(args.support_bundle_status),
    )
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.write_md:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(render_markdown(payload), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
