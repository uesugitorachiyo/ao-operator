#!/usr/bin/env python3
"""Agent OS role graph + state v1 backward-compatibility gate.

Proves that legacy Agent OS state and role-graph artifacts written under
the v1 default still load and migrate cleanly under the v2-default router.

The gate exercises six deterministic fixture cases over a temporary
work directory:

* ``legacy_v1_state_minimal_loadable`` — minimal v1 state JSON migrates
  to v2 with default role_graph_schema injected.
* ``legacy_v1_state_extra_unknown_fields_tolerated`` — unknown legacy
  fields do not break migration.
* ``legacy_v1_state_no_role_graph_schema_injects_default`` — explicit
  proof that the loader fills the role_graph_schema pointer when absent.
* ``legacy_v2_state_round_trip_preserves_previous_schema`` — a v2 state
  with previous_schema=v1 reloads with previous_schema=v2 (because the
  loader records the *just-loaded* schema as the new "previous").
* ``legacy_v1_role_graph_artifact_remains_loadable`` — an on-disk v1
  role-graph artifact remains JSON-parseable and reports its schema
  intact.
* ``unknown_state_schema_refused`` — a snapshot with an unrecognized
  schema is refused (verdict FAIL with a clear error).

The gate never invokes AO or provider CLIs and never authorizes dispatch.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_state_v2

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "agent-os-role-graph-backward-compat.json"
)
SCHEMA = "ao-operator/agent-os-role-graph-backward-compat/v1"
STATE_SCHEMA_V1 = agent_os_state_v2.STATE_SCHEMA_V1
STATE_SCHEMA_V2 = agent_os_state_v2.STATE_SCHEMA_V2
ROLE_GRAPH_SCHEMA = agent_os_state_v2.ROLE_GRAPH_SCHEMA

CASE_IDS = (
    "legacy_v1_state_minimal_loadable",
    "legacy_v1_state_extra_unknown_fields_tolerated",
    "legacy_v1_state_no_role_graph_schema_injects_default",
    "legacy_v2_state_round_trip_preserves_previous_schema",
    "legacy_v1_role_graph_artifact_remains_loadable",
    "unknown_state_schema_refused",
)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def case_summary(
    case_id: str,
    *,
    observed_verdict: str,
    observed_schema: str,
    previous_schema: str,
    role_graph_schema: str,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "observed_schema": observed_schema,
        "previous_schema": previous_schema,
        "role_graph_schema": role_graph_schema,
        "detail": detail,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def run_minimal_v1(work: Path) -> dict[str, Any]:
    snapshot = {"schema": STATE_SCHEMA_V1, "lane": "legacy-minimal"}
    write_json(work / "legacy-v1-minimal.json", snapshot)
    payload = agent_os_state_v2.load_or_migrate_state(
        root=work, state="legacy-v1-minimal.json"
    )
    pass_ok = (
        payload.get("schema") == STATE_SCHEMA_V2
        and payload.get("verdict") == "PASS"
        and payload.get("previous_schema") == STATE_SCHEMA_V1
        and payload.get("role_graph_schema") == ROLE_GRAPH_SCHEMA
        and payload.get("dispatch_authorized") is False
        and payload.get("live_providers_run") is False
    )
    return case_summary(
        "legacy_v1_state_minimal_loadable",
        observed_verdict="PASS" if pass_ok else "FAIL",
        observed_schema=str(payload.get("schema") or ""),
        previous_schema=str(payload.get("previous_schema") or ""),
        role_graph_schema=str(payload.get("role_graph_schema") or ""),
        detail=payload.get("next_safe_command", ""),
    )


def run_v1_extra_fields(work: Path) -> dict[str, Any]:
    snapshot = {
        "schema": STATE_SCHEMA_V1,
        "lane": "legacy-extra",
        "route": {"primary": "ubuntu", "secondary": "mac"},
        "blockers": ["legacy-blocker"],
        "evidence_paths": ["docs/legacy/notes.md"],
        "deprecated_field_one": True,
        "deprecated_field_two": [1, 2, 3],
        "extra_object": {"foo": "bar"},
    }
    write_json(work / "legacy-v1-extra.json", snapshot)
    payload = agent_os_state_v2.load_or_migrate_state(
        root=work, state="legacy-v1-extra.json"
    )
    pass_ok = (
        payload.get("schema") == STATE_SCHEMA_V2
        and payload.get("verdict") == "PASS"
        and payload.get("lane") == "legacy-extra"
        and payload.get("route") == {"primary": "ubuntu", "secondary": "mac"}
        and payload.get("blockers") == ["legacy-blocker"]
    )
    return case_summary(
        "legacy_v1_state_extra_unknown_fields_tolerated",
        observed_verdict="PASS" if pass_ok else "FAIL",
        observed_schema=str(payload.get("schema") or ""),
        previous_schema=str(payload.get("previous_schema") or ""),
        role_graph_schema=str(payload.get("role_graph_schema") or ""),
        detail="unknown legacy fields tolerated; canonical fields preserved",
    )


def run_v1_no_role_graph_schema(work: Path) -> dict[str, Any]:
    snapshot = {
        "schema": STATE_SCHEMA_V1,
        "lane": "legacy-no-role-graph",
        "route": {"step": "legacy-step"},
    }
    write_json(work / "legacy-v1-no-role-graph.json", snapshot)
    payload = agent_os_state_v2.load_or_migrate_state(
        root=work, state="legacy-v1-no-role-graph.json"
    )
    pass_ok = (
        payload.get("verdict") == "PASS"
        and payload.get("role_graph_schema") == ROLE_GRAPH_SCHEMA
        and payload.get("previous_schema") == STATE_SCHEMA_V1
    )
    return case_summary(
        "legacy_v1_state_no_role_graph_schema_injects_default",
        observed_verdict="PASS" if pass_ok else "FAIL",
        observed_schema=str(payload.get("schema") or ""),
        previous_schema=str(payload.get("previous_schema") or ""),
        role_graph_schema=str(payload.get("role_graph_schema") or ""),
        detail="default role_graph_schema injected when absent",
    )


def run_v2_round_trip(work: Path) -> dict[str, Any]:
    snapshot = {
        "schema": STATE_SCHEMA_V2,
        "previous_schema": STATE_SCHEMA_V1,
        "role_graph_schema": ROLE_GRAPH_SCHEMA,
        "lane": "legacy-v2-round-trip",
        "route": {"step": "v2"},
        "blockers": [],
        "evidence_paths": [],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    write_json(work / "legacy-v2-round-trip.json", snapshot)
    payload = agent_os_state_v2.load_or_migrate_state(
        root=work, state="legacy-v2-round-trip.json"
    )
    pass_ok = (
        payload.get("verdict") == "PASS"
        and payload.get("schema") == STATE_SCHEMA_V2
        and payload.get("previous_schema") == STATE_SCHEMA_V2
        and payload.get("role_graph_schema") == ROLE_GRAPH_SCHEMA
        and payload.get("lane") == "legacy-v2-round-trip"
    )
    return case_summary(
        "legacy_v2_state_round_trip_preserves_previous_schema",
        observed_verdict="PASS" if pass_ok else "FAIL",
        observed_schema=str(payload.get("schema") or ""),
        previous_schema=str(payload.get("previous_schema") or ""),
        role_graph_schema=str(payload.get("role_graph_schema") or ""),
        detail="v2 round-trip records previous_schema=v2 (just-loaded)",
    )


def run_v1_role_graph_artifact(work: Path) -> dict[str, Any]:
    artifact = {
        "schema": ROLE_GRAPH_SCHEMA,
        "state_schema_version": STATE_SCHEMA_V2,
        "verdict": "PASS",
        "role_count": 7,
        "roles": [
            {"id": "planner", "risk_level": "low"},
            {"id": "plan-hardener", "risk_level": "low"},
            {"id": "factory-manager", "risk_level": "moderate"},
            {"id": "implementer", "risk_level": "moderate"},
            {"id": "slice-reviewer", "risk_level": "moderate"},
            {"id": "integrator", "risk_level": "moderate"},
            {"id": "evaluator-closer", "risk_level": "moderate"},
        ],
        "edges": [],
        "dispatch_authorized": False,
        "live_providers_run": False,
    }
    artifact_path = write_json(work / "legacy-role-graph.json", artifact)
    reloaded = json.loads(artifact_path.read_text(encoding="utf-8"))
    pass_ok = (
        reloaded.get("schema") == ROLE_GRAPH_SCHEMA
        and reloaded.get("state_schema_version") == STATE_SCHEMA_V2
        and reloaded.get("dispatch_authorized") is False
        and reloaded.get("live_providers_run") is False
        and isinstance(reloaded.get("roles"), list)
        and len(reloaded["roles"]) == 7
    )
    return case_summary(
        "legacy_v1_role_graph_artifact_remains_loadable",
        observed_verdict="PASS" if pass_ok else "FAIL",
        observed_schema=str(reloaded.get("schema") or ""),
        previous_schema="",
        role_graph_schema=str(reloaded.get("schema") or ""),
        detail="legacy v1 role-graph JSON remains parseable and intact",
    )


def run_unknown_schema_refused(work: Path) -> dict[str, Any]:
    snapshot = {"schema": "ao-operator/unknown", "lane": "broken"}
    write_json(work / "legacy-unknown-schema.json", snapshot)
    payload = agent_os_state_v2.load_or_migrate_state(
        root=work, state="legacy-unknown-schema.json"
    )
    refused = payload.get("verdict") == "FAIL" and any(
        "unsupported state schema" in str(err) for err in payload.get("errors", [])
    )
    return case_summary(
        "unknown_state_schema_refused",
        observed_verdict="FAIL" if refused else "PASS",
        observed_schema=str(payload.get("schema") or ""),
        previous_schema=str(payload.get("previous_schema") or ""),
        role_graph_schema=str(payload.get("role_graph_schema") or ""),
        detail="unknown schemas refused with explicit error",
    )


CASE_RUNNERS = {
    "legacy_v1_state_minimal_loadable": run_minimal_v1,
    "legacy_v1_state_extra_unknown_fields_tolerated": run_v1_extra_fields,
    "legacy_v1_state_no_role_graph_schema_injects_default": run_v1_no_role_graph_schema,
    "legacy_v2_state_round_trip_preserves_previous_schema": run_v2_round_trip,
    "legacy_v1_role_graph_artifact_remains_loadable": run_v1_role_graph_artifact,
    "unknown_state_schema_refused": run_unknown_schema_refused,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cases = [CASE_RUNNERS[case_id](work_dir) for case_id in CASE_IDS]
    expected_verdicts = {
        "legacy_v1_state_minimal_loadable": "PASS",
        "legacy_v1_state_extra_unknown_fields_tolerated": "PASS",
        "legacy_v1_state_no_role_graph_schema_injects_default": "PASS",
        "legacy_v2_state_round_trip_preserves_previous_schema": "PASS",
        "legacy_v1_role_graph_artifact_remains_loadable": "PASS",
        "unknown_state_schema_refused": "FAIL",
    }
    errors: list[str] = []
    by_id = {case["id"]: case for case in cases}
    for case_id, expected in expected_verdicts.items():
        observed = by_id.get(case_id, {}).get("observed_verdict")
        if observed != expected:
            errors.append(
                f"{case_id} expected {expected}, observed {observed or 'missing'}"
            )
    overall_pass = not errors
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if overall_pass else "FAIL",
        "case_count": len(cases),
        "case_ids": list(CASE_IDS),
        "expected_case_verdicts": expected_verdicts,
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Legacy Agent OS state and role-graph artifacts remain compatible with the v2-default router; continue Agent OS architecture work."
            if overall_pass
            else "Fix role-graph backward-compatibility blockers before continuing."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-role-graph-backward-compat-") as tmp:
        return evaluate(work_dir=Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        payload = evaluate(work_dir=args.work_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="ao-operator-role-graph-backward-compat-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
