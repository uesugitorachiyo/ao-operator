#!/usr/bin/env python3
"""Hermes-facing bridge for AO Operator context and AO2 memory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import ao2_queue_failure_recovery_ownership as ao2_queue_ownership
import factory_run
import hermes_context_with_ao2_refs as ao2_refs_helper


SCHEMA = "ao-operator/hermes-ao-bridge/v1"
TRUST_BOUNDARY = {
    "hermes_role": "front_end_queue_cron_and_memory_surface",
    "ao2_role": "trusted_execution_memory_and_signed_evidence_boundary",
    "factory_v3_role": "contracts_profiles_role_discipline_and_evaluator_closure",
    "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
}
FORBIDDEN_PROVIDER_KEY_ENVS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
SCRIPTED_PROVIDER_SUFFIXES = {".bat", ".cmd", ".ps1", ".sh", ".bash", ".zsh"}


def build_ao2_queue_ownership_payload(
    submit_path: Path, transition_paths: list[Path]
) -> dict[str, Any]:
    """Validate AO2 queue evidence and return a ao-operator ownership claim.

    Wraps :mod:`ao2_queue_failure_recovery_ownership` so the bridge can attach a
    failure-recovery ownership claim to repair-resume payloads without
    shelling out to the script. Raises ``RuntimeError`` on any validation
    failure so callers can convert it to a clean non-zero exit.
    """
    submit = ao2_queue_ownership._load_json(submit_path)
    try:
        ao2_queue_ownership._validate_submit(submit, submit_path)
    except ao2_queue_ownership.InvalidOwnershipInputError as exc:
        raise RuntimeError(str(exc)) from exc
    expected_run_id = (
        submit.get("run_id")
        or (submit.get("entry") or {}).get("run_id")
        or ""
    )
    transitions: list[dict[str, Any]] = []
    for transition_path in transition_paths:
        transition = ao2_queue_ownership._load_json(transition_path)
        try:
            ao2_queue_ownership._validate_transition(
                transition, transition_path, expected_run_id
            )
        except ao2_queue_ownership.InvalidOwnershipInputError as exc:
            raise RuntimeError(str(exc)) from exc
        transitions.append(transition)
    return ao2_queue_ownership.build_ownership(
        submit=submit, transitions=transitions
    )


def resolve_repair_resume_ao2_queue_ownership(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Compute the AO2 queue ownership claim for a repair-resume call.

    Returns the ownership payload when AO2 queue evidence is supplied,
    ``None`` when no evidence is supplied and ownership is not required, or
    raises ``RuntimeError`` when ownership is required but unsupplied / the
    evidence does not validate against the original run_id.
    """
    submit_path: Path | None = getattr(args, "ao2_queue_submit", None)
    transition_paths: list[Path] = list(
        getattr(args, "ao2_queue_transitions", None) or []
    )
    require = bool(getattr(args, "require_ao2_queue_ownership", False))
    if submit_path is None:
        if require:
            raise RuntimeError(
                "repair-resume requires AO2 queue ownership evidence "
                "(--ao2-queue-submit and at least one --ao2-queue-transition) "
                "when --require-ao2-queue-ownership is set; ao-operator must "
                "not retain failure-recovery ownership"
            )
        return None
    if not transition_paths:
        raise RuntimeError(
            "--ao2-queue-submit was supplied without any --ao2-queue-transition; "
            "AO2 queue ownership requires at least one queue-retry / "
            "queue-cancel transition record"
        )
    payload = build_ao2_queue_ownership_payload(submit_path, transition_paths)
    run_id = str(getattr(args, "run_id", "") or "")
    if run_id and payload.get("run_id") != run_id:
        raise RuntimeError(
            f"AO2 queue ownership run_id {payload.get('run_id')!r} does not "
            f"match repair-resume --run-id {run_id!r}; refusing to attach "
            "ownership claim to a different run"
        )
    return payload


def write_ao2_queue_ownership_claim(
    payload: dict[str, Any], out_path: Path | None
) -> str | None:
    if out_path is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return str(out_path)


def resolve_ao2_bin(ao2_bin: str, factory_root: Path) -> str:
    """Prefer the checked-out AO2 binary over a stale ao2 on PATH."""
    if ao2_bin != "ao2":
        return ao2_bin
    adjacent = factory_root.resolve().parent / "ao2" / "target" / "release" / "ao2"
    if adjacent.is_file():
        return str(adjacent)
    return ao2_bin




def context_payload(slug: str, factory_root: Path) -> dict[str, Any]:
    original_root = factory_run.ROOT
    try:
        factory_run.ROOT = factory_root.resolve()
        return factory_run.hermes_context_payload(slug)
    finally:
        factory_run.ROOT = original_root


def run_ao2(argv: list[str]) -> dict[str, Any]:
    payload, _exit_code = run_ao2_json(argv, allow_nonzero=False)
    return payload


def parse_key_value_output(stdout: str) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            return None
        payload[key] = value.strip()
    if not payload:
        return None
    return payload


def run_ao2_run(argv: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ao2 command failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = parse_key_value_output(result.stdout)
        if payload is None:
            raise RuntimeError(f"ao2 command did not return JSON: {result.stdout!r}")
        payload.setdefault("schema_version", "ao2.run-start.v1")
        return payload


def run_ao2_json(argv: list[str], *, allow_nonzero: bool) -> tuple[dict[str, Any], int]:
    result = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 and not allow_nonzero:
        raise RuntimeError(
            f"ao2 command failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout), result.returncode
    except json.JSONDecodeError as exc:
        if result.returncode != 0:
            raise RuntimeError(
                f"ao2 command failed with exit {result.returncode}: {result.stderr.strip()}"
            ) from exc
        raise RuntimeError(f"ao2 command did not return JSON: {result.stdout!r}") from exc


def sanitize_invocation(argv: list[str]) -> list[str]:
    sanitized = list(argv)
    for secret_flag in ("--api-token", "--bearer-token", "--token", "--signing-key"):
        if secret_flag in sanitized:
            idx = sanitized.index(secret_flag)
            if idx + 1 < len(sanitized):
                sanitized[idx + 1] = "<redacted>"
    return sanitized


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        if any(
            item in value
            for item in ("--api-token", "--bearer-token", "--token", "--signing-key")
        ):
            return sanitize_invocation([str(item) for item in value])
        return [sanitize_payload(item) for item in value]
    return value


def post_json_bytes(url: str, api_token: str, body: bytes) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"control-plane POST failed with status {exc.code}: {raw}") from exc
    return json.loads(raw), status_code


def get_json(url: str, api_token: str) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"control-plane GET failed with status {exc.code}: {raw}") from exc
    return json.loads(raw), status_code


def control_plane_link(base_url: str, value: Any, default_path: str) -> str:
    link = str(value or default_path)
    if link.startswith(("http://", "https://")):
        return link
    if link.startswith("/"):
        return f"{base_url}{link}"
    return f"{base_url}{default_path}"


def validate_governed_run_request(args: argparse.Namespace) -> None:
    if args.provider_prompt:
        raise RuntimeError(
            "--provider-prompt-file is required; raw --provider-prompt is not accepted by the Hermes bridge"
        )
    if not args.provider_prompt_file:
        raise RuntimeError("--provider-prompt-file is required for governed-run")
    if not args.provider_prompt_file.is_file():
        raise RuntimeError(f"provider prompt file not found: {args.provider_prompt_file}")
    validate_scripted_provider_prompt_file(args.provider, args.provider_prompt_file)
    present = [name for name in FORBIDDEN_PROVIDER_KEY_ENVS if os.environ.get(name)]
    if present:
        names = ", ".join(sorted(present))
        raise RuntimeError(f"Provider API-key environment variables are forbidden: {names}")


def is_script_like_prompt_file(path: Path) -> bool:
    if path.suffix.lower() in SCRIPTED_PROVIDER_SUFFIXES:
        return True
    if os.access(path, os.X_OK):
        return True
    try:
        prefix = path.read_text(encoding="utf-8", errors="replace")[:256]
    except OSError:
        return False
    return prefix.startswith("#!")


def validate_scripted_provider_prompt_file(provider: str | None, prompt_file: Path) -> None:
    if str(provider or "").strip().lower() != "scripted":
        return
    if is_script_like_prompt_file(prompt_file):
        return
    raise RuntimeError(
        "scripted provider prompt file must be executable/script-like; "
        "use a shell/PowerShell script file for provider=scripted, or use codex/claude "
        "for prose prompts"
    )


def validate_repair_resume_request(args: argparse.Namespace) -> None:
    if args.provider_prompt:
        raise RuntimeError(
            "--provider-prompt-file is required; raw --provider-prompt is not accepted by the Hermes bridge"
        )
    if not args.provider_prompt_file:
        raise RuntimeError("--provider-prompt-file is required for repair-resume")
    if not args.provider_prompt_file.is_file():
        raise RuntimeError(f"provider prompt file not found: {args.provider_prompt_file}")
    validate_scripted_provider_prompt_file(args.provider, args.provider_prompt_file)
    if not args.evidence_pack.is_file():
        raise RuntimeError(f"source evidence pack not found: {args.evidence_pack}")
    if not args.workflow and not args.template:
        raise RuntimeError("--workflow or --template is required for repair-resume")
    present = [name for name in FORBIDDEN_PROVIDER_KEY_ENVS if os.environ.get(name)]
    if present:
        names = ", ".join(sorted(present))
        raise RuntimeError(f"Provider API-key environment variables are forbidden: {names}")


