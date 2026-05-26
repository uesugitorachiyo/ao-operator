#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/ao2-release-support-verifier-handoff/v1"
CONTROL_PLANE_HANDOFF_SCHEMA = "ao2.cp-release-support-verifier-handoff.v1"
VERIFIER_SCHEMA_SAMPLE = "ao2.cp-release-support-bundle-verifier-output-sample.v1"
MANIFEST_SCHEMA = "ao2.cp-release-support-bundle-manifest.v1"
EXPECTED_OWNER = "ao-operator evaluator-closer"
EXPECTED_ROLE = "read_only_observer"

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)),
    ("authorization_header", re.compile(r"\bAuthorization\s*[:=]\s*[^\s,}]+", re.IGNORECASE)),
    ("api_key_assignment", re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}")),
    ("credential_query", re.compile(r"(?i)[?&](?:access_token|api_key|token|secret)=([^\s&#]+)")),
)


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


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def secret_markers(value: Any) -> list[str]:
    text = json_text(value)
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


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


def bool_check(check_id: str, label: str, observed: bool, expected: bool) -> dict[str, str]:
    return check(check_id, label, str(observed).lower(), str(expected).lower())


def parse_manifest_sample(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {}
    sample = manifest.get("verifier_output_schema_sample")
    return sample if isinstance(sample, dict) else {}


def verifier_surface_count(verifier: dict[str, Any]) -> int:
    count = verifier.get("surface_count")
    if isinstance(count, int) and count >= 0:
        return count
    checks = verifier.get("checks")
    if isinstance(checks, list):
        return len(checks)
    return 0


def verifier_failures(verifier: dict[str, Any]) -> list[Any]:
    failures = verifier.get("failures")
    if isinstance(failures, list):
        return failures
    blockers = verifier.get("blockers")
    if isinstance(blockers, list):
        return blockers
    return []


def control_plane_handoff_as_verifier(handoff: dict[str, Any]) -> dict[str, Any]:
    """Normalize the AO2 Control Plane handoff endpoint into verifier shape.

    The control-plane /api/v1/release/support-bundle/handoff.json surface is
    already a read-only observer summary. Factory-v3 still converts it into its
    own evaluator-closer handoff schema so release acceptance remains outside
    the control plane.
    """
    verification = handoff.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    checks = handoff.get("checks")
    checks = checks if isinstance(checks, list) else []
    blockers = handoff.get("blockers")
    blockers = blockers if isinstance(blockers, list) else []
    status = nested_str(verification, "status", default=nested_str(handoff, "status"))
    trust_status = nested_str(verification, "trust_boundary_status")
    return {
        "status": "passed" if status == "passed" and trust_status == "passed" else status,
        "checksum_verified": status == "passed" and not blockers,
        "bundle_sha256": nested_str(handoff, "bundle_sha256"),
        "surface_count": verification.get("surface_count", len(checks)),
        "failures": blockers,
        "control_plane_role": nested_str(handoff, "control_plane_role"),
        "release_acceptance_owner": nested_str(handoff, "release_acceptance_owner"),
        "mutates_ao_artifacts": nested_bool(handoff, "mutates_ao_artifacts", default=True),
        "control_plane_approves_release": nested_bool(
            handoff, "control_plane_approves_release", default=True
        ),
        "safe_for_scheduler_indexing": nested_bool(
            handoff, "safe_for_scheduler_indexing", default=False
        ),
        "contains_bearer_token": nested_bool(handoff, "contains_bearer_token", default=True),
        "source_schema_version": nested_str(handoff, "schema_version"),
        "generated_from": nested_str(handoff, "generated_from"),
        "checks": checks,
    }


def verifier_role(verifier: dict[str, Any]) -> str:
    role = nested_str(verifier, "control_plane_role")
    if role != "missing":
        return role
    trust_boundary = nested_str(verifier, "trust_boundary")
    if trust_boundary == EXPECTED_ROLE:
        return EXPECTED_ROLE
    return role


def verifier_mutates_ao_artifacts(verifier: dict[str, Any]) -> bool:
    if "mutates_ao_artifacts" in verifier:
        return nested_bool(verifier, "mutates_ao_artifacts", default=True)
    scope = nested_str(verifier, "verification_scope").lower()
    if "no ao2 artifact mutation" in scope or "never mutates ao2" in scope:
        return False
    return True


def verifier_control_plane_approves_release(verifier: dict[str, Any]) -> bool:
    if "control_plane_approves_release" in verifier:
        return nested_bool(verifier, "control_plane_approves_release", default=True)
    scope = nested_str(verifier, "verification_scope").lower()
    if "no release approval" in scope or "does not approve" in scope:
        return False
    return True


def build_handoff(
    verifier: dict[str, Any],
    *,
    verifier_path: Path,
    manifest: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    source_schema = nested_str(verifier, "schema_version")
    source_kind = (
        "ao2-control-plane handoff endpoint"
        if source_schema == CONTROL_PLANE_HANDOFF_SCHEMA
        else "ao2-control-plane offline support-bundle verifier output"
    )
    if source_schema == CONTROL_PLANE_HANDOFF_SCHEMA:
        verifier = control_plane_handoff_as_verifier(verifier)
    sample = parse_manifest_sample(manifest)
    marker_hits = secret_markers(verifier)
    manifest_marker_hits = secret_markers(manifest) if manifest else []
    surface_count = verifier_surface_count(verifier)
    failures = verifier_failures(verifier)

    checks = [
        check("verifier_status", "Verifier status", nested_str(verifier, "status"), "passed"),
        bool_check(
            "checksum_verified",
            "Downloaded bundle checksum verified",
            nested_bool(verifier, "checksum_verified"),
            True,
        ),
        check(
            "control_plane_role",
            "Control-plane role",
            verifier_role(verifier),
            EXPECTED_ROLE,
        ),
        check(
            "release_acceptance_owner",
            "Release acceptance owner",
            nested_str(verifier, "release_acceptance_owner"),
            EXPECTED_OWNER,
        ),
        bool_check(
            "mutates_ao_artifacts",
            "Verifier mutates AO artifacts",
            verifier_mutates_ao_artifacts(verifier),
            False,
        ),
        bool_check(
            "control_plane_approves_release",
            "Control plane approves release",
            verifier_control_plane_approves_release(verifier),
            False,
        ),
        check(
            "verifier_failures",
            "Verifier failure count",
            str(len(failures)),
            "0",
        ),
        check(
            "secret_hygiene",
            "Verifier JSON secret hygiene",
            ",".join(marker_hits) if marker_hits else "clean",
            "clean",
        ),
        bool_check(
            "contains_bearer_token",
            "Control-plane handoff contains bearer token",
            nested_bool(verifier, "contains_bearer_token"),
            False,
        ),
    ]

    if source_schema == CONTROL_PLANE_HANDOFF_SCHEMA:
        checks.extend(
            [
                check(
                    "control_plane_handoff_schema",
                    "Control-plane handoff schema",
                    source_schema,
                    CONTROL_PLANE_HANDOFF_SCHEMA,
                ),
                bool_check(
                    "safe_for_scheduler_indexing",
                    "Control-plane handoff scheduler indexing safety",
                    nested_bool(verifier, "safe_for_scheduler_indexing"),
                    True,
                ),
            ]
        )

    if manifest is not None:
        checks.extend(
            [
                check(
                    "manifest_schema",
                    "Support-bundle manifest schema",
                    nested_str(manifest, "schema_version"),
                    MANIFEST_SCHEMA,
                ),
                check(
                    "manifest_sample_schema",
                    "Manifest verifier output schema sample",
                    nested_str(sample, "schema_version"),
                    VERIFIER_SCHEMA_SAMPLE,
                ),
                check(
                    "manifest_sample_role",
                    "Manifest sample control-plane role",
                    nested_str(sample, "control_plane_role"),
                    EXPECTED_ROLE,
                ),
                check(
                    "manifest_secret_hygiene",
                    "Manifest JSON secret hygiene",
                    ",".join(manifest_marker_hits) if manifest_marker_hits else "clean",
                    "clean",
                ),
            ]
        )

    blockers = [
        f"{item['id']}: expected {item['expected']}, observed {item['observed']}"
        for item in checks
        if item["status"] != "passed"
    ]
    status = "ready_for_evaluator_closer" if not blockers else "blocked"

    return {
        "schema": SCHEMA,
        "status": status,
        "verifier": {
            "path": str(verifier_path),
            "status": nested_str(verifier, "status"),
            "checksum_verified": nested_bool(verifier, "checksum_verified"),
            "bundle_sha256": nested_str(verifier, "bundle_sha256"),
            "surface_count": surface_count,
            "failure_count": len(failures),
            "source_schema_version": source_schema,
        },
        "manifest": {
            "path": str(manifest_path) if manifest_path else "not_provided",
            "schema_version": nested_str(manifest or {}, "schema_version"),
            "verifier_output_schema_sample": nested_str(sample, "schema_version"),
        },
        "checks": checks,
        "blockers": blockers,
        "operator_decision": {
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
            "next_action": (
                "ao-operator evaluator-closer may review verifier handoff beside AO2 signed release evidence"
                if not blockers
                else "resolve verifier, checksum, trust-boundary, or secret-hygiene blockers before evaluator-closer review"
            ),
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": verifier_role(verifier),
            "mutates_ao_artifacts": verifier_mutates_ao_artifacts(verifier),
            "release_acceptance_owner": EXPECTED_OWNER,
            "source": source_kind,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AO2 Release Support Verifier Handoff",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Verifier",
        "",
        f"- Path: `{payload['verifier']['path']}`",
        f"- Status: `{payload['verifier']['status']}`",
        f"- Checksum verified: `{str(payload['verifier']['checksum_verified']).lower()}`",
        f"- Bundle SHA-256: `{payload['verifier']['bundle_sha256']}`",
        f"- Surface count: `{payload['verifier']['surface_count']}`",
        "",
        "## Checks",
        "",
    ]
    for item in payload["checks"]:
        lines.append(
            f"- `{item['status']}` {item['id']}: expected `{item['expected']}`, observed `{item['observed']}`"
        )
    lines.extend(["", "## Blockers", ""])
    if payload["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload["blockers"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Trust boundary",
            "",
            "ao-operator evaluator-closer owns release acceptance. The control plane remains a read-only observer, and this handoff does not mutate AO artifacts or approve a release.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verifier-json", required=True, type=Path)
    parser.add_argument("--manifest-json", type=Path)
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-md", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    verifier = read_json(args.verifier_json)
    manifest = read_json(args.manifest_json) if args.manifest_json else None
    payload = build_handoff(
        verifier,
        verifier_path=args.verifier_json,
        manifest=manifest,
        manifest_path=args.manifest_json,
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
        print(render_markdown(payload))
    return 0 if payload["status"] == "ready_for_evaluator_closer" else 2


if __name__ == "__main__":
    raise SystemExit(main())
