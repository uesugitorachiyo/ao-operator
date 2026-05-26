#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/ao2-release-handoff-checklist/v1"
HANDOFF_SCHEMA = "ao2.cp-release-candidate-handoff.v1"


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


def extract_handoff(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version") == HANDOFF_SCHEMA:
        return payload
    snapshot = payload.get("handoff_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("schema_version") == HANDOFF_SCHEMA:
        return snapshot
    return None


def nested_str(value: dict[str, Any], *keys: str, default: str = "missing") -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    if isinstance(current, str) and current:
        return current
    return default


def nested_bool(value: dict[str, Any], *keys: str, default: bool = False) -> bool:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if isinstance(current, bool) else default


def check(check_id: str, label: str, observed: str, expected: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "observed": observed,
        "expected": expected,
        "status": "passed" if observed == expected else "blocked",
    }


def provider_acceptance_state(handoff: dict[str, Any], provider: str) -> str:
    status = nested_str(handoff, "acceptance", provider, "status")
    source = nested_str(handoff, "acceptance", provider, "source_class")
    if status == "passed" and source == "live":
        return "passed/live"
    return f"{status}/{source}"


def parse_expected_repo_heads(values: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for value in values:
        name, separator, head = value.partition("=")
        if not separator or not name or not head:
            raise SystemExit(
                "--expected-repo-head must be formatted as <repo>=<head>"
            )
        if any(char.isspace() for char in name) or any(char.isspace() for char in head):
            raise SystemExit("--expected-repo-head cannot contain whitespace")
        expected[name] = head
    return expected


def build_repo_head_checks(
    handoff: dict[str, Any], expected_repo_heads: dict[str, str]
) -> list[dict[str, str]]:
    checks = []
    for repo, expected_head in sorted(expected_repo_heads.items()):
        observed = nested_str(handoff, "release", "repositories", repo, "head")
        item = check(
            f"repo_head_{repo}",
            f"Repo head {repo}",
            observed,
            expected_head,
        )
        metadata_refresh = release_publication_metadata_refresh(
            handoff, repo, observed, expected_head
        )
        if metadata_refresh is not None:
            item.update(metadata_refresh)
        checks.append(item)
    return checks


def release_publication_metadata_refresh(
    handoff: dict[str, Any], repo: str, observed: str, expected: str
) -> dict[str, Any] | None:
    if repo != "ao2" or observed == expected:
        return None
    root = nested_str(handoff, "release", "repositories", repo, "path")
    if root == "missing":
        return None
    try:
        subprocess.run(
            ["git", "-C", root, "merge-base", "--is-ancestor", observed, expected],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        diff = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", f"{observed}..{expected}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None
    changed_paths = [line.strip() for line in diff if line.strip()]
    if not changed_paths:
        return None
    allowed_prefixes = ("run-artifacts/release-candidates/",)
    if any(not path.startswith(allowed_prefixes) for path in changed_paths):
        return None
    return {
        "status": "passed_with_metadata_refresh",
        "metadata_refresh_paths": changed_paths,
        "metadata_refresh_reason": (
            "ao2 HEAD advanced only by release-candidate metadata refresh files"
        ),
    }


def build_checklist(
    handoff: dict[str, Any], expected_repo_heads: dict[str, str] | None = None
) -> dict[str, Any]:
    mutates = nested_bool(handoff, "operator_handoff", "mutates_ao_artifacts", default=True)
    trust_state = (
        "read_only_evaluator_owned"
        if nested_str(handoff, "operator_handoff", "control_plane_role") == "read_only_observer"
        and not mutates
        and nested_str(handoff, "operator_handoff", "release_acceptance_owner")
        == "ao-operator evaluator-closer"
        else "attention"
    )
    checks = [
        check("handoff_schema", "Handoff schema", nested_str(handoff, "schema_version"), HANDOFF_SCHEMA),
        check("handoff_status", "Handoff status", nested_str(handoff, "status"), "ready"),
        check(
            "release_cockpit",
            "Release cockpit",
            nested_str(handoff, "gates", "release_cockpit"),
            "ready",
        ),
        check(
            "phase1_promotion",
            "Phase 1 promotion",
            nested_str(handoff, "gates", "phase1_promotion"),
            "observed",
        ),
        check(
            "decision_signature",
            "Decision signature",
            nested_str(handoff, "gates", "decision_signature"),
            "present",
        ),
        check(
            "provider_acceptance",
            "Provider acceptance",
            nested_str(handoff, "gates", "provider_acceptance"),
            "live_complete",
        ),
        check(
            "codex_acceptance",
            "Codex acceptance",
            provider_acceptance_state(handoff, "codex"),
            "passed/live",
        ),
        check(
            "claude_acceptance",
            "Claude acceptance",
            provider_acceptance_state(handoff, "claude"),
            "passed/live",
        ),
        check(
            "trust_boundary",
            "Trust boundary",
            trust_state,
            "read_only_evaluator_owned",
        ),
    ]
    checks.extend(build_repo_head_checks(handoff, expected_repo_heads or {}))
    blockers = [
        f"{item['id']}: expected {item['expected']}, observed {item['observed']}"
        for item in checks
        if not str(item["status"]).startswith("passed")
    ]
    status = "ready_for_evaluator_closer" if not blockers else "blocked"
    return {
        "schema": SCHEMA,
        "status": status,
        "release": handoff.get("release", {}),
        "checks": checks,
        "blockers": blockers,
        "operator_decision": {
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
            "next_action": (
                "ao-operator evaluator-closer may review and accept or reject the release-line decision"
                if not blockers
                else "resolve blockers before evaluator-closer release-line review"
            ),
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
        "links": handoff.get("links", {}),
    }


def build_unavailable_checklist(source: dict[str, Any], status: str) -> dict[str, Any]:
    reason = str(source.get("reason") or "AO2 release-candidate handoff is not available")
    return {
        "schema": SCHEMA,
        "status": status,
        "release": {},
        "checks": [
            check("handoff_available", "Handoff available", status, "ready"),
        ],
        "blockers": [f"handoff_available: {reason}"] if status != "planned" else [],
        "operator_decision": {
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
            "next_action": "fetch AO2 release-candidate handoff before evaluator-closer release-line review",
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
        "links": source.get("links", {}) if isinstance(source.get("links"), dict) else {},
    }


def render_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release", {})
    checks = payload.get("checks", [])
    lines = [
        "# AO2 Release Handoff Checklist",
        "",
        f"- status: `{payload.get('status', 'missing')}`",
        f"- release_tag: `{release.get('release_tag', 'missing')}`",
        f"- evaluator_closer_required: `{payload['operator_decision']['factory_v3_evaluator_closer_required']}`",
        f"- control_plane_approves_release: `{payload['operator_decision']['control_plane_approves_release']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Observed | Expected |",
        "| --- | --- | --- | --- |",
    ]
    for item in checks:
        lines.append(
            f"| {item['label']} | `{item['status']}` | `{item['observed']}` | `{item['expected']}` |"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Trust Boundary",
            "",
            "- Hermes remains front end, queue, cron, and memory surface.",
            "- ao2 remains the trusted signed evidence boundary.",
            "- ao2-control-plane remains read-only and does not approve releases.",
            "- ao-operator evaluator-closer owns release acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument(
        "--expected-repo-head",
        action="append",
        default=[],
        help="Expected repository HEAD in <repo>=<head> form. May be repeated.",
    )
    parser.add_argument("--allow-skipped", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    expected_repo_heads = parse_expected_repo_heads(args.expected_repo_head)
    source = read_json(args.handoff)
    handoff = extract_handoff(source)
    if handoff is None:
        if not args.allow_skipped:
            raise SystemExit("input does not contain an AO2 release-candidate handoff")
        source_status = str(source.get("status") or "skipped")
        payload = build_unavailable_checklist(
            source,
            "planned" if source_status == "planned" else "skipped",
        )
    else:
        payload = build_checklist(handoff, expected_repo_heads)
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