def latest_nonaccepted_evidence_pack(ao2_target: Path) -> dict[str, Any]:
    runs_root = ao2_target / ".ao2" / "runs"
    candidates: list[dict[str, Any]] = []
    repaired_sources: dict[str, int] = {}
    for evidence_pack in runs_root.glob("*/evidence-pack/evidence-pack.json"):
        try:
            payload = json.loads(evidence_pack.read_text(encoding="utf-8"))
            stat = evidence_pack.stat()
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema_version") != "ao2.evidence-pack.v1":
            continue
        run_id = str(payload.get("run_id") or evidence_pack.parents[1].name)
        verdict = str(payload.get("verdict") or payload.get("status") or "").strip().lower()
        repair_source = payload.get("repair_source") or {}
        source_run_id = str(repair_source.get("source_run_id") or "").strip()
        if verdict == "accepted" and source_run_id:
            repaired_sources[source_run_id] = max(
                repaired_sources.get(source_run_id, 0),
                stat.st_mtime_ns,
            )
        if not verdict or verdict == "accepted":
            continue
        candidates.append(
            {
                "path": str(evidence_pack),
                "run_id": run_id,
                "verdict": verdict,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    candidates = [
        candidate
        for candidate in candidates
        if repaired_sources.get(str(candidate["run_id"]), 0) <= int(candidate["mtime_ns"])
    ]
    if not candidates:
        raise RuntimeError(f"no non-accepted AO2 evidence pack found under {runs_root}")
    candidates.sort(key=lambda item: (int(item["mtime_ns"]), item["path"]), reverse=True)
    return candidates[0]


def bridge_result(action: str, **fields: Any) -> dict[str, Any]:
    return {"schema": SCHEMA, "action": action, **fields}


def context_command(args: argparse.Namespace) -> dict[str, Any]:
    return bridge_result("context", context=context_payload(args.slug, args.factory_root))


def context_with_ao2_refs_command(args: argparse.Namespace) -> dict[str, Any]:
    bridge = (
        ao2_refs_helper._load_json(args.bridge_evidence) if args.bridge_evidence else None
    )
    pack = (
        ao2_refs_helper._load_json(args.evidence_pack) if args.evidence_pack else None
    )
    record = (
        ao2_refs_helper._load_json(args.memory_record) if args.memory_record else None
    )
    receipt = (
        ao2_refs_helper._load_json(args.control_plane_receipt)
        if args.control_plane_receipt
        else None
    )
    try:
        payload = ao2_refs_helper.build_payload(
            args.slug,
            bridge_evidence=bridge,
            evidence_pack=pack,
            evidence_pack_path=args.evidence_pack,
            memory_record=record,
            cp_receipt=receipt,
            require_all_ao2_ref_categories=getattr(
                args, "require_all_ao2_ref_categories", False
            ),
        )
    except (
        ao2_refs_helper.MissingAo2RefsError,
        ao2_refs_helper.MissingAo2RefCategoryError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except SystemExit as exc:
        # Helper raises SystemExit on schema mismatch and on missing/invalid
        # JSON inputs. The bridge always reports input-validation failures
        # with exit code 2.
        message = str(exc) if exc.code not in (0, None) else "ao2-refs helper rejected input"
        print(message, file=sys.stderr)
        raise SystemExit(2) from exc
    return bridge_result("context-with-ao2-refs", context_with_ao2_refs=payload)


def remember_context_command(args: argparse.Namespace) -> dict[str, Any]:
    context = context_payload(args.slug, args.factory_root)
    records = context["memory"]["recommended_records"]
    if not records:
        raise RuntimeError("Hermes context did not include recommended memory records")
    record = records[0]
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "write",
        "--target",
        str(args.ao2_target),
        "--kind",
        str(record["kind"]),
        "--title",
        str(record["title"]),
        "--body",
        str(record["body"]),
    ]
    source_path = str(record.get("source_path") or "").strip()
    if source_path:
        command.extend(["--source-path", source_path])
    for tag in context["memory"]["tags"]:
        command.extend(["--tag", str(tag)])
    command.append("--json")
    ao2_result = run_ao2(command)
    return bridge_result(
        "remember-context",
        slug=context["slug"],
        context=context,
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def search_memory_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "search",
        "--target",
        str(args.ao2_target),
        "--query",
        args.query,
        "--limit",
        str(args.limit),
        "--json",
    ]
    ao2_result = run_ao2(command)
    return bridge_result(
        "search-memory",
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def remember_note_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "write",
        "--target",
        str(args.ao2_target),
        "--kind",
        args.kind,
        "--title",
        args.title,
        "--body",
        args.body,
    ]
    if args.source_run_id:
        command.extend(["--source-run-id", args.source_run_id])
    if args.source_path:
        command.extend(["--source-path", args.source_path])
    for tag in args.tags:
        command.extend(["--tag", tag])
    command.append("--json")
    ao2_result = run_ao2(command)
    return bridge_result(
        "remember-note",
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def export_memory_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "export",
        "--target",
        str(args.ao2_target),
        "--query",
        args.query,
        "--limit",
        str(args.limit),
        "--out",
        str(args.out),
    ]
    if args.signing_key:
        command.extend(["--signing-key", str(args.signing_key)])
        command.extend(["--signer-id", args.signer_id])
    command.append("--json")
    ao2_result = run_ao2(command)
    return bridge_result(
        "export-memory",
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def publish_memory_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "publish",
        "--export",
        str(args.export),
        "--control-plane-url",
        args.control_plane_url,
        "--api-token",
        args.api_token,
        "--json",
    ]
    ao2_result = run_ao2(command)
    return bridge_result(
        "publish-memory",
        ao2_invocation=sanitize_invocation(command),
        ao2_result=sanitize_payload(ao2_result),
    )


def provider_registry_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "provider",
        "registry",
        "--json",
    ]
    ao2_result = run_ao2(command)
    return bridge_result(
        "provider-registry",
        trust_boundary={"mode": "ao2_provider_plugin_registry_read_only", **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def provider_registry_observer_links(control_plane_url: str) -> dict[str, str]:
    base_url = control_plane_url.rstrip("/")
    provider_registry_base = f"{base_url}/api/v1/provider/registry"
    return {
        "dashboard": f"{provider_registry_base}/dashboard",
        "dashboard_json": f"{provider_registry_base}/dashboard.json",
        "latest": f"{provider_registry_base}/latest",
        "list": provider_registry_base,
        "acceptance_dashboard": f"{base_url}/api/v1/acceptance/dashboard",
        "phase1_operator_panel": f"{base_url}/api/v1/phase1/promotion/operator-panel",
        "phase1_operator_panel_json": f"{base_url}/api/v1/phase1/promotion/operator-panel.json",
    }


def publish_provider_registry_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "provider",
        "registry",
        "--control-plane-url",
        args.control_plane_url,
        "--api-token",
        args.api_token,
    ]
    if args.signing_key:
        command.extend(["--signing-key", str(args.signing_key)])
        command.extend(["--signer-id", args.signer_id])
    command.append("--json")
    ao2_result = run_ao2(command)
    return bridge_result(
        "publish-provider-registry",
        trust_boundary={"mode": "ao2_provider_plugin_registry_publish", **TRUST_BOUNDARY},
        ao2_invocation=sanitize_invocation(command),
        ao2_result=sanitize_payload(ao2_result),
        control_plane_url=args.control_plane_url.rstrip("/"),
        observer_links=provider_registry_observer_links(args.control_plane_url),
    )


def publish_provider_acceptance_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.acceptance.is_file():
        raise RuntimeError(f"provider acceptance bundle not found: {args.acceptance}")
    raw = args.acceptance.read_bytes()
    try:
        acceptance = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"provider acceptance bundle is not valid JSON: {args.acceptance}") from exc
    schema = str(acceptance.get("schema_version") or "")
    if schema not in {
        "ao2.codex-provider-pilot-acceptance.v1",
        "ao2.claude-provider-pilot-acceptance.v1",
    }:
        raise RuntimeError(f"unsupported provider acceptance schema: {schema or '<missing>'}")
    provider = str(acceptance.get("provider") or "")
    if (schema.startswith("ao2.codex-") and provider != "codex") or (
        schema.startswith("ao2.claude-") and provider != "claude"
    ):
        raise RuntimeError(f"provider {provider or '<missing>'} does not match acceptance schema {schema}")
    base_url = args.control_plane_url.rstrip("/")
    receipt, status_code = post_json_bytes(
        f"{base_url}/api/v1/acceptance",
        args.api_token,
        raw,
    )
    dashboard_snapshot, dashboard_status_code = get_json(
        f"{base_url}/api/v1/acceptance/dashboard.json",
        args.api_token,
    )
    return bridge_result(
        "publish-provider-acceptance",
        trust_boundary={"mode": "provider_pilot_acceptance_observer_publish", **TRUST_BOUNDARY},
        acceptance=str(args.acceptance),
        provider=provider,
        schema_version=schema,
        status_code=status_code,
        receipt=sanitize_payload(receipt),
        dashboard_status_code=dashboard_status_code,
        dashboard_snapshot=sanitize_payload(dashboard_snapshot),
        links={
            "acceptance_dashboard": f"{base_url}/api/v1/acceptance/dashboard",
            "acceptance_dashboard_json": f"{base_url}/api/v1/acceptance/dashboard.json",
        },
    )


def publish_phase1_checklist_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.checklist.is_file():
        raise RuntimeError(f"Phase 1 checklist artifact not found: {args.checklist}")
    raw = args.checklist.read_bytes()
    try:
        checklist = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Phase 1 checklist artifact is not valid JSON: {args.checklist}") from exc
    schema = str(checklist.get("schema") or checklist.get("schema_version") or "")
    if schema != "ao-operator/ao2-phase1-promotion-checklist/v1":
        raise RuntimeError(f"unsupported Phase 1 checklist schema: {schema or '<missing>'}")
    base_url = args.control_plane_url.rstrip("/")
    receipt, status_code = post_json_bytes(
        f"{base_url}/api/v1/phase1/promotion/checklist",
        args.api_token,
        raw,
    )
    dashboard_snapshot, dashboard_status_code = get_json(
        f"{base_url}/api/v1/phase1/promotion/dashboard.json",
        args.api_token,
    )
    return bridge_result(
        "publish-phase1-checklist",
        trust_boundary={"mode": "phase1_promotion_checklist_observer_publish", **TRUST_BOUNDARY},
        checklist=str(args.checklist),
        checklist_schema=schema,
        status_code=status_code,
        receipt=sanitize_payload(receipt),
        dashboard_status_code=dashboard_status_code,
        dashboard_snapshot=sanitize_payload(dashboard_snapshot),
        links={
            "phase1_promotion_dashboard": f"{base_url}/api/v1/phase1/promotion/dashboard",
            "phase1_promotion_dashboard_json": f"{base_url}/api/v1/phase1/promotion/dashboard.json",
            "latest_checklist": f"{base_url}/api/v1/phase1/promotion/checklist/latest",
        },
    )


def publish_three_os_smoke_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.summary.is_file():
        raise RuntimeError(f"three-OS smoke summary not found: {args.summary}")
    raw = args.summary.read_bytes()
    try:
        summary = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"three-OS smoke summary is not valid JSON: {args.summary}") from exc
    schema = str(summary.get("schema") or summary.get("schema_version") or "")
    if schema != "ao2-control-plane.three-os-release-smoke.v1":
        raise RuntimeError(f"unsupported three-OS smoke schema: {schema or '<missing>'}")
    base_url = args.control_plane_url.rstrip("/")
    receipt, status_code = post_json_bytes(
        f"{base_url}/api/v1/phase1/promotion/three-os-smoke",
        args.api_token,
        raw,
    )
    dashboard_snapshot, dashboard_status_code = get_json(
        f"{base_url}/api/v1/phase1/promotion/dashboard.json",
        args.api_token,
    )
    return bridge_result(
        "publish-three-os-smoke",
        trust_boundary={"mode": "three_os_smoke_observer_publish", **TRUST_BOUNDARY},
        summary=str(args.summary),
        summary_schema=schema,
        status_code=status_code,
        receipt=sanitize_payload(receipt),
        dashboard_status_code=dashboard_status_code,
        dashboard_snapshot=sanitize_payload(dashboard_snapshot),
        links={
            "phase1_promotion_dashboard": f"{base_url}/api/v1/phase1/promotion/dashboard",
            "phase1_promotion_dashboard_json": f"{base_url}/api/v1/phase1/promotion/dashboard.json",
            "latest_three_os_smoke": f"{base_url}/api/v1/phase1/promotion/three-os-smoke/latest",
        },
    )


