#!/usr/bin/env python3
"""Exercise Agent OS RunSpec failure-injection cases without dispatch."""

from __future__ import annotations

import argparse
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_os_runspec_renderer
import agent_os_runspec_validator
import check_agent_os_runspec_execution_approval_gate
import validate_agent_os_runspec_execution_approval


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-failure-injection-matrix.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def handoff(root: Path) -> Path:
    packets = []
    for index, role in enumerate(["planner", "implementer"]):
        packets.append(
            {
                "packet_id": f"{index + 1:02d}-{role}",
                "role": role,
                "dispatch_mode": "ao-role",
                "depends_on": [] if index == 0 else ["planner"],
                "scoped_context": {
                    "reads": ["docs/sdd/86-agent-os-architecture-implementation-gate.md"],
                    "writes": [f"run-artifacts/agent-os/{role}.json"],
                },
                "verification_commands": ["python3 scripts/validate.py"],
            }
        )
    return write_json(
        root / "handoff.json",
        {
            "schema": "ao-operator/agent-os-phase-handoff/v1",
            "verdict": "PASS",
            "handoff_packets": packets,
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def state_baseline(root: Path) -> Path:
    return write_json(
        root / "state-v2.json",
        {
            "schema": "ao-operator/agent-os-state/v2",
            "verdict": "PASS",
            "architecture_ready": True,
            "role_graph_schema": "ao-operator/agent-os-role-graph/v1",
            "blockers": [],
            "dispatch_authorized": False,
            "live_providers_run": False,
        },
    )


def provider_profile(root: Path, *, value: str = "codex") -> Path:
    return write_text(root / f"{value}-providers.env", f"FACTORY_V3_DEFAULT_PROVIDER={value}\n")


def render_fixture(root: Path, *, profile: Path | None = None, state: Path | None = None) -> dict[str, Any]:
    profile_path = profile or provider_profile(root)
    state_path = state or state_baseline(root)
    payload = agent_os_runspec_renderer.render_agent_os_runspec(
        root=root,
        handoff_report=handoff(root),
        provider_profile=profile_path,
        state_baseline=state_path,
    )
    renderer_path = root / "renderer.json"
    write_json(renderer_path, payload)
    if payload["verdict"] == "PASS":
        agent_os_runspec_renderer.write_artifacts(root, payload, root / payload["runspec_path"])
    return {"payload": payload, "renderer_path": renderer_path, "profile": profile_path, "state": state_path}


def case_result(
    *,
    case_id: str,
    observed_verdict: str,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "error_count": len(errors or []),
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def build_matrix(*, root: Path = ROOT) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ao-operator-agent-os-runspec-failures-") as tmp:
        work = Path(tmp)

        baseline = render_fixture(work)
        baseline_validation = agent_os_runspec_validator.validate_agent_os_runspec(
            root=work,
            renderer_report=baseline["renderer_path"],
            provider_profile=baseline["profile"],
        )

        stale_gate_path = write_json(
            work / "approval-gate.json",
            check_agent_os_runspec_execution_approval_gate.build_gate(
                root=work,
                validation_report=write_json(work / "validation.json", baseline_validation),
                approval_file=work / "approval.json",
            ),
        )
        now = datetime(2026, 5, 8, 0, 0, tzinfo=timezone.utc)
        write_json(
            work / "approval.json",
            {
                "schema": "ao-operator/agent-os-runspec-execution-approval/v1",
                "approved": True,
                "operator": "failure-injection-fixture",
                "approved_at": now.isoformat(),
                "expires_at": now.replace(hour=1).isoformat(),
                "accepted_risk": "fixture only",
                "runspec_path": stale_gate_path.read_text(encoding="utf-8") and baseline_validation["runspec_path"],
                "runspec_sha256": "0" * 64,
                "task_count": baseline_validation["task_count"],
            },
        )
        stale_approval = validate_agent_os_runspec_execution_approval.validate_approval(
            root=work,
            approval_gate=stale_gate_path,
            approval_file=work / "approval.json",
            now=now,
        )

        missing_prompt = render_fixture(work / "missing-prompt")
        prompt = missing_prompt["payload"]["prompt_files"][0]
        (work / "missing-prompt" / prompt).unlink()
        missing_prompt_validation = agent_os_runspec_validator.validate_agent_os_runspec(
            root=work / "missing-prompt",
            renderer_report=missing_prompt["renderer_path"],
            provider_profile=missing_prompt["profile"],
        )

        dispatch_mutation = render_fixture(work / "dispatch-mutation")
        dispatch_payload = deepcopy(dispatch_mutation["payload"])
        dispatch_payload["runspec"]["spec"]["tasks"][0]["spec"]["dispatchAuthorized"] = True
        dispatch_report = write_json(work / "dispatch-mutation" / "renderer-mutated.json", dispatch_payload)
        dispatch_validation = agent_os_runspec_validator.validate_agent_os_runspec(
            root=work / "dispatch-mutation",
            renderer_report=dispatch_report,
            provider_profile=dispatch_mutation["profile"],
        )

        profile_mismatch = render_fixture(work / "profile-mismatch")
        bad_profile = provider_profile(work / "profile-mismatch", value="claude")
        profile_mismatch_validation = agent_os_runspec_validator.validate_agent_os_runspec(
            root=work / "profile-mismatch",
            renderer_report=profile_mismatch["renderer_path"],
            provider_profile=bad_profile,
        )

        invalid_provider = render_fixture(work / "invalid-provider")
        invalid_payload = deepcopy(invalid_provider["payload"])
        invalid_payload["runspec"]["spec"]["tasks"][0]["spec"]["provider"] = "openai"
        invalid_report = write_json(work / "invalid-provider" / "renderer-invalid-provider.json", invalid_payload)
        invalid_provider_validation = agent_os_runspec_validator.validate_agent_os_runspec(
            root=work / "invalid-provider",
            renderer_report=invalid_report,
            provider_profile=invalid_provider["profile"],
        )

        missing_state = render_fixture(work / "missing-state", state=work / "missing-state" / "absent-state.json")

    cases = [
        case_result(
            case_id="baseline_validates",
            observed_verdict=baseline_validation["verdict"],
            errors=baseline_validation.get("errors", []),
        ),
        case_result(
            case_id="stale_approval_hash_refused",
            observed_verdict="REFUSED" if stale_approval["verdict"] == "FAIL" else stale_approval["verdict"],
            errors=stale_approval.get("errors", []),
        ),
        case_result(
            case_id="missing_prompt_refused",
            observed_verdict=missing_prompt_validation["verdict"],
            errors=missing_prompt_validation.get("errors", []),
        ),
        case_result(
            case_id="dispatch_flag_mutation_refused",
            observed_verdict=dispatch_validation["verdict"],
            errors=dispatch_validation.get("errors", []),
        ),
        case_result(
            case_id="bad_provider_profile_refused",
            observed_verdict=profile_mismatch_validation["verdict"],
            errors=profile_mismatch_validation.get("errors", []),
        ),
        case_result(
            case_id="invalid_provider_refused",
            observed_verdict=invalid_provider_validation["verdict"],
            errors=invalid_provider_validation.get("errors", []),
        ),
        case_result(
            case_id="missing_state_baseline_refused",
            observed_verdict=missing_state["payload"]["verdict"],
            errors=missing_state["payload"].get("errors", []),
        ),
    ]

    expected = {
        "baseline_validates": "PASS",
        "stale_approval_hash_refused": "REFUSED",
        "missing_prompt_refused": "FAIL",
        "dispatch_flag_mutation_refused": "FAIL",
        "bad_provider_profile_refused": "FAIL",
        "invalid_provider_refused": "FAIL",
        "missing_state_baseline_refused": "FAIL",
    }
    errors: list[str] = []
    for case in cases:
        if case["observed_verdict"] != expected[case["id"]]:
            errors.append(f"{case['id']} expected {expected[case['id']]}, got {case['observed_verdict']}")
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case['id']} must keep top-level dispatch/live flags false")

    return {
        "schema": "ao-operator/agent-os-runspec-failure-injection-matrix/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec failure-injection matrix passes; keep execution blocked unless explicit approval validates."
            if not errors
            else "Fix Agent OS RunSpec failure-injection regressions before execution architecture changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Agent OS RunSpec failure-injection matrix")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_matrix(root=args.root)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
