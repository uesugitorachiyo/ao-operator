#!/usr/bin/env python3
"""Render a non-dispatching Agent OS RunSpec draft from scoped handoff packets."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HANDOFF = "run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-handoff.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-renderer.json"
DEFAULT_RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"
DEFAULT_STATE_BASELINE = "run-artifacts/remote-transfer-v2-stress-live/agent-os-router-v2-state.json"
PROMPT_DIR = "ao/prompts/agent-os-phase"
POLICY_PROFILE = "ao/policy/local-dev.yaml"
VALID_PROVIDERS = {"codex", "claude", "antigravity"}
STATE_SCHEMA_V2 = "ao-operator/agent-os-state/v2"
ROLE_GRAPH_SCHEMA = "ao-operator/agent-os-role-graph/v1"
PROVIDER_AGENTS = {
    "codex": "codex-default",
    "claude": "claude-default",
    "antigravity": "antigravity-default",
}
ROLE_PROVIDER_KEYS = {
    "planner": "FACTORY_V3_PLANNER_PROVIDER",
    "spec-forge": "FACTORY_V3_SPEC_FORGE_PROVIDER",
    "ralph-loop": "FACTORY_V3_RALPH_LOOP_PROVIDER",
    "plan-hardener": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
    "factory-manager": "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
    "implementer": "FACTORY_V3_IMPLEMENTER_PROVIDER",
    "slice-reviewer": "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
    "integrator": "FACTORY_V3_INTEGRATOR_PROVIDER",
    "evaluator-closer": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
}


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return cleaned or "unknown"


def packets_from(data: dict[str, Any]) -> list[dict[str, Any]]:
    packets = data.get("handoff_packets")
    return [packet for packet in packets if isinstance(packet, dict)] if isinstance(packets, list) else []


def task_id_for(packet: dict[str, Any]) -> str:
    return f"agent-os-{slug(str(packet.get('role') or packet.get('packet_id') or 'unknown'))}"


def prompt_file_for(packet: dict[str, Any]) -> str:
    packet_id = slug(str(packet.get("packet_id") or packet.get("role") or "unknown"))
    return f"{PROMPT_DIR}/{packet_id}.md"


def validate_source(data: dict[str, Any], packets: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-phase-handoff/v1":
        errors.append("handoff schema must be ao-operator/agent-os-phase-handoff/v1")
    if data.get("verdict") != "PASS":
        errors.append("handoff verdict must be PASS")
    if data.get("dispatch_authorized") is not False:
        errors.append("handoff dispatch_authorized must remain false")
    if data.get("live_providers_run") is not False:
        errors.append("handoff live_providers_run must remain false")
    if not packets:
        errors.append("handoff packets must be non-empty")
    seen_roles = {str(packet.get("role")) for packet in packets if packet.get("role")}
    for packet in packets:
        role = str(packet.get("role") or "<missing>")
        context = packet.get("scoped_context") if isinstance(packet.get("scoped_context"), dict) else {}
        if not packet.get("packet_id"):
            errors.append(f"packet {role} missing packet_id")
        if not packet.get("role"):
            errors.append("packet missing role")
        if packet.get("dispatch_mode") != "ao-role":
            errors.append(f"packet {role} dispatch_mode must be ao-role")
        if not string_list(context.get("reads")):
            errors.append(f"packet {role} missing scoped reads")
        if not string_list(context.get("writes")):
            errors.append(f"packet {role} missing scoped writes")
        if not string_list(packet.get("verification_commands")):
            errors.append(f"packet {role} missing verification commands")
        for dep in string_list(packet.get("depends_on")):
            if dep not in seen_roles:
                errors.append(f"packet {role} depends on unknown role {dep}")
    return errors


def validate_state_baseline(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != STATE_SCHEMA_V2:
        errors.append(f"state baseline schema must be {STATE_SCHEMA_V2}")
    if data.get("verdict") != "PASS":
        errors.append("state baseline verdict must be PASS")
    if data.get("architecture_ready") is not True:
        errors.append("state baseline architecture_ready must be true")
    if data.get("role_graph_schema") != ROLE_GRAPH_SCHEMA:
        errors.append(f"state baseline role_graph_schema must be {ROLE_GRAPH_SCHEMA}")
    if data.get("dispatch_authorized") is not False:
        errors.append("state baseline dispatch_authorized must remain false")
    if data.get("live_providers_run") is not False:
        errors.append("state baseline live_providers_run must remain false")
    blockers = data.get("blockers")
    if isinstance(blockers, list) and blockers:
        errors.append("state baseline blockers must be empty")
    return errors


def parse_provider_profile(path: Path) -> tuple[dict[str, str], list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}, [f"provider profile missing: {path}"]
    values: dict[str, str] = {}
    errors: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"provider profile line is not KEY=VALUE: {line}")
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    for key, value in sorted(values.items()):
        if key == "FACTORY_V3_DEFAULT_PROVIDER" or (key.startswith("FACTORY_V3_") and key.endswith("_PROVIDER")):
            if value not in VALID_PROVIDERS:
                errors.append(f"{key} resolved to unsupported provider {value!r}")
    return values, errors


def provider_for_role(provider_profile: dict[str, str], role: str) -> str:
    key = ROLE_PROVIDER_KEYS.get(role)
    if key and provider_profile.get(key):
        return provider_profile[key]
    return provider_profile.get("FACTORY_V3_DEFAULT_PROVIDER", "codex")


def build_prompt(packet: dict[str, Any]) -> str:
    context = packet.get("scoped_context") if isinstance(packet.get("scoped_context"), dict) else {}
    lines = [
        f"# Agent OS Role Packet: {packet.get('role')}",
        "",
        "Use only the scoped context below. Do not use full conversation history.",
        "",
        "## Reads",
        *[f"- {item}" for item in string_list(context.get("reads"))],
        "",
        "## Writes",
        *[f"- {item}" for item in string_list(context.get("writes"))],
        "",
        "## Verification Commands",
        *[f"- `{item}`" for item in string_list(packet.get("verification_commands"))],
        "",
        "## Required Status Fields",
        "- Result",
        "- Artifact",
        "- Evidence",
        "- Concerns",
        "- Blocker",
        "",
        "Dispatch is not authorized by this rendered draft.",
    ]
    return "\n".join(lines) + "\n"


def build_runspec(packets: list[dict[str, Any]], provider_profile: dict[str, str] | None = None) -> dict[str, Any]:
    profile = provider_profile or {}
    role_to_task = {str(packet.get("role")): task_id_for(packet) for packet in packets}
    tasks: list[dict[str, Any]] = []
    for packet in packets:
        role = str(packet.get("role") or "")
        provider = provider_for_role(profile, role)
        deps = [role_to_task[dep] for dep in string_list(packet.get("depends_on")) if dep in role_to_task]
        tasks.append(
            {
                "id": task_id_for(packet),
                "kind": "agent",
                "deps": deps,
                "spec": {
                    "provider": provider,
                    "agent": PROVIDER_AGENTS.get(provider, f"{provider}-default"),
                    "promptFile": prompt_file_for(packet),
                    "workspace": ".",
                    "policyProfile": POLICY_PROFILE,
                    "dispatchAuthorized": False,
                },
            }
        )
    return {
        "apiVersion": "ao.dev/v1",
        "kind": "Run",
        "metadata": {
            "name": "agent-os-phase-draft",
            "description": "Non-dispatching Agent OS RunSpec draft rendered from scoped handoff packets.",
        },
        "spec": {"tasks": tasks},
    }


def yaml_scalar(value: Any) -> str:
    if value is False:
        return "false"
    if value is True:
        return "true"
    if value == []:
        return "[]"
    return str(value)


def render_runspec_yaml(runspec: dict[str, Any]) -> str:
    lines = [
        f"apiVersion: {runspec['apiVersion']}",
        f"kind: {runspec['kind']}",
        "metadata:",
        f"  name: {runspec['metadata']['name']}",
        f"  description: {runspec['metadata']['description']}",
        "spec:",
        "  tasks:",
    ]
    for task in runspec["spec"]["tasks"]:
        lines.extend(
            [
                f"    - id: {task['id']}",
                f"      kind: {task['kind']}",
                "      deps: " + ("[" + ", ".join(f'"{dep}"' for dep in task["deps"]) + "]" if task["deps"] else "[]"),
                "      spec:",
            ]
        )
        for key in ["provider", "agent", "promptFile", "workspace", "policyProfile", "dispatchAuthorized"]:
            lines.append(f"        {key}: {yaml_scalar(task['spec'][key])}")
    return "\n".join(lines) + "\n"


def render_agent_os_runspec(
    *,
    root: Path = ROOT,
    handoff_report: str | Path = DEFAULT_HANDOFF,
    provider_profile: str | Path | None = None,
    state_baseline: str | Path | None = None,
) -> dict[str, Any]:
    handoff_path = resolve_path(root, handoff_report)
    data = load_json(handoff_path)
    packets = packets_from(data)
    errors = validate_source(data, packets)
    profile_path = resolve_path(root, provider_profile) if provider_profile is not None else None
    provider_values: dict[str, str] = {}
    profile_errors: list[str] = []
    if profile_path is not None:
        provider_values, profile_errors = parse_provider_profile(profile_path)
        errors.extend(profile_errors)
    state_path = resolve_path(root, state_baseline) if state_baseline is not None else None
    state_payload = load_json(state_path) if state_path is not None else {}
    if state_path is not None:
        errors.extend(validate_state_baseline(state_payload))
    runspec = build_runspec(packets, provider_values)
    prompt_files = [prompt_file_for(packet) for packet in packets]
    return {
        "schema": "ao-operator/agent-os-runspec-renderer/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "handoff_report": relpath(root, handoff_path),
        "provider_profile": relpath(root, profile_path) if profile_path is not None else "",
        "provider_profile_checked": profile_path is not None,
        "state_baseline": relpath(root, state_path) if state_path is not None else "",
        "state_baseline_checked": state_path is not None,
        "state_schema_version": str(state_payload.get("schema") or "") if state_path is not None else "",
        "role_graph_schema": str(state_payload.get("role_graph_schema") or "") if state_path is not None else "",
        "architecture_ready": state_payload.get("architecture_ready") is True if state_path is not None else False,
        "runspec_path": DEFAULT_RUNSPEC,
        "prompt_dir": PROMPT_DIR,
        "task_count": len(packets),
        "prompt_files": prompt_files,
        "runspec": runspec,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": (
            "Review the Agent OS RunSpec draft or choose the next gated SDD lane."
            if not errors
            else "Fix Agent OS handoff before rendering a RunSpec draft."
        ),
    }


def write_text(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def write_artifacts(root: Path, payload: dict[str, Any], runspec_path: Path) -> None:
    write_text(runspec_path, render_runspec_yaml(payload["runspec"]))
    packets = packets_from(load_json(resolve_path(root, payload["handoff_report"])))
    for packet in packets:
        write_text(root / prompt_file_for(packet), build_prompt(packet))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a AO Operator Agent OS RunSpec draft")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--handoff-report", default=DEFAULT_HANDOFF)
    parser.add_argument("--provider-profile")
    parser.add_argument("--state-baseline")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--write-runspec", nargs="?", const=DEFAULT_RUNSPEC)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = render_agent_os_runspec(
        root=args.root,
        handoff_report=args.handoff_report,
        provider_profile=args.provider_profile,
        state_baseline=args.state_baseline,
    )
    if args.write_runspec is not None and payload["verdict"] == "PASS":
        runspec_arg = Path(args.write_runspec)
        runspec_path = runspec_arg if runspec_arg.is_absolute() else args.root / runspec_arg
        write_artifacts(args.root, payload, runspec_path)
        payload["runspec_path"] = relpath(args.root, runspec_path)
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_text(output_path, json_dumps(payload))
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