def publish_watchdog_panel_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.panel.is_file():
        raise RuntimeError(f"Hermes watchdog panel not found: {args.panel}")
    raw = args.panel.read_bytes()
    try:
        panel = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Hermes watchdog panel is not valid JSON: {args.panel}") from exc
    schema = str(panel.get("schema") or "")
    if schema != "ao-operator/hermes-ao2-watchdog-panel/v1":
        raise RuntimeError(f"unsupported Hermes watchdog panel schema: {schema or '<missing>'}")
    base_url = args.control_plane_url.rstrip("/")
    receipt, status_code = post_json_bytes(
        f"{base_url}/api/v1/hermes/watchdog/panel",
        args.api_token,
        raw,
    )
    latest_snapshot, latest_status_code = get_json(
        f"{base_url}/api/v1/hermes/watchdog/panel/latest.json",
        args.api_token,
    )
    links = latest_snapshot.get("links") if isinstance(latest_snapshot.get("links"), dict) else {}
    return bridge_result(
        "publish-watchdog-panel",
        trust_boundary={"mode": "hermes_watchdog_panel_observer_publish", **TRUST_BOUNDARY},
        panel=str(args.panel),
        panel_schema=schema,
        status_code=status_code,
        receipt=sanitize_payload(receipt),
        latest_status_code=latest_status_code,
        latest_snapshot=sanitize_payload(latest_snapshot),
        observer_links={
            "panel": control_plane_link(
                base_url, links.get("panel_html"), "/api/v1/hermes/watchdog/panel"
            ),
            "latest_json": f"{base_url}/api/v1/hermes/watchdog/panel/latest.json",
            "history_json": control_plane_link(
                base_url, links.get("history_json"), "/api/v1/hermes/watchdog/history.json"
            ),
        },
    )


def publish_release_publication_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.publication.is_file():
        raise RuntimeError(f"release publication artifact not found: {args.publication}")
    raw = args.publication.read_bytes()
    try:
        publication = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"release publication artifact is not valid JSON: {args.publication}"
        ) from exc
    schema = str(publication.get("schema") or publication.get("schema_version") or "")
    if schema != "ao2.release-publication-summary.v1":
        raise RuntimeError(f"unsupported release publication schema: {schema or '<missing>'}")
    base_url = args.control_plane_url.rstrip("/")
    receipt, status_code = post_json_bytes(
        f"{base_url}/api/v1/release/publication",
        args.api_token,
        raw,
    )
    dashboard_snapshot, dashboard_status_code = get_json(
        f"{base_url}/api/v1/release/publication/dashboard.json",
        args.api_token,
    )
    return bridge_result(
        "publish-release-publication",
        trust_boundary={"mode": "release_publication_observer_publish", **TRUST_BOUNDARY},
        publication=str(args.publication),
        publication_schema=schema,
        release_tag=str(publication.get("release_tag") or ""),
        status_code=status_code,
        receipt=sanitize_payload(receipt),
        dashboard_status_code=dashboard_status_code,
        dashboard_snapshot=sanitize_payload(dashboard_snapshot),
        links={
            "release_publication_dashboard": f"{base_url}/api/v1/release/publication/dashboard",
            "release_publication_dashboard_json": f"{base_url}/api/v1/release/publication/dashboard.json",
            "latest_release_publication": f"{base_url}/api/v1/release/publication/latest",
        },
    )


def phase1_promotion_status_from_fetch(fetch: dict[str, Any]) -> dict[str, Any]:
    history = fetch.get("history") if isinstance(fetch.get("history"), dict) else {}
    grouped = history.get("history") if isinstance(history.get("history"), dict) else {}
    checklists = grouped.get("checklists") if isinstance(grouped.get("checklists"), list) else []
    decisions = (
        grouped.get("signed_decisions")
        if isinstance(grouped.get("signed_decisions"), list)
        else []
    )
    smokes = (
        grouped.get("three_os_smokes")
        if isinstance(grouped.get("three_os_smokes"), list)
        else []
    )
    latest_checklist = checklists[0] if checklists and isinstance(checklists[0], dict) else {}
    latest_decision = decisions[0] if decisions and isinstance(decisions[0], dict) else {}
    latest_smoke = smokes[0] if smokes and isinstance(smokes[0], dict) else {}
    signature = (
        latest_decision.get("signature")
        if isinstance(latest_decision.get("signature"), dict)
        else {}
    )
    next_action = (
        str(latest_checklist.get("next_action") or "").strip()
        or str(latest_smoke.get("next_action") or "").strip()
        or "review Phase 1 promotion history in AO Operator evaluator-closer before release-line decisions"
    )
    return {
        "state": str(latest_checklist.get("phase1_state") or "unknown"),
        "checklist_status": str(latest_checklist.get("status") or "missing"),
        "signed_decision_status": str(latest_decision.get("status") or "missing"),
        "decision": str(latest_decision.get("decision") or ""),
        "signature_verified": bool(signature.get("signature_verified")),
        "three_os_status": str(latest_smoke.get("status") or "missing"),
        "three_os_state": str(latest_smoke.get("state") or ""),
        "counts": history.get("counts") if isinstance(history.get("counts"), dict) else {},
        "next_action": next_action,
    }


def phase1_promotion_status_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "release",
        "phase1-history-fetch",
        "--control-plane-url",
        args.control_plane_url,
        "--api-token-env",
        args.api_token_env,
        "--json",
    ]
    ao2_result = run_ao2(command)
    base_url = args.control_plane_url.rstrip("/")
    return bridge_result(
        "phase1-promotion-status",
        trust_boundary={"mode": "phase1_promotion_history_read_only", **TRUST_BOUNDARY},
        operator_status=phase1_promotion_status_from_fetch(ao2_result),
        links={
            "dashboard": f"{base_url}/api/v1/phase1/promotion/dashboard",
            "dashboard_json": f"{base_url}/api/v1/phase1/promotion/dashboard.json",
            "history_json": f"{base_url}/api/v1/phase1/promotion/history.json",
            "gap_report_json": f"{base_url}/api/v1/phase1/promotion/gap-report.json",
        },
        ao2_invocation=sanitize_invocation(command),
        ao2_result=sanitize_payload(ao2_result),
    )


def _surface_value(cockpit: dict[str, Any], surface: str) -> dict[str, Any]:
    surfaces = cockpit.get("surfaces") if isinstance(cockpit.get("surfaces"), dict) else {}
    value = surfaces.get(surface) if isinstance(surfaces.get(surface), dict) else {}
    return value


def release_cockpit_frontend_status(cockpit: dict[str, Any]) -> dict[str, Any]:
    release_publication = _surface_value(cockpit, "release_publication")
    phase1_promotion = _surface_value(cockpit, "phase1_promotion")
    provider_registry = _surface_value(cockpit, "provider_registry")
    provider_readiness = _surface_value(cockpit, "provider_readiness")
    provider_acceptance = _surface_value(cockpit, "provider_acceptance")
    return {
        "status": str(cockpit.get("status") or "unknown"),
        "release_publication": str(
            release_publication.get("state") or release_publication.get("status") or "missing"
        ),
        "phase1_promotion": str(
            phase1_promotion.get("state") or phase1_promotion.get("status") or "missing"
        ),
        "phase1_signature_verified": bool(phase1_promotion.get("signature_verified")),
        "provider_registry": str(provider_registry.get("status") or "missing"),
        "provider_registry_signed": bool(provider_registry.get("signed")),
        "provider_count": int(provider_registry.get("provider_count") or 0),
        "provider_readiness": str(provider_readiness.get("status") or "missing"),
        "provider_readiness_codex_gate": str(provider_readiness.get("codex_gate") or "missing"),
        "provider_acceptance": str(provider_acceptance.get("status") or "missing"),
        "provider_acceptance_total": int(provider_acceptance.get("total_count") or 0),
        "latest_provider_acceptance": {
            "codex": release_cockpit_acceptance_summary(provider_acceptance, "latest_codex"),
            "claude": release_cockpit_acceptance_summary(provider_acceptance, "latest_claude"),
        },
        "next_action": str(cockpit.get("next_action") or "review AO2 release cockpit"),
    }


def release_cockpit_acceptance_summary(
    provider_acceptance: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    entry = provider_acceptance.get(key) if isinstance(provider_acceptance.get(key), dict) else {}
    return {
        "provider": str(entry.get("provider") or "unknown"),
        "status": str(entry.get("status") or "missing"),
        "source_class": str(entry.get("source_class") or "missing"),
        "run_id": str(entry.get("run_id") or "missing"),
        "score": entry.get("score"),
        "raw_url": str(entry.get("raw_url") or ""),
    }


def release_cockpit_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(f"{args.api_token_env} is required for release cockpit status")
    base_url = args.control_plane_url.rstrip("/")
    cockpit, status_code = get_json(f"{base_url}/api/v1/release/cockpit.json", token)
    links = cockpit.get("links") if isinstance(cockpit.get("links"), dict) else {}
    return bridge_result(
        "release-cockpit-status",
        trust_boundary={"mode": "release_cockpit_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=release_cockpit_frontend_status(cockpit),
        cockpit_snapshot=sanitize_payload(cockpit),
        links={
            "cockpit": f"{base_url}/api/v1/release/cockpit",
            "cockpit_json": f"{base_url}/api/v1/release/cockpit.json",
            "release_publication_dashboard": str(
                links.get("release_publication_dashboard")
                or f"{base_url}/api/v1/release/publication/dashboard"
            ),
            "phase1_operator_panel": str(
                links.get("phase1_operator_panel")
                or f"{base_url}/api/v1/phase1/promotion/operator-panel"
            ),
            "provider_registry_dashboard": str(
                links.get("provider_registry_dashboard")
                or f"{base_url}/api/v1/provider/registry/dashboard"
            ),
            "provider_acceptance_dashboard": str(
                links.get("acceptance_dashboard") or f"{base_url}/api/v1/acceptance/dashboard"
            ),
        },
    )


def release_handoff_frontend_status(handoff: dict[str, Any]) -> dict[str, Any]:
    release = handoff.get("release") if isinstance(handoff.get("release"), dict) else {}
    gates = handoff.get("gates") if isinstance(handoff.get("gates"), dict) else {}
    acceptance = handoff.get("acceptance") if isinstance(handoff.get("acceptance"), dict) else {}
    codex = acceptance.get("codex") if isinstance(acceptance.get("codex"), dict) else {}
    claude = acceptance.get("claude") if isinstance(acceptance.get("claude"), dict) else {}
    return {
        "status": str(handoff.get("status") or "unknown"),
        "handoff_kind": str(handoff.get("handoff_kind") or "unknown"),
        "release_version": str(release.get("version") or "unknown"),
        "release_tag": str(release.get("release_tag") or "unknown"),
        "release_cockpit": str(gates.get("release_cockpit") or "missing"),
        "phase1_promotion": str(gates.get("phase1_promotion") or "missing"),
        "decision_signature": str(gates.get("decision_signature") or "missing"),
        "provider_acceptance": str(gates.get("provider_acceptance") or "missing"),
        "codex_acceptance": (
            f"{codex.get('status') or 'missing'}/{codex.get('source_class') or 'missing'}"
        ),
        "claude_acceptance": (
            f"{claude.get('status') or 'missing'}/{claude.get('source_class') or 'missing'}"
        ),
        "next_action": (
            "ao-operator evaluator-closer reviews the handoff before release-line decisions"
        ),
    }


def release_handoff_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(f"{args.api_token_env} is required for release handoff status")
    base_url = args.control_plane_url.rstrip("/")
    handoff, status_code = get_json(f"{base_url}/api/v1/release/handoff.json", token)
    links = handoff.get("links") if isinstance(handoff.get("links"), dict) else {}
    return bridge_result(
        "release-handoff-status",
        trust_boundary={"mode": "release_handoff_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=release_handoff_frontend_status(handoff),
        handoff_snapshot=sanitize_payload(handoff),
        links={
            "release_candidate_handoff": str(
                links.get("release_candidate_handoff")
                or f"{base_url}/api/v1/release/handoff"
            ),
            "release_candidate_handoff_json": str(
                links.get("release_candidate_handoff_json")
                or f"{base_url}/api/v1/release/handoff.json"
            ),
            "cockpit_json": str(links.get("cockpit_json") or f"{base_url}/api/v1/release/cockpit.json"),
            "phase1_operator_panel_json": str(
                links.get("phase1_operator_panel_json")
                or f"{base_url}/api/v1/phase1/promotion/operator-panel.json"
            ),
        },
    )


def route_index_frontend_status(route_index: dict[str, Any]) -> dict[str, Any]:
    routes_value = route_index.get("routes")
    routes: list[Any] = routes_value if isinstance(routes_value, list) else []
    route_dicts = [route for route in routes if isinstance(route, dict)]
    recommended_usage_value = route_index.get("recommended_frontend_usage")
    recommended_usage: list[Any] = (
        recommended_usage_value if isinstance(recommended_usage_value, list) else []
    )
    auth_value = route_index.get("auth")
    auth: dict[str, Any] = auth_value if isinstance(auth_value, dict) else {}
    credential_material_in_urls = bool(auth.get("credential_material_in_urls"))
    mutates_ao_artifacts = bool(route_index.get("mutates_ao_artifacts")) or any(
        bool(route.get("mutates_ao_artifacts")) for route in route_dicts
    )
    control_plane_approves_release = bool(route_index.get("control_plane_approves_release")) or any(
        bool(route.get("control_plane_approves_release")) for route in route_dicts
    )
    release_approval_route_count = sum(
        1 for route in route_dicts if bool(route.get("control_plane_approves_release"))
    )
    status = (
        "failed"
        if credential_material_in_urls or mutates_ao_artifacts or control_plane_approves_release
        else "passed"
    )
    return {
        "status": status,
        "route_count": len(route_dicts),
        "portable_route_count": sum(1 for route in route_dicts if bool(route.get("portable"))),
        "download_route_count": sum(1 for route in route_dicts if bool(route.get("download"))),
        "mutating_observer_route_count": sum(
            1 for route in route_dicts if bool(route.get("mutates_observer_storage"))
        ),
        "auth_required_route_count": sum(
            1 for route in route_dicts if bool(route.get("auth_required"))
        ),
        "release_approval_route_count": release_approval_route_count,
        "credential_material_in_urls": credential_material_in_urls,
        "mutates_ao_artifacts": mutates_ao_artifacts,
        "control_plane_approves_release": control_plane_approves_release,
        "recommended_frontend_usage_count": len(recommended_usage),
    }


def route_index_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(f"{args.api_token_env} is required for route index status")
    base_url = args.control_plane_url.rstrip("/")
    route_index, status_code = get_json(f"{base_url}/api/v1/control-plane/routes.json", token)
    return bridge_result(
        "route-index-status",
        trust_boundary={"mode": "control_plane_route_index_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=route_index_frontend_status(route_index),
        route_index_snapshot=sanitize_payload(route_index),
        links={
            "route_index_json": f"{base_url}/api/v1/control-plane/routes.json",
        },
    )


def release_readiness_frontend_status(readiness: dict[str, Any]) -> dict[str, Any]:
    release = readiness.get("release") if isinstance(readiness.get("release"), dict) else {}
    gates = readiness.get("gate_results") if isinstance(readiness.get("gate_results"), list) else []
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    operator_decision = (
        readiness.get("operator_decision")
        if isinstance(readiness.get("operator_decision"), dict)
        else {}
    )
    blocked_gate_count = sum(
        1
        for gate in gates
        if isinstance(gate, dict) and str(gate.get("status") or "missing") != "passed"
    )
    return {
        "status": str(readiness.get("status") or "unknown"),
        "release_version": str(release.get("version") or "unknown"),
        "release_tag": str(release.get("release_tag") or "unknown"),
        "gate_count": len(gates),
        "blocked_gate_count": blocked_gate_count,
        "blocker_count": len(blockers),
        "factory_v3_evaluator_closer_required": bool(
            operator_decision.get("factory_v3_evaluator_closer_required")
        ),
        "control_plane_approves_release": bool(
            operator_decision.get("control_plane_approves_release")
        ),
        "next_action": str(
            operator_decision.get("next_action")
            or "ao-operator evaluator-closer reviews release readiness"
        ),
    }


def release_readiness_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(f"{args.api_token_env} is required for release readiness status")
    base_url = args.control_plane_url.rstrip("/")
    readiness, status_code = get_json(f"{base_url}/api/v1/release/readiness.json", token)
    links = readiness.get("links") if isinstance(readiness.get("links"), dict) else {}
    return bridge_result(
        "release-readiness-status",
        trust_boundary={"mode": "release_readiness_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=release_readiness_frontend_status(readiness),
        readiness_snapshot=sanitize_payload(readiness),
        links={
            "release_readiness": str(
                links.get("release_readiness") or f"{base_url}/api/v1/release/readiness"
            ),
            "release_readiness_json": str(
                links.get("release_readiness_json")
                or f"{base_url}/api/v1/release/readiness.json"
            ),
            "release_candidate_handoff": str(
                links.get("release_candidate_handoff")
                or f"{base_url}/api/v1/release/handoff"
            ),
            "release_candidate_handoff_json": str(
                links.get("release_candidate_handoff_json")
                or f"{base_url}/api/v1/release/handoff.json"
            ),
        },
    )


def release_support_bundle_frontend_status(bundle: dict[str, Any]) -> dict[str, Any]:
    release_assembly = (
        bundle.get("release_assembly")
        if isinstance(bundle.get("release_assembly"), dict)
        else {}
    )
    required_artifacts = (
        release_assembly.get("required_artifacts")
        if isinstance(release_assembly.get("required_artifacts"), list)
        else []
    )
    missing_artifact_count = sum(
        1
        for artifact in required_artifacts
        if isinstance(artifact, dict) and str(artifact.get("status") or "missing") != "observed"
    )
    return {
        "status": str(release_assembly.get("status") or bundle.get("status") or "unknown"),
        "release_candidate_version": str(
            release_assembly.get("release_candidate_version") or "unknown"
        ),
        "release_tag": str(release_assembly.get("release_tag") or "unknown"),
        "candidate_correlation": str(
            release_assembly.get("candidate_correlation") or "unknown"
        ),
        "required_artifact_count": len(required_artifacts),
        "missing_artifact_count": missing_artifact_count,
        "control_plane_approves_release": bool(
            release_assembly.get("control_plane_approves_release")
        ),
        "release_acceptance_owner": str(
            release_assembly.get("release_acceptance_owner")
            or "ao-operator evaluator-closer"
        ),
        "next_action": str(
            release_assembly.get("next_action")
            or "ao-operator evaluator-closer reviews release support bundle"
        ),
    }


def release_support_bundle_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(f"{args.api_token_env} is required for release support bundle status")
    base_url = args.control_plane_url.rstrip("/")
    path = f"/api/v1/release/support-bundle.json?keep_latest={args.keep_latest}"
    bundle, status_code = get_json(f"{base_url}{path}", token)
    links = bundle.get("links") if isinstance(bundle.get("links"), dict) else {}
    return bridge_result(
        "release-support-bundle-status",
        trust_boundary={"mode": "release_support_bundle_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=release_support_bundle_frontend_status(bundle),
        support_bundle_snapshot=sanitize_payload(bundle),
        links={
            "release_support_bundle_json": control_plane_link(
                base_url,
                links.get("release_support_bundle_json"),
                path,
            ),
            "release_readiness_json": control_plane_link(
                base_url,
                links.get("release_readiness_json"),
                "/api/v1/release/readiness.json",
            ),
            "release_candidate_handoff_json": control_plane_link(
                base_url,
                links.get("release_candidate_handoff_json"),
                "/api/v1/release/handoff.json",
            ),
        },
    )


def release_evaluator_decision_frontend_status(dashboard: dict[str, Any]) -> dict[str, Any]:
    latest = dashboard.get("latest") if isinstance(dashboard.get("latest"), dict) else {}
    release = latest.get("release") if isinstance(latest.get("release"), dict) else {}
    blockers = dashboard.get("blockers") if isinstance(dashboard.get("blockers"), list) else []
    trust_boundary = (
        dashboard.get("trust_boundary")
        if isinstance(dashboard.get("trust_boundary"), dict)
        else {}
    )
    return {
        "status": str(latest.get("status") or dashboard.get("status") or "unknown"),
        "state": str(dashboard.get("state") or latest.get("state") or "unknown"),
        "decision": str(latest.get("decision") or "unknown"),
        "release_version": str(release.get("version") or "unknown"),
        "release_tag": str(release.get("release_tag") or "unknown"),
        "blocker_count": len(blockers),
        "control_plane_approves_release": bool(
            trust_boundary.get("control_plane_approves_release")
        ),
        "release_acceptance_owner": str(
            trust_boundary.get("release_acceptance_owner")
            or "ao-operator evaluator-closer"
        ),
        "next_action": (
            "ao-operator evaluator-closer owns release acceptance; control plane only observes the signed decision"
        ),
    }


def release_evaluator_decision_status_command(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(
            f"{args.api_token_env} is required for release evaluator decision status"
        )
    base_url = args.control_plane_url.rstrip("/")
    dashboard, status_code = get_json(
        f"{base_url}/api/v1/release/evaluator-decision/dashboard.json",
        token,
    )
    links = dashboard.get("links") if isinstance(dashboard.get("links"), dict) else {}
    return bridge_result(
        "release-evaluator-decision-status",
        trust_boundary={"mode": "release_evaluator_decision_read_only", **TRUST_BOUNDARY},
        status_code=status_code,
        frontend_status=release_evaluator_decision_frontend_status(dashboard),
        decision_snapshot=sanitize_payload(dashboard),
        links={
            "latest_release_evaluator_decision": control_plane_link(
                base_url,
                links.get("latest_release_evaluator_decision"),
                "/api/v1/release/evaluator-decision/latest",
            ),
            "release_evaluator_decision_dashboard": control_plane_link(
                base_url,
                links.get("dashboard"),
                "/api/v1/release/evaluator-decision/dashboard",
            ),
            "release_evaluator_decision_dashboard_json": control_plane_link(
                base_url,
                links.get("dashboard_json"),
                "/api/v1/release/evaluator-decision/dashboard.json",
            ),
        },
    )


def _parse_sse_event_block(block: list[str]) -> dict[str, Any] | None:
    if not block:
        return None
    event_type: str | None = None
    event_id: str | None = None
    data_lines: list[str] = []
    for line in block:
        if line.startswith(":"):
            continue
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_type = value
        elif field == "id":
            event_id = value
        elif field == "data":
            data_lines.append(value)
    if event_type is None and not data_lines:
        return None
    raw_data = "\n".join(data_lines)
    parsed_data: Any = None
    if raw_data:
        try:
            parsed_data = json.loads(raw_data)
        except json.JSONDecodeError:
            parsed_data = None
    return {
        "event": event_type,
        "id": event_id,
        "data": parsed_data,
    }


def audit_log_stream_command(args: argparse.Namespace) -> dict[str, Any]:
    import socket
    import time

    token = os.environ.get(args.api_token_env)
    if not token:
        raise RuntimeError(
            f"{args.api_token_env} is required for audit-log stream subscription"
        )
    base_url = args.control_plane_url.rstrip("/")
    query: list[str] = []
    if args.last_event_id is not None:
        query.append(f"last_event_id={args.last_event_id}")
    for label, value in (
        ("method", args.filter_method),
        ("status", args.filter_status),
        ("status_class", args.filter_status_class),
        ("path_prefix", args.filter_path_prefix),
    ):
        if value:
            query.append(f"{label}={urllib.parse.quote(value)}")
    if args.filter_authenticated is not None:
        query.append(f"authenticated={'true' if args.filter_authenticated else 'false'}")
    url = f"{base_url}/api/v1/audit-log/stream"
    if query:
        url = f"{url}?{'&'.join(query)}"

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        },
    )

    events: list[dict[str, Any]] = []
    lagged_events: list[dict[str, Any]] = []
    keepalive_count = 0
    method_counts: dict[str, int] = {}
    status_class_counts: dict[str, int] = {}
    authenticated_count = 0
    unauthenticated_count = 0
    last_event_id: str | None = None
    first_event_id: str | None = None
    started_at = time.monotonic()
    deadline = started_at + max(1, args.max_seconds)
    target_count = args.max_events if args.max_events > 0 else None
    stop_reason = "deadline"
    open_status_code: int | None = None

    try:
        with urllib.request.urlopen(request, timeout=args.connect_timeout_seconds) as response:
            open_status_code = int(response.status)
            try:
                response.fp.raw._sock.settimeout(args.read_timeout_seconds)  # type: ignore[attr-defined]
            except Exception:
                pass
            block: list[str] = []
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop_reason = "deadline"
                    break
                try:
                    raw_line = response.readline()
                except (socket.timeout, TimeoutError):
                    # idle timeout; loop and check deadline
                    continue
                except OSError:
                    # readline() socket-level timeouts surface in different
                    # shapes across platforms (socket.timeout, TimeoutError,
                    # bare OSError on macOS, EAGAIN/EWOULDBLOCK on Linux).
                    # Treat any OSError as a transient socket timeout and
                    # continue; the top-of-loop deadline check will set
                    # stop_reason="deadline" cleanly when the wall clock
                    # has expired.
                    continue
                except Exception as exc:  # noqa: BLE001
                    stop_reason = f"read_error:{exc.__class__.__name__}"
                    break
                if not raw_line:
                    stop_reason = "eof"
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line == "":
                    parsed = _parse_sse_event_block(block)
                    block = []
                    if parsed is None:
                        continue
                    event_type = parsed.get("event") or "audit-log"
                    if event_type == "lagged":
                        lagged_events.append(parsed)
                    elif event_type == "audit-log":
                        data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
                        events.append(parsed)
                        if parsed.get("id"):
                            if first_event_id is None:
                                first_event_id = str(parsed["id"])
                            last_event_id = str(parsed["id"])
                        method = str(data.get("method") or "")
                        if method:
                            method_counts[method] = method_counts.get(method, 0) + 1
                        status = data.get("status")
                        if isinstance(status, int):
                            bucket = f"{status // 100}xx"
                            status_class_counts[bucket] = (
                                status_class_counts.get(bucket, 0) + 1
                            )
                        if data.get("authenticated") is True:
                            authenticated_count += 1
                        elif data.get("authenticated") is False:
                            unauthenticated_count += 1
                    if target_count is not None and len(events) >= target_count:
                        stop_reason = "max_events"
                        break
                    continue
                if line.startswith(":"):
                    # SSE comment / keepalive
                    keepalive_count += 1
                    continue
                block.append(line)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"audit-log stream subscription failed with status {exc.code}: {raw}"
        ) from exc

    elapsed = time.monotonic() - started_at
    tail_sample = events[-args.tail_sample :] if args.tail_sample > 0 else []
    trust_boundary = {
        "mode": "audit_log_live_tail_consumer",
        **TRUST_BOUNDARY,
    }
    payload = bridge_result(
        "audit-log-stream",
        trust_boundary=trust_boundary,
        control_plane_url=base_url,
        request_url=url,
        connect_status_code=open_status_code,
        stop_reason=stop_reason,
        elapsed_seconds=round(elapsed, 3),
        events_consumed=len(events),
        keepalive_count=keepalive_count,
        lagged_event_count=len(lagged_events),
        first_event_id=first_event_id,
        last_event_id=last_event_id,
        method_counts=method_counts,
        status_class_counts=status_class_counts,
        authenticated_count=authenticated_count,
        unauthenticated_count=unauthenticated_count,
        lagged_events=sanitize_payload(lagged_events),
        tail_sample=sanitize_payload(tail_sample),
        filters={
            "method": args.filter_method,
            "status": args.filter_status,
            "status_class": args.filter_status_class,
            "path_prefix": args.filter_path_prefix,
            "authenticated": args.filter_authenticated,
            "last_event_id": args.last_event_id,
        },
        links={
            "audit_log_stream": url,
            "audit_log_dashboard": f"{base_url}/api/v1/audit-log/dashboard",
            "audit_log_polling_json": f"{base_url}/api/v1/audit-log",
        },
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        payload["out"] = str(args.out)
    return payload


def phase1_promotion_panel_payload(status_payload: dict[str, Any]) -> dict[str, Any]:
    operator_status = (
        status_payload.get("operator_status")
        if isinstance(status_payload.get("operator_status"), dict)
        else {}
    )
    links = status_payload.get("links") if isinstance(status_payload.get("links"), dict) else {}
    trust_boundary = (
        status_payload.get("trust_boundary")
        if isinstance(status_payload.get("trust_boundary"), dict)
        else {}
    )
    checklist_status = str(operator_status.get("checklist_status") or "missing")
    signed_decision_status = str(operator_status.get("signed_decision_status") or "missing")
    three_os_status = str(operator_status.get("three_os_status") or "missing")
    signature_verified = bool(operator_status.get("signature_verified"))
    source_status = str(status_payload.get("status") or "")
    if source_status == "planned" or operator_status.get("state") == "planned":
        panel_status = "planned"
    elif (
        checklist_status == "passed"
        and signed_decision_status == "passed"
        and three_os_status == "passed"
        and signature_verified
    ):
        panel_status = "ready"
    else:
        panel_status = "attention"

    return {
        "schema": "ao-operator/hermes-phase1-promotion-panel/v1",
        "action": "phase1-promotion-panel",
        "status": panel_status,
        "summary": (
            "AO2 Phase 1 candidate is ready for an operator release-line decision"
            if panel_status == "ready"
            else "AO2 Phase 1 promotion state needs operator review"
            if panel_status == "attention"
            else "AO2 Phase 1 promotion panel is planned until the guarded run fetches live observer history"
        ),
        "operator_status": operator_status,
        "badges": {
            "checklist": checklist_status,
            "signed_decision": signed_decision_status,
            "signature": "verified" if signature_verified else "missing",
            "three_os": three_os_status,
        },
        "links": links,
        "next_action": str(
            operator_status.get("next_action")
            or "review AO Operator evaluator-closer evidence before release-line decisions"
        ),
        "trust_boundary": {
            "mode": "operator_panel_from_read_only_phase1_status",
            **TRUST_BOUNDARY,
            **trust_boundary,
        },
        "source": {
            "schema": status_payload.get("schema") or status_payload.get("schema_version"),
            "action": status_payload.get("action"),
            "status": source_status or None,
        },
    }


def write_phase1_promotion_panel_markdown(panel: dict[str, Any], path: Path) -> None:
    operator_status = panel.get("operator_status", {})
    if not isinstance(operator_status, dict):
        operator_status = {}
    badges = panel.get("badges", {})
    if not isinstance(badges, dict):
        badges = {}
    links = panel.get("links", {})
    if not isinstance(links, dict):
        links = {}
    lines = [
        "# AO2 Phase 1 Operator Panel",
        "",
        f"- status: `{panel.get('status', 'unknown')}`",
        f"- summary: {panel.get('summary', '')}",
        f"- state: `{operator_status.get('state', 'unknown')}`",
        f"- checklist: `{badges.get('checklist', 'unknown')}`",
        f"- signed_decision: `{badges.get('signed_decision', 'unknown')}`",
        f"- decision: `{operator_status.get('decision', '')}`",
        f"- signature: `{badges.get('signature', 'unknown')}`",
        f"- three_os: `{badges.get('three_os', 'unknown')}`",
        f"- three_os_state: `{operator_status.get('three_os_state', '')}`",
        f"- next_action: `{panel.get('next_action', '')}`",
        "",
        "## Observer Links",
        "",
    ]
    for key in ("dashboard", "dashboard_json", "history_json", "gap_report_json"):
        value = links.get(key)
        if value:
            lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Trust Boundary",
            "",
            "- Hermes remains front end, queue, cron, and memory surface.",
            "- AO2 remains trusted execution, memory, and signed evidence boundary.",
            "- AO2 Control Plane remains a read-only observer outside the trust path.",
            "- AO Operator / AO Operator evaluator-closer owns release acceptance.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def phase1_promotion_panel_command(args: argparse.Namespace) -> dict[str, Any]:
    status_payload = json.loads(args.status.read_text(encoding="utf-8"))
    panel = phase1_promotion_panel_payload(status_payload)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(panel, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_phase1_promotion_panel_markdown(panel, args.out_markdown)
    return panel


def link_run_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "memory",
        "link-run",
        "--target",
        str(args.ao2_target),
        "--memory-id",
        args.memory_id,
        "--run-id",
        args.run_id,
        "--relationship",
        args.relationship,
        "--json",
    ]
    ao2_result = run_ao2(command)
    return bridge_result(
        "link-run",
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def governed_run_command(args: argparse.Namespace) -> dict[str, Any]:
    validate_governed_run_request(args)
    ao2_bin = resolve_ao2_bin(args.ao2_bin, args.factory_root)
    command = [ao2_bin, "run"]
    if args.workflow:
        command.append(args.workflow)
    command.extend(["--target", str(args.ao2_target)])
    if args.template:
        command.extend(["--template", args.template])
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.pause_for_approval:
        command.append("--pause-for-approval")
    if args.resume:
        command.extend(["--resume", args.resume])
    if args.provider:
        command.extend(["--provider", args.provider])
    if args.provider_prompt_file:
        command.extend(["--provider-prompt-file", str(args.provider_prompt_file)])
    if args.provider_max_budget_usd is not None:
        command.extend(["--provider-max-budget-usd", str(args.provider_max_budget_usd)])
    command.extend(["--max-repair-attempts", str(args.max_repair_attempts)])

    if args.dry_run:
        run_id = str(args.run_id or "")
        return bridge_result(
            "governed-run",
            status="planned",
            dry_run=True,
            trust_boundary=TRUST_BOUNDARY,
            run_id=run_id,
            status_path=str(args.ao2_target / ".ao2" / "runs" / run_id / "run-record.json") if run_id else None,
            evidence_pack_path=str(args.ao2_target / ".ao2" / "runs" / run_id / "evidence-pack" / "evidence-pack.json") if run_id else None,
            ao2_invocation=command,
            ao2_result=None,
        )

    ao2_result = run_ao2_run(command)
    run_id = str(args.run_id or ao2_result.get("run_id") or "")
    return bridge_result(
        "governed-run",
        status=str(ao2_result.get("status") or "started"),
        dry_run=False,
        trust_boundary=TRUST_BOUNDARY,
        run_id=run_id,
        status_path=str(args.ao2_target / ".ao2" / "runs" / run_id / "run-record.json") if run_id else None,
        evidence_pack_path=str(args.ao2_target / ".ao2" / "runs" / run_id / "evidence-pack" / "evidence-pack.json") if run_id else None,
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def repair_resume_command(args: argparse.Namespace) -> dict[str, Any]:
    validate_repair_resume_request(args)
    ao2_queue_ownership_payload = resolve_repair_resume_ao2_queue_ownership(args)
    ao2_queue_ownership_path = write_ao2_queue_ownership_claim(
        ao2_queue_ownership_payload,
        getattr(args, "ao2_queue_ownership_out", None),
    ) if ao2_queue_ownership_payload is not None else None
    ao2_bin = resolve_ao2_bin(args.ao2_bin, args.factory_root)
    command = [
        ao2_bin,
        "repair",
        "resume",
        "--evidence-pack",
        str(args.evidence_pack),
        "--target",
        str(args.ao2_target),
    ]
    if args.workflow:
        command.extend(["--workflow", args.workflow])
    if args.template:
        command.extend(["--template", args.template])
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.provider:
        command.extend(["--provider", args.provider])
    command.extend(["--provider-prompt-file", str(args.provider_prompt_file)])
    if args.provider_max_budget_usd is not None:
        command.extend(["--provider-max-budget-usd", str(args.provider_max_budget_usd)])
    command.extend(["--max-repair-attempts", str(args.max_repair_attempts), "--json"])

    if args.dry_run:
        run_id = str(args.run_id or "")
        return bridge_result(
            "repair-resume",
            status="planned",
            dry_run=True,
            trust_boundary=TRUST_BOUNDARY,
            run_id=run_id,
            source_evidence_pack_path=str(args.evidence_pack),
            evidence_pack_path=str(args.ao2_target / ".ao2" / "runs" / run_id / "evidence-pack" / "evidence-pack.json") if run_id else None,
            ao2_invocation=command,
            ao2_result=None,
            ao2_queue_ownership=ao2_queue_ownership_payload,
            ao2_queue_ownership_path=ao2_queue_ownership_path,
        )

    ao2_result = run_ao2(command)
    run_id = str(args.run_id or ao2_result.get("run_id") or "")
    return bridge_result(
        "repair-resume",
        status=str(ao2_result.get("status") or "started"),
        dry_run=False,
        trust_boundary=TRUST_BOUNDARY,
        run_id=run_id,
        source_run_id=str(ao2_result.get("source_run_id") or ""),
        source_evidence_pack_path=str(args.evidence_pack),
        evidence_pack_path=str(
            ao2_result.get("evidence_pack")
            or (args.ao2_target / ".ao2" / "runs" / run_id / "evidence-pack" / "evidence-pack.json")
        ),
        report_path=str(ao2_result.get("report") or ""),
        ao2_invocation=command,
        ao2_result=ao2_result,
        ao2_queue_ownership=ao2_queue_ownership_payload,
        ao2_queue_ownership_path=ao2_queue_ownership_path,
    )


def repair_resume_latest_command(args: argparse.Namespace) -> dict[str, Any]:
    selected = latest_nonaccepted_evidence_pack(args.ao2_target)
    repair_args = argparse.Namespace(**vars(args))
    repair_args.evidence_pack = Path(selected["path"])
    repair_payload = repair_resume_command(repair_args)
    return bridge_result(
        "repair-resume-latest",
        status=repair_payload.get("status"),
        dry_run=repair_payload.get("dry_run", False),
        trust_boundary=TRUST_BOUNDARY,
        selected=selected,
        repair_resume=repair_payload,
        ao2_queue_ownership=repair_payload.get("ao2_queue_ownership"),
        ao2_queue_ownership_path=repair_payload.get("ao2_queue_ownership_path"),
    )


def watch_run_command(args: argparse.Namespace) -> dict[str, Any]:
    ao2_bin = resolve_ao2_bin(args.ao2_bin, args.factory_root)
    status_command = [ao2_bin, "status", args.run_id, "--target", str(args.ao2_target)]
    show_command = [
        ao2_bin,
        "runs",
        "show",
        args.run_id,
        "--target",
        str(args.ao2_target),
        "--json",
    ]
    ao2_status = run_ao2(status_command)
    ao2_run_record = run_ao2(show_command)
    return bridge_result(
        "watch-run",
        trust_boundary=TRUST_BOUNDARY,
        run_id=args.run_id,
        status_path=str(args.ao2_target / ".ao2" / "runs" / args.run_id / "run-record.json"),
        evidence_pack_path=str(args.ao2_target / ".ao2" / "runs" / args.run_id / "evidence-pack" / "evidence-pack.json"),
        status_invocation=status_command,
        run_record_invocation=show_command,
        ao2_status=ao2_status,
        ao2_run_record=ao2_run_record,
    )


def git_status_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "git",
        "status",
        "--target",
        str(args.ao2_target),
        "--json",
    ]
    ao2_result = run_ao2(command)
    return bridge_result(
        "git-status",
        trust_boundary={"mode": "ao2_read_only_git_evidence", **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def git_diff_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "git",
        "diff",
        "--target",
        str(args.ao2_target),
    ]
    if args.stat:
        command.append("--stat")
    command.append("--json")
    ao2_result = run_ao2(command)
    return bridge_result(
        "git-diff",
        trust_boundary={"mode": "ao2_read_only_git_evidence", **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_result=ao2_result,
    )


def git_commit_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "git",
        "commit",
        "--target",
        str(args.ao2_target),
        "--message",
        args.message,
    ]
    for path in args.paths:
        command.extend(["--path", path])
    if args.approve_action_digest:
        command.extend(["--approve-action-digest", args.approve_action_digest])
    if args.approver:
        command.extend(["--approver", args.approver])
    command.append("--json")
    ao2_result, exit_code = run_ao2_json(command, allow_nonzero=True)
    return bridge_result(
        "git-commit",
        trust_boundary={"mode": "ao2_exact_digest_approved_git_write", **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_exit_code=exit_code,
        ao2_result=ao2_result,
    )


def git_tag_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "git",
        "tag",
        "--target",
        str(args.ao2_target),
        "--tag",
        args.tag,
    ]
    if args.message:
        command.extend(["--message", args.message])
    if args.approve_action_digest:
        command.extend(["--approve-action-digest", args.approve_action_digest])
    if args.approver:
        command.extend(["--approver", args.approver])
    command.append("--json")
    ao2_result, exit_code = run_ao2_json(command, allow_nonzero=True)
    return bridge_result(
        "git-tag",
        trust_boundary={"mode": "ao2_exact_digest_approved_git_write", **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_exit_code=exit_code,
        ao2_result=ao2_result,
    )


def contract_gate_command(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        resolve_ao2_bin(args.ao2_bin, args.factory_root),
        "contract",
        "gate",
        "--ledger",
        str(args.ledger),
        "--target",
        str(args.ao2_target),
        "--stage",
        args.stage,
        "--out",
        str(args.out),
        "--json",
    ]
    signing_key = getattr(args, "support_signing_key", None)
    if signing_key is not None:
        command.extend(["--support-signing-key", str(signing_key)])
        signer_id = (getattr(args, "support_signer_id", None) or "").strip()
        if signer_id:
            command.extend(["--support-signer-id", signer_id])
        operator_role = (getattr(args, "support_operator_role", None) or "").strip()
        if operator_role:
            command.extend(["--support-operator-role", operator_role])
        run_id = (getattr(args, "support_run_id", None) or "").strip()
        if run_id:
            command.extend(["--support-run-id", run_id])
        exports_dir = getattr(args, "exports_dir", None)
        if exports_dir is not None:
            command.extend(["--exports-dir", str(exports_dir)])
    ao2_result, exit_code = run_ao2_json(command, allow_nonzero=True)
    trust_mode = (
        "ao2_obligation_lifecycle_gate_signed"
        if signing_key is not None
        else "ao2_obligation_lifecycle_gate"
    )
    return bridge_result(
        "contract-gate",
        trust_boundary={"mode": trust_mode, **TRUST_BOUNDARY},
        ao2_invocation=command,
        ao2_exit_code=exit_code,
        ao2_result=ao2_result,
    )


def print_result(payload: dict[str, Any], json_output: bool) -> int:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"schema={payload['schema']}")
        print(f"action={payload['action']}")
        result = payload.get("ao2_result")
        if isinstance(result, dict) and "id" in result:
            print(f"memory_id={result['id']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge Hermes front ends to AO Operator context and AO2 memory."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    context = subparsers.add_parser("context", help="Export AO Operator Hermes context")
    context.add_argument("--slug", required=True)
    context.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    context.add_argument("--json", action="store_true")
    context.set_defaults(handler=context_command)

    context_refs = subparsers.add_parser(
        "context-with-ao2-refs",
        help=(
            "Export a Hermes context payload that references only AO2-owned "
            "identifiers (run IDs, evidence-pack SHAs, memory record IDs, "
            "control-plane receipts) instead of ao-operator-local paths."
        ),
    )
    context_refs.add_argument("--slug", required=True)
    context_refs.add_argument("--bridge-evidence", type=Path, default=None)
    context_refs.add_argument("--evidence-pack", type=Path, default=None)
    context_refs.add_argument("--memory-record", type=Path, default=None)
    context_refs.add_argument("--control-plane-receipt", type=Path, default=None)
    context_refs.add_argument(
        "--require-all-ao2-ref-categories",
        action="store_true",
        help=(
            "Strict mode: refuse to emit a payload unless all four Phase "
            "2 exit-gate #3 AO2 ref categories (bridge_evidence, "
            "evidence_pack, memory_record, cp_receipt) are supplied."
        ),
    )
    context_refs.add_argument("--json", action="store_true")
    context_refs.set_defaults(handler=context_with_ao2_refs_command)

    remember = subparsers.add_parser(
        "remember-context", help="Write AO Operator context into AO2 memory"
    )
    remember.add_argument("--slug", required=True)
    remember.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    remember.add_argument("--ao2-bin", default="ao2")
    remember.add_argument("--ao2-target", type=Path, default=Path("."))
    remember.add_argument("--json", action="store_true")
    remember.set_defaults(handler=remember_context_command)

    search = subparsers.add_parser("search-memory", help="Search AO2 memory")
    search.add_argument("--query", required=True)
    search.add_argument("--ao2-bin", default="ao2")
    search.add_argument("--ao2-target", type=Path, default=Path("."))
    search.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true")
    search.set_defaults(handler=search_memory_command)

    note = subparsers.add_parser(
        "remember-note", help="Write a free-form Hermes note into AO2 memory"
    )
    note.add_argument("--kind", required=True)
    note.add_argument("--title", required=True)
    note.add_argument("--body", required=True)
    note.add_argument("--tag", dest="tags", action="append", default=[])
    note.add_argument("--source-run-id")
    note.add_argument("--source-path")
    note.add_argument("--ao2-bin", default="ao2")
    note.add_argument("--ao2-target", type=Path, default=Path("."))
    note.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    note.add_argument("--json", action="store_true")
    note.set_defaults(handler=remember_note_command)

    export = subparsers.add_parser(
        "export-memory", help="Export a filtered AO2 memory bundle"
    )
    export.add_argument("--query", required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--limit", type=int, default=50)
    export.add_argument("--signing-key", type=Path)
    export.add_argument("--signer-id", default="hermes-operator")
    export.add_argument("--ao2-bin", default="ao2")
    export.add_argument("--ao2-target", type=Path, default=Path("."))
    export.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    export.add_argument("--json", action="store_true")
    export.set_defaults(handler=export_memory_command)

    publish = subparsers.add_parser(
        "publish-memory", help="Publish an AO2 memory export to ao2-control-plane"
    )
    publish.add_argument("--export", type=Path, required=True)
    publish.add_argument("--control-plane-url", required=True)
    publish.add_argument("--api-token", required=True)
    publish.add_argument("--ao2-bin", default="ao2")
    publish.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish.add_argument("--json", action="store_true")
    publish.set_defaults(handler=publish_memory_command)

    provider_registry = subparsers.add_parser(
        "provider-registry",
        help="Read AO2 provider/plugin registry and live-provider guard metadata",
    )
    provider_registry.add_argument("--ao2-bin", default="ao2")
    provider_registry.add_argument("--ao2-target", type=Path, default=Path("."))
    provider_registry.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    provider_registry.add_argument("--json", action="store_true")
    provider_registry.set_defaults(handler=provider_registry_command)

    publish_provider_registry = subparsers.add_parser(
        "publish-provider-registry",
        help="Publish AO2 provider/plugin registry metadata to ao2-control-plane",
    )
    publish_provider_registry.add_argument("--control-plane-url", required=True)
    publish_provider_registry.add_argument("--api-token", required=True)
    publish_provider_registry.add_argument("--signing-key", type=Path)
    publish_provider_registry.add_argument("--signer-id", default="ao2-provider-registry")
    publish_provider_registry.add_argument("--ao2-bin", default="ao2")
    publish_provider_registry.add_argument("--ao2-target", type=Path, default=Path("."))
    publish_provider_registry.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_provider_registry.add_argument("--json", action="store_true")
    publish_provider_registry.set_defaults(handler=publish_provider_registry_command)

    publish_provider_acceptance = subparsers.add_parser(
        "publish-provider-acceptance",
        help="Publish an AO2 provider-pilot acceptance bundle to ao2-control-plane",
    )
    publish_provider_acceptance.add_argument("--acceptance", type=Path, required=True)
    publish_provider_acceptance.add_argument("--control-plane-url", required=True)
    publish_provider_acceptance.add_argument("--api-token", required=True)
    publish_provider_acceptance.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_provider_acceptance.add_argument("--json", action="store_true")
    publish_provider_acceptance.set_defaults(handler=publish_provider_acceptance_command)

    publish_phase1_checklist = subparsers.add_parser(
        "publish-phase1-checklist",
        help="Publish a ao-operator Phase 1 promotion checklist artifact to ao2-control-plane",
    )
    publish_phase1_checklist.add_argument("--checklist", type=Path, required=True)
    publish_phase1_checklist.add_argument("--control-plane-url", required=True)
    publish_phase1_checklist.add_argument("--api-token", required=True)
    publish_phase1_checklist.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_phase1_checklist.add_argument("--json", action="store_true")
    publish_phase1_checklist.set_defaults(handler=publish_phase1_checklist_command)

    publish_three_os_smoke = subparsers.add_parser(
        "publish-three-os-smoke",
        help="Publish an ao2-control-plane three-OS smoke summary to the read-only observer",
    )
    publish_three_os_smoke.add_argument("--summary", type=Path, required=True)
    publish_three_os_smoke.add_argument("--control-plane-url", required=True)
    publish_three_os_smoke.add_argument("--api-token", required=True)
    publish_three_os_smoke.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_three_os_smoke.add_argument("--json", action="store_true")
    publish_three_os_smoke.set_defaults(handler=publish_three_os_smoke_command)

    publish_watchdog_panel = subparsers.add_parser(
        "publish-watchdog-panel",
        help="Publish a Hermes AO2 watchdog panel to the read-only control-plane observer",
    )
    publish_watchdog_panel.add_argument("--panel", type=Path, required=True)
    publish_watchdog_panel.add_argument("--control-plane-url", required=True)
    publish_watchdog_panel.add_argument("--api-token", required=True)
    publish_watchdog_panel.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_watchdog_panel.add_argument("--json", action="store_true")
    publish_watchdog_panel.set_defaults(handler=publish_watchdog_panel_command)

    publish_release_publication = subparsers.add_parser(
        "publish-release-publication",
        help="Publish AO2 release-publication evidence to the read-only control-plane observer",
    )
    publish_release_publication.add_argument("--publication", type=Path, required=True)
    publish_release_publication.add_argument("--control-plane-url", required=True)
    publish_release_publication.add_argument("--api-token", required=True)
    publish_release_publication.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    publish_release_publication.add_argument("--json", action="store_true")
    publish_release_publication.set_defaults(handler=publish_release_publication_command)

    phase1_promotion_status = subparsers.add_parser(
        "phase1-promotion-status",
        help="Read AO2 Phase 1 promotion history for Hermes/front-end operator status",
    )
    phase1_promotion_status.add_argument("--control-plane-url", required=True)
    phase1_promotion_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    phase1_promotion_status.add_argument("--ao2-bin", default="ao2")
    phase1_promotion_status.add_argument("--ao2-target", type=Path, default=Path("."))
    phase1_promotion_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    phase1_promotion_status.add_argument("--json", action="store_true")
    phase1_promotion_status.set_defaults(handler=phase1_promotion_status_command)

    release_cockpit_status = subparsers.add_parser(
        "release-cockpit-status",
        help="Read the ao2-control-plane release cockpit JSON as Hermes front-end status",
    )
    release_cockpit_status.add_argument("--control-plane-url", required=True)
    release_cockpit_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    release_cockpit_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    release_cockpit_status.add_argument("--json", action="store_true")
    release_cockpit_status.set_defaults(handler=release_cockpit_status_command)

    release_handoff_status = subparsers.add_parser(
        "release-handoff-status",
        help="Read the ao2-control-plane release-candidate handoff JSON as Hermes front-end status",
    )
    release_handoff_status.add_argument("--control-plane-url", required=True)
    release_handoff_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    release_handoff_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    release_handoff_status.add_argument("--json", action="store_true")
    release_handoff_status.set_defaults(handler=release_handoff_status_command)

    route_index_status = subparsers.add_parser(
        "route-index-status",
        help="Read the ao2-control-plane route index as Hermes/front-end discovery status",
    )
    route_index_status.add_argument("--control-plane-url", required=True)
    route_index_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    route_index_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    route_index_status.add_argument("--json", action="store_true")
    route_index_status.set_defaults(handler=route_index_status_command)

    release_readiness_status = subparsers.add_parser(
        "release-readiness-status",
        help="Read the ao2-control-plane release-readiness JSON as Hermes front-end status",
    )
    release_readiness_status.add_argument("--control-plane-url", required=True)
    release_readiness_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    release_readiness_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    release_readiness_status.add_argument("--json", action="store_true")
    release_readiness_status.set_defaults(handler=release_readiness_status_command)

    release_support_bundle_status = subparsers.add_parser(
        "release-support-bundle-status",
        help="Read the ao2-control-plane release support bundle as Hermes front-end status",
    )
    release_support_bundle_status.add_argument("--control-plane-url", required=True)
    release_support_bundle_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    release_support_bundle_status.add_argument("--keep-latest", type=int, default=25)
    release_support_bundle_status.add_argument(
        "--factory-root",
        type=Path,
        default=factory_run.ROOT,
    )
    release_support_bundle_status.add_argument("--json", action="store_true")
    release_support_bundle_status.set_defaults(handler=release_support_bundle_status_command)

    release_evaluator_decision_status = subparsers.add_parser(
        "release-evaluator-decision-status",
        help="Read the ao2-control-plane evaluator decision dashboard as Hermes front-end status",
    )
    release_evaluator_decision_status.add_argument("--control-plane-url", required=True)
    release_evaluator_decision_status.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    release_evaluator_decision_status.add_argument(
        "--factory-root",
        type=Path,
        default=factory_run.ROOT,
    )
    release_evaluator_decision_status.add_argument("--json", action="store_true")
    release_evaluator_decision_status.set_defaults(
        handler=release_evaluator_decision_status_command
    )

    audit_log_stream = subparsers.add_parser(
        "audit-log-stream",
        help=(
            "Subscribe to the ao2-control-plane /api/v1/audit-log/stream SSE "
            "tail and return a bounded bridge-status snapshot. Bounded by "
            "--max-events and --max-seconds for nightly + interactive use."
        ),
    )
    audit_log_stream.add_argument("--control-plane-url", required=True)
    audit_log_stream.add_argument("--api-token-env", default="AO2_CP_API_TOKEN")
    audit_log_stream.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Stop after N audit-log events (0 = unbounded by event count).",
    )
    audit_log_stream.add_argument(
        "--max-seconds",
        type=int,
        default=10,
        help="Stop after N wall-clock seconds. Default 10s.",
    )
    audit_log_stream.add_argument(
        "--connect-timeout-seconds",
        type=int,
        default=10,
        help="Socket connect timeout for the initial subscription.",
    )
    audit_log_stream.add_argument(
        "--read-timeout-seconds",
        type=int,
        default=2,
        help=(
            "Per-readline socket timeout. Short timeouts let the consumer "
            "check --max-seconds even on quiet streams."
        ),
    )
    audit_log_stream.add_argument(
        "--last-event-id",
        type=int,
        default=None,
        help="Resume cursor (timestamp_unix_micros). Replays entries > this id.",
    )
    audit_log_stream.add_argument("--filter-method", default=None)
    audit_log_stream.add_argument("--filter-status", default=None)
    audit_log_stream.add_argument("--filter-status-class", default=None)
    audit_log_stream.add_argument("--filter-path-prefix", default=None)
    audit_log_stream.add_argument(
        "--filter-authenticated",
        dest="filter_authenticated",
        action="store_true",
        default=None,
        help="Pass authenticated=true to the SSE filter.",
    )
    audit_log_stream.add_argument(
        "--filter-unauthenticated",
        dest="filter_authenticated",
        action="store_false",
        help="Pass authenticated=false to the SSE filter.",
    )
    audit_log_stream.add_argument(
        "--tail-sample",
        type=int,
        default=10,
        help="Include the last N events verbatim in the snapshot (0 disables).",
    )
    audit_log_stream.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Optional path to write the bridge-status snapshot as JSON "
            "(suitable for nightly status artifacts)."
        ),
    )
    audit_log_stream.add_argument("--json", action="store_true")
    audit_log_stream.set_defaults(handler=audit_log_stream_command)

    phase1_promotion_panel = subparsers.add_parser(
        "phase1-promotion-panel",
        help="Render a Hermes/front-end operator panel from Phase 1 promotion status",
    )
    phase1_promotion_panel.add_argument("--status", type=Path, required=True)
    phase1_promotion_panel.add_argument("--out-json", type=Path, required=True)
    phase1_promotion_panel.add_argument("--out-markdown", type=Path, required=True)
    phase1_promotion_panel.add_argument("--json", action="store_true")
    phase1_promotion_panel.set_defaults(handler=phase1_promotion_panel_command)

    link = subparsers.add_parser("link-run", help="Link an AO2 memory record to a run")
    link.add_argument("--memory-id", required=True)
    link.add_argument("--run-id", required=True)
    link.add_argument("--relationship", default="related")
    link.add_argument("--ao2-bin", default="ao2")
    link.add_argument("--ao2-target", type=Path, default=Path("."))
    link.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    link.add_argument("--json", action="store_true")
    link.set_defaults(handler=link_run_command)

    governed = subparsers.add_parser(
        "governed-run", help="Start a governed AO2 run without bypassing AO2 policy/evidence"
    )
    governed.add_argument("--workflow")
    governed.add_argument("--template")
    governed.add_argument("--ao2-bin", default="ao2")
    governed.add_argument("--ao2-target", type=Path, default=Path("."))
    governed.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    governed.add_argument("--run-id")
    governed.add_argument("--pause-for-approval", action="store_true")
    governed.add_argument("--resume")
    governed.add_argument("--provider")
    governed.add_argument("--provider-prompt")
    governed.add_argument("--provider-prompt-file", type=Path)
    governed.add_argument("--provider-max-budget-usd")
    governed.add_argument("--max-repair-attempts", type=int, default=1)
    governed.add_argument("--dry-run", action="store_true")
    governed.add_argument("--json", action="store_true")
    governed.set_defaults(handler=governed_run_command)

    repair_resume = subparsers.add_parser(
        "repair-resume",
        help="Resume a rejected AO2 run from a source evidence pack without bypassing AO2",
    )
    repair_resume.add_argument("--workflow")
    repair_resume.add_argument("--template")
    repair_resume.add_argument("--evidence-pack", type=Path, required=True)
    repair_resume.add_argument("--ao2-bin", default="ao2")
    repair_resume.add_argument("--ao2-target", type=Path, default=Path("."))
    repair_resume.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    repair_resume.add_argument("--run-id")
    repair_resume.add_argument("--provider")
    repair_resume.add_argument("--provider-prompt")
    repair_resume.add_argument("--provider-prompt-file", type=Path)
    repair_resume.add_argument("--provider-max-budget-usd")
    repair_resume.add_argument("--max-repair-attempts", type=int, default=1)
    repair_resume.add_argument("--dry-run", action="store_true")
    repair_resume.add_argument("--json", action="store_true")
    repair_resume.add_argument(
        "--ao2-queue-submit",
        dest="ao2_queue_submit",
        type=Path,
        default=None,
        help=(
            "AO2 queue-submit JSON (ao2.ao-operator-compat-workbench-queue-submit.v1) "
            "for the run being repaired. When supplied, the bridge attaches a "
            "ao-operator/ao2-queue-failure-recovery-ownership/v1 claim."
        ),
    )
    repair_resume.add_argument(
        "--ao2-queue-transition",
        dest="ao2_queue_transitions",
        type=Path,
        action="append",
        default=[],
        help=(
            "AO2 queue-transition JSON (ao2.ao-operator-compat-workbench-queue-transition.v1); "
            "repeatable. Required when --ao2-queue-submit is supplied."
        ),
    )
    repair_resume.add_argument(
        "--ao2-queue-ownership-out",
        dest="ao2_queue_ownership_out",
        type=Path,
        default=None,
        help=(
            "Optional path to write the AO2 queue ownership claim "
            "(ao-operator/ao2-queue-failure-recovery-ownership/v1)."
        ),
    )
    repair_resume.add_argument(
        "--require-ao2-queue-ownership",
        dest="require_ao2_queue_ownership",
        action="store_true",
        help=(
            "Refuse to run repair-resume unless AO2 queue ownership evidence is "
            "supplied; prevents ao-operator from retaining failure-recovery ownership."
        ),
    )
    repair_resume.set_defaults(handler=repair_resume_command)

    repair_resume_latest = subparsers.add_parser(
        "repair-resume-latest",
        help="Find the latest non-accepted AO2 evidence pack and resume repair through AO2",
    )
    repair_resume_latest.add_argument("--workflow")
    repair_resume_latest.add_argument("--template")
    repair_resume_latest.add_argument("--ao2-bin", default="ao2")
    repair_resume_latest.add_argument("--ao2-target", type=Path, default=Path("."))
    repair_resume_latest.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    repair_resume_latest.add_argument("--run-id")
    repair_resume_latest.add_argument("--provider")
    repair_resume_latest.add_argument("--provider-prompt")
    repair_resume_latest.add_argument("--provider-prompt-file", type=Path)
    repair_resume_latest.add_argument("--provider-max-budget-usd")
    repair_resume_latest.add_argument("--max-repair-attempts", type=int, default=1)
    repair_resume_latest.add_argument("--dry-run", action="store_true")
    repair_resume_latest.add_argument("--json", action="store_true")
    repair_resume_latest.add_argument(
        "--ao2-queue-submit",
        dest="ao2_queue_submit",
        type=Path,
        default=None,
        help=(
            "AO2 queue-submit JSON for the latest non-accepted run; forwarded to "
            "the underlying repair-resume call."
        ),
    )
    repair_resume_latest.add_argument(
        "--ao2-queue-transition",
        dest="ao2_queue_transitions",
        type=Path,
        action="append",
        default=[],
        help="AO2 queue-transition JSON; repeatable. Forwarded to repair-resume.",
    )
    repair_resume_latest.add_argument(
        "--ao2-queue-ownership-out",
        dest="ao2_queue_ownership_out",
        type=Path,
        default=None,
        help="Optional path to write the AO2 queue ownership claim.",
    )
    repair_resume_latest.add_argument(
        "--require-ao2-queue-ownership",
        dest="require_ao2_queue_ownership",
        action="store_true",
        help=(
            "Refuse to run repair-resume-latest unless AO2 queue ownership "
            "evidence is supplied."
        ),
    )
    repair_resume_latest.set_defaults(handler=repair_resume_latest_command)

    watch = subparsers.add_parser(
        "watch-run", help="Read AO2 run status and evidence metadata"
    )
    watch.add_argument("--run-id", required=True)
    watch.add_argument("--ao2-bin", default="ao2")
    watch.add_argument("--ao2-target", type=Path, default=Path("."))
    watch.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    watch.add_argument("--json", action="store_true")
    watch.set_defaults(handler=watch_run_command)

    git_status = subparsers.add_parser(
        "git-status", help="Read AO2-owned git status evidence"
    )
    git_status.add_argument("--ao2-bin", default="ao2")
    git_status.add_argument("--ao2-target", type=Path, default=Path("."))
    git_status.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    git_status.add_argument("--json", action="store_true")
    git_status.set_defaults(handler=git_status_command)

    git_diff = subparsers.add_parser(
        "git-diff", help="Read AO2-owned git diff evidence"
    )
    git_diff.add_argument("--stat", action="store_true")
    git_diff.add_argument("--ao2-bin", default="ao2")
    git_diff.add_argument("--ao2-target", type=Path, default=Path("."))
    git_diff.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    git_diff.add_argument("--json", action="store_true")
    git_diff.set_defaults(handler=git_diff_command)

    git_commit = subparsers.add_parser(
        "git-commit", help="Route AO2-owned exact-digest git commit"
    )
    git_commit.add_argument("--message", required=True)
    git_commit.add_argument("--path", dest="paths", action="append", default=[])
    git_commit.add_argument("--approve-action-digest")
    git_commit.add_argument("--approver", default="human:hermes-operator")
    git_commit.add_argument("--ao2-bin", default="ao2")
    git_commit.add_argument("--ao2-target", type=Path, default=Path("."))
    git_commit.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    git_commit.add_argument("--json", action="store_true")
    git_commit.set_defaults(handler=git_commit_command)

    git_tag = subparsers.add_parser(
        "git-tag", help="Route AO2-owned exact-digest git tag"
    )
    git_tag.add_argument("--tag", required=True)
    git_tag.add_argument("--message")
    git_tag.add_argument("--approve-action-digest")
    git_tag.add_argument("--approver", default="human:hermes-operator")
    git_tag.add_argument("--ao2-bin", default="ao2")
    git_tag.add_argument("--ao2-target", type=Path, default=Path("."))
    git_tag.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    git_tag.add_argument("--json", action="store_true")
    git_tag.set_defaults(handler=git_tag_command)

    contract_gate = subparsers.add_parser(
        "contract-gate", help="Run an AO2 obligation lifecycle gate"
    )
    contract_gate.add_argument("--ledger", type=Path, required=True)
    contract_gate.add_argument("--stage", required=True)
    contract_gate.add_argument("--out", type=Path, required=True)
    contract_gate.add_argument("--ao2-bin", default="ao2")
    contract_gate.add_argument("--ao2-target", type=Path, default=Path("."))
    contract_gate.add_argument("--factory-root", type=Path, default=factory_run.ROOT)
    contract_gate.add_argument("--json", action="store_true")
    contract_gate.add_argument(
        "--support-signing-key",
        type=Path,
        default=None,
        help=(
            "Path to an RSA PKCS#8 PEM private key. When supplied, threaded "
            "through to `ao2 contract gate --support-signing-key`, which "
            "emits an `ao2.workbench-evidence-export.v1` wrapper + .json.sig "
            "+ workbench-evidence-signing-public.pem sidecars alongside the "
            "raw gate so downstream `ao2 contract verify-obligation-gate-"
            "signing` reports `signed-and-verified`. Default off preserves "
            "the unsigned legacy path."
        ),
    )
    contract_gate.add_argument(
        "--support-signer-id",
        default=None,
        help="Passthrough for `ao2 contract gate --support-signer-id`.",
    )
    contract_gate.add_argument(
        "--support-operator-role",
        default=None,
        help="Passthrough for `ao2 contract gate --support-operator-role`.",
    )
    contract_gate.add_argument(
        "--support-run-id",
        default=None,
        help="Passthrough for `ao2 contract gate --support-run-id`.",
    )
    contract_gate.add_argument(
        "--exports-dir",
        type=Path,
        default=None,
        help="Passthrough for `ao2 contract gate --exports-dir`.",
    )
    contract_gate.set_defaults(handler=contract_gate_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except Exception as exc:
        print(f"hermes_ao_bridge.py: {exc}", file=sys.stderr)
        return 1
    return print_result(payload, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
