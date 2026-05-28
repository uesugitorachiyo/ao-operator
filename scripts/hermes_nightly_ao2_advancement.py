#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = "ao-operator/hermes-nightly-ao2-advancement/v1"
GAP_BACKLOG_SCHEMA = "ao-operator/hermes-nightly-gap-backlog/v1"
NOTIFICATION_SCHEMA = "ao-operator/hermes-nightly-notification/v1"
FAILURE_HISTORY_SCHEMA = "ao-operator/hermes-nightly-failure-history/v1"
REPAIR_HANDOFF_SCHEMA = "ao-operator/hermes-nightly-repair-handoff/v1"
PROVIDER_PHASE1_READINESS_SCHEMA = "ao-operator/hermes-provider-phase1-readiness/v1"
GAP_PATTERNS = ("TODO", "FIXME", "skip", "openssl")
SKIP_DIRS = {
    ".ao2",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "tmp",
    "vendor",
}
SKIP_PATH_FRAGMENTS = {
    ("docs", "status"),
}
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".cmd",
    ".js",
    ".json",
    ".lock",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}
SECRET_OUTPUT_PATTERNS = (
    (re.compile(r"(?i)\bAO2_CP_API_TOKEN=[^\s]+"), "AO2_CP_API_TOKEN:<redacted>"),
    (re.compile(r"(?i)\b(api_token=)[^\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(token=)[^&\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(Authorization:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
)


def command_step(
    step_id: str,
    title: str,
    cwd: Path,
    command: list[str],
    env: dict[str, str] | None = None,
    env_remove: list[str] | None = None,
) -> dict[str, Any]:
    step = {
        "id": step_id,
        "title": title,
        "cwd": str(cwd),
        "command": command,
        "env": env or {},
        "status": "planned",
    }
    if env_remove:
        step["env_remove"] = env_remove
    return step


def ao2_release_bin(args: argparse.Namespace) -> Path:
    return args.ao2_root / "target" / "release" / ("ao2.exe" if os.name == "nt" else "ao2")


def nightly_obligation_ledger_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "nightly-obligation-ledger.json"


def nightly_obligation_gate_path(args: argparse.Namespace, stage: str) -> Path:
    return args.out_dir / f"{stage}-obligation-gate.json"


def nightly_release_summary_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "three-os-smoke-summary.json"


def nightly_provider_registry_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "ao2-provider-registry.json"


def nightly_provider_registry_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "ao2-provider-registry-publish.json"


def nightly_control_plane_release_smoke_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "control-plane-release-smoke.json"


def nightly_provider_phase1_readiness_dir(args: argparse.Namespace) -> Path:
    return args.out_dir / "provider-phase1-readiness"


def nightly_provider_phase1_readiness_path(args: argparse.Namespace) -> Path:
    return nightly_provider_phase1_readiness_dir(args) / "summary.json"


def nightly_provider_phase1_readiness_markdown_path(args: argparse.Namespace) -> Path:
    return nightly_provider_phase1_readiness_dir(args) / "summary.md"


def nightly_provider_phase1_readiness_publish_path(args: argparse.Namespace) -> Path:
    return nightly_provider_phase1_readiness_dir(args) / "publish.json"


def nightly_provider_acceptance_publish_path(args: argparse.Namespace) -> Path:
    return nightly_provider_phase1_readiness_dir(args) / "acceptance-publish.json"


def nightly_provider_acceptance_preservation_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "provider-acceptance-preservation.json"


def provider_acceptance_preservation_root(args: argparse.Namespace) -> Path:
    root_value = getattr(args, "provider_acceptance_root", None)
    if root_value is not None:
        return Path(root_value)
    return Path(getattr(args, "ao2_root", Path("."))) / "target" / "provider-pilot-acceptance"


def provider_phase1_observer_links(args: argparse.Namespace) -> dict[str, str]:
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    if not base_url:
        return {}
    readiness_base = f"{base_url}/api/v1/provider/readiness"
    return {
        "list": readiness_base,
        "latest": f"{readiness_base}/latest",
        "dashboard": f"{readiness_base}/dashboard",
        "dashboard_json": f"{readiness_base}/dashboard.json",
    }


def provider_registry_observer_links(args: argparse.Namespace) -> dict[str, str]:
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    if not base_url:
        return {}
    registry_base = f"{base_url}/api/v1/provider/registry"
    return {
        "list": registry_base,
        "latest": f"{registry_base}/latest",
        "dashboard": f"{registry_base}/dashboard",
        "dashboard_json": f"{registry_base}/dashboard.json",
        "acceptance_dashboard": f"{base_url}/api/v1/acceptance/dashboard",
        "phase1_operator_panel": f"{base_url}/api/v1/phase1/promotion/operator-panel",
        "phase1_operator_panel_json": f"{base_url}/api/v1/phase1/promotion/operator-panel.json",
    }


def provider_acceptance_observer_links(args: argparse.Namespace) -> dict[str, str]:
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    if not base_url:
        return {}
    acceptance_base = f"{base_url}/api/v1/acceptance"
    return {
        "list": acceptance_base,
        "dashboard": f"{acceptance_base}/dashboard",
        "dashboard_json": f"{acceptance_base}/dashboard.json",
    }


def phase1_promotion_observer_links(args: argparse.Namespace) -> dict[str, str]:
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    if not base_url:
        return {}
    promotion_base = f"{base_url}/api/v1/phase1/promotion"
    return {
        "checklist": f"{promotion_base}/checklist",
        "three_os_smoke": f"{promotion_base}/three-os-smoke",
        "latest_three_os_smoke": f"{promotion_base}/three-os-smoke/latest",
        "latest_checklist": f"{promotion_base}/checklist/latest",
        "latest_decision": f"{promotion_base}/decision/latest",
        "dashboard": f"{promotion_base}/dashboard",
        "dashboard_json": f"{promotion_base}/dashboard.json",
        "operator_panel": f"{promotion_base}/operator-panel",
        "operator_panel_json": f"{promotion_base}/operator-panel.json",
        "history_json": f"{promotion_base}/history.json",
    }


def release_publication_observer_links(args: argparse.Namespace) -> dict[str, str]:
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    if not base_url:
        return {}
    publication_base = f"{base_url}/api/v1/release/publication"
    evaluator_decision_base = f"{base_url}/api/v1/release/evaluator-decision"
    return {
        "publication": publication_base,
        "latest": f"{publication_base}/latest",
        "dashboard": f"{publication_base}/dashboard",
        "dashboard_json": f"{publication_base}/dashboard.json",
        "evaluator_decision": evaluator_decision_base,
        "evaluator_decision_latest": f"{evaluator_decision_base}/latest",
        "evaluator_decision_dashboard": f"{evaluator_decision_base}/dashboard",
        "evaluator_decision_dashboard_json": f"{evaluator_decision_base}/dashboard.json",
        "cockpit": f"{base_url}/api/v1/release/cockpit",
        "cockpit_json": f"{base_url}/api/v1/release/cockpit.json",
        "handoff": f"{base_url}/api/v1/release/handoff",
        "handoff_json": f"{base_url}/api/v1/release/handoff.json",
        "readiness": f"{base_url}/api/v1/release/readiness",
        "readiness_json": f"{base_url}/api/v1/release/readiness.json",
        "support_bundle_json": f"{base_url}/api/v1/release/support-bundle.json?keep_latest=25",
    }


def provider_acceptance_bundle_candidates(args: argparse.Namespace) -> tuple[list[Path], str]:
    explicit = list(getattr(args, "provider_acceptance_bundle", []) or [])
    if explicit:
        return [Path(path) for path in explicit], "explicit"
    root_value = getattr(args, "provider_acceptance_root", None)
    if root_value is None:
        root_value = getattr(args, "ao2_root", Path(".")) / "target" / "provider-pilot-acceptance"
    root = Path(root_value)
    if not root.is_dir():
        return [], "auto_discovered"
    release_candidates, _release_source = release_publication_artifact_candidates(args)
    expected_release_version = ""
    if release_candidates:
        release_payload = load_json_artifact(release_candidates[0])
        expected_release_version = str(release_payload.get("version") or "")
    latest_by_provider: dict[str, tuple[int, str, Path]] = {}
    for candidate in root.rglob("provider-pilot-acceptance.json"):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema = str(payload.get("schema_version") or "")
        provider = str(payload.get("provider") or "")
        if schema not in {
            "ao2.codex-provider-pilot-acceptance.v1",
            "ao2.claude-provider-pilot-acceptance.v1",
        }:
            continue
        if (schema.startswith("ao2.codex-") and provider != "codex") or (
            schema.startswith("ao2.claude-") and provider != "claude"
        ):
            continue
        if payload.get("status") != "passed":
            continue
        if expected_release_version and str(payload.get("release_candidate_version") or "") != expected_release_version:
            continue
        try:
            modified = candidate.stat().st_mtime_ns
        except OSError:
            continue
        current = latest_by_provider.get(provider)
        replacement = (modified, str(candidate), candidate)
        if current is None or replacement > current:
            latest_by_provider[provider] = replacement
    ordered = []
    for provider in ("codex", "claude"):
        if provider in latest_by_provider:
            ordered.append(latest_by_provider[provider][2])
    return ordered, "auto_discovered"


def provider_acceptance_bundle_source_class(path: Path, args: argparse.Namespace) -> str:
    normalized = path.as_posix()
    if "tests/fixtures/" in normalized or "discovered-acceptance-root/" in normalized:
        return "fixture"
    ao2_root = Path(getattr(args, "ao2_root", Path(".")))
    live_root = ao2_root / "target" / "provider-pilot-acceptance"
    try:
        path.resolve(strict=False).relative_to(live_root.resolve(strict=False))
        return "live"
    except ValueError:
        pass
    if "/target/provider-pilot-acceptance/" in normalized:
        return "live"
    return "external"


def provider_acceptance_bundle_source_classes(
    bundles: list[Path],
    args: argparse.Namespace,
) -> list[dict[str, str]]:
    return [
        {
            "acceptance_bundle": str(path),
            "source_class": provider_acceptance_bundle_source_class(path, args),
        }
        for path in bundles
    ]


def fetch_provider_phase1_observer_dashboard(args: argparse.Namespace, token: str) -> dict[str, Any]:
    links = provider_phase1_observer_links(args)
    dashboard_json_url = links.get("dashboard_json", "")
    if not dashboard_json_url:
        return {"status": "skipped", "reason": "missing provider readiness dashboard URL"}
    request = urllib.request.Request(
        dashboard_json_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "status_code": int(exc.code),
            "response": redact_nightly_log_output(exc.read().decode("utf-8", errors="replace")),
        }
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc.reason)}
    try:
        snapshot = json.loads(body)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "status_code": status_code,
            "error": "provider readiness dashboard JSON response was not valid JSON",
            "response": redact_nightly_log_output(body),
        }
    return {
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "snapshot": snapshot,
    }


def fetch_provider_acceptance_observer_dashboard(args: argparse.Namespace, token: str) -> dict[str, Any]:
    links = provider_acceptance_observer_links(args)
    dashboard_json_url = links.get("dashboard_json", "")
    if not dashboard_json_url:
        return {"status": "skipped", "reason": "missing provider acceptance dashboard URL"}
    request = urllib.request.Request(
        dashboard_json_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "status_code": int(exc.code),
            "response": redact_nightly_log_output(exc.read().decode("utf-8", errors="replace")),
        }
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc.reason)}
    try:
        snapshot = json.loads(body)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "status_code": status_code,
            "error": "provider acceptance dashboard JSON response was not valid JSON",
            "response": redact_nightly_log_output(body),
        }
    return {
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "snapshot": snapshot,
    }


def fetch_phase1_promotion_observer_dashboard(args: argparse.Namespace, token: str) -> dict[str, Any]:
    links = phase1_promotion_observer_links(args)
    dashboard_json_url = links.get("dashboard_json", "")
    if not dashboard_json_url:
        return {"status": "skipped", "reason": "missing Phase 1 promotion dashboard URL"}
    request = urllib.request.Request(
        dashboard_json_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "status_code": int(exc.code),
            "response": redact_nightly_log_output(exc.read().decode("utf-8", errors="replace")),
        }
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc.reason)}
    try:
        snapshot = json.loads(body)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "status_code": status_code,
            "error": "Phase 1 promotion dashboard JSON response was not valid JSON",
            "response": redact_nightly_log_output(body),
        }
    return {
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "snapshot": snapshot,
    }


def fetch_release_publication_observer_dashboard(args: argparse.Namespace, token: str) -> dict[str, Any]:
    links = release_publication_observer_links(args)
    dashboard_json_url = links.get("dashboard_json", "")
    if not dashboard_json_url:
        return {"status": "skipped", "reason": "missing release publication dashboard URL"}
    request = urllib.request.Request(
        dashboard_json_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "status_code": int(exc.code),
            "response": redact_nightly_log_output(exc.read().decode("utf-8", errors="replace")),
        }
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc.reason)}
    try:
        snapshot = json.loads(body)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "status_code": status_code,
            "error": "release publication dashboard JSON response was not valid JSON",
            "response": redact_nightly_log_output(body),
        }
    return {
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "snapshot": snapshot,
    }


def fetch_release_evaluator_decision_observer_dashboard(
    args: argparse.Namespace,
    token: str,
) -> dict[str, Any]:
    links = release_publication_observer_links(args)
    dashboard_json_url = links.get("evaluator_decision_dashboard_json", "")
    if not dashboard_json_url:
        return {"status": "skipped", "reason": "missing release evaluator decision dashboard URL"}
    request = urllib.request.Request(
        dashboard_json_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "status_code": int(exc.code),
            "response": redact_nightly_log_output(exc.read().decode("utf-8", errors="replace")),
        }
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc.reason)}
    try:
        snapshot = json.loads(body)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "status_code": status_code,
            "error": "release evaluator decision dashboard JSON response was not valid JSON",
            "response": redact_nightly_log_output(body),
        }
    return {
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "snapshot": snapshot,
    }


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def control_plane_health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/healthz"


def control_plane_is_healthy(base_url: str) -> bool:
    if not base_url:
        return False
    try:
        with urllib.request.urlopen(control_plane_health_url(base_url), timeout=1) as response:
            return int(response.status) == 200
    except (OSError, urllib.error.URLError):
        return False


@contextlib.contextmanager
def managed_provider_readiness_control_plane(args: argparse.Namespace):
    if args.dry_run or not (
        getattr(args, "require_provider_readiness_publish", False)
        or getattr(args, "require_provider_acceptance_publish", False)
    ):
        metadata = {"status": "not_required"}
        args.provider_readiness_control_plane = metadata
        yield metadata
        return

    original_url = str(getattr(args, "provider_registry_control_plane_url", ""))
    original_token = os.environ.get("AO2_CP_API_TOKEN")
    if original_token and control_plane_is_healthy(original_url):
        metadata = {
            "status": "external",
            "control_plane_url": original_url,
            "health_url": control_plane_health_url(original_url),
            "token_transport": "existing_environment",
            "token_in_command_args": False,
            "token_exposure_check": "passed",
        }
        args.provider_readiness_control_plane = metadata
        yield metadata
        return

    token = original_token or secrets.token_hex(24)
    original_control_plane_url_env = os.environ.get("AO2_CP_URL")
    port = reserve_local_port()
    url = f"http://127.0.0.1:{port}"
    data_dir = tempfile.TemporaryDirectory(prefix="ao-operator-ao2-cp-")
    process_env = os.environ.copy()
    process_env["AO2_CP_API_TOKEN"] = token
    process_env["AO2_CP_URL"] = url
    command = [
        "cargo",
        "run",
        "-p",
        "ao2-cp-server",
        "--bin",
        "ao2-cp-server",
        "--",
        "--bind",
        f"127.0.0.1:{port}",
        "--data-dir",
        data_dir.name,
    ]
    process = subprocess.Popen(
        command,
        cwd=args.ao2_control_plane,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=process_env,
    )
    os.environ["AO2_CP_API_TOKEN"] = token
    os.environ["AO2_CP_URL"] = url
    args.provider_registry_control_plane_url = url
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"ao2-control-plane exited during startup: {stderr.strip()}")
            if control_plane_is_healthy(url):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("ao2-control-plane did not become healthy within 30s")
        command_contains_token = token in " ".join(str(part) for part in command)
        metadata = {
            "status": "managed",
            "control_plane_url": url,
            "health_url": control_plane_health_url(url),
            "token_transport": "environment",
            "token_in_command_args": command_contains_token,
            "token_exposure_check": "failed" if command_contains_token else "passed",
        }
        args.provider_readiness_control_plane = metadata
        yield metadata
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        data_dir.cleanup()
        args.provider_registry_control_plane_url = original_url
        if original_token is None:
            os.environ.pop("AO2_CP_API_TOKEN", None)
        else:
            os.environ["AO2_CP_API_TOKEN"] = original_token
        if original_control_plane_url_env is None:
            os.environ.pop("AO2_CP_URL", None)
        else:
            os.environ["AO2_CP_URL"] = original_control_plane_url_env


def provider_readiness_publish_gate_check(publish: dict[str, Any]) -> tuple[bool, str]:
    status_code = publish.get("status_code")
    status_code_ok = isinstance(status_code, int) and 200 <= status_code < 300
    if publish.get("status") != "passed" or not status_code_ok:
        detail = publish.get("reason") or publish.get("error") or publish.get("status") or "unknown publish state"
        return False, f"provider readiness publish must pass when required; observed {detail}"
    observer_status_code = publish.get("observer_dashboard_status_code")
    observer_status_code_ok = isinstance(observer_status_code, int) and 200 <= observer_status_code < 300
    if publish.get("observer_dashboard_status") != "passed" or not observer_status_code_ok:
        detail = (
            publish.get("observer_dashboard_reason")
            or publish.get("observer_dashboard_error")
            or publish.get("observer_dashboard_status")
            or "missing observer dashboard snapshot"
        )
        return False, f"provider readiness observer dashboard must pass when required; observed {detail}"
    if not isinstance(publish.get("observer_dashboard_snapshot"), dict):
        return False, "provider readiness observer dashboard snapshot is missing"
    if publish.get("status") == "passed" and status_code_ok:
        return True, "provider readiness publish and observer dashboard passed with 2xx control-plane responses"
    detail = publish.get("reason") or publish.get("error") or publish.get("status") or "unknown publish state"
    return False, f"provider readiness publish must pass when required; observed {detail}"


def provider_acceptance_publish_gate_check(publish: dict[str, Any]) -> tuple[bool, str]:
    published = publish.get("published", [])
    if publish.get("status") != "passed" or not isinstance(published, list) or not published:
        detail = publish.get("reason") or publish.get("error") or publish.get("status") or "unknown publish state"
        return False, f"provider acceptance publish must pass when required; observed {detail}"
    for index, item in enumerate(published):
        if not isinstance(item, dict):
            return False, f"provider acceptance publish item {index} is not an object"
        status_code = item.get("status_code")
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            return False, f"provider acceptance publish item {index} did not return a 2xx control-plane response"
    observer_status_code = publish.get("observer_dashboard_status_code")
    observer_status_code_ok = isinstance(observer_status_code, int) and 200 <= observer_status_code < 300
    if publish.get("observer_dashboard_status") != "passed" or not observer_status_code_ok:
        detail = (
            publish.get("observer_dashboard_reason")
            or publish.get("observer_dashboard_error")
            or publish.get("observer_dashboard_status")
            or "missing observer dashboard snapshot"
        )
        return False, f"provider acceptance observer dashboard must pass when required; observed {detail}"
    snapshot = publish.get("observer_dashboard_snapshot")
    if not isinstance(snapshot, dict):
        return False, "provider acceptance observer dashboard snapshot is missing"
    passed_count = snapshot.get("passed_count")
    if not isinstance(passed_count, int) or passed_count < len(published):
        return False, "provider acceptance observer dashboard must show the published bundles as passed"
    return True, "provider acceptance publish and observer dashboard passed with 2xx control-plane responses"


def provider_acceptance_source_gate_check(
    publish: dict[str, Any],
    required_source: str,
) -> tuple[bool, str]:
    if required_source in {"", "any"}:
        return True, "provider acceptance source may be any verified bundle source"
    published = publish.get("published", [])
    if publish.get("status") != "passed" or not isinstance(published, list) or not published:
        detail = publish.get("reason") or publish.get("error") or publish.get("status") or "unknown publish state"
        return False, f"provider acceptance source requires published evidence; observed {detail}"
    source_classes = []
    for index, item in enumerate(published):
        if not isinstance(item, dict):
            return False, f"provider acceptance source item {index} is not an object"
        source_class = str(item.get("source_class") or "")
        if not source_class:
            return False, f"provider acceptance source item {index} is missing source_class"
        source_classes.append(source_class)
    mismatches = sorted({source for source in source_classes if source != required_source})
    if mismatches:
        return (
            False,
            "provider acceptance source must be "
            f"{required_source}; observed {', '.join(mismatches)}",
        )
    return True, f"provider acceptance source is {required_source}"


def provider_readiness_control_plane_gate_check(control_plane: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(control_plane, dict) or not control_plane:
        return False, "provider readiness control-plane token-safety proof is missing"
    status = control_plane.get("status")
    if status not in {"managed", "external"}:
        return False, f"provider readiness control-plane proof must be managed or external; observed {status or 'missing'}"
    if not str(control_plane.get("control_plane_url", "")).startswith("http://127.0.0.1:"):
        return False, "provider readiness control-plane proof must use a loopback control-plane URL"
    if control_plane.get("token_in_command_args") is not False:
        return False, "provider readiness control-plane proof must not expose the bearer token in process command args"
    if control_plane.get("token_exposure_check") != "passed":
        return False, "provider readiness control-plane token exposure check must pass"
    token_transport = control_plane.get("token_transport")
    if token_transport not in {"environment", "existing_environment"}:
        return False, f"provider readiness control-plane token transport must be environment-only; observed {token_transport or 'missing'}"
    return True, "provider readiness control-plane proof shows loopback observer and environment-only token transport"


def nightly_enriched_release_summary_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "three-os-smoke-summary.enriched.json"


def nightly_malformed_release_summary_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "three-os-smoke-summary.malformed.json"


def nightly_release_gate_dry_run_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-gate-dry-run.json"


def nightly_three_os_smoke_observer_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "three-os-smoke-observer.json"


def nightly_three_os_smoke_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "three-os-smoke-publish.json"


def nightly_phase1_promotion_checklist_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-checklist.json"


def nightly_phase1_promotion_checklist_markdown_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-checklist.md"


def nightly_phase1_promotion_checklist_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-checklist-publish.json"


def nightly_phase1_promotion_decision_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-decision.json"


def nightly_phase1_promotion_decision_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-decision-publish.json"


def nightly_phase1_promotion_history_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-history-fetch.json"


def nightly_phase1_promotion_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-status.json"


def nightly_phase1_promotion_panel_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-panel.json"


def nightly_phase1_promotion_panel_markdown_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "phase1-promotion-panel.md"


def nightly_release_publication_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-publication-publish.json"


def nightly_release_cockpit_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-cockpit-status.json"


def nightly_release_handoff_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-handoff-status.json"


def nightly_release_readiness_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-readiness-status.json"


def nightly_release_support_bundle_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-bundle-status.json"


def nightly_release_support_bundle_post_decision_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-bundle-post-decision-status.json"


def nightly_cancel_authority_dry_run_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "cancel-authority-dry-run.json"


def nightly_release_support_verifier_json_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-bundle-verifier.json"


def nightly_release_support_manifest_json_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-bundle-manifest.json"


def nightly_release_support_verifier_handoff_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-verifier-handoff.json"


def nightly_release_support_verifier_handoff_markdown_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-support-verifier-handoff.md"


def nightly_release_handoff_checklist_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-handoff-checklist.json"


def nightly_release_handoff_checklist_markdown_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-handoff-checklist.md"


def nightly_release_evaluator_decision_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-evaluator-decision.json"


def nightly_release_evaluator_decision_markdown_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-evaluator-decision.md"


def nightly_release_evaluator_decision_publish_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-evaluator-decision-publish.json"


def nightly_release_evaluator_decision_status_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "release-evaluator-decision-status.json"


def nightly_release_ao2_native_evidence_pack_producer_summary_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-ao2-native-evidence-pack-producer.json"


def nightly_release_ao2_native_evidence_pack_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-ao2-native-evidence-pack.json"


# ---------------------------------------------------------------------------
# Phase 2 factory-compat orchestration (plan→queue→run-next→pack-evidence)
# ---------------------------------------------------------------------------

NIGHTLY_FACTORY_COMPAT_RUN_ID = "nightly-factory-compat-run"
NIGHTLY_FACTORY_COMPAT_FIXTURE_REL = ("fixtures", "discount-service")
NIGHTLY_FACTORY_COMPAT_TARGET_REL = ("target", "nightly-factory-compat-target")


def nightly_factory_compat_fixture_path(args: argparse.Namespace) -> Path:
    return args.ao2_root.joinpath(*NIGHTLY_FACTORY_COMPAT_FIXTURE_REL)


def nightly_factory_compat_target_path(args: argparse.Namespace) -> Path:
    # Lives under the AO2 repo's gitignored target/ tree so the populated
    # factory-compat queue + run results never pollute the working copy.
    return args.ao2_root.joinpath(*NIGHTLY_FACTORY_COMPAT_TARGET_REL)


def nightly_factory_compat_workdir_path(args: argparse.Namespace) -> Path:
    return args.ao2_root.joinpath(
        *NIGHTLY_FACTORY_COMPAT_TARGET_REL[:-1],
        "nightly-factory-compat-workdir",
    )


def nightly_factory_compat_evidence_pack_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "factory-compat-nightly-run-evidence-pack.json"


def nightly_factory_compat_nightly_run_summary_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "factory-compat-nightly-run.json"


def nightly_factory_compat_bridge_evidence_path(
    args: argparse.Namespace,
) -> Path:
    """Where the AO Operator -> AO2 bridge evidence lands when wired in.

    Phase 2 exit-gate items #1 (real RunSpec drives bridge) and #2
    (deterministic mapping testable) require the bridge evidence to be
    committable next to the orchestrator summary.
    """
    return args.out_dir / "factory-compat-ao-operator-bridge-evidence.json"


def nightly_factory_compat_hermes_context_path(
    args: argparse.Namespace,
) -> Path:
    """Where the Hermes AO2-refs context payload lands when wired in.

    Phase 2 exit-gate item #3 requires Hermes context to reference AO2-owned
    identifiers (mapping digest, run id, evidence-pack sha256) rather than
    ao-operator-local paths.
    """
    return args.out_dir / "factory-compat-hermes-context-with-ao2-refs.json"


def nightly_factory_compat_cp_ingest_receipt_path(
    args: argparse.Namespace,
) -> Path:
    """Default discovery path for an ao2.cp-ingest-receipt.v1 file.

    Phase 2 exit-gate item #3's ao2-control-plane observer half asks
    Hermes context to reference an ao2-control-plane receipt sha256.
    When an operator runs `ao2 control-plane ingest --out <this-path>`
    out-of-band, the nightly step picks it up and pins it into the
    AO2-refs payload automatically.
    """
    return args.out_dir / "factory-compat-cp-ingest-receipt.json"


def nightly_factory_compat_memory_export_path(
    args: argparse.Namespace,
) -> Path:
    """Where ``ao2 memory export`` writes the signed ao2.memory-export.v1.

    Phase 2 exit-gate item #3's ao2-control-plane observer half asks
    Hermes context to reference an ao2-control-plane receipt sha256.
    The memory-publish producer (``ao2_factory_compat_memory_publish.py``)
    chains ``ao2 memory export`` → ``ao2 memory publish``; the
    intermediate export artifact lands here so the receipt that downstream
    auto-discovery consumes can be traced back to the AO2-signed export
    it was produced from.
    """
    return args.out_dir / "factory-compat-memory-export.json"


def nightly_factory_compat_memory_publish_summary_path(
    args: argparse.Namespace,
) -> Path:
    """Where the memory-publish producer writes its status summary JSON."""
    return args.out_dir / "factory-compat-memory-publish.json"


def nightly_factory_compat_memory_record_path(
    args: argparse.Namespace,
) -> Path:
    """Default path the orchestrator writes the AO2 memory record JSON to.

    Phase 2 exit-gate item #3's memory record id half asks Hermes
    context to reference an AO2 memory record id + sha256. The
    orchestrator invokes ``ao2 memory write --json`` after pack-evidence
    and writes the returned record here. The nightly step then pins
    the record id + sha256 into the Hermes AO2-refs payload.
    """
    return args.out_dir / "factory-compat-memory-record.json"


def nightly_factory_compat_ao_operator_runspec_path(
    args: argparse.Namespace,
) -> Path | None:
    """Default AO Operator RunSpec used to drive the nightly bridge.

    Returns the canonical ao-operator smoke RunSpec if it exists on disk,
    otherwise ``None``. The orchestrator step skips bridge wiring when
    no RunSpec is supplied.
    """
    candidate = (
        args.factory_root / "ao" / "runspecs" / "ao-operator-smoke.yaml"
    )
    return candidate if candidate.is_file() else None


def nightly_release_ao2_native_evaluator_producer_summary_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-ao2-native-evaluator-producer.json"


def nightly_release_ao2_native_evaluator_producer_decision_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-ao2-native-evaluator-decision.json"


def nightly_release_ao2_native_evaluator_verification_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-ao2-native-evaluator-verification.json"


def nightly_release_evaluator_closure_with_ao2_verification_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-evaluator-closure-with-ao2-verification.json"


def nightly_release_evaluator_closure_with_ao2_verification_markdown_path(
    args: argparse.Namespace,
) -> Path:
    return args.out_dir / "release-evaluator-closure-with-ao2-verification.md"


def nightly_failure_history_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "nightly-failure-history.json"


def nightly_repair_handoff_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "nightly-repair-handoff.md"


def nightly_repair_handoff_json_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "nightly-repair-handoff.json"


def nightly_repair_prompt_path(args: argparse.Namespace) -> Path:
    return args.out_dir / "nightly-repair-prompt.md"


def git_revision_label(root: Path) -> str:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        ).stdout
        dirty_hash = hashlib.sha256(status.encode("utf-8")).hexdigest()[:12] if status else "clean"
        return f"{head}:{dirty_hash}"
    except (OSError, subprocess.CalledProcessError):
        return f"nogit:{root.resolve()}"


def git_revision_status(root: Path) -> tuple[str, bool]:
    label = git_revision_label(root)
    if label.startswith("nogit:"):
        return label, True
    head, _, dirty_hash = label.partition(":")
    return head, dirty_hash != "clean"


def nightly_revision_fingerprint(args: argparse.Namespace) -> str:
    script_path = Path(__file__).resolve()
    script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()
    parts = {
        "schema": "ao-operator/hermes-nightly-revision-fingerprint/v1",
        "factory": git_revision_label(args.factory_root),
        "ao2": git_revision_label(args.ao2_root),
        "ao2_control_plane": git_revision_label(args.ao2_control_plane),
        "script_sha256": script_sha,
        "require_remotes": bool(getattr(args, "require_remotes", False)),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def read_failure_history(args: argparse.Namespace) -> dict[str, Any]:
    path = nightly_failure_history_path(args)
    if not path.is_file():
        return {"schema": FAILURE_HISTORY_SCHEMA}
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema": FAILURE_HISTORY_SCHEMA, "unreadable_previous_history": str(path)}
    if history.get("schema") != FAILURE_HISTORY_SCHEMA:
        return {"schema": FAILURE_HISTORY_SCHEMA, "ignored_previous_schema": history.get("schema")}
    return history


def write_failure_history(args: argparse.Namespace, history: dict[str, Any]) -> Path:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = nightly_failure_history_path(args)
    history["schema"] = FAILURE_HISTORY_SCHEMA
    history["updated_at_ms"] = int(time.time() * 1000)
    path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def recent_log_excerpt(log_path: str, line_count: int = 40) -> str:
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-line_count:])


def redact_nightly_log_output(output: str) -> str:
    redacted = output
    for pattern, replacement in SECRET_OUTPUT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def sanitize_for_nightly_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lower = str(key).lower()
            if "token" in lower or lower in {"authorization", "api_key", "apikey", "secret"}:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = sanitize_for_nightly_artifact(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_nightly_artifact(item) for item in value]
    if isinstance(value, str):
        return redact_nightly_log_output(value)
    return value


def sanitize_command_for_artifact(command: list[str]) -> list[str]:
    sanitized: list[str] = []
    redact_next = False
    for part in command:
        text = str(part)
        if redact_next:
            sanitized.append("<redacted>")
            redact_next = False
            continue
        sanitized.append(text)
        if text in {"--api-token", "--signing-key"}:
            redact_next = True
    return sanitized


def write_repair_handoff(
    args: argparse.Namespace,
    *,
    failed_step: str,
    consecutive_count: int,
    fingerprint: str,
    steps: list[dict[str, Any]],
) -> dict[str, str]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    step = next((candidate for candidate in steps if candidate.get("id") == failed_step), {})
    handoff = {
        "schema": REPAIR_HANDOFF_SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "failed_step": failed_step,
        "consecutive_count": consecutive_count,
        "fingerprint": fingerprint,
        "step": step,
        "recommendation": "Do not rerun the same cron sequence unchanged. Fix the failed step or change the revision fingerprint, then rerun manually.",
        "manual_rerun": [
            "python3",
            "scripts/hermes_nightly_ao2_advancement.py",
            "--factory-root",
            str(args.factory_root),
            "--ao2-root",
            str(args.ao2_root),
            "--ao2-control-plane",
            str(args.ao2_control_plane),
            "--ao-runtime",
            str(getattr(args, "ao_runtime", args.factory_root.parent / "ao-runtime")),
            "--out-dir",
            str(args.out_dir),
            "--json",
        ],
    }
    if getattr(args, "require_remotes", False):
        handoff["manual_rerun"].append("--require-remotes")
    handoff["manual_rerun"].append("--force-repeat-failure-run")
    json_path = nightly_repair_handoff_json_path(args)
    markdown_path = nightly_repair_handoff_path(args)
    prompt_path = nightly_repair_prompt_path(args)
    json_path.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = " ".join(step.get("command", []))
    log_path = step.get("log", "")
    log_excerpt = recent_log_excerpt(str(log_path))
    markdown = "\n".join(
        [
            "# Hermes Nightly Repair Handoff",
            "",
            f"- failed_step: `{failed_step}`",
            f"- consecutive_count: `{consecutive_count}`",
            f"- fingerprint: `{fingerprint}`",
            f"- cwd: `{step.get('cwd', '')}`",
            f"- command: `{command}`",
            f"- log: `{log_path}`",
            "",
            "Do not rerun the same cron sequence unchanged.",
            "Fix the failed step or change the revision fingerprint, then rerun manually.",
            "",
            "## Recent Log Excerpt",
            "",
            "```text",
            log_excerpt or "No log excerpt available.",
            "```",
            "",
            "## Manual Rerun",
            "",
            "```sh",
            " ".join(handoff["manual_rerun"]),
            "```",
            "",
        ]
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    prompt = "\n".join(
        [
            "You are Hermes TUI working on AO2 nightly repair.",
            "",
            "Goal: fix the repeated Factory/Hermes AO2 nightly failure without weakening AO2 policy gates, release gates, evidence signing, or cross-platform verification.",
            "",
            "Context:",
            f"- failed_step: {failed_step}",
            f"- consecutive_count: {consecutive_count}",
            f"- revision_fingerprint: {fingerprint}",
            f"- factory_root: {args.factory_root}",
            f"- ao2_root: {args.ao2_root}",
            f"- ao2_control_plane_root: {args.ao2_control_plane}",
            f"- cwd: {step.get('cwd', '')}",
            f"- command: {command}",
            f"- log: {log_path}",
            f"- structured_handoff: {json_path}",
            "",
            "Recent log excerpt:",
            "```text",
            log_excerpt or "No log excerpt available.",
            "```",
            "",
            "Instructions:",
            "1. Inspect the failed step log and the structured handoff JSON first.",
            "2. Fix the root cause in the smallest repo and file set that owns the failure.",
            "3. Add or update regression tests that would have caught the repeated failure.",
            "4. Do not skip verification.",
            "5. Rerun the manual command below with --force-repeat-failure-run only after a code or config fix changes the failure condition.",
            "6. Commit and push the fix to the private origin if verification passes.",
            "",
            "Manual rerun command:",
            "",
            "```sh",
            " ".join(handoff["manual_rerun"]),
            "```",
            "",
            "Expected completion evidence:",
            "- failing step passes",
            "- nightly status is passed",
            "- nightly-notification severity is info",
            "- failure history consecutive_count resets to 0",
            "",
        ]
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    return {
        "repair_handoff": str(markdown_path),
        "repair_handoff_json": str(json_path),
        "repair_prompt": str(prompt_path),
    }


def repeat_failure_guard_payload(
    args: argparse.Namespace, steps: list[dict[str, Any]]
) -> dict[str, Any] | None:
    threshold = int(getattr(args, "repeat_failure_threshold", 2))
    if threshold <= 0 or getattr(args, "force_repeat_failure_run", False):
        return None
    fingerprint = nightly_revision_fingerprint(args)
    history = read_failure_history(args)
    current = history.get("current", {})
    if current.get("fingerprint") != fingerprint:
        return None
    failed_step = current.get("failed_step", "")
    consecutive_count = int(current.get("consecutive_count", 0) or 0)
    if not failed_step or consecutive_count < threshold:
        return None
    guarded_steps = []
    for step in steps:
        guarded = dict(step)
        if step.get("id") == failed_step:
            guarded["status"] = "blocked"
            guarded["exit_code"] = 75
        else:
            guarded["status"] = "skipped"
            guarded["exit_code"] = 0
        guarded_steps.append(guarded)
    handoff_artifacts = write_repair_handoff(
        args,
        failed_step=failed_step,
        consecutive_count=consecutive_count,
        fingerprint=fingerprint,
        steps=steps,
    )
    return {
        "schema": SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "status": "blocked",
        "steps": guarded_steps,
        "failures": [failed_step],
        "remotes_required": bool(getattr(args, "require_remotes", False)),
        "repeat_failure_guard": {
            "schema": "ao-operator/hermes-nightly-repeat-failure-guard/v1",
            "status": "blocked",
            "failed_step": failed_step,
            "consecutive_count": consecutive_count,
            "threshold": threshold,
            "fingerprint": fingerprint,
        },
        "artifacts": {
            "failure_history": str(nightly_failure_history_path(args)),
            **handoff_artifacts,
        },
    }


def update_failure_history_from_payload(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    fingerprint = nightly_revision_fingerprint(args)
    history = read_failure_history(args)
    previous = history.get("current", {})
    failures = payload.get("failures", [])
    if payload.get("status") == "passed" or not failures:
        history["current"] = {
            "fingerprint": fingerprint,
            "status": payload.get("status"),
            "failed_step": "",
            "consecutive_count": 0,
        }
        write_failure_history(args, history)
        return {}
    failed_step = str(failures[0])
    if previous.get("fingerprint") == fingerprint and previous.get("failed_step") == failed_step:
        consecutive_count = int(previous.get("consecutive_count", 0) or 0) + 1
    else:
        consecutive_count = 1
    history["current"] = {
        "fingerprint": fingerprint,
        "status": payload.get("status"),
        "failed_step": failed_step,
        "consecutive_count": consecutive_count,
        "last_generated_at_ms": payload.get("generated_at_ms"),
    }
    write_failure_history(args, history)
    artifacts = {"failure_history": str(nightly_failure_history_path(args))}
    threshold = int(getattr(args, "repeat_failure_threshold", 2))
    if threshold > 0 and consecutive_count >= threshold:
        artifacts.update(
            write_repair_handoff(
                args,
                failed_step=failed_step,
                consecutive_count=consecutive_count,
                fingerprint=fingerprint,
                steps=payload.get("steps", []),
            )
        )
    return artifacts


def obligation_gate_signing_key_candidates(args: argparse.Namespace) -> list[Path]:
    """Ordered fallback chain for the AO2-owned key that signs the nightly
    midpoint/closure obligation gates. Mirrors the pack-evidence and
    provider-registry signing-key chains so operators do not have to
    provision a separate key for this surface. The first existing file
    wins; if none exist, the step runs unsigned (legacy default-off)."""
    return [
        Path(p)
        for p in (
            getattr(args, "obligation_gate_signing_key", None),
            getattr(args, "pack_evidence_signing_key", None),
            getattr(args, "phase1_decision_signing_key", None),
            getattr(args, "provider_registry_signing_key", None),
            args.factory_root / "keys" / "ao2-release-signing-key.pem",
            args.ao2_root / ".release-signing" / "ao2-release-signing-key.pem",
        )
        if p is not None
    ]


def discover_obligation_gate_signing_key(args: argparse.Namespace) -> Path | None:
    if getattr(args, "obligation_gate_disable_signing", False):
        return None
    for candidate in obligation_gate_signing_key_candidates(args):
        if candidate.is_file():
            return candidate
    return None


def contract_gate_step(args: argparse.Namespace, stage: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(args.factory_root / "scripts" / "hermes_ao_bridge.py"),
        "contract-gate",
        "--ledger",
        str(nightly_obligation_ledger_path(args)),
        "--ao2-target",
        str(args.ao2_root),
        "--ao2-bin",
        str(ao2_release_bin(args)),
        "--stage",
        stage,
        "--out",
        str(nightly_obligation_gate_path(args, stage)),
        "--factory-root",
        str(args.factory_root),
        "--json",
    ]
    signing_key = discover_obligation_gate_signing_key(args)
    if signing_key is not None:
        command.extend(["--support-signing-key", str(signing_key)])
        signer_id = (getattr(args, "obligation_gate_signer_id", None) or "").strip()
        if signer_id:
            command.extend(["--support-signer-id", signer_id])
        operator_role = (
            getattr(args, "obligation_gate_operator_role", None) or ""
        ).strip()
        if operator_role:
            command.extend(["--support-operator-role", operator_role])
        run_id = (getattr(args, "obligation_gate_signer_run_id", None) or "").strip()
        if run_id:
            command.extend(["--support-run-id", run_id])
    return command_step(
        f"ao2-{stage}-obligation-gate",
        f"AO2 {stage} obligation lifecycle gate",
        args.factory_root,
        command,
    )


def provider_phase1_readiness_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "provider-phase1-readiness",
        "AO2 Phase 1 provider readiness checkpoint",
        args.factory_root,
        [
            "internal:provider-phase1-readiness",
            str(nightly_provider_phase1_readiness_path(args)),
        ],
    )


def provider_phase1_readiness_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "provider-phase1-readiness-publish",
        "Publish AO2 Phase 1 provider readiness to control plane",
        args.factory_root,
        [
            "internal:provider-phase1-readiness-publish",
            str(nightly_provider_phase1_readiness_publish_path(args)),
        ],
    )


def phase1_promotion_checklist_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "phase1-promotion-checklist-publish",
        "Publish AO2 Phase 1 promotion checklist to control plane",
        args.factory_root,
        [
            "internal:phase1-promotion-checklist-publish",
            str(nightly_phase1_promotion_checklist_publish_path(args)),
        ],
    )


def three_os_smoke_observer_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "three-os-smoke-observer",
        "Materialize control-plane Phase 1 three-OS smoke observer artifact",
        args.factory_root,
        [
            "internal:three-os-smoke-observer",
            str(nightly_three_os_smoke_observer_path(args)),
        ],
    )


def three_os_smoke_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "three-os-smoke-publish",
        "Publish three-OS smoke observer artifact to control plane",
        args.factory_root,
        [
            "internal:three-os-smoke-publish",
            str(nightly_three_os_smoke_publish_path(args)),
        ],
    )


def phase1_promotion_decision_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "phase1-promotion-decision-publish",
        "Publish signed AO2 Phase 1 promotion decision to control plane",
        args.factory_root,
        [
            "internal:phase1-promotion-decision-publish",
            str(nightly_phase1_promotion_decision_publish_path(args)),
        ],
    )


def phase1_promotion_history_fetch_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "phase1-promotion-history-fetch",
        "Fetch AO2 Phase 1 promotion history from control plane",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + str(args.ao2_root / "target" / "release" / "ao2")
                + ' release phase1-history-fetch '
                '--control-plane-url "$CONTROL_PLANE_URL" '
                '--api-token-env AO2_CP_API_TOKEN '
                '--out '
                + shlex.quote(str(args.out_dir / "phase1-promotion-history.json"))
                + " --json > "
                + shlex.quote(str(nightly_phase1_promotion_history_path(args)))
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema_version": "ao2.phase1-promotion-history-control-plane-fetch.v1",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for Phase 1 promotion history fetch",
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_phase1_promotion_history_path(args)))
                + "; fi"
            ),
        ],
    )


def phase1_promotion_status_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "phase1-promotion-status",
        "Materialize Hermes front-end Phase 1 promotion operator status",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + shlex.quote(sys.executable)
                + " "
                + shlex.quote(str(args.factory_root / "scripts" / "hermes_ao_bridge.py"))
                + " phase1-promotion-status "
                "--ao2-target "
                + shlex.quote(str(args.ao2_root))
                + " --ao2-bin "
                + shlex.quote(str(args.ao2_root / "target" / "release" / "ao2"))
                + ' --control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--json > "
                + shlex.quote(str(nightly_phase1_promotion_status_path(args)))
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema": "ao-operator/hermes-ao-bridge/v1",
                            "action": "phase1-promotion-status",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for Phase 1 promotion status",
                            "links": phase1_promotion_observer_links(args),
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_phase1_promotion_status_path(args)))
                + "; fi"
            ),
        ],
    )


def phase1_promotion_panel_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "phase1-promotion-panel",
        "Render Hermes front-end Phase 1 promotion operator panel",
        args.factory_root,
        [
            sys.executable,
            str(args.factory_root / "scripts" / "hermes_ao_bridge.py"),
            "phase1-promotion-panel",
            "--status",
            str(nightly_phase1_promotion_status_path(args)),
            "--out-json",
            str(nightly_phase1_promotion_panel_path(args)),
            "--out-markdown",
            str(nightly_phase1_promotion_panel_markdown_path(args)),
            "--json",
        ],
    )


def release_publication_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-publication-publish",
        "Publish AO2 release-publication evidence to control plane",
        args.factory_root,
        [
            "internal:release-publication-publish",
            str(nightly_release_publication_publish_path(args)),
        ],
    )


def release_cockpit_status_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-cockpit-status",
        "Fetch AO2 release cockpit JSON for Hermes front-end status",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + f"{shlex.quote(sys.executable)} "
                + f"{shlex.quote(str(args.factory_root / 'scripts' / 'hermes_ao_bridge.py'))} "
                + "release-cockpit-status "
                + '--control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--json > "
                + f"{shlex.quote(str(nightly_release_cockpit_status_path(args)))}"
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema": "ao-operator/hermes-ao-bridge/v1",
                            "action": "release-cockpit-status",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for release cockpit status",
                            "links": {
                                "cockpit": release_publication_observer_links(args).get("cockpit", ""),
                                "cockpit_json": release_publication_observer_links(args).get("cockpit_json", ""),
                            },
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_release_cockpit_status_path(args)))
                + "; fi"
            ),
        ],
    )


def release_handoff_status_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-handoff-status",
        "Fetch AO2 release-candidate handoff JSON for Hermes front-end status",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + f"{shlex.quote(sys.executable)} "
                + f"{shlex.quote(str(args.factory_root / 'scripts' / 'hermes_ao_bridge.py'))} "
                + "release-handoff-status "
                + '--control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--json > "
                + f"{shlex.quote(str(nightly_release_handoff_status_path(args)))}"
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema": "ao-operator/hermes-ao-bridge/v1",
                            "action": "release-handoff-status",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for release handoff status",
                            "links": {
                                "release_candidate_handoff": release_publication_observer_links(args).get(
                                    "handoff", ""
                                ),
                                "release_candidate_handoff_json": release_publication_observer_links(args).get(
                                    "handoff_json", ""
                                ),
                                "cockpit_json": release_publication_observer_links(args).get("cockpit_json", ""),
                            },
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_release_handoff_status_path(args)))
                + "; fi"
            ),
        ],
    )


def release_handoff_checklist_step(args: argparse.Namespace) -> dict[str, Any]:
    ao2_head, _ = git_revision_status(args.ao2_root)
    factory_head, _ = git_revision_status(args.factory_root)
    control_plane_head, _ = git_revision_status(args.ao2_control_plane)
    return command_step(
        "release-handoff-checklist",
        "Render ao-operator evaluator-closer checklist from AO2 release-candidate handoff",
        args.factory_root,
        [
            sys.executable,
            str(args.factory_root / "scripts" / "ao2_release_handoff_checklist.py"),
            "--handoff",
            str(nightly_release_handoff_status_path(args)),
            "--write-json",
            str(nightly_release_handoff_checklist_path(args)),
            "--write-md",
            str(nightly_release_handoff_checklist_markdown_path(args)),
            "--expected-repo-head",
            f"ao2={ao2_head}",
            "--expected-repo-head",
            f"factory_v3={factory_head}",
            "--expected-repo-head",
            f"ao2_control_plane={control_plane_head}",
            "--allow-skipped",
            "--json",
        ],
    )


def release_evaluator_decision_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-evaluator-decision",
        "Render ao-operator evaluator-closer release-line decision from readiness and handoff evidence",
        args.factory_root,
        [
            sys.executable,
            str(args.factory_root / "scripts" / "ao2_release_evaluator_decision.py"),
            "--readiness",
            str(nightly_release_readiness_status_path(args)),
            "--handoff-checklist",
            str(nightly_release_handoff_checklist_path(args)),
            "--support-bundle-status",
            str(nightly_release_support_bundle_status_path(args)),
            "--write-json",
            str(nightly_release_evaluator_decision_path(args)),
            "--write-md",
            str(nightly_release_evaluator_decision_markdown_path(args)),
            "--json",
        ],
    )


def release_evaluator_decision_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-evaluator-decision-publish",
        "Publish ao-operator evaluator-closer release-line decision to control plane",
        args.factory_root,
        [
            "internal:release-evaluator-decision-publish",
            str(nightly_release_evaluator_decision_publish_path(args)),
        ],
    )


def release_evaluator_decision_status_step(args: argparse.Namespace) -> dict[str, Any]:
    links = release_publication_observer_links(args)
    return command_step(
        "release-evaluator-decision-status",
        "Fetch release evaluator decision dashboard JSON for Hermes front-end status",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + f"{shlex.quote(sys.executable)} "
                + f"{shlex.quote(str(args.factory_root / 'scripts' / 'hermes_ao_bridge.py'))} "
                + "release-evaluator-decision-status "
                + '--control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--json > "
                + f"{shlex.quote(str(nightly_release_evaluator_decision_status_path(args)))}"
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema": "ao-operator/hermes-ao-bridge/v1",
                            "action": "release-evaluator-decision-status",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for release evaluator decision status",
                            "links": {
                                "latest_release_evaluator_decision": links.get(
                                    "evaluator_decision_latest",
                                    "",
                                ),
                                "release_evaluator_decision_dashboard": links.get(
                                    "evaluator_decision_dashboard",
                                    "",
                                ),
                                "release_evaluator_decision_dashboard_json": links.get(
                                    "evaluator_decision_dashboard_json",
                                    "",
                                ),
                            },
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_release_evaluator_decision_status_path(args)))
                + "; fi"
            ),
        ],
    )


def pack_evidence_signing_key_candidates(args: argparse.Namespace) -> list[Path]:
    """Ordered fallback chain for the AO2-owned key that signs the nightly
    pack-evidence output. Mirrors the provider-registry signing-key chain so
    operators do not have to provision a separate key for this slice. The
    first existing file wins; if none exist, the step runs unsigned."""
    return [
        Path(p)
        for p in (
            getattr(args, "pack_evidence_signing_key", None),
            getattr(args, "phase1_decision_signing_key", None),
            getattr(args, "provider_registry_signing_key", None),
            args.factory_root / "keys" / "ao2-release-signing-key.pem",
            args.ao2_root / ".release-signing" / "ao2-release-signing-key.pem",
        )
        if p is not None
    ]


def discover_pack_evidence_signing_key(args: argparse.Namespace) -> Path | None:
    for candidate in pack_evidence_signing_key_candidates(args):
        if candidate.is_file():
            return candidate
    return None


def bridge_evidence_signing_key_candidates(
    args: argparse.Namespace,
) -> list[Path]:
    """Ordered fallback chain for the AO2-owned key that signs the nightly
    factory-compat bridge evidence (Phase 2 exit-gate item #4 — switches the
    orchestrator from the Python-local canonicalizer to
    `ao2 factory bridge --signing-key` and emits the AO2-native
    `ao2.factory-bridge.v1` schema + signed sidecars). Mirrors the
    pack-evidence / obligation-gate / evaluator-decision chains so operators
    do not have to provision a separate key for this surface."""
    return [
        Path(p)
        for p in (
            getattr(args, "bridge_evidence_signing_key", None),
            getattr(args, "evaluator_decision_signing_key", None),
            getattr(args, "obligation_gate_signing_key", None),
            getattr(args, "pack_evidence_signing_key", None),
            getattr(args, "phase1_decision_signing_key", None),
            getattr(args, "provider_registry_signing_key", None),
            args.factory_root / "keys" / "ao2-release-signing-key.pem",
            args.ao2_root / ".release-signing" / "ao2-release-signing-key.pem",
        )
        if p is not None
    ]


def discover_bridge_evidence_signing_key(
    args: argparse.Namespace,
) -> Path | None:
    if getattr(args, "bridge_evidence_disable_signing", False):
        return None
    for candidate in bridge_evidence_signing_key_candidates(args):
        if candidate.is_file():
            return candidate
    return None


def factory_compat_nightly_run_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(
            args.factory_root
            / "scripts"
            / "ao2_factory_compat_nightly_run.py"
        ),
        "--ao2-binary",
        str(ao2_release_bin(args)),
        "--ao2-fixture",
        str(nightly_factory_compat_fixture_path(args)),
        "--target",
        str(nightly_factory_compat_target_path(args)),
        "--workdir",
        str(nightly_factory_compat_workdir_path(args)),
        "--run-id",
        NIGHTLY_FACTORY_COMPAT_RUN_ID,
        "--evidence-pack-out",
        str(nightly_factory_compat_evidence_pack_path(args)),
        "--native-governed-run",
        "--write-json",
        str(nightly_factory_compat_nightly_run_summary_path(args)),
        "--json",
    ]

    # Phase 2 exit-gate items #1, #2, #3: wire the real AO Operator RunSpec
    # through the deterministic bridge and emit Hermes context that
    # references AO2-owned identifiers (mapping digest + evidence-pack
    # sha256 + AO2 run id) instead of ao-operator-local paths. The bridge
    # is opt-out via --factory-compat-disable-ao-operator-bridge for tests
    # that exercise the legacy synthetic-runspec path.
    if not getattr(args, "factory_compat_disable_ao_operator_bridge", False):
        runspec_override = getattr(
            args, "factory_compat_ao_operator_runspec", None
        )
        runspec_default = nightly_factory_compat_ao_operator_runspec_path(args)
        runspec = runspec_override or runspec_default
        if runspec is not None:
            command.extend(
                [
                    "--ao-operator-runspec",
                    str(runspec),
                    "--bridge-evidence-out",
                    str(nightly_factory_compat_bridge_evidence_path(args)),
                    "--hermes-context-out",
                    str(nightly_factory_compat_hermes_context_path(args)),
                    "--hermes-context-slug",
                    NIGHTLY_FACTORY_COMPAT_RUN_ID,
                ]
            )
            # Phase 2 exit-gate item #4 — bridge-evidence AO2-native signing
            # (slice 14): when a key is discoverable, forward it so the
            # orchestrator shells out to `ao2 factory bridge --signing-key`
            # and emits AO2-native `ao2.factory-bridge.v1` schema +
            # signed sidecars. Factory-v3's slice-12 default-on passthrough
            # verifier then accepts the evidence end-to-end without
            # operator intervention.
            discovered_bridge_key = discover_bridge_evidence_signing_key(args)
            if discovered_bridge_key is not None:
                command.extend(
                    [
                        "--bridge-evidence-signing-key",
                        str(discovered_bridge_key),
                        "--bridge-evidence-signer-id",
                        str(
                            getattr(
                                args,
                                "bridge_evidence_signer_id",
                                "ao2-factory-bridge",
                            )
                        ),
                    ]
                )
            # Optional ao2-control-plane ingest receipt; when supplied (via
            # explicit override or a pre-existing receipt file at the
            # nightly default location), pin it into the Hermes AO2-refs
            # payload. Closes the ao2-control-plane observer half of
            # Phase 2 exit-gate item #3 without forcing the nightly to
            # run a networked `ao2 control-plane ingest` itself.
            cp_receipt = getattr(
                args, "factory_compat_control_plane_receipt", None
            )
            if cp_receipt is None:
                cp_default = nightly_factory_compat_cp_ingest_receipt_path(args)
                if cp_default.is_file():
                    cp_receipt = cp_default
            if cp_receipt is not None:
                command.extend(
                    ["--control-plane-receipt", str(cp_receipt)]
                )
            # AO2 memory record id half of Phase 2 exit-gate item #3:
            # invoke `ao2 memory write --json` after pack-evidence and
            # pin the returned record id + sha256 into the Hermes
            # AO2-refs payload. Opt-out via
            # --factory-compat-disable-ao-operator-memory-record so
            # tests that exercise the legacy code path can skip the
            # extra AO2 call.
            if not getattr(
                args,
                "factory_compat_disable_ao_operator_memory_record",
                False,
            ):
                memory_record_override = getattr(
                    args, "factory_compat_memory_record_out", None
                )
                memory_record_out = (
                    memory_record_override
                    or nightly_factory_compat_memory_record_path(args)
                )
                command.extend(
                    ["--memory-record-out", str(memory_record_out)]
                )

            # Phase 2 exit-gate item #3 — strict-mode CP-receipt presence
            # check. Forward the operator-level
            # --factory-compat-require-all-ao2-ref-categories flag so the
            # orchestrator refuses to emit a Hermes context payload that
            # is missing any of bridge_evidence, evidence_pack,
            # memory_record, or cp_receipt. Disabled by default; opt-in
            # once the CP receipt producer (memory-publish step) is wired
            # into the operator's nightly invocation. Only meaningful when
            # the bridge actually fires (runspec resolved), since the
            # strict check applies to the Hermes context payload.
            if getattr(
                args,
                "factory_compat_require_all_ao2_ref_categories",
                False,
            ):
                command.append("--require-all-ao2-ref-categories")

    # Sign the orchestrator's own evidence pack with the same AO2-owned key
    # discovery the producer step uses; this keeps the two pack artifacts
    # byte-stable + signature-consistent so downstream readers can compare.
    if not getattr(args, "pack_evidence_disable_signing", False):
        discovered = discover_pack_evidence_signing_key(args)
        if discovered is not None:
            command.extend(
                [
                    "--signing-key",
                    str(discovered),
                    "--signer-id",
                    str(
                        getattr(
                            args,
                            "pack_evidence_signer_id",
                            "ao2-factory-pack-evidence-signer",
                        )
                    ),
                ]
            )

    return command_step(
        "factory-compat-nightly-run",
        (
            "Drive AO2 factory plan → queue-submit → queue-run-next → "
            "pack-evidence through AO2's native governed-run command "
            "against a fresh fixture copy so the "
            "downstream evidence-pack producer has a populated "
            "factory-compat target (Phase 2 exit-gate items #1, #2, #4, #5)."
        ),
        args.factory_root,
        command,
    )


def factory_compat_memory_publish_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run ao2 memory export → publish to land the cp-ingest receipt.

    Closes the producer half of Phase 2 exit-gate item #3's control-plane
    observer slice. The receipt-pinning consumer (already wired upstream)
    auto-discovers a receipt at the path returned by
    ``nightly_factory_compat_cp_ingest_receipt_path``; this step writes
    it. The step skips with ``status="skipped"`` when the operator has
    not configured ``--factory-compat-memory-publish-control-plane-url``
    or has not exported ``--factory-compat-memory-publish-api-token-env``,
    matching the existing nightly token-gated skip pattern.
    """
    target_override = getattr(
        args, "factory_compat_memory_publish_target", None
    )
    target = target_override or nightly_factory_compat_target_path(args)
    export_override = getattr(
        args, "factory_compat_memory_publish_export_out", None
    )
    export_out = export_override or nightly_factory_compat_memory_export_path(args)
    receipt_out = nightly_factory_compat_cp_ingest_receipt_path(args)
    summary_out = nightly_factory_compat_memory_publish_summary_path(args)

    command = [
        sys.executable,
        str(
            args.factory_root
            / "scripts"
            / "ao2_factory_compat_memory_publish.py"
        ),
        "--ao2-binary",
        str(ao2_release_bin(args)),
        "--target",
        str(target),
        "--export-out",
        str(export_out),
        "--receipt-out",
        str(receipt_out),
        "--signer-id",
        str(
            getattr(
                args,
                "factory_compat_memory_publish_signer_id",
                "ao2-memory",
            )
        ),
        "--api-token-env",
        str(
            getattr(
                args,
                "factory_compat_memory_publish_api_token_env",
                "AO2_CP_API_TOKEN",
            )
        ),
        "--out",
        str(summary_out),
    ]

    cp_url = getattr(args, "factory_compat_memory_publish_control_plane_url", None)
    if cp_url:
        command.extend(["--control-plane-url", str(cp_url)])

    if getattr(args, "factory_compat_memory_publish_allow_unsigned", False):
        command.append("--allow-unsigned-memory-export")
    else:
        signing_override = getattr(
            args, "factory_compat_memory_publish_signing_key", None
        )
        discovered = (
            signing_override
            if signing_override is not None
            else discover_pack_evidence_signing_key(args)
        )
        if discovered is not None:
            command.extend(["--signing-key", str(discovered)])

    return command_step(
        "factory-compat-memory-publish",
        (
            "Run ao2 memory export → publish so an ao2.cp-ingest-receipt.v1 "
            "lands at <out-dir>/factory-compat-cp-ingest-receipt.json for the "
            "Hermes AO2-refs auto-discovery to consume (Phase 2 exit-gate "
            "item #3, ao2-control-plane observer half)."
        ),
        args.factory_root,
        command,
    )


def release_ao2_native_evidence_pack_producer_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(
            args.factory_root
            / "scripts"
            / "ao2_release_ao2_native_evidence_pack_producer.py"
        ),
        "--ao2-binary",
        str(ao2_release_bin(args)),
        "--ao2-target",
        str(nightly_factory_compat_target_path(args)),
        "--run-id",
        NIGHTLY_FACTORY_COMPAT_RUN_ID,
        "--evidence-pack-out",
        str(nightly_release_ao2_native_evidence_pack_path(args)),
        "--write-json",
        str(
            nightly_release_ao2_native_evidence_pack_producer_summary_path(args)
        ),
        "--json",
    ]

    # When an AO2-owned signing key is available locally, exercise the signed
    # release-handoff path (Phase 2 exit-gate items #4 and #5). Factory-v3
    # only passes the discovered path — AO2 owns the key material and the
    # sidecar writes. Operators can override discovery with
    # `--pack-evidence-signing-key`, or disable signing wiring entirely with
    # `--pack-evidence-disable-signing` (used in tests where no key exists).
    if not getattr(args, "pack_evidence_disable_signing", False):
        discovered = discover_pack_evidence_signing_key(args)
        if discovered is not None:
            command.extend(
                [
                    "--signing-key",
                    str(discovered),
                    "--signer-id",
                    str(
                        getattr(
                            args,
                            "pack_evidence_signer_id",
                            "ao2-factory-pack-evidence-signer",
                        )
                    ),
                ]
            )
            if getattr(args, "require_pack_evidence_signed", False):
                command.append("--require-signed-evidence")

    return command_step(
        "release-ao2-native-evidence-pack-producer",
        (
            "Produce AO2 native ao2.evidence-pack.v1 via `ao2 factory "
            "pack-evidence` (Phase 2 closure-owner discipline; emits "
            "status=missing_inputs when no completed AO2 queue entry exists "
            "and feeds the evaluator-decision producer when it does). When "
            "an AO2-owned signing key is discovered, forwards --signing-key "
            "so the bridge surfaces AO2's signature + deterministic_replay "
            "verdict for the release-handoff path."
        ),
        args.factory_root,
        command,
    )


def evaluator_decision_signing_key_candidates(
    args: argparse.Namespace,
) -> list[Path]:
    """Ordered fallback chain for the AO2-owned key that signs the nightly
    AO2-native evaluator decision (Phase 2 exit-gate item #4 — flips
    `ao2_can_sign_native_evaluator_decision` from `false` to `true`).
    Mirrors the pack-evidence / obligation-gate / provider-registry chains
    so operators do not have to provision a separate key for this surface.
    The first existing file wins; if none exist, the step runs unsigned."""
    return [
        Path(p)
        for p in (
            getattr(args, "evaluator_decision_signing_key", None),
            getattr(args, "obligation_gate_signing_key", None),
            getattr(args, "pack_evidence_signing_key", None),
            getattr(args, "phase1_decision_signing_key", None),
            getattr(args, "provider_registry_signing_key", None),
            args.factory_root / "keys" / "ao2-release-signing-key.pem",
            args.ao2_root / ".release-signing" / "ao2-release-signing-key.pem",
        )
        if p is not None
    ]


def discover_evaluator_decision_signing_key(
    args: argparse.Namespace,
) -> Path | None:
    if getattr(args, "evaluator_decision_disable_signing", False):
        return None
    for candidate in evaluator_decision_signing_key_candidates(args):
        if candidate.is_file():
            return candidate
    return None


def release_ao2_native_evaluator_producer_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(
            args.factory_root
            / "scripts"
            / "ao2_release_ao2_native_evaluator_producer.py"
        ),
        "--ao2-binary",
        str(ao2_release_bin(args)),
        "--evidence-pack",
        str(nightly_release_ao2_native_evidence_pack_path(args)),
        "--ao2-decision-out",
        str(nightly_release_ao2_native_evaluator_producer_decision_path(args)),
        "--write-json",
        str(nightly_release_ao2_native_evaluator_producer_summary_path(args)),
        "--json",
    ]

    # When an AO2-owned signing key is discovered, forward it so
    # `ao2 factory evaluate --signing-key` emits a signed AO2 native
    # evaluator decision (Phase 2 exit-gate item #4 parity-checklist:
    # `ao2_can_sign_native_evaluator_decision: true`). Factory-v3 only
    # passes the discovered path — AO2 owns the key material and the
    # sidecar writes. Disable wiring entirely with
    # `--evaluator-decision-disable-signing` (used in tests).
    discovered = discover_evaluator_decision_signing_key(args)
    if discovered is not None:
        command.extend(
            [
                "--signing-key",
                str(discovered),
                "--signer-id",
                str(
                    getattr(
                        args,
                        "evaluator_decision_signer_id",
                        "ao2-native-evaluator-closer",
                    )
                ),
            ]
        )

    return command_step(
        "release-ao2-native-evaluator-producer",
        (
            "Produce AO2 native evaluator decision via `ao2 factory evaluate` "
            "(Phase 2 closure-owner discipline; consumes the AO2 native "
            "evidence pack when produced and short-circuits to "
            "status=missing_inputs when the upstream pack producer reported "
            "missing inputs). When an AO2-owned signing key is discovered, "
            "forwards --signing-key so the decision is AO2-signed natively "
            "(parity checklist: ao2_can_sign_native_evaluator_decision=true)."
        ),
        args.factory_root,
        command,
    )


def release_ao2_native_evaluator_verification_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    return command_step(
        "release-ao2-native-evaluator-verification",
        (
            "Produce AO2 native evaluator-decision verification artifact "
            "(Phase 2 closure-owner discipline; consumes the producer summary "
            "and emits status=missing_inputs when AO2 evidence is not wired)"
        ),
        args.factory_root,
        [
            sys.executable,
            str(
                args.factory_root
                / "scripts"
                / "ao2_release_ao2_native_evaluator_verification.py"
            ),
            "--ao2-binary",
            str(ao2_release_bin(args)),
            "--ao2-producer-summary",
            str(nightly_release_ao2_native_evaluator_producer_summary_path(args)),
            "--write-json",
            str(nightly_release_ao2_native_evaluator_verification_path(args)),
            "--json",
        ],
    )


def release_evaluator_closure_with_ao2_verification_step(
    args: argparse.Namespace,
) -> dict[str, Any]:
    return command_step(
        "release-evaluator-closure-with-ao2-verification",
        (
            "Issue release-evaluator closure consulting AO2 native verifier "
            "verdict (Phase 2 exit-gate item #4)"
        ),
        args.factory_root,
        [
            sys.executable,
            str(
                args.factory_root
                / "scripts"
                / "ao2_release_evaluator_closure_with_ao2_verification.py"
            ),
            "--factory-decision",
            str(nightly_release_evaluator_decision_path(args)),
            "--ao2-verification",
            str(nightly_release_ao2_native_evaluator_verification_path(args)),
            "--write-json",
            str(nightly_release_evaluator_closure_with_ao2_verification_path(args)),
            "--write-md",
            str(
                nightly_release_evaluator_closure_with_ao2_verification_markdown_path(
                    args
                )
            ),
            "--json",
        ],
    )


def release_readiness_status_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "release-readiness-status",
        "Fetch AO2 release-readiness JSON for Hermes front-end status",
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + f"{shlex.quote(sys.executable)} "
                + f"{shlex.quote(str(args.factory_root / 'scripts' / 'hermes_ao_bridge.py'))} "
                + "release-readiness-status "
                + '--control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--json > "
                + f"{shlex.quote(str(nightly_release_readiness_status_path(args)))}"
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(
                        {
                            "schema": "ao-operator/hermes-ao-bridge/v1",
                            "action": "release-readiness-status",
                            "status": "skipped",
                            "reason": "AO2_CP_API_TOKEN is required for release readiness status",
                            "links": {
                                "release_readiness": release_publication_observer_links(args).get(
                                    "readiness", ""
                                ),
                                "release_readiness_json": release_publication_observer_links(args).get(
                                    "readiness_json", ""
                                ),
                                "release_candidate_handoff": release_publication_observer_links(args).get(
                                    "handoff", ""
                                ),
                            },
                        },
                        sort_keys=True,
                    )
                )
                + " > "
                + shlex.quote(str(nightly_release_readiness_status_path(args)))
                + "; fi"
            ),
        ],
    )


def release_support_bundle_status_step(
    args: argparse.Namespace,
    *,
    step_id: str = "release-support-bundle-status",
    title: str = "Fetch AO2 release support bundle assembly JSON for Hermes front-end status",
    output_path: Path | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    target_path = output_path or nightly_release_support_bundle_status_path(args)
    planned_artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-support-bundle-status",
        "status": "planned",
        "reason": "AO2_CP_API_TOKEN is required for release support bundle status",
        "trust_boundary": {"mode": "release_support_bundle_read_only"},
        "links": {
            "release_support_bundle_json": release_publication_observer_links(args).get(
                "support_bundle_json", ""
            ),
            "release_readiness_json": release_publication_observer_links(args).get(
                "readiness_json", ""
            ),
            "release_candidate_handoff_json": release_publication_observer_links(args).get(
                "handoff_json", ""
            ),
        },
        "frontend_status": {
            "status": "planned",
            "release_candidate_version": "unknown",
            "candidate_correlation": "unknown",
            "required_artifact_count": 0,
            "missing_artifact_count": 0,
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "next_action": "fetch release support bundle assembly after observer evidence is published",
        },
    }
    if phase:
        planned_artifact["phase"] = phase
        planned_artifact["frontend_status"][
            "next_action"
        ] = "refresh release support bundle after evaluator decision publication"
    return command_step(
        step_id,
        title,
        args.factory_root,
        [
            "sh",
            "-lc",
            (
                'CONTROL_PLANE_URL="${AO2_CP_URL:-'
                + str(getattr(args, "provider_registry_control_plane_url", "http://127.0.0.1:8744"))
                + '}"; '
                'if [ -n "${AO2_CP_API_TOKEN:-}" ]; then '
                + f"{shlex.quote(sys.executable)} "
                + f"{shlex.quote(str(args.factory_root / 'scripts' / 'hermes_ao_bridge.py'))} "
                + "release-support-bundle-status "
                + '--control-plane-url "$CONTROL_PLANE_URL" '
                "--api-token-env AO2_CP_API_TOKEN "
                "--keep-latest 25 "
                "--json > "
                + f"{shlex.quote(str(target_path))}"
                + (
                    f" && {shlex.quote(sys.executable)} -c "
                    + shlex.quote(
                        "import json, pathlib, sys; "
                        "path = pathlib.Path(sys.argv[1]); "
                        "payload = json.loads(path.read_text(encoding='utf-8')); "
                        f"payload['phase'] = {phase!r}; "
                        "path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')"
                    )
                    + f" {shlex.quote(str(target_path))}"
                    if phase
                    else ""
                )
                + "; else printf '%s\\n' "
                + shlex.quote(
                    json.dumps(planned_artifact, sort_keys=True)
                )
                + " > "
                + shlex.quote(str(target_path))
                + "; fi"
            ),
        ],
    )


def release_support_verifier_handoff_step(args: argparse.Namespace) -> dict[str, Any]:
    verifier_path = nightly_release_support_verifier_json_path(args)
    manifest_path = nightly_release_support_manifest_json_path(args)
    handoff_path = nightly_release_support_verifier_handoff_path(args)
    handoff_md_path = nightly_release_support_verifier_handoff_markdown_path(args)
    planned_payload = planned_release_support_verifier_handoff_payload(
        args,
        verifier_path=verifier_path,
        manifest_path=manifest_path,
    )
    command = (
        "HANDOFF_JSON=\"${AO2_CP_RELEASE_SUPPORT_HANDOFF_JSON:-}\"; "
        "VERIFIER_JSON=\"${AO2_CP_RELEASE_SUPPORT_VERIFIER_JSON:-"
        + shlex.quote(str(verifier_path))
        + "}\"; "
        "if [ -n \"$HANDOFF_JSON\" ] && [ -f \"$HANDOFF_JSON\" ]; then VERIFIER_JSON=\"$HANDOFF_JSON\"; fi; "
        "MANIFEST_JSON=\"${AO2_CP_RELEASE_SUPPORT_MANIFEST_JSON:-"
        + shlex.quote(str(manifest_path))
        + "}\"; "
        "if [ -f \"$VERIFIER_JSON\" ]; then "
        "set --; if [ -f \"$MANIFEST_JSON\" ]; then set -- --manifest-json \"$MANIFEST_JSON\"; fi; "
        + f"{shlex.quote(sys.executable)} "
        + f"{shlex.quote(str(args.factory_root / 'scripts' / 'ao2_release_support_verifier_handoff.py'))} "
        + "--verifier-json \"$VERIFIER_JSON\" \"$@\" "
        + "--write-json "
        + shlex.quote(str(handoff_path))
        + " --write-md "
        + shlex.quote(str(handoff_md_path))
        + " --json; "
        + "else printf '%s\\n' "
        + shlex.quote(json.dumps(planned_payload, sort_keys=True))
        + " > "
        + shlex.quote(str(handoff_path))
        + " && printf '%s\\n' "
        + shlex.quote(render_release_support_verifier_handoff_markdown(planned_payload))
        + " > "
        + shlex.quote(str(handoff_md_path))
        + "; fi"
    )
    return command_step(
        "release-support-verifier-handoff",
        "Generate ao-operator evaluator handoff from AO2 Control Plane support-bundle verifier JSON",
        args.factory_root,
        ["sh", "-lc", command],
    )


def provider_acceptance_publish_step(args: argparse.Namespace) -> dict[str, Any]:
    return command_step(
        "provider-acceptance-publish",
        "Publish AO2 provider-pilot acceptance evidence to control plane",
        args.factory_root,
        [
            "internal:provider-acceptance-publish",
            str(nightly_provider_acceptance_publish_path(args)),
        ],
    )


def provider_acceptance_preservation_step(args: argparse.Namespace) -> dict[str, Any]:
    acceptance_root = provider_acceptance_preservation_root(args)
    preservation_path = nightly_provider_acceptance_preservation_path(args)
    skipped_payload = shlex.quote(
        json.dumps(
            {
                "schema": "ao2.provider-pilot-acceptance-preservation.v1",
                "status": "skipped",
                "reason": "No provider-pilot acceptance root is available to preserve.",
                "acceptance_root": str(acceptance_root),
            },
            sort_keys=True,
        )
    )
    command = (
        f"if [ -d {shlex.quote(str(acceptance_root))} ]; then "
        f"AO2_PROVIDER_PILOT_ACCEPTANCE_ROOT={shlex.quote(str(acceptance_root))} "
        f"AO2_PROVIDER_PILOT_PRESERVE_JSON={shlex.quote(str(preservation_path))} "
        "npm run release:preserve-provider-acceptance; "
        "else "
        f"printf '%s\\n' {skipped_payload} > {shlex.quote(str(preservation_path))}; "
        "fi"
    )
    return command_step(
        "provider-acceptance-preservation",
        "Preserve live AO2 provider-pilot acceptance bundles as durable release evidence",
        args.ao2_root,
        ["sh", "-lc", command],
    )


def build_steps(args: argparse.Namespace) -> list[dict[str, Any]]:
    provider_registry_command = " ".join(
        shlex.quote(part)
        for part in [
            sys.executable,
            str(args.factory_root / "scripts" / "hermes_ao_bridge.py"),
            "provider-registry",
            "--ao2-target",
            str(args.ao2_root),
            "--ao2-bin",
            str(ao2_release_bin(args)),
            "--factory-root",
            str(args.factory_root),
            "--json",
        ]
    )
    publish_provider_registry_command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(args.factory_root / "scripts" / "hermes_ao_bridge.py")),
            "publish-provider-registry",
            "--control-plane-url",
            '"$CONTROL_PLANE_URL"',
            "--api-token",
            '"$AO2_CP_API_TOKEN"',
            "--signing-key",
            '"$SIGNING_KEY"',
            "--signer-id",
            shlex.quote(args.provider_registry_signer_id),
            "--ao2-target",
            shlex.quote(str(args.ao2_root)),
            "--ao2-bin",
            shlex.quote(str(ao2_release_bin(args))),
            "--factory-root",
            shlex.quote(str(args.factory_root)),
            "--json",
        ]
    )
    signing_key_default = shlex.quote(str(args.provider_registry_signing_key))
    provider_registry_signing_candidates = [
        args.provider_registry_signing_key,
        args.phase1_decision_signing_key,
        args.factory_root / "keys" / "ao2-release-signing-key.pem",
        args.ao2_root / ".release-signing" / "ao2-release-signing-key.pem",
    ]
    provider_registry_signing_candidate_shell = " ".join(
        shlex.quote(str(candidate)) for candidate in provider_registry_signing_candidates
    )
    provider_registry_publish_path = shlex.quote(str(nightly_provider_registry_publish_path(args)))
    provider_registry_publish_shell = (
        f"SIGNING_KEY=\"${{AO2_PROVIDER_REGISTRY_SIGNING_KEY:-{signing_key_default}}}\"; "
        f"if [ ! -f \"$SIGNING_KEY\" ]; then SIGNING_KEY=\"\"; "
        f"for candidate in {provider_registry_signing_candidate_shell}; do "
        f"if [ -f \"$candidate\" ]; then SIGNING_KEY=\"$candidate\"; break; fi; "
        "done; fi; "
        f"CONTROL_PLANE_URL=\"${{AO2_CP_URL:-{shlex.quote(args.provider_registry_control_plane_url)}}}\"; "
        f"if [ -n \"${{AO2_CP_API_TOKEN:-}}\" ] && [ -f \"$SIGNING_KEY\" ]; then "
        f"{publish_provider_registry_command} > {provider_registry_publish_path}; "
        "else "
        "printf '%s\\n' "
        + shlex.quote(
            json.dumps(
                {
                    "schema": "ao-operator/hermes-nightly-provider-registry-publish/v1",
                    "status": "skipped",
                    "reason": "AO2_CP_API_TOKEN and AO2_PROVIDER_REGISTRY_SIGNING_KEY are required for signed registry publish",
                    "observer_links": provider_registry_observer_links(args),
                },
                sort_keys=True,
            )
        )
        + f" > {provider_registry_publish_path}; "
        "fi"
    )
    bridge_command = [
        sys.executable,
        str(args.factory_root / "scripts" / "hermes_bridge_three_os_smoke.py"),
        "--control-plane-mode",
        "real",
        "--ao2-root",
        str(args.ao2_root),
        "--ao2-control-plane",
        str(args.ao2_control_plane),
        "--ao2-bin",
        str(ao2_release_bin(args)),
        "--ao-runtime",
        str(args.ao_runtime),
        "--ubuntu-target",
        args.ubuntu_target,
        "--windows-target",
        args.windows_target,
        "--skip-node",
        "--json",
    ]
    if args.require_remotes:
        bridge_command.append("--require-remotes")
    else:
        bridge_command.append("--local-only")

    return [
        command_step(
            "ao2-verify",
            "AO2 full verification",
            args.ao2_root,
            ["npm", "run", "verify"],
        ),
        command_step(
            "ao2-release-build",
            "AO2 release CLI build for Hermes bridge commands",
            args.ao2_root,
            ["cargo", "build", "--release", "-p", "ao2-cli"],
        ),
        command_step(
            "control-plane-verify",
            "ao2-control-plane full verification",
            args.ao2_control_plane,
            [
                "sh",
                "-lc",
                "unset AO2_CP_API_TOKEN; cargo fmt --all -- --check && cargo test --workspace && cargo clippy --workspace --all-targets -- -D warnings",
            ],
        ),
        command_step(
            "control-plane-release-smoke",
            "ao2-control-plane release archive smoke",
            args.ao2_control_plane,
            [
                "sh",
                "-lc",
                (
                    "cargo build --release -p ao2-cp-server && "
                    "scripts/package-local.sh --out-dir dist --version 0.1.0 --binary target/release/ao2-cp-server && "
                    "AO2_CP_ARCHIVE=dist/ao2-control-plane-0.1.0-macos-aarch64.tar.gz "
                    f"AO2_CP_SMOKE_JSON={shlex.quote(str(nightly_control_plane_release_smoke_path(args)))} "
                    "scripts/smoke-release-archive.sh"
                ),
            ],
        ),
        command_step(
            "factory-verify",
            "AO Operator Python verification",
            args.factory_root,
            ["pytest", "-q"],
            env_remove=["AO2_CP_API_TOKEN", "AO2_CP_URL"],
        ),
        command_step(
            "ao2-provider-registry",
            "AO2 provider registry guard snapshot",
            args.factory_root,
            [
                "sh",
                "-lc",
                f"{provider_registry_command} > {shlex.quote(str(nightly_provider_registry_path(args)))}",
            ],
        ),
        command_step(
            "ao2-provider-registry-publish",
            "AO2 signed provider registry publish to control plane",
            args.factory_root,
            [
                "sh",
                "-lc",
                provider_registry_publish_shell,
            ],
        ),
        provider_phase1_readiness_step(args),
        provider_phase1_readiness_publish_step(args),
        provider_acceptance_publish_step(args),
        provider_acceptance_preservation_step(args),
        contract_gate_step(args, "midpoint"),
        command_step(
            "real-hermes-bridge-smoke",
            "Hermes AO2 control-plane bridge smoke",
            args.factory_root,
            bridge_command,
        ),
        contract_gate_step(args, "closure"),
        command_step(
            "ao2-release-summary-enrich",
            "AO2 release summary obligation-gate enrichment",
            args.ao2_root,
            [
                str(ao2_release_bin(args)),
                "release",
                "summary-enrich",
                "--summary",
                str(nightly_release_summary_path(args)),
                "--target",
                str(args.ao2_root),
                "--obligation-gate",
                str(nightly_obligation_gate_path(args, "midpoint")),
                "--obligation-gate",
                str(nightly_obligation_gate_path(args, "closure")),
                "--out",
                str(nightly_enriched_release_summary_path(args)),
                "--json",
            ],
        ),
        command_step(
            "ao2-release-gate-dry-run",
            "AO2 release gate summary dry-run",
            args.factory_root,
            [
                "internal:release-gate-dry-run",
                str(nightly_enriched_release_summary_path(args)),
                str(nightly_release_gate_dry_run_path(args)),
            ],
        ),
        three_os_smoke_observer_step(args),
        three_os_smoke_publish_step(args),
        command_step(
            "phase1-promotion-checklist",
            "AO2 Phase 1 promotion checklist",
            args.factory_root,
            [
                "internal:phase1-promotion-checklist",
                str(nightly_phase1_promotion_checklist_path(args)),
            ],
        ),
        phase1_promotion_checklist_publish_step(args),
        phase1_promotion_decision_publish_step(args),
        phase1_promotion_history_fetch_step(args),
        phase1_promotion_status_step(args),
        phase1_promotion_panel_step(args),
        release_publication_publish_step(args),
        release_cockpit_status_step(args),
        release_handoff_status_step(args),
        release_readiness_status_step(args),
        release_support_bundle_status_step(args),
        release_handoff_checklist_step(args),
        release_evaluator_decision_step(args),
        release_evaluator_decision_publish_step(args),
        release_evaluator_decision_status_step(args),
        factory_compat_nightly_run_step(args),
        factory_compat_memory_publish_step(args),
        release_ao2_native_evidence_pack_producer_step(args),
        release_ao2_native_evaluator_producer_step(args),
        release_ao2_native_evaluator_verification_step(args),
        release_evaluator_closure_with_ao2_verification_step(args),
        release_support_bundle_status_step(
            args,
            step_id="release-support-bundle-post-decision-status",
            title="Refresh AO2 release support bundle after evaluator decision publication",
            output_path=nightly_release_support_bundle_post_decision_status_path(args),
            phase="post_evaluator_decision_publish",
        ),
        release_support_verifier_handoff_step(args),
        cancel_authority_dry_run_step(args),
        command_step(
            "gap-miner",
            "Rank obvious follow-up gaps",
            args.factory_root,
            [
                "internal:ranked-gap-miner",
                "TODO|FIXME|skip|openssl",
            ],
        ),
    ]


def write_nightly_obligation_ledger(args: argparse.Namespace) -> dict[str, str]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = nightly_obligation_ledger_path(args)
    source_path = args.factory_root / "scripts" / "hermes_nightly_ao2_advancement.py"
    if not source_path.is_file():
        source_path = Path(__file__).resolve()
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    ledger = {
        "schema_version": "ao2.obligation-ledger.v1",
        "source_contracts": [
            {
                "path": str(source_path),
                "sha256": source_sha256,
            }
        ],
        "obligations": [
            {
                "id": "NIGHTLY-AO2-WORKBENCH-GATE",
                "kind": "behavior",
                "statement": "AO2 workbench must expose the operator obligation gate endpoint and response schema.",
                "source_path": "scripts/hermes_nightly_ao2_advancement.py",
                "source_line": 1,
                "source_excerpt_hash": "sha256:nightly-generated-contract",
                "expected_fragments": [
                    "/api/obligations/gate",
                    "ao2.workbench-obligation-gate.v1",
                ],
                "status": "unverified",
                "evidence": [],
                "waiver": None,
            },
            {
                "id": "NIGHTLY-AO2-EVIDENCE-SCAN-SCOPE",
                "kind": "correctness",
                "statement": "AO2 obligation scanning must not satisfy required fragments from generated .ao2 evidence.",
                "source_path": "scripts/hermes_nightly_ao2_advancement.py",
                "source_line": 1,
                "source_excerpt_hash": "sha256:nightly-generated-contract",
                "expected_fragments": [
                    'name == ".ao2"',
                    "node_modules",
                ],
                "status": "unverified",
                "evidence": [],
                "waiver": None,
            },
            {
                "id": "NIGHTLY-AO2-CONTRACT-GATE",
                "kind": "evidence",
                "statement": "AO2 must continue emitting signed obligation gate artifacts with the stable schema.",
                "source_path": "scripts/hermes_nightly_ao2_advancement.py",
                "source_line": 1,
                "source_excerpt_hash": "sha256:nightly-generated-contract",
                "expected_fragments": [
                    "ao2.obligation-gate.v1",
                    "failed_obligations",
                    "unverified_obligations",
                ],
                "status": "unverified",
                "evidence": [],
                "waiver": None,
            },
        ],
        "summary": {"pass": 0, "fail": 0, "unverified": 3, "waived": 0},
        "verdict": "rejected",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "obligation_ledger": str(ledger_path),
        "midpoint_gate": str(nightly_obligation_gate_path(args, "midpoint")),
        "closure_gate": str(nightly_obligation_gate_path(args, "closure")),
        "release_summary": str(nightly_release_summary_path(args)),
        "enriched_release_summary": str(nightly_enriched_release_summary_path(args)),
        "release_gate_dry_run": str(nightly_release_gate_dry_run_path(args)),
        "three_os_smoke_observer": str(nightly_three_os_smoke_observer_path(args)),
        "three_os_smoke_publish": str(nightly_three_os_smoke_publish_path(args)),
        "phase1_promotion_checklist": str(nightly_phase1_promotion_checklist_path(args)),
        "phase1_promotion_checklist_publish": str(nightly_phase1_promotion_checklist_publish_path(args)),
        "phase1_promotion_decision": str(nightly_phase1_promotion_decision_path(args)),
        "phase1_promotion_decision_publish": str(nightly_phase1_promotion_decision_publish_path(args)),
        "phase1_promotion_history": str(nightly_phase1_promotion_history_path(args)),
        "phase1_promotion_status": str(nightly_phase1_promotion_status_path(args)),
    }


def planned_release_support_verifier_handoff_payload(
    args: argparse.Namespace,
    *,
    verifier_path: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    verifier = verifier_path or nightly_release_support_verifier_json_path(args)
    manifest = manifest_path or nightly_release_support_manifest_json_path(args)
    return {
        "schema": "ao-operator/ao2-release-support-verifier-handoff/v1",
        "status": "planned",
        "reason": "support-bundle verifier JSON has not been produced yet",
        "verifier": {
            "path": str(verifier),
            "status": "planned",
            "checksum_verified": False,
            "bundle_sha256": "unknown",
            "surface_count": 0,
            "failure_count": 0,
        },
        "manifest": {
            "path": str(manifest),
            "schema_version": "unknown",
            "verifier_output_schema_sample": "unknown",
        },
        "checks": [],
        "blockers": [],
        "operator_decision": {
            "factory_v3_evaluator_closer_required": True,
            "control_plane_approves_release": False,
            "next_action": "run ao2-control-plane offline support-bundle verifier JSON, then regenerate this evaluator-closer handoff",
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "source": "planned ao2-control-plane offline support-bundle verifier output",
        },
    }


def render_release_support_verifier_handoff_markdown(payload: dict[str, Any]) -> str:
    operator_decision = payload.get("operator_decision", {})
    trust_boundary = payload.get("trust_boundary", {})
    return "\n".join(
        [
            "# AO2 Release Support Verifier Handoff",
            "",
            f"Status: `{payload.get('status', 'unknown')}`",
            "",
            "## Verifier",
            "",
            f"- Path: `{payload.get('verifier', {}).get('path', 'unknown')}`",
            f"- Status: `{payload.get('verifier', {}).get('status', 'unknown')}`",
            "",
            "## Trust boundary",
            "",
            f"- release_acceptance_owner: `{trust_boundary.get('release_acceptance_owner', 'ao-operator evaluator-closer')}`",
            f"- control_plane_approves_release: `{str(operator_decision.get('control_plane_approves_release', False)).lower()}`",
            f"- factory_v3_evaluator_closer_required: `{str(operator_decision.get('factory_v3_evaluator_closer_required', True)).lower()}`",
            "",
        ]
    )


def write_planned_release_support_verifier_handoff_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = planned_release_support_verifier_handoff_payload(args)
    nightly_release_support_verifier_handoff_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nightly_release_support_verifier_handoff_markdown_path(args).write_text(
        render_release_support_verifier_handoff_markdown(artifact),
        encoding="utf-8",
    )
    return artifact


def write_planned_release_gate_dry_run_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-release-gate-dry-run/v1",
        "status": "planned",
        "enriched_summary": str(nightly_enriched_release_summary_path(args)),
        "malformed_summary": str(nightly_malformed_release_summary_path(args)),
        "require_provider_acceptance_source": str(getattr(args, "require_provider_acceptance_source", "any")),
        "checks": [],
    }
    nightly_release_gate_dry_run_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_three_os_smoke_observer_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao2-control-plane.three-os-release-smoke.v1",
        "status": "planned",
        "source_commit": "planned",
        "source_dirty": True,
        "message": "Dry-run only. The real step converts the enriched AO2 three-OS summary into the control-plane observer schema.",
        "targets": {
            "macos": {"status": "planned"},
            "ubuntu": {"status": "planned"},
            "windows": {"status": "planned"},
        },
    }
    nightly_three_os_smoke_observer_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_three_os_smoke_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-three-os-smoke-publish/v1",
        "status": "planned",
        "three_os_smoke_artifact": str(nightly_three_os_smoke_observer_path(args)),
        "observer_links": phase1_promotion_observer_links(args),
    }
    nightly_three_os_smoke_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_control_plane_release_smoke_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao2-control-plane.release-smoke.v1",
        "status": "planned",
        "archive": str(args.ao2_control_plane / "dist" / "ao2-control-plane-0.1.0-macos-aarch64.tar.gz"),
        "message": "Dry-run only. The real step packages ao2-cp-server and smokes the installed archive.",
    }
    nightly_control_plane_release_smoke_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_provider_phase1_readiness_artifact(args: argparse.Namespace) -> dict[str, Any]:
    phase_dir = nightly_provider_phase1_readiness_dir(args)
    phase_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": PROVIDER_PHASE1_READINESS_SCHEMA,
        "status": "planned",
        "live_provider_policy": "not_run_by_default",
        "required_live_provider_pilots": list(getattr(args, "require_live_provider_pilot", [])),
        "message": "Dry-run only. Live provider smoke is intentionally not started by the nightly default path.",
        "artifacts": {},
    }
    nightly_provider_phase1_readiness_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_provider_phase1_readiness_markdown(artifact, nightly_provider_phase1_readiness_markdown_path(args))
    return artifact


def write_planned_provider_phase1_readiness_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    phase_dir = nightly_provider_phase1_readiness_dir(args)
    phase_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/hermes-provider-phase1-readiness-publish/v1",
        "status": "planned",
        "control_plane_url": str(getattr(args, "provider_registry_control_plane_url", "")),
        "readiness_artifact": str(nightly_provider_phase1_readiness_path(args)),
        "observer_links": provider_phase1_observer_links(args),
    }
    nightly_provider_phase1_readiness_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_provider_acceptance_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    phase_dir = nightly_provider_phase1_readiness_dir(args)
    phase_dir.mkdir(parents=True, exist_ok=True)
    bundles, bundle_source = provider_acceptance_bundle_candidates(args)
    artifact = {
        "schema": "ao-operator/hermes-provider-acceptance-publish/v1",
        "status": "planned",
        "control_plane_url": str(getattr(args, "provider_registry_control_plane_url", "")),
        "acceptance_bundle_source": bundle_source,
        "acceptance_bundles": [str(path) for path in bundles],
        "acceptance_bundle_source_classes": provider_acceptance_bundle_source_classes(bundles, args),
        "require_provider_acceptance_source": str(getattr(args, "require_provider_acceptance_source", "any")),
        "observer_links": provider_acceptance_observer_links(args),
    }
    nightly_provider_acceptance_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_provider_acceptance_preservation_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao2.provider-pilot-acceptance-preservation.v1",
        "status": "planned",
        "acceptance_root": str(provider_acceptance_preservation_root(args)),
        "summary_path": str(nightly_provider_acceptance_preservation_path(args)),
        "message": "Dry-run only. The real step copies live Codex and Claude provider-pilot acceptance bundles into AO2 release evidence.",
    }
    nightly_provider_acceptance_preservation_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_cancel_authority_dry_run_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = nightly_cancel_authority_dry_run_path(args)
    artifact = {
        "schema": "ao-operator/hermes-nightly-cancel-authority-dry-run/v1",
        "dry_run_schema": "ao-operator/ao2-watchdog-cancel-authority-dry-run/v1",
        "status": "planned",
        "mode": str(getattr(args, "cancel_authority_dry_run_mode", "auto")),
        "weekday_configured": int(getattr(args, "cancel_authority_dry_run_weekday", 1)),
        "active_pid": int(getattr(args, "cancel_authority_dry_run_active_pid", 4242)),
        "ao2_bin": str(ao2_release_bin(args)),
        "out_path": str(out_path),
        "message": (
            "Dry-run only. The real step shells out to "
            "scripts/hermes_nightly_cancel_authority_dry_run.py which "
            "re-runs the AO2 watchdog cancel-authority producer ↔ "
            "consumer round trip against a fresh tempdir on the "
            "configured weekday and overwrites this artifact with the "
            "executed-status evidence (or skipped/binary_missing). The "
            "live launchd loop is never invoked."
        ),
        "dry_run_evidence": None,
        "blockers": [],
    }
    out_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def cancel_authority_dry_run_step(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(args.factory_root / "scripts" / "hermes_nightly_cancel_authority_dry_run.py"),
        "--ao2-bin",
        str(ao2_release_bin(args)),
        "--out-path",
        str(nightly_cancel_authority_dry_run_path(args)),
        "--mode",
        str(getattr(args, "cancel_authority_dry_run_mode", "auto")),
        "--weekday",
        str(int(getattr(args, "cancel_authority_dry_run_weekday", 1))),
        "--active-pid",
        str(int(getattr(args, "cancel_authority_dry_run_active_pid", 4242))),
        "--reason",
        str(getattr(args, "cancel_authority_dry_run_reason", "")) or (
            "hermes-nightly-cancel-authority-dry-run "
            "(weekly cadence; never invokes the live launchd loop)"
        ),
    ]
    if getattr(args, "cancel_authority_dry_run_strict", False):
        command.append("--strict")
    return command_step(
        "cancel-authority-dry-run",
        "Weekly AO2 watchdog cancel-authority producer ↔ consumer dry-run",
        args.factory_root,
        command,
    )


def provider_phase1_readiness_status(summary: dict[str, Any]) -> str:
    def item_status(item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        return str(item.get("status") or item.get("verdict") or "")

    contracts = summary.get("contracts", {})
    codex_contract = contracts.get("codex", {}) if isinstance(contracts, dict) else {}
    claude_contract = contracts.get("claude", {}) if isinstance(contracts, dict) else {}
    scripted_gate = summary.get("scripted_gate", {})
    codex_gate = summary.get("codex_gate", {})
    codex_pilot = summary.get("codex_pilot", {})
    contract_statuses = {
        str(codex_contract.get("status", "")),
        str(claude_contract.get("status", "")),
    }
    if contract_statuses != {"verified"}:
        return "failed"
    if item_status(scripted_gate) != "ready":
        return "failed"
    if item_status(codex_gate) not in {"ready", "not_ready", "blocked"}:
        return "failed"
    if item_status(codex_pilot) not in {"ready", "blocked", "planned", "not_run"}:
        return "failed"
    required_live = summary.get("required_live_provider_pilots", [])
    if isinstance(required_live, list) and "codex" in required_live:
        if item_status(codex_gate) != "ready" or item_status(codex_pilot) != "ready":
            return "failed"
    return "passed"


def load_json_artifact(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text.lstrip())
        except json.JSONDecodeError as exc:
            return {"status": "unreadable", "error": str(exc), "artifact": str(path)}
        if isinstance(payload, dict):
            return payload
        return {"status": "unreadable", "error": "artifact JSON is not an object", "artifact": str(path)}
    except OSError as exc:
        return {"status": "unreadable", "error": str(exc), "artifact": str(path)}


def run_provider_phase1_command(args: argparse.Namespace, command: list[str], artifact: Path) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=args.ao2_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    output = redact_nightly_log_output(result.stdout or "")
    artifact.write_text(output, encoding="utf-8", errors="replace")
    payload = load_json_artifact(artifact)
    if "status" not in payload and "verdict" not in payload:
        payload["status"] = "failed" if result.returncode else "passed"
    payload["exit_code"] = result.returncode
    return payload


def write_provider_phase1_readiness_markdown(summary: dict[str, Any], path: Path) -> None:
    def item_status(name: str) -> str:
        item = summary.get(name, {})
        if not isinstance(item, dict):
            return "unknown"
        return str(item.get("status") or item.get("verdict") or "unknown")

    artifacts = summary.get("artifacts", {})
    contracts = summary.get("contracts", {})
    lines = [
        "# AO2 Provider Phase 1 Readiness",
        "",
        f"- status: `{summary.get('status', 'unknown')}`",
        f"- live_provider_policy: `{summary.get('live_provider_policy', 'unknown')}`",
        "",
        "## Contracts",
        "",
    ]
    for provider in ("codex", "claude"):
        contract = contracts.get(provider, {}) if isinstance(contracts, dict) else {}
        lines.append(f"- {provider}: `{contract.get('status', 'unknown')}`")
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- scripted_gate: `{item_status('scripted_gate')}`",
            f"- codex_gate: `{item_status('codex_gate')}`",
            f"- codex_pilot: `{item_status('codex_pilot')}`",
        ]
    )
    recovery_target = summary.get("recovery_target")
    if recovery_target:
        lines.extend(["", f"- recovery_target: `{recovery_target}`"])
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    if isinstance(artifacts, dict):
        for name, artifact in sorted(artifacts.items()):
            lines.append(f"- {name}: `{artifact}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_provider_phase1_readiness_artifact(args: argparse.Namespace) -> dict[str, Any]:
    phase_dir = nightly_provider_phase1_readiness_dir(args)
    phase_dir.mkdir(parents=True, exist_ok=True)
    fixture = args.ao2_root / "fixtures" / "discount-service"
    if not fixture.is_dir():
        summary = {
            "schema": PROVIDER_PHASE1_READINESS_SCHEMA,
            "status": "failed",
            "live_provider_policy": "not_run_by_default",
            "required_live_provider_pilots": list(getattr(args, "require_live_provider_pilot", [])),
            "error": f"missing AO2 provider smoke fixture: {fixture}",
            "artifacts": {},
        }
        nightly_provider_phase1_readiness_path(args).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_provider_phase1_readiness_markdown(summary, nightly_provider_phase1_readiness_markdown_path(args))
        return summary

    ao2_bin = str(ao2_release_bin(args))
    prompt_file = phase_dir / "codex-pilot-prompt.md"
    prompt_file.write_text(
        "\n".join(
            [
                "You are validating AO2 Phase 1 provider readiness.",
                "Do not make external network calls.",
                "Inspect the discount-service fixture and report whether the provider adapter can execute the governed contract.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    artifact_paths = {
        "codex_contract": phase_dir / "codex-contract.json",
        "claude_contract": phase_dir / "claude-contract.json",
        "scripted_smoke_all": phase_dir / "scripted-smoke-all.json",
        "scripted_gate": phase_dir / "scripted-gate.json",
        "codex_gate": phase_dir / "codex-gate.json",
        "codex_pilot": phase_dir / "codex-pilot-plan.json",
    }
    recovery_target = phase_dir / "recovery-target" / "discount-service"
    if recovery_target.exists():
        shutil.rmtree(recovery_target)
    recovery_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, recovery_target)
    target = recovery_target

    with tempfile.TemporaryDirectory(prefix="ao2-provider-phase1-"):
        codex_contract = run_provider_phase1_command(
            args,
            [ao2_bin, "provider", "contract", "--provider", "codex", "--verify", "--require", "codex", "--json"],
            artifact_paths["codex_contract"],
        )
        claude_contract = run_provider_phase1_command(
            args,
            [ao2_bin, "provider", "contract", "--provider", "claude", "--verify", "--require", "claude", "--json"],
            artifact_paths["claude_contract"],
        )
        scripted_smoke_all = run_provider_phase1_command(
            args,
            [ao2_bin, "provider", "smoke-all", "--target", str(target), "--json"],
            artifact_paths["scripted_smoke_all"],
        )
        scripted_gate = run_provider_phase1_command(
            args,
            [ao2_bin, "provider", "gate", "--target", str(target), "--require", "scripted", "--json"],
            artifact_paths["scripted_gate"],
        )
        codex_gate = run_provider_phase1_command(
            args,
            [ao2_bin, "provider", "gate", "--target", str(target), "--require", "codex", "--json"],
            artifact_paths["codex_gate"],
        )
        codex_pilot = run_provider_phase1_command(
            args,
            [
                ao2_bin,
                "provider",
                "pilot",
                "--target",
                str(target),
                "--provider",
                "codex",
                "--provider-prompt-file",
                str(prompt_file),
                "--json",
            ],
            artifact_paths["codex_pilot"],
        )
    summary = {
        "schema": PROVIDER_PHASE1_READINESS_SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "live_provider_policy": "not_run_by_default",
        "required_live_provider_pilots": list(getattr(args, "require_live_provider_pilot", [])),
        "contracts": {
            "codex": codex_contract,
            "claude": claude_contract,
        },
        "scripted_smoke_all": scripted_smoke_all,
        "scripted_gate": scripted_gate,
        "codex_gate": codex_gate,
        "codex_pilot": codex_pilot,
        "recovery_target": str(recovery_target),
        "artifacts": {name: str(path) for name, path in artifact_paths.items()},
    }
    summary["status"] = provider_phase1_readiness_status(summary)
    nightly_provider_phase1_readiness_path(args).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_provider_phase1_readiness_markdown(summary, nightly_provider_phase1_readiness_markdown_path(args))
    return summary


def write_provider_phase1_readiness_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_provider_phase1_readiness_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = nightly_provider_phase1_readiness_path(args)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    if not token:
        artifact = {
            "schema": "ao-operator/hermes-provider-phase1-readiness-publish/v1",
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for provider readiness publish",
            "readiness_artifact": str(summary_path),
            "observer_links": provider_phase1_observer_links(args),
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not summary_path.is_file():
        artifact = {
            "schema": "ao-operator/hermes-provider-phase1-readiness-publish/v1",
            "status": "failed",
            "error": f"missing provider readiness summary: {summary_path}",
            "readiness_artifact": str(summary_path),
            "observer_links": provider_phase1_observer_links(args),
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip(
        "/"
    ) + "/api/v1/provider/readiness"
    data = summary_path.read_bytes()
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except urllib.error.URLError as exc:
        artifact = {
            "schema": "ao-operator/hermes-provider-phase1-readiness-publish/v1",
            "status": "failed",
            "error": str(exc.reason),
            "readiness_artifact": str(summary_path),
            "control_plane_url": url,
            "observer_links": provider_phase1_observer_links(args),
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    observer_dashboard = (
        fetch_provider_phase1_observer_dashboard(args, token)
        if 200 <= status_code < 300
        else {"status": "skipped", "reason": "provider readiness publish did not return 2xx"}
    )
    artifact = {
        "schema": "ao-operator/hermes-provider-phase1-readiness-publish/v1",
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "readiness_artifact": str(summary_path),
        "control_plane_url": url,
        "response": redact_nightly_log_output(response_body),
        "observer_links": provider_phase1_observer_links(args),
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = observer_dashboard["snapshot"]
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_provider_acceptance_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_provider_acceptance_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    bundles, bundle_source = provider_acceptance_bundle_candidates(args)
    base_url = str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/")
    common = {
        "schema": "ao-operator/hermes-provider-acceptance-publish/v1",
        "acceptance_bundle_source": bundle_source,
        "acceptance_bundles": [str(path) for path in bundles],
        "acceptance_bundle_source_classes": provider_acceptance_bundle_source_classes(bundles, args),
        "require_provider_acceptance_source": str(getattr(args, "require_provider_acceptance_source", "any")),
        "observer_links": provider_acceptance_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for provider acceptance publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not bundles:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "provider acceptance bundle is required",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    published: list[dict[str, Any]] = []
    for bundle in bundles:
        bundle_path = Path(bundle)
        if not bundle_path.is_file():
            artifact = {
                **common,
                "status": "failed",
                "error": f"missing provider acceptance bundle: {bundle_path}",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
        raw = bundle_path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            artifact = {
                **common,
                "status": "failed",
                "error": f"provider acceptance bundle is not valid JSON: {bundle_path}: {exc}",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
        schema = str(payload.get("schema_version") or "")
        provider = str(payload.get("provider") or "")
        if schema not in {
            "ao2.codex-provider-pilot-acceptance.v1",
            "ao2.claude-provider-pilot-acceptance.v1",
        }:
            artifact = {
                **common,
                "status": "failed",
                "error": f"unsupported provider acceptance schema: {schema or '<missing>'}",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
        if (schema.startswith("ao2.codex-") and provider != "codex") or (
            schema.startswith("ao2.claude-") and provider != "claude"
        ):
            artifact = {
                **common,
                "status": "failed",
                "error": f"provider {provider or '<missing>'} does not match acceptance schema {schema}",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
        request = urllib.request.Request(
            f"{base_url}/api/v1/acceptance",
            data=raw,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                status_code = int(response.status)
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            status_code = int(exc.code)
        except urllib.error.URLError as exc:
            artifact = {
                **common,
                "status": "failed",
                "error": str(exc.reason),
                "control_plane_url": f"{base_url}/api/v1/acceptance",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
        try:
            receipt = json.loads(response_body)
        except json.JSONDecodeError:
            receipt = {"raw_response": redact_nightly_log_output(response_body)}
        item = {
            "acceptance_bundle": str(bundle_path),
            "source_class": provider_acceptance_bundle_source_class(bundle_path, args),
            "provider": provider,
            "schema_version": schema,
            "status_code": status_code,
            "receipt": receipt,
        }
        published.append(item)
        if not 200 <= status_code < 300:
            artifact = {
                **common,
                "status": "failed",
                "control_plane_url": f"{base_url}/api/v1/acceptance",
                "published": published,
            }
            publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return artifact
    observer_dashboard = fetch_provider_acceptance_observer_dashboard(args, token)
    artifact = {
        **common,
        "status": "passed" if observer_dashboard.get("status") == "passed" else "failed",
        "control_plane_url": f"{base_url}/api/v1/acceptance",
        "published": published,
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = observer_dashboard["snapshot"]
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def release_gate_summary_dry_run(
    summary: dict[str, Any],
    *,
    require_native_windows: bool,
    require_remotes: bool = False,
    require_provider_readiness_publish: bool = False,
    provider_readiness_publish: dict[str, Any] | None = None,
    provider_readiness_control_plane: dict[str, Any] | None = None,
    require_provider_acceptance_publish: bool = False,
    provider_acceptance_publish: dict[str, Any] | None = None,
    require_provider_acceptance_source: str = "any",
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, message: str) -> None:
        checks.append({"name": name, "status": "passed" if passed else "failed", "message": message})

    add_check(
        "schema",
        summary.get("schema") == "ao2.three-os-smoke-summary.v1",
        "summary schema must be ao2.three-os-smoke-summary.v1",
    )
    add_check(
        "local_smoke",
        summary.get("local_smoke") == "passed",
        "local macOS/control-plane release smoke must pass",
    )
    if "linux_x86_64_remote_smoke" in summary:
        linux_status = summary.get("linux_x86_64_remote_smoke")
        linux_evidence = summary.get("linux_x86_64_remote_evidence", {})
        linux_local_only_skip = (
            not require_remotes
            and linux_status == "skipped"
            and isinstance(linux_evidence, dict)
            and linux_evidence.get("reason") == "local_only"
        )
        add_check(
            "linux_x86_64_remote_smoke",
            linux_status == "passed" or linux_local_only_skip,
            (
                "native Ubuntu x86_64 release smoke must pass when remotes are required; "
                "local-only skips are accepted for non-promoting advancement runs"
            ),
        )
    windows_required = bool(require_native_windows or summary.get("native_windows_required"))
    if windows_required:
        add_check(
            "windows_native_smoke",
            summary.get("windows_native_smoke") == "passed",
            "native Windows smoke must pass when required",
        )

    obligation_gates = summary.get("obligation_gates")
    gates = obligation_gates.get("gates", []) if isinstance(obligation_gates, dict) else []
    add_check(
        "obligation_gates_present",
        isinstance(obligation_gates, dict) and obligation_gates.get("present") is True,
        "release summary must include obligation_gates.present=true",
    )
    add_check(
        "obligation_gates_non_empty",
        isinstance(gates, list) and len(gates) > 0,
        "release summary must include at least one obligation gate",
    )
    closure_gates = [
        gate for gate in gates if isinstance(gate, dict) and gate.get("stage") == "closure"
    ]
    add_check(
        "closure_obligation_gate_present",
        len(closure_gates) > 0,
        "release summary must include a closure obligation gate",
    )
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            add_check(f"obligation_gate_{index}_shape", False, "obligation gate must be an object")
            continue
        gate_summary = gate.get("summary", {})
        clean = (
            gate.get("status") == "passed"
            and gate.get("verdict") == "accepted"
            and int(gate_summary.get("fail", 0)) == 0
            and int(gate_summary.get("unverified", 0)) == 0
        )
        add_check(
            f"obligation_gate_{index}_clean",
            clean,
            "all release obligation gates must be passed, accepted, and free of failed or unverified items",
        )
    if require_provider_readiness_publish:
        publish_ok, publish_message = provider_readiness_publish_gate_check(provider_readiness_publish or {})
        add_check(
            "provider_readiness_publish",
            publish_ok,
            publish_message,
        )
        control_plane_ok, control_plane_message = provider_readiness_control_plane_gate_check(
            provider_readiness_control_plane or {}
        )
        add_check(
            "provider_readiness_control_plane",
            control_plane_ok,
            control_plane_message,
        )
    if require_provider_acceptance_publish or require_provider_acceptance_source not in {"", "any"}:
        publish_ok, publish_message = provider_acceptance_publish_gate_check(provider_acceptance_publish or {})
        add_check(
            "provider_acceptance_publish",
            publish_ok,
            publish_message,
        )
        source_ok, source_message = provider_acceptance_source_gate_check(
            provider_acceptance_publish or {},
            require_provider_acceptance_source,
        )
        add_check(
            "provider_acceptance_source",
            source_ok,
            source_message,
        )
        control_plane_ok, control_plane_message = provider_readiness_control_plane_gate_check(
            provider_readiness_control_plane or {}
        )
        add_check(
            "provider_acceptance_control_plane",
            control_plane_ok,
            control_plane_message,
        )

    status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return {"status": status, "checks": checks}


def write_release_gate_dry_run_artifact(args: argparse.Namespace) -> dict[str, Any]:
    enriched_path = nightly_enriched_release_summary_path(args)
    malformed_path = nightly_malformed_release_summary_path(args)
    artifact_path = nightly_release_gate_dry_run_path(args)
    if not enriched_path.is_file():
        artifact = {
            "schema": "ao-operator/ao2-release-gate-dry-run/v1",
            "status": "failed",
            "error": f"missing enriched release summary: {enriched_path}",
            "enriched_summary": str(enriched_path),
            "malformed_summary": str(malformed_path),
        }
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    enriched_summary = json.loads(enriched_path.read_text(encoding="utf-8"))
    provider_publish_path = nightly_provider_phase1_readiness_publish_path(args)
    provider_publish = load_json_artifact(provider_publish_path) if provider_publish_path.is_file() else {}
    provider_acceptance_publish_path = nightly_provider_acceptance_publish_path(args)
    provider_acceptance_publish = (
        load_json_artifact(provider_acceptance_publish_path)
        if provider_acceptance_publish_path.is_file()
        else {}
    )
    malformed_summary = dict(enriched_summary)
    malformed_summary.pop("obligation_gates", None)
    malformed_summary.pop("obligation_gate_source", None)
    malformed_path.write_text(
        json.dumps(malformed_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    enriched_result = release_gate_summary_dry_run(
        enriched_summary,
        require_native_windows=bool(args.require_remotes),
        require_remotes=bool(args.require_remotes),
        require_provider_readiness_publish=bool(getattr(args, "require_provider_readiness_publish", False)),
        provider_readiness_publish=provider_publish,
        provider_readiness_control_plane=getattr(args, "provider_readiness_control_plane", {}),
        require_provider_acceptance_publish=bool(getattr(args, "require_provider_acceptance_publish", False)),
        provider_acceptance_publish=provider_acceptance_publish,
        require_provider_acceptance_source=str(getattr(args, "require_provider_acceptance_source", "any")),
    )
    malformed_result = release_gate_summary_dry_run(
        malformed_summary,
        require_native_windows=bool(args.require_remotes),
        require_remotes=bool(args.require_remotes),
        require_provider_readiness_publish=bool(getattr(args, "require_provider_readiness_publish", False)),
        provider_readiness_publish=provider_publish,
        provider_readiness_control_plane=getattr(args, "provider_readiness_control_plane", {}),
        require_provider_acceptance_publish=bool(getattr(args, "require_provider_acceptance_publish", False)),
        provider_acceptance_publish=provider_acceptance_publish,
        require_provider_acceptance_source=str(getattr(args, "require_provider_acceptance_source", "any")),
    )
    status = (
        "passed"
        if enriched_result["status"] == "passed" and malformed_result["status"] == "failed"
        else "failed"
    )
    artifact = {
        "schema": "ao-operator/ao2-release-gate-dry-run/v1",
        "status": status,
        "enriched_summary": str(enriched_path),
        "malformed_summary": str(malformed_path),
        "provider_readiness_publish": provider_publish,
        "provider_acceptance_publish": provider_acceptance_publish,
        "provider_readiness_control_plane": getattr(args, "provider_readiness_control_plane", {}),
        "require_provider_readiness_publish": bool(getattr(args, "require_provider_readiness_publish", False)),
        "require_provider_acceptance_publish": bool(getattr(args, "require_provider_acceptance_publish", False)),
        "require_provider_acceptance_source": str(getattr(args, "require_provider_acceptance_source", "any")),
        "enriched": enriched_result,
        "malformed": malformed_result,
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_planned_phase1_promotion_checklist_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-phase1-promotion-checklist/v1",
        "status": "planned",
        "phase1_state": "planned",
        "message": "Dry-run only. The real step correlates provider readiness, live acceptance, release gate, and three-OS smoke evidence.",
    }
    nightly_phase1_promotion_checklist_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nightly_phase1_promotion_checklist_markdown_path(args).write_text(
        "# AO2 Phase 1 Promotion Checklist\n\n- status: `planned`\n- phase1_state: `planned`\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_phase1_promotion_checklist_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-phase1-promotion-checklist-publish/v1",
        "status": "planned",
        "control_plane_url": str(getattr(args, "provider_registry_control_plane_url", "")),
        "checklist_artifact": str(nightly_phase1_promotion_checklist_path(args)),
        "observer_links": phase1_promotion_observer_links(args),
    }
    nightly_phase1_promotion_checklist_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def ao2_package_version(args: argparse.Namespace) -> str:
    package_json = Path(getattr(args, "ao2_root", Path("."))) / "package.json"
    if not package_json.is_file():
        return ""
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("version") or "")


def write_three_os_smoke_observer_artifact(args: argparse.Namespace) -> dict[str, Any]:
    observer_path = nightly_three_os_smoke_observer_path(args)
    observer_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = nightly_enriched_release_summary_path(args)
    if not summary_path.is_file():
        artifact = {
            "schema": "ao2-control-plane.three-os-release-smoke.v1",
            "status": "failed",
            "source_commit": "unknown",
            "source_dirty": True,
            "error": f"missing enriched three-OS smoke summary: {summary_path}",
            "targets": {
                "macos": {"status": "failed"},
                "ubuntu": {"status": "failed"},
                "windows": {"status": "failed"},
            },
        }
        observer_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    summary = load_json_artifact(summary_path)
    version = str(summary.get("version") or summary.get("release_candidate_version") or "")
    release_candidate_version = str(summary.get("release_candidate_version") or version)
    if not version or not release_candidate_version:
        candidates, _source = release_publication_artifact_candidates(args)
        if candidates:
            publication = load_json_artifact(candidates[0])
            version = version or str(publication.get("version") or "")
            release_candidate_version = release_candidate_version or str(
                publication.get("version") or ""
            )
    if not version or not release_candidate_version:
        package_version = ao2_package_version(args)
        version = version or package_version
        release_candidate_version = release_candidate_version or package_version
    source_commit, source_dirty = git_revision_status(Path(getattr(args, "ao2_control_plane", Path("."))))
    targets = {
        "macos": {
            "status": summary.get("local_smoke", "unknown"),
            "source": "ao2.three-os-smoke-summary.v1.local_smoke",
        },
        "ubuntu": {
            "status": summary.get("linux_x86_64_remote_smoke", "unknown"),
            "source": "ao2.three-os-smoke-summary.v1.linux_x86_64_remote_smoke",
        },
        "windows": {
            "status": summary.get("windows_native_smoke", "unknown"),
            "required": bool(summary.get("native_windows_required", True)),
            "source": "ao2.three-os-smoke-summary.v1.windows_native_smoke",
        },
    }
    ubuntu_local_only_skip = (
        not bool(getattr(args, "require_remotes", False))
        and targets["ubuntu"].get("status") == "skipped"
        and isinstance(summary.get("linux_x86_64_remote_evidence"), dict)
        and summary["linux_x86_64_remote_evidence"].get("reason") == "local_only"
    )
    windows_optional_skip = (
        not targets["windows"].get("required", True)
        and targets["windows"].get("status") == "skipped"
    )
    status = "passed" if (
        targets["macos"].get("status") == "passed"
        and (targets["ubuntu"].get("status") == "passed" or ubuntu_local_only_skip)
        and (targets["windows"].get("status") == "passed" or windows_optional_skip)
    ) else "failed"
    if ubuntu_local_only_skip:
        targets["ubuntu"]["accepted_skip_reason"] = "local_only_non_promoting_run"
    if windows_optional_skip:
        targets["windows"]["accepted_skip_reason"] = "optional_non_promoting_run"
    artifact = {
        "schema": "ao2-control-plane.three-os-release-smoke.v1",
        "status": status,
        "version": version,
        "release_candidate_version": release_candidate_version,
        "source_commit": source_commit,
        "source_dirty": source_dirty,
        "summary": str(summary_path),
        "report": str(args.out_dir / "nightly-ao2-advancement.md"),
        "targets": targets,
        "source": {
            "schema": summary.get("schema"),
            "bridge_log": (
                summary.get("source", {}).get("bridge_log", "")
                if isinstance(summary.get("source"), dict)
                else ""
            ),
        },
    }
    observer_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_three_os_smoke_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_three_os_smoke_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    smoke_path = nightly_three_os_smoke_observer_path(args)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    common = {
        "schema": "ao-operator/ao2-three-os-smoke-publish/v1",
        "three_os_smoke_artifact": str(smoke_path),
        "observer_links": phase1_promotion_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for three-OS smoke publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not smoke_path.is_file():
        artifact = {
            **common,
            "status": "failed",
            "error": f"missing three-OS smoke observer artifact: {smoke_path}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    raw = smoke_path.read_bytes()
    try:
        smoke = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": f"three-OS smoke observer artifact is not valid JSON: {exc}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    schema = str(smoke.get("schema") or smoke.get("schema_version") or "")
    if schema != "ao2-control-plane.three-os-release-smoke.v1":
        artifact = {
            **common,
            "status": "failed",
            "error": f"unsupported three-OS smoke schema: {schema or '<missing>'}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    links = phase1_promotion_observer_links(args)
    smoke_url = links.get("three_os_smoke", "")
    request = urllib.request.Request(
        smoke_url,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except urllib.error.URLError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": str(exc.reason),
            "control_plane_url": smoke_url,
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    try:
        receipt = json.loads(response_body)
    except json.JSONDecodeError:
        receipt = {
            "status": "unreadable",
            "response": redact_nightly_log_output(response_body),
        }
    observer_dashboard = (
        fetch_phase1_promotion_observer_dashboard(args, token)
        if 200 <= status_code < 300
        else {"status": "skipped", "reason": "three-OS smoke publish did not return 2xx"}
    )
    artifact = {
        **common,
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "control_plane_url": smoke_url,
        "receipt": sanitize_for_nightly_artifact(receipt),
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = sanitize_for_nightly_artifact(observer_dashboard["snapshot"])
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_planned_phase1_promotion_decision_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    decision = {
        "schema": "ao-operator/ao2-phase1-promotion-decision/v1",
        "status": "planned",
        "decision": "planned",
        "phase1_state": "planned",
        "message": "Dry-run only. The real step signs and publishes the release-line decision after the checklist is observed.",
    }
    nightly_phase1_promotion_decision_path(args).write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact = {
        "schema": "ao-operator/ao2-phase1-promotion-decision-publish/v1",
        "status": "planned",
        "decision_artifact": str(nightly_phase1_promotion_decision_path(args)),
        "checklist_publish_artifact": str(nightly_phase1_promotion_checklist_publish_path(args)),
        "control_plane_url": str(getattr(args, "provider_registry_control_plane_url", "")),
        "signer_id": str(getattr(args, "phase1_decision_signer_id", "ao2-phase1-release")),
        "observer_links": phase1_promotion_observer_links(args),
    }
    nightly_phase1_promotion_decision_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_phase1_promotion_history_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": "ao2.phase1-promotion-history-control-plane-fetch.v1",
        "status": "planned",
        "history_artifact": str(args.out_dir / "phase1-promotion-history.json"),
        "observer_links": phase1_promotion_observer_links(args),
        "trust_boundary": {
            "role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
        },
    }
    nightly_phase1_promotion_history_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_phase1_promotion_status_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "phase1-promotion-status",
        "status": "planned",
        "operator_status": {
            "state": "planned",
            "next_action": "run the guarded nightly advancement to fetch control-plane Phase 1 promotion history",
        },
        "links": phase1_promotion_observer_links(args),
        "trust_boundary": {
            "mode": "phase1_promotion_history_read_only",
            "hermes_role": "front_end_queue_cron_and_memory_surface",
            "ao2_role": "trusted_execution_memory_and_signed_evidence_boundary",
            "factory_v3_role": "contracts_profiles_role_discipline_and_evaluator_closure",
            "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
        },
    }
    nightly_phase1_promotion_status_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_phase1_promotion_panel_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/hermes-phase1-promotion-panel/v1",
        "action": "phase1-promotion-panel",
        "status": "planned",
        "summary": "AO2 Phase 1 promotion panel is planned until the guarded run fetches live observer history",
        "operator_status": {
            "state": "planned",
            "next_action": "run the guarded nightly advancement to fetch control-plane Phase 1 promotion history",
        },
        "badges": {
            "checklist": "planned",
            "signed_decision": "planned",
            "signature": "planned",
            "three_os": "planned",
        },
        "links": phase1_promotion_observer_links(args),
        "next_action": "run the guarded nightly advancement to fetch control-plane Phase 1 promotion history",
        "trust_boundary": {
            "mode": "operator_panel_from_read_only_phase1_status",
            "hermes_role": "front_end_queue_cron_and_memory_surface",
            "ao2_role": "trusted_execution_memory_and_signed_evidence_boundary",
            "factory_v3_role": "contracts_profiles_role_discipline_and_evaluator_closure",
            "control_plane_role": "read_only_observer_for_signed_evidence_and_memory_exports",
        },
        "source": {
            "schema": "ao-operator/hermes-ao-bridge/v1",
            "action": "phase1-promotion-status",
            "status": "planned",
        },
    }
    nightly_phase1_promotion_panel_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# AO2 Phase 1 Operator Panel",
        "",
        "- status: `planned`",
        "- state: `planned`",
        "- next_action: `run the guarded nightly advancement to fetch control-plane Phase 1 promotion history`",
        "",
    ]
    nightly_phase1_promotion_panel_markdown_path(args).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return artifact


def release_publication_artifact_candidates(args: argparse.Namespace) -> tuple[list[Path], str]:
    explicit = getattr(args, "release_publication_artifact", None)
    if explicit:
        return [Path(explicit)], "explicit"
    candidates_root = Path(getattr(args, "ao2_root", Path("."))) / "run-artifacts" / "release-candidates"
    if not candidates_root.is_dir():
        return [], "auto_discovered"
    candidates: list[tuple[int, str, Path]] = []
    for candidate in candidates_root.glob("v*-phase1-release.json"):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            modified = candidate.stat().st_mtime_ns
        except (OSError, json.JSONDecodeError):
            continue
        schema = str(payload.get("schema") or payload.get("schema_version") or "")
        if schema != "ao2.release-publication-summary.v1":
            continue
        if payload.get("status") != "published_verified":
            continue
        if release_publication_head_freshness(payload, args).get("status") == "blocked":
            continue
        candidates.append((modified, str(candidate), candidate))
    candidates.sort(reverse=True)
    return [candidates[0][2]] if candidates else [], "auto_discovered"


def release_publication_candidate_freshness_reports(
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    explicit = getattr(args, "release_publication_artifact", None)
    if explicit:
        paths = [Path(explicit)]
    else:
        candidates_root = (
            Path(getattr(args, "ao2_root", Path(".")))
            / "run-artifacts"
            / "release-candidates"
        )
        paths = sorted(candidates_root.glob("v*-phase1-release.json")) if candidates_root.is_dir() else []
    reports = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            reports.append(
                {
                    "path": str(path),
                    "status": "unreadable",
                    "error": str(exc),
                }
            )
            continue
        schema = str(payload.get("schema") or payload.get("schema_version") or "")
        if schema != "ao2.release-publication-summary.v1":
            continue
        if payload.get("status") != "published_verified":
            continue
        reports.append(
            {
                "path": str(path),
                "release_tag": str(payload.get("release_tag") or ""),
                "head_freshness": release_publication_head_freshness(payload, args),
            }
        )
    return reports


def release_publication_expected_repo_heads(args: argparse.Namespace) -> dict[str, str]:
    roots = {
        "ao2": getattr(args, "ao2_root", None),
        "factory_v3": getattr(args, "factory_root", None),
        "ao2_control_plane": getattr(args, "ao2_control_plane", None),
    }
    expected: dict[str, str] = {}
    for repo, root in roots.items():
        if root is None:
            continue
        head, _dirty = git_revision_status(Path(root))
        if not head.startswith("nogit:"):
            expected[repo] = head
    return expected


def nested_release_publication_str(
    payload: dict[str, Any], *keys: str, default: str = "missing"
) -> str:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    if isinstance(current, str) and current:
        return current
    return default


def release_publication_ao2_metadata_refresh(
    repo: str, observed: str, expected: str, args: argparse.Namespace
) -> dict[str, Any] | None:
    if repo != "ao2" or observed == expected:
        return None
    root_value = getattr(args, "ao2_root", None)
    if root_value is None:
        return None
    root = Path(root_value)
    try:
        subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", observed, expected],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", f"{observed}..{expected}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None
    allowed_prefixes = ("run-artifacts/release-candidates/",)
    changed_paths = [line.strip() for line in diff if line.strip()]
    if not changed_paths:
        return None
    disallowed = [
        path for path in changed_paths if not path.startswith(allowed_prefixes)
    ]
    if disallowed:
        return None
    return {
        "status": "passed_with_metadata_refresh",
        "changed_paths": changed_paths,
        "reason": "ao2 HEAD advanced only by release-candidate metadata refresh files",
    }


def release_publication_head_freshness(
    payload: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    expected = release_publication_expected_repo_heads(args)
    checks = []
    for repo, expected_head in sorted(expected.items()):
        observed = nested_release_publication_str(
            payload, "repositories", repo, "head"
        )
        metadata_refresh = release_publication_ao2_metadata_refresh(
            repo, observed, expected_head, args
        )
        check = {
            "id": f"repo_head_{repo}",
            "repo": repo,
            "observed": observed,
            "expected": expected_head,
            "status": "passed" if observed == expected_head else "blocked",
        }
        if metadata_refresh is not None:
            check.update(metadata_refresh)
        checks.append(check)
    blockers = [
        f"{item['id']}: expected {item['expected']}, observed {item['observed']}"
        for item in checks
        if not str(item["status"]).startswith("passed")
    ]
    return {
        "schema": "ao-operator/ao2-release-publication-head-freshness/v1",
        "status": "not_checked" if not checks else ("passed" if not blockers else "blocked"),
        "checks": checks,
        "blockers": blockers,
    }


def write_planned_release_publication_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    candidates, source = release_publication_artifact_candidates(args)
    artifact = {
        "schema": "ao-operator/ao2-release-publication-publish/v1",
        "status": "planned",
        "release_publication_artifact_source": source,
        "release_publication_artifact": str(candidates[0]) if candidates else "",
        "release_publication_candidate_freshness": release_publication_candidate_freshness_reports(args),
        "observer_links": release_publication_observer_links(args),
    }
    nightly_release_publication_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_cockpit_status_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    links = release_publication_observer_links(args)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-cockpit-status",
        "status": "planned",
        "trust_boundary": {"mode": "release_cockpit_read_only"},
        "links": {
            "cockpit": links.get("cockpit", ""),
            "cockpit_json": links.get("cockpit_json", ""),
            "release_publication_dashboard": links.get("dashboard", ""),
        },
        "frontend_status": {
            "status": "planned",
            "next_action": "fetch ao2-control-plane release cockpit JSON after observer evidence is published",
        },
    }
    nightly_release_cockpit_status_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_handoff_status_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    links = release_publication_observer_links(args)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-handoff-status",
        "status": "planned",
        "trust_boundary": {"mode": "release_handoff_read_only"},
        "links": {
            "release_candidate_handoff": links.get("handoff", ""),
            "release_candidate_handoff_json": links.get("handoff_json", ""),
            "cockpit_json": links.get("cockpit_json", ""),
        },
        "frontend_status": {
            "status": "planned",
            "next_action": "fetch ao2-control-plane release-candidate handoff after observer evidence is published",
        },
    }
    nightly_release_handoff_status_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_handoff_checklist_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-release-handoff-checklist/v1",
        "status": "planned",
        "release": {},
        "checks": [
            {
                "id": "handoff_available",
                "label": "Handoff available",
                "observed": "planned",
                "expected": "ready",
                "status": "blocked",
            }
        ],
        "blockers": [],
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
    }
    nightly_release_handoff_checklist_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nightly_release_handoff_checklist_markdown_path(args).write_text(
        "\n".join(
            [
                "# AO2 Release Handoff Checklist",
                "",
                "- status: `planned`",
                "- evaluator_closer_required: `True`",
                "- control_plane_approves_release: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return artifact


def write_planned_release_readiness_status_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    links = release_publication_observer_links(args)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-readiness-status",
        "status": "planned",
        "trust_boundary": {"mode": "release_readiness_read_only"},
        "links": {
            "release_readiness": links.get("readiness", ""),
            "release_readiness_json": links.get("readiness_json", ""),
            "release_candidate_handoff": links.get("handoff", ""),
        },
        "frontend_status": {
            "status": "planned",
            "next_action": "fetch ao2-control-plane release-readiness after observer evidence is published",
        },
    }
    nightly_release_readiness_status_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_support_bundle_status_artifact(
    args: argparse.Namespace,
    *,
    output_path: Path | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    links = release_publication_observer_links(args)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-support-bundle-status",
        "status": "planned",
        "trust_boundary": {"mode": "release_support_bundle_read_only"},
        "links": {
            "release_support_bundle_json": links.get("support_bundle_json", ""),
            "release_readiness_json": links.get("readiness_json", ""),
            "release_candidate_handoff_json": links.get("handoff_json", ""),
        },
        "frontend_status": {
            "status": "planned",
            "release_candidate_version": "unknown",
            "candidate_correlation": "unknown",
            "required_artifact_count": 0,
            "missing_artifact_count": 0,
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "next_action": "fetch release support bundle assembly after observer evidence is published",
        },
    }
    if phase:
        artifact["phase"] = phase
        artifact["frontend_status"][
            "next_action"
        ] = "refresh release support bundle after evaluator decision publication"
    (output_path or nightly_release_support_bundle_status_path(args)).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_evaluator_decision_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-release-evaluator-decision/v1",
        "status": "planned",
        "decision": "planned",
        "release": {},
        "checks": [],
        "blockers": [],
        "evidence": {
            "release_readiness_status": str(nightly_release_readiness_status_path(args)),
            "release_handoff_checklist": str(nightly_release_handoff_checklist_path(args)),
            "release_support_bundle_status": str(nightly_release_support_bundle_status_path(args)),
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
        "next_action": "dry-run only; evaluate readiness and handoff checklist after live observer evidence is fetched",
    }
    nightly_release_evaluator_decision_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nightly_release_evaluator_decision_markdown_path(args).write_text(
        "\n".join(
            [
                "# AO2 Release Evaluator Decision",
                "",
                "- status: `planned`",
                "- decision: `planned`",
                "- release_acceptance_owner: `ao-operator evaluator-closer`",
                "- control_plane_approves_release: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return artifact


def write_planned_release_evaluator_decision_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-release-evaluator-decision-publish/v1",
        "status": "planned",
        "release_evaluator_decision_artifact": str(nightly_release_evaluator_decision_path(args)),
        "observer_links": release_publication_observer_links(args),
    }
    nightly_release_evaluator_decision_publish_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_evaluator_decision_status_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    links = release_publication_observer_links(args)
    artifact = {
        "schema": "ao-operator/hermes-ao-bridge/v1",
        "action": "release-evaluator-decision-status",
        "status": "planned",
        "trust_boundary": {"mode": "release_evaluator_decision_read_only"},
        "links": {
            "latest_release_evaluator_decision": links.get(
                "evaluator_decision_latest",
                "",
            ),
            "release_evaluator_decision_dashboard": links.get(
                "evaluator_decision_dashboard",
                "",
            ),
            "release_evaluator_decision_dashboard_json": links.get(
                "evaluator_decision_dashboard_json",
                "",
            ),
        },
        "frontend_status": {
            "status": "planned",
            "state": "planned",
            "decision": "planned",
            "control_plane_approves_release": False,
            "release_acceptance_owner": "ao-operator evaluator-closer",
            "next_action": "fetch ao2-control-plane evaluator decision dashboard after ao-operator publishes the signed decision",
        },
    }
    nightly_release_evaluator_decision_status_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_factory_compat_nightly_run_summary_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = nightly_factory_compat_nightly_run_summary_path(args)
    artifact = {
        "schema_version": "ao-operator/ao2-factory-compat-nightly-run/v1",
        "status": "missing_inputs",
        "stage": "preflight",
        "missing": ["dry_run"],
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-governed-run",
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "factory_target": str(nightly_factory_compat_target_path(args)),
        "evidence_pack_path": None,
        "inputs": {
            "ao2_binary": str(ao2_release_bin(args)),
            "ao2_binary_resolved": None,
            "ao2_fixture": str(nightly_factory_compat_fixture_path(args)),
            "factory_target": str(nightly_factory_compat_target_path(args)),
            "run_id": NIGHTLY_FACTORY_COMPAT_RUN_ID,
            "signing_key": None,
            "signer_id": None,
            "runspec_id": "nightly-factory-compat",
            "runspec_verifier": "python -m pytest -q",
            "ao_operator_runspec": None,
            "bridge_evidence_out": None,
            "hermes_context_out": None,
            "hermes_context_slug": NIGHTLY_FACTORY_COMPAT_RUN_ID,
            "control_plane_receipt": None,
            "memory_record_out": None,
            "memory_record_target": None,
            "memory_record_kind": None,
            "memory_record_title": None,
            "memory_record_body": None,
            "require_all_ao2_ref_categories": False,
        },
        "bridge_evidence": None,
        "hermes_context_with_ao2_refs": None,
        "memory_record": None,
        "next_action": (
            "dry-run only; execute the nightly orchestrator so AO2 drives "
            "its native factory governed-run command and the "
            "downstream evidence-pack producer consumes a populated "
            "factory-compat target"
        ),
    }
    summary_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_ao2_native_evidence_pack_producer_summary_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pack_path = nightly_release_ao2_native_evidence_pack_path(args)
    summary_path = nightly_release_ao2_native_evidence_pack_producer_summary_path(args)
    artifact = {
        "schema_version": "ao-operator/ao2-release-ao2-native-evidence-pack-producer/v1",
        "status": "missing_inputs",
        "missing": ["dry_run", "ao2_factory_queue_completed_entry"],
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-governed-run",
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "evidence_pack_path": str(pack_path),
        "evidence_pack_schema": "ao2.evidence-pack.v1",
        "evidence_pack_emitted": False,
        "next_action": (
            "dry-run only; run `ao2 factory governed-run` against the AO2 "
            "governed target so AO2 emits a real ao2.evidence-pack.v1 for the "
            "nightly evaluator-decision producer"
        ),
    }
    summary_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_ao2_native_evaluator_producer_summary_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    decision_path = nightly_release_ao2_native_evaluator_producer_decision_path(args)
    summary_path = nightly_release_ao2_native_evaluator_producer_summary_path(args)
    artifact = {
        "schema_version": "ao-operator/ao2-release-ao2-native-evaluator-producer/v1",
        "status": "missing_inputs",
        "missing": [
            "dry_run",
            "evidence_pack",
            "ao2_native_evidence_pack_producer_status_missing_inputs",
        ],
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-evaluator-closer",
        "control_plane_role": "read_only_observer",
        "ao2_native_decision_path": str(decision_path),
        "ao2_native_decision_schema": "ao2.ao-operator-compat-native-evaluator-result.v1",
        "ao2_native_decision_emitted": False,
        "next_action": (
            "dry-run only; wire an AO2 evidence pack into the nightly pipeline "
            "so 'ao2 factory evaluate' can emit a real AO2 native evaluator decision"
        ),
    }
    summary_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_ao2_native_evaluator_verification_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    producer_summary_path = nightly_release_ao2_native_evaluator_producer_summary_path(
        args
    )
    artifact = {
        "schema_version": "ao2.ao-operator-compat-native-evaluator-verification.v1",
        "status": "missing_inputs",
        "missing": ["dry_run", "ao2_producer_status_missing_inputs"],
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-native-evaluator-decision-verifier",
        "control_plane_role": "read_only_observer",
        "trust_boundary_ok": False,
        "signature_status": "missing",
        "signature_verified": False,
        "signature_requirement_satisfied": False,
        "verdict": {
            "status": "missing_inputs",
            "factory_v3_required_to_decide": False,
            "owner": "ao2-native-evaluator-decision-verifier",
        },
        "inputs": {
            "ao2_producer_summary": str(producer_summary_path),
        },
        "producer": {
            "status": "missing_inputs",
            "missing": ["dry_run"],
        },
        "next_action": (
            "dry-run only; wire an AO2 native evaluator decision into the "
            "nightly pipeline before AO2 can verify it"
        ),
    }
    nightly_release_ao2_native_evaluator_verification_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def write_planned_release_evaluator_closure_with_ao2_verification_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "ao-operator/ao2-release-evaluator-closure-with-ao2-verification/v1",
        "status": "planned",
        "decision": "planned",
        "release": {},
        "factory_v3_decision": {
            "status": "planned",
            "decision": "planned",
            "blockers": [],
        },
        "ao2_verification": {
            "status": "missing_inputs",
            "missing": ["dry_run"],
            "factory_v3_role": "parity_oracle_only",
            "ao2_decision_owner": "ao2-native-evaluator-decision-verifier",
            "control_plane_role": "read_only_observer",
        },
        "blockers": [],
        "evidence": {
            "factory_v3_decision_path": str(
                nightly_release_evaluator_decision_path(args)
            ),
            "ao2_verification_path": str(
                nightly_release_ao2_native_evaluator_verification_path(args)
            ),
        },
        "trust_boundary": {
            "frontend": "Hermes front end / queue / memory surface",
            "governed_backend": "ao-operator / AO Operator compat closer",
            "trusted_execution": "ao2 signed evidence boundary",
            "closure_decision_owner": "ao2_native_evaluator_decision_verifier",
            "factory_v3_role": "compat_closer_consumes_ao2_verdict",
            "control_plane_role": "read_only_observer",
            "mutates_ao_artifacts": False,
            "control_plane_approves_release": False,
        },
        "next_action": (
            "dry-run only; the closer will block until an AO2 native evaluator "
            "verification artifact is wired into the nightly pipeline"
        ),
    }
    nightly_release_evaluator_closure_with_ao2_verification_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nightly_release_evaluator_closure_with_ao2_verification_markdown_path(
        args
    ).write_text(
        "\n".join(
            [
                "# AO2 Release Evaluator Closure (with AO2 verification)",
                "",
                "- status: `planned`",
                "- decision: `planned`",
                "- closure_decision_owner: `ao2_native_evaluator_decision_verifier`",
                "- factory_v3_role: `compat_closer_consumes_ao2_verdict`",
                "- control_plane_approves_release: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return artifact


def write_release_publication_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_release_publication_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    candidates, source = release_publication_artifact_candidates(args)
    publication_path = candidates[0] if candidates else Path()
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    common = {
        "schema": "ao-operator/ao2-release-publication-publish/v1",
        "release_publication_artifact_source": source,
        "release_publication_artifact": str(publication_path) if candidates else "",
        "release_publication_candidate_freshness": release_publication_candidate_freshness_reports(args),
        "observer_links": release_publication_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for release-publication publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not candidates or not publication_path.is_file():
        artifact = {
            **common,
            "status": "skipped",
            "reason": "No AO2 release-publication summary artifact is available to publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    raw = publication_path.read_bytes()
    try:
        publication = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": f"release-publication artifact is not valid JSON: {exc}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    schema = str(publication.get("schema") or publication.get("schema_version") or "")
    if schema != "ao2.release-publication-summary.v1":
        artifact = {
            **common,
            "status": "failed",
            "error": f"unsupported release-publication schema: {schema or '<missing>'}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    freshness = release_publication_head_freshness(publication, args)
    common = {**common, "release_publication_head_freshness": freshness}
    if freshness.get("status") == "blocked":
        artifact = {
            **common,
            "status": "failed",
            "error": "release-publication repository heads are stale",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    links = release_publication_observer_links(args)
    publication_url = links.get("publication", "")
    request = urllib.request.Request(
        publication_url,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except urllib.error.URLError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": str(exc.reason),
            "control_plane_url": publication_url,
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    try:
        receipt = json.loads(response_body)
    except json.JSONDecodeError:
        receipt = {
            "status": "unreadable",
            "response": redact_nightly_log_output(response_body),
        }
    observer_dashboard = (
        fetch_release_publication_observer_dashboard(args, token)
        if 200 <= status_code < 300
        else {"status": "skipped", "reason": "release-publication publish did not return 2xx"}
    )
    artifact = {
        **common,
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "control_plane_url": publication_url,
        "release_tag": str(publication.get("release_tag") or ""),
        "receipt": sanitize_for_nightly_artifact(receipt),
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = sanitize_for_nightly_artifact(observer_dashboard["snapshot"])
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_release_evaluator_decision_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_release_evaluator_decision_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path = nightly_release_evaluator_decision_path(args)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    common = {
        "schema": "ao-operator/ao2-release-evaluator-decision-publish/v1",
        "release_evaluator_decision_artifact": str(decision_path),
        "observer_links": release_publication_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for release evaluator decision publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not decision_path.is_file():
        artifact = {
            **common,
            "status": "failed",
            "error": f"missing release evaluator decision artifact: {decision_path}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    raw = decision_path.read_bytes()
    try:
        decision = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": f"release evaluator decision artifact is not valid JSON: {exc}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    schema = str(decision.get("schema") or decision.get("schema_version") or "")
    if schema != "ao-operator/ao2-release-evaluator-decision/v1":
        artifact = {
            **common,
            "status": "failed",
            "error": f"unsupported release evaluator decision schema: {schema or '<missing>'}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    links = release_publication_observer_links(args)
    decision_url = links.get("evaluator_decision", "")
    request = urllib.request.Request(
        decision_url,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except urllib.error.URLError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": str(exc.reason),
            "control_plane_url": decision_url,
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    try:
        receipt = json.loads(response_body)
    except json.JSONDecodeError:
        receipt = {
            "status": "unreadable",
            "response": redact_nightly_log_output(response_body),
        }
    observer_dashboard = (
        fetch_release_evaluator_decision_observer_dashboard(args, token)
        if 200 <= status_code < 300
        else {"status": "skipped", "reason": "release evaluator decision publish did not return 2xx"}
    )
    release = decision.get("release", {})
    release_tag = release.get("release_tag") if isinstance(release, dict) else ""
    artifact = {
        **common,
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "control_plane_url": decision_url,
        "decision": str(decision.get("decision") or ""),
        "release_tag": str(release_tag or ""),
        "receipt": sanitize_for_nightly_artifact(receipt),
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = sanitize_for_nightly_artifact(observer_dashboard["snapshot"])
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_phase1_promotion_checklist_markdown(artifact: dict[str, Any], path: Path) -> None:
    checklist = artifact.get("checklist", {})
    lines = [
        "# AO2 Phase 1 Promotion Checklist",
        "",
        f"- status: `{artifact.get('status', 'unknown')}`",
        f"- phase1_state: `{artifact.get('phase1_state', 'unknown')}`",
        f"- next_action: `{artifact.get('next_action', 'unknown')}`",
        "",
        "## Checks",
        "",
    ]
    if isinstance(checklist, dict):
        for key in ("provider_readiness", "live_provider_acceptance", "release_gate", "three_os_smoke"):
            item = checklist.get(key, {})
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"### {key}",
                    "",
                    f"- status: `{item.get('status', 'unknown')}`",
                ]
            )
            for field in (
                "phase1_state",
                "state",
                "codex",
                "claude",
                "source_class",
                "observer_publish_status",
                "observer_receipt_sha256",
                "observer_latest_url",
            ):
                if item.get(field) is not None:
                    lines.append(f"- {field}: `{item[field]}`")
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_phase1_promotion_checklist_artifact(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    provider_publish = load_json_artifact(nightly_provider_phase1_readiness_publish_path(args))
    provider_acceptance_publish = load_json_artifact(nightly_provider_acceptance_publish_path(args))
    release_gate = load_json_artifact(nightly_release_gate_dry_run_path(args))
    enriched_summary = load_json_artifact(nightly_enriched_release_summary_path(args))
    three_os_publish_path = nightly_three_os_smoke_publish_path(args)
    three_os_publish = (
        load_json_artifact(three_os_publish_path)
        if three_os_publish_path.is_file()
        else {"status": "missing"}
    )

    provider_phase1 = (
        provider_publish.get("observer_dashboard_snapshot", {}).get("phase1_status", {})
        if isinstance(provider_publish, dict)
        else {}
    )
    acceptance_phase1 = (
        provider_acceptance_publish.get("observer_dashboard_snapshot", {}).get("phase1_acceptance", {})
        if isinstance(provider_acceptance_publish, dict)
        else {}
    )
    require_remotes = bool(getattr(args, "require_remotes", False))
    linux_status = enriched_summary.get("linux_x86_64_remote_smoke")
    linux_evidence = enriched_summary.get("linux_x86_64_remote_evidence", {})
    linux_local_only_skip = (
        not require_remotes
        and linux_status == "skipped"
        and isinstance(linux_evidence, dict)
        and linux_evidence.get("reason") == "local_only"
    )
    windows_required = bool(enriched_summary.get("native_windows_required") or require_remotes)
    windows_status = enriched_summary.get("windows_native_smoke")
    windows_optional_skip = not windows_required and windows_status == "skipped"
    three_os_passed = (
        enriched_summary.get("local_smoke") == "passed"
        and (linux_status == "passed" or linux_local_only_skip)
        and (windows_status == "passed" or windows_optional_skip)
    )
    acceptance_passed = (
        provider_acceptance_publish.get("status") == "passed"
        and acceptance_phase1.get("state") == "live_acceptance_complete"
        and acceptance_phase1.get("source_class") == "live"
    )
    release_gate_passed = release_gate.get("status") == "passed"
    readiness_observed = provider_publish.get("status") == "passed" and bool(provider_phase1)
    readiness_phase1_state = provider_phase1.get("state", "unknown")
    readiness_superseded = (
        readiness_observed
        and acceptance_passed
        and readiness_phase1_state not in {"ready", "live_acceptance_complete"}
    )
    readiness_satisfied = readiness_observed and (
        readiness_phase1_state in {"ready", "live_acceptance_complete"} or readiness_superseded
    )
    candidate_ready = all(
        [readiness_satisfied, acceptance_passed, release_gate_passed, three_os_passed]
    )
    # Phase 1 promotion evidence is intentionally stricter than the normal AO2
    # solidification/nightly advancement path: a run can prove the AO2 release
    # gate and three-OS smoke while live provider acceptance publication remains
    # unavailable because the local control-plane token or guarded live provider
    # pilots were not supplied. Treat that case as a rendered, non-promoting
    # blocked checklist instead of a failed backend step so downstream evaluator
    # handoff/status artifacts still materialize. Hard release/smoke failures stay
    # failed and continue to stop the governed run.
    promotion_evidence_blocked = (
        not candidate_ready and release_gate_passed and three_os_passed
    )
    status = (
        "passed"
        if candidate_ready
        else "blocked"
        if promotion_evidence_blocked
        else "failed"
    )
    phase1_state = "phase1_candidate_ready" if status == "passed" else "evidence_incomplete"
    artifact = {
        "schema": "ao-operator/ao2-phase1-promotion-checklist/v1",
        "status": status,
        "phase1_state": phase1_state,
        "next_action": (
            "operator release-line decision: ship current AO2 Phase 1 candidate or bump patch before final release"
            if status == "passed"
            else "collect missing provider, release gate, or three-OS evidence before Phase 1 promotion"
        ),
        "checklist": {
            "provider_readiness": {
                "status": (
                    "superseded_by_live_acceptance"
                    if readiness_superseded
                    else "observed"
                    if readiness_observed
                    else "missing"
                ),
                "phase1_state": readiness_phase1_state,
                "reason": provider_phase1.get("reason", "unknown"),
                "superseded_by": (
                    "live_provider_acceptance" if readiness_superseded else None
                ),
            },
            "live_provider_acceptance": {
                "status": "passed" if acceptance_passed else "failed",
                "state": acceptance_phase1.get("state", "unknown"),
                "codex": acceptance_phase1.get("codex", "unknown"),
                "claude": acceptance_phase1.get("claude", "unknown"),
                "source_class": acceptance_phase1.get("source_class", "unknown"),
            },
            "release_gate": {
                "status": release_gate.get("status", "missing"),
                "state": "dry_run_passed" if release_gate_passed else "not_ready",
            },
            "three_os_smoke": {
                "status": "passed" if three_os_passed else "failed",
                "local_smoke": enriched_summary.get("local_smoke", "unknown"),
                "linux_x86_64_remote_smoke": linux_status or "unknown",
                "linux_x86_64_remote_accepted_skip_reason": (
                    "local_only_non_promoting_run" if linux_local_only_skip else None
                ),
                "windows_native_smoke": windows_status or "unknown",
                "windows_native_accepted_skip_reason": (
                    "optional_non_promoting_run" if windows_optional_skip else None
                ),
                "native_windows_required": windows_required,
                "observer_publish_status": three_os_publish.get("status", "missing"),
                "observer_receipt_sha256": (
                    three_os_publish.get("receipt", {}).get("sha256")
                    if isinstance(three_os_publish.get("receipt"), dict)
                    else None
                ),
                "observer_latest_url": phase1_promotion_observer_links(args).get("latest_three_os_smoke"),
            },
        },
        "artifacts": {
            "provider_readiness_publish": str(nightly_provider_phase1_readiness_publish_path(args)),
            "provider_acceptance_publish": str(nightly_provider_acceptance_publish_path(args)),
            "release_gate_dry_run": str(nightly_release_gate_dry_run_path(args)),
            "enriched_release_summary": str(nightly_enriched_release_summary_path(args)),
            "three_os_smoke_observer": str(nightly_three_os_smoke_observer_path(args)),
            "three_os_smoke_publish": str(nightly_three_os_smoke_publish_path(args)),
            "markdown": str(nightly_phase1_promotion_checklist_markdown_path(args)),
        },
    }
    nightly_phase1_promotion_checklist_path(args).write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_phase1_promotion_checklist_markdown(
        artifact, nightly_phase1_promotion_checklist_markdown_path(args)
    )
    return artifact


def write_phase1_promotion_checklist_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_phase1_promotion_checklist_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    checklist_path = nightly_phase1_promotion_checklist_path(args)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    common = {
        "schema": "ao-operator/ao2-phase1-promotion-checklist-publish/v1",
        "checklist_artifact": str(checklist_path),
        "observer_links": phase1_promotion_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for Phase 1 promotion checklist publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not checklist_path.is_file():
        artifact = {
            **common,
            "status": "failed",
            "error": f"missing Phase 1 promotion checklist artifact: {checklist_path}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    raw = checklist_path.read_bytes()
    try:
        checklist = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": f"Phase 1 promotion checklist is not valid JSON: {exc}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    schema = str(checklist.get("schema") or checklist.get("schema_version") or "")
    if schema != "ao-operator/ao2-phase1-promotion-checklist/v1":
        artifact = {
            **common,
            "status": "failed",
            "error": f"unsupported Phase 1 promotion checklist schema: {schema or '<missing>'}",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    links = phase1_promotion_observer_links(args)
    checklist_url = links.get("checklist", "")
    request = urllib.request.Request(
        checklist_url,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except urllib.error.URLError as exc:
        artifact = {
            **common,
            "status": "failed",
            "error": str(exc.reason),
            "control_plane_url": checklist_url,
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact

    try:
        receipt = json.loads(response_body)
    except json.JSONDecodeError:
        receipt = {
            "status": "unreadable",
            "response": redact_nightly_log_output(response_body),
        }
    observer_dashboard = (
        fetch_phase1_promotion_observer_dashboard(args, token)
        if 200 <= status_code < 300
        else {"status": "skipped", "reason": "Phase 1 promotion checklist publish did not return 2xx"}
    )
    artifact = {
        **common,
        "status": "passed" if 200 <= status_code < 300 else "failed",
        "status_code": status_code,
        "control_plane_url": checklist_url,
        "receipt": sanitize_for_nightly_artifact(receipt),
        "observer_dashboard_status": observer_dashboard.get("status", "unknown"),
    }
    if "status_code" in observer_dashboard:
        artifact["observer_dashboard_status_code"] = observer_dashboard["status_code"]
    if "snapshot" in observer_dashboard:
        artifact["observer_dashboard_snapshot"] = sanitize_for_nightly_artifact(observer_dashboard["snapshot"])
    if observer_dashboard.get("error"):
        artifact["observer_dashboard_error"] = observer_dashboard["error"]
    if observer_dashboard.get("reason"):
        artifact["observer_dashboard_reason"] = observer_dashboard["reason"]
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def write_phase1_promotion_decision_publish_artifact(args: argparse.Namespace) -> dict[str, Any]:
    publish_path = nightly_phase1_promotion_decision_publish_path(args)
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path = nightly_phase1_promotion_decision_path(args)
    checklist_path = nightly_phase1_promotion_checklist_path(args)
    checklist_publish_path = nightly_phase1_promotion_checklist_publish_path(args)
    token = os.environ.get("AO2_CP_API_TOKEN", "")
    signing_key = Path(getattr(args, "phase1_decision_signing_key", ""))
    common = {
        "schema": "ao-operator/ao2-phase1-promotion-decision-publish/v1",
        "decision_artifact": str(decision_path),
        "checklist_artifact": str(checklist_path),
        "checklist_publish_artifact": str(checklist_publish_path),
        "observer_links": phase1_promotion_observer_links(args),
    }
    if not token:
        artifact = {
            **common,
            "status": "skipped",
            "reason": "AO2_CP_API_TOKEN is required for signed Phase 1 promotion decision publish",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    if not signing_key.is_file():
        artifact = {
            **common,
            "status": "skipped",
            "reason": "Phase 1 promotion decision signing key is missing",
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    checklist = load_json_artifact(checklist_path) if checklist_path.is_file() else {}
    checklist_publish = (
        load_json_artifact(checklist_publish_path) if checklist_publish_path.is_file() else {}
    )
    checklist_sha = (
        checklist_publish.get("receipt", {}).get("sha256")
        if isinstance(checklist_publish.get("receipt"), dict)
        else None
    )
    if (
        checklist.get("status") != "passed"
        or checklist.get("phase1_state") != "phase1_candidate_ready"
        or not isinstance(checklist_sha, str)
        or len(checklist_sha) != 64
    ):
        artifact = {
            **common,
            "status": "failed",
            "error": "Phase 1 promotion decision requires a passed checklist and observed checklist sha256",
            "checklist_status": checklist.get("status", "missing"),
            "checklist_phase1_state": checklist.get("phase1_state", "missing"),
        }
        publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return artifact
    decision = {
        "schema": "ao-operator/ao2-phase1-promotion-decision/v1",
        "status": "passed",
        "decision": "promote_phase1_candidate",
        "phase1_state": "phase1_candidate_ready",
        "checklist_sha256": checklist_sha,
        "operator": str(getattr(args, "phase1_decision_signer_id", "ao2-phase1-release")),
        "rationale": "All required Phase 1 checklist evidence is present and observed by ao2-control-plane.",
        "artifacts": {
            "phase1_promotion_checklist": str(checklist_path),
            "phase1_promotion_checklist_publish": str(checklist_publish_path),
        },
    }
    decision_path.write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    command = [
        str(ao2_release_bin(args)),
        "release",
        "phase1-decision-publish",
        "--decision",
        str(decision_path),
        "--signing-key",
        str(signing_key),
        "--signer-id",
        str(getattr(args, "phase1_decision_signer_id", "ao2-phase1-release")),
        "--control-plane-url",
        str(getattr(args, "provider_registry_control_plane_url", "")).rstrip("/"),
        "--api-token",
        token,
        "--json",
    ]
    result = subprocess.run(
        command,
        cwd=args.ao2_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    output = redact_nightly_log_output(result.stdout or "")
    try:
        ao2_result = json.loads(output)
    except json.JSONDecodeError:
        ao2_result = {"status": "unreadable", "output": output}
    artifact = {
        **common,
        "status": "passed" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "signed": bool(ao2_result.get("signed", False)) if isinstance(ao2_result, dict) else False,
        "ao2_invocation": sanitize_command_for_artifact(command),
        "ao2_result": sanitize_for_nightly_artifact(ao2_result),
    }
    if isinstance(ao2_result, dict):
        artifact["receipt"] = sanitize_for_nightly_artifact(ao2_result.get("receipt", {}))
        artifact["endpoint"] = ao2_result.get("endpoint", "")
        artifact["detail_url"] = ao2_result.get("detail_url", "")
        artifact["signature_url"] = ao2_result.get("signature_url", "")
        artifact["dashboard_url"] = ao2_result.get("dashboard_url", "")
    publish_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def run_step(step: dict[str, Any], log_dir: Path) -> dict[str, Any]:
    started = time.time()
    log_path = log_dir / f"{step['id']}.log"
    env = os.environ.copy()
    for key in step.get("env_remove", []):
        env.pop(str(key), None)
    env.update(step.get("env", {}))
    result = subprocess.run(
        step["command"],
        cwd=step["cwd"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    output = redact_nightly_log_output(result.stdout or "")
    log_path.write_text(output, encoding="utf-8", errors="replace")
    step["status"] = "passed" if result.returncode == 0 else "failed"
    step["exit_code"] = result.returncode
    step["duration_seconds"] = round(time.time() - started, 3)
    step["log"] = str(log_path)
    return step


def write_release_summary_from_bridge_log(args: argparse.Namespace, log_dir: Path) -> None:
    bridge_log = log_dir / "real-hermes-bridge-smoke.log"
    bridge_payload = json.loads(bridge_log.read_text(encoding="utf-8"))
    checks = bridge_payload.get("checks", {})
    macos_status = checks.get("macos", {}).get("status", "unknown")
    ubuntu_status = checks.get("ubuntu", {}).get("status", "unknown")
    windows_status = checks.get("windows", {}).get("status", "unknown")
    ubuntu_check = checks.get("ubuntu", {})
    windows_check = checks.get("windows", {})
    candidates, _source = release_publication_artifact_candidates(args)
    publication = load_json_artifact(candidates[0]) if candidates else {}
    version = str(publication.get("version") or "")
    summary = {
        "schema": "ao2.three-os-smoke-summary.v1",
        "version": version,
        "release_candidate_version": version,
        "local_smoke": "passed" if bridge_payload.get("status") == "passed" and macos_status == "passed" else "failed",
        "linux_x86_64_remote_smoke": ubuntu_status,
        "linux_x86_64_remote_evidence": {
            "target": args.ubuntu_target,
            "status": ubuntu_status,
            "reason": ubuntu_check.get("reason", ""),
            "control_plane_mode": "real",
            "source": "hermes_bridge_three_os_smoke",
        },
        "native_windows_required": bool(args.require_remotes),
        "windows_native_smoke": windows_status,
        "windows_skip_reason": "" if windows_status == "passed" else windows_check.get("reason", ""),
        "windows_native_evidence": {
            "target": args.windows_target,
            "status": windows_status,
            "reason": windows_check.get("reason", ""),
            "control_plane_mode": "real",
            "source": "hermes_bridge_three_os_smoke",
            "required": bool(args.require_remotes),
        },
        "source": {
            "schema": bridge_payload.get("schema"),
            "status": bridge_payload.get("status"),
            "bridge_log": str(bridge_log),
        },
    }
    nightly_release_summary_path(args).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def repo_name(path: Path, roots: dict[str, Path]) -> str:
    resolved = path.resolve()
    for name, root in roots.items():
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return name
    return path.parent.name


def should_scan_file(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    parts = tuple(path.parts)
    for fragment in SKIP_PATH_FRAGMENTS:
        if any(parts[index : index + len(fragment)] == fragment for index in range(len(parts))):
            return False
    if not path.is_file():
        return False
    return path.suffix in TEXT_SUFFIXES


def classify_gap(line: str, path: Path) -> tuple[str, str, str]:
    lower = line.lower()
    normalized = path.as_posix().lower()
    if "openssl" in lower:
        if path.name == "hermes_nightly_ao2_advancement.py":
            return (
                "gap-miner-rule",
                "low",
                "Classifier rule text; no product runtime dependency is implied.",
            )
        if any(marker in normalized for marker in ("/tests/", "_test")) and any(
            marker in lower
            for marker in (
                "!source.contains",
                "!sign_script.contains",
                "!verify_script.contains",
                "without_openssl",
                "openssl-backed signature test",
                "must not shell out",
            )
        ):
            return (
                "openssl-test-guard",
                "low",
                "Keep this negative assertion as regression coverage for native crypto portability.",
            )
        if any(marker in normalized for marker in ("/tests/", "_test")):
            return (
                "openssl-test-fixture",
                "medium",
                "Test fixture still mentions OpenSSL; replace only if this test must pass on hosts without OpenSSL.",
            )
        if "/docs/" in normalized or "/plans/" in normalized:
            return (
                "historical-openssl-reference",
                "low",
                "Historical documentation mentions OpenSSL; refresh only if it is still part of active operator guidance.",
            )
        if any(marker in lower for marker in ("dgst", "genrsa", "pkey", "rsa", "signature", "verify")):
            return (
                "openssl-runtime-dependency",
                "high",
                "Replace runtime OpenSSL shellouts with native crypto and keep signatures portable across Windows/Mac/Ubuntu.",
            )
        return (
            "openssl-reference",
            "medium",
            "Confirm whether this OpenSSL mention is documentation-only or still part of an executable dependency path.",
        )
    if "provider readiness gate skipped because local preflight checks failed" in lower or (
        "provider_gate" in lower and "skipped" in lower
    ):
        return (
            "provider-local-preflight-skip",
            "low",
            "Provider readiness gate is skipped only when local prerequisites fail; keep as explicit preflight metadata.",
        )
    if (
        "windows_skip_reason" in lower
        or "optional_windows_skip" in lower
        or ("skipped" in lower and ("windows_native_smoke" in lower or "windows-x86_64" in lower))
    ):
        return (
            "optional-windows-smoke-skip-metadata",
            "low",
            "Records why native Windows smoke is optional or unavailable; gate still fails when native Windows is required.",
        )
    if "--skip-git-repo-check" in lower:
        return (
            "provider-sandbox-git-preflight-bypass",
            "low",
            "Codex runs inside AO2 disposable sandboxes; keep this documented provider flag unless the sandbox contract changes.",
        )
    if ".skip(" in lower:
        return (
            "code-navigation-skip",
            "low",
            "Iterator or slice navigation uses skip; no skipped test coverage is implied.",
        )
    if any(
        marker in lower
        for marker in (
            "--dangerously-skip-permissions",
            '"status": "skipped"',
            "'status': 'skipped'",
            "status=skipped",
            "should_skip_repo_entry",
            "skip_serializing_if",
        )
    ):
        return (
            "accepted-skip-reference",
            "low",
            "Skip-shaped literal or helper metadata; no skipped verification is implied.",
        )
    if "skip" in lower and any(marker in normalized for marker in ("/test", "tests/", "_test", ".rs")):
        return (
            "test-skip",
            "medium",
            "Review the skipped coverage and either convert it into a deterministic check or document the remaining external prerequisite.",
        )
    return (
        "follow-up-marker",
        "low",
        "Triage this marker into a tracked issue, acceptance criterion, or remove it if it is stale.",
    )


def severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def mine_ranked_gaps(args: argparse.Namespace, limit: int = 200) -> dict[str, Any]:
    roots = {
        "ao2": args.ao2_root,
        "ao2-control-plane": args.ao2_control_plane,
        "ao-operator": args.factory_root,
    }
    items: list[dict[str, Any]] = []
    accepted_items: list[dict[str, Any]] = []
    for root in roots.values():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not should_scan_file(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if not any(pattern.lower() in line.lower() for pattern in GAP_PATTERNS):
                    continue
                category, severity, recommendation = classify_gap(line, path)
                item = {
                    "repo": repo_name(path, roots),
                    "path": str(path),
                    "line": line_number,
                    "category": category,
                    "severity": severity,
                    "match": redact_nightly_log_output(line.strip())[:240],
                    "recommendation": recommendation,
                }
                if category == "accepted-skip-reference":
                    accepted_items.append(item)
                else:
                    items.append(item)
    items.sort(key=lambda item: (severity_rank(item["severity"]), item["repo"], item["path"], item["line"]))
    accepted_items.sort(
        key=lambda item: (severity_rank(item["severity"]), item["repo"], item["path"], item["line"])
    )
    return {
        "schema": GAP_BACKLOG_SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "patterns": list(GAP_PATTERNS),
        "item_count": len(items[:limit]),
        "items": items[:limit],
        "accepted_item_count": len(accepted_items[:limit]),
        "accepted_items": accepted_items[:limit],
    }


def write_gap_backlog(payload: dict[str, Any], out_dir: Path, args: argparse.Namespace) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    backlog = mine_ranked_gaps(args)
    path = out_dir / "gap-backlog.json"
    path.write_text(json.dumps(backlog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["gap_backlog"] = {
        "schema": backlog["schema"],
        "item_count": backlog["item_count"],
        "high_count": sum(1 for item in backlog["items"] if item["severity"] == "high"),
    }
    return path


def release_gate_failed_checks(payload: dict[str, Any]) -> list[dict[str, str]]:
    gate_artifact_path = Path(payload.get("artifacts", {}).get("release_gate_dry_run", ""))
    if not gate_artifact_path or not gate_artifact_path.is_file():
        return []
    try:
        gate_artifact = json.loads(gate_artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [
            {
                "name": "release_gate_artifact_unreadable",
                "message": f"release gate artifact is not valid JSON: {gate_artifact_path}",
            }
        ]
    failed_checks: list[dict[str, str]] = []
    for check in gate_artifact.get("enriched", {}).get("checks", []):
        if check.get("status") == "failed":
            failed_checks.append(
                {
                    "name": f"enriched.{check.get('name', 'unknown')}",
                    "message": check.get("message", ""),
                }
            )
    malformed = gate_artifact.get("malformed", {})
    if isinstance(malformed, dict) and malformed.get("status") == "passed":
        failed_checks.append(
            {
                "name": "malformed.expected_failure",
                "message": "malformed release summary unexpectedly passed the release gate",
            }
        )
    return failed_checks


def cancel_authority_alerts(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Surface AO2 watchdog cancel-authority nightly drift as notification alerts.

    Reads ``cancel-authority-dry-run.json`` (schema
    ``ao-operator/hermes-nightly-cancel-authority-dry-run/v1``). The
    ``planned`` and ``skipped`` statuses are expected and produce no
    alert; ``executed`` only alerts when ``accepted`` is False;
    ``binary_missing`` and ``capture_failed`` always alert. Unreadable
    or schema-violating artifacts also alert so silent corruption can't
    masquerade as a passing gate.
    """

    artifact_path = Path(
        payload.get("artifacts", {}).get("cancel_authority_dry_run", "")
    )
    if not artifact_path or not artifact_path.is_file():
        return []
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [
            {
                "name": "cancel_authority_artifact_unreadable",
                "message": (
                    f"cancel-authority dry-run artifact is not valid JSON: "
                    f"{artifact_path}"
                ),
            }
        ]
    if not isinstance(artifact, dict):
        return [
            {
                "name": "cancel_authority_artifact_malformed",
                "message": (
                    f"cancel-authority dry-run artifact is not a JSON object: "
                    f"{artifact_path}"
                ),
            }
        ]
    status = str(artifact.get("status") or "")
    alerts: list[dict[str, str]] = []
    if status == "binary_missing":
        alerts.append(
            {
                "name": "cancel_authority_binary_missing",
                "message": (
                    "AO2 binary for cancel-authority dry-run not found: "
                    f"{artifact.get('ao2_bin', 'unknown')}"
                ),
            }
        )
    elif status == "capture_failed":
        blockers = artifact.get("blockers") or []
        message = (
            blockers[0]
            if blockers and isinstance(blockers[0], str)
            else "ao2 factory queue-list capture failed"
        )
        alerts.append(
            {
                "name": "cancel_authority_capture_failed",
                "message": message,
            }
        )
    elif status == "executed":
        if artifact.get("accepted") is not True:
            outcome = artifact.get("outcome") or "unknown"
            alerts.append(
                {
                    "name": "cancel_authority_round_trip_refused",
                    "message": (
                        "AO2 watchdog cancel-authority round trip did not "
                        f"accept the producer attestation: outcome={outcome}"
                    ),
                }
            )
    elif status not in {"planned", "skipped"}:
        alerts.append(
            {
                "name": "cancel_authority_unexpected_status",
                "message": (
                    f"cancel-authority dry-run artifact status={status!r} "
                    "is not one of {planned, skipped, executed, "
                    "binary_missing, capture_failed}"
                ),
            }
        )
    return alerts


ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT = 17


def _role_contracts_expected_loaded_count(
    payload: dict[str, Any],
    artifact: dict[str, Any],
) -> int:
    override = payload.get("role_contracts_expected_loaded_count")
    if override is not None:
        return int(override)

    task_roles: set[str] = set()
    tasks = artifact.get("governed_run_plan", {}).get("tasks") or []
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict):
                continue
            role = task.get("canonical_role") or task.get("role")
            if isinstance(role, str) and role:
                task_roles.add(role)
    if task_roles:
        return len(task_roles)

    return ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT


def role_contracts_alerts(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Surface AO2 role-contracts regressions as notification alerts.

    Reads the AO2-native bridge evidence file (schema
    ``ao2.factory-bridge.v1``) via the ``factory_compat_bridge_evidence``
    artifacts key and inspects its read-only ``role_contracts`` block.
    Alerts fire when ``missing_roles`` is non-empty (a previously-resolved
    role has dropped out of AO2's loader) or when ``loaded_count`` falls
    below the expected coverage threshold. The threshold is derived from
    the bridge evidence's distinct governed-run roles when available,
    falls back to ``role_contracts_expected_loaded_count`` when provided,
    and otherwise uses ``ROLE_CONTRACTS_EXPECTED_LOADED_COUNT_DEFAULT`` =
    17 for legacy artifacts that predate role-bearing bridge tasks.

    No alerts fire when the artifact path is unregistered or the file
    has not landed yet — that is a planning state, not a regression.
    Unreadable / malformed / wrong-schema artifacts always alert so
    silent corruption cannot masquerade as a passing gate.

    Trust boundary: ao-operator reads the AO2-owned block; it does not
    mutate it. The expected ``loaded_count`` threshold is owned by
    ao-operator because *ao-operator* knows how many of its own
    ``agents/*.toml`` files AO2 should be loading. AO2's evidence is
    the input; ao-operator's threshold is the assertion.
    """

    artifact_path_raw = payload.get("artifacts", {}).get(
        "factory_compat_bridge_evidence", ""
    )
    if not artifact_path_raw:
        return []
    artifact_path = Path(artifact_path_raw)
    if not artifact_path.is_file():
        return []
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [
            {
                "name": "role_contracts_artifact_unreadable",
                "message": (
                    f"factory-compat bridge evidence is not valid JSON: "
                    f"{artifact_path}"
                ),
            }
        ]
    if not isinstance(artifact, dict):
        return [
            {
                "name": "role_contracts_artifact_malformed",
                "message": (
                    f"factory-compat bridge evidence is not a JSON object: "
                    f"{artifact_path}"
                ),
            }
        ]
    schema = str(artifact.get("schema") or "")
    if schema and schema != "ao2.factory-bridge.v1":
        return [
            {
                "name": "role_contracts_artifact_schema_drift",
                "message": (
                    f"factory-compat bridge evidence has unexpected schema "
                    f"{schema!r}; expected 'ao2.factory-bridge.v1'"
                ),
            }
        ]
    block = artifact.get("role_contracts")
    if not isinstance(block, dict):
        return [
            {
                "name": "role_contracts_block_absent",
                "message": (
                    "factory-compat bridge evidence has no role_contracts "
                    f"block (artifact={artifact_path}); AO2 did not load "
                    "any role contracts this run"
                ),
            }
        ]
    alerts: list[dict[str, str]] = []
    missing = block.get("missing_roles")
    if isinstance(missing, list) and missing:
        preview = ", ".join(str(role) for role in missing[:5])
        alerts.append(
            {
                "name": "role_contracts_missing_roles",
                "message": (
                    f"AO2 reported {len(missing)} role(s) missing a loaded "
                    f"contract: {preview}"
                ),
            }
        )
    expected = _role_contracts_expected_loaded_count(payload, artifact)
    loaded_count = block.get("loaded_count")
    if isinstance(loaded_count, int) and loaded_count < expected:
        alerts.append(
            {
                "name": "role_contracts_loaded_count_regression",
                "message": (
                    f"AO2 role_contracts.loaded_count={loaded_count} is "
                    f"below expected coverage threshold={expected}; a "
                    "previously-loaded role contract has dropped out"
                ),
            }
        )
    return alerts


def build_notification_payload(payload: dict[str, Any]) -> dict[str, Any]:
    failed_steps = [
        step["id"]
        for step in payload.get("steps", [])
        if step.get("status") in {"failed", "blocked"}
    ]
    release_gate_alerts = release_gate_failed_checks(payload)
    cancel_authority_alert_list = cancel_authority_alerts(payload)
    role_contracts_alert_list = role_contracts_alerts(payload)
    status = payload.get("status", "unknown")
    severity = (
        "failure"
        if status == "failed"
        or failed_steps
        or release_gate_alerts
        or cancel_authority_alert_list
        or role_contracts_alert_list
        else "info"
    )
    title = f"Hermes nightly AO2 advancement {status}"
    summary_lines = [
        title,
        f"failed_steps={','.join(failed_steps) if failed_steps else 'none'}",
        f"release_gate_alerts={len(release_gate_alerts)}",
        f"cancel_authority_alerts={len(cancel_authority_alert_list)}",
        f"role_contracts_alerts={len(role_contracts_alert_list)}",
    ]
    for alert in release_gate_alerts:
        summary_lines.append(f"{alert['name']}: {alert['message']}")
    for alert in cancel_authority_alert_list:
        summary_lines.append(f"{alert['name']}: {alert['message']}")
    for alert in role_contracts_alert_list:
        summary_lines.append(f"{alert['name']}: {alert['message']}")
    return {
        "schema": NOTIFICATION_SCHEMA,
        "status": status,
        "severity": severity,
        "title": title,
        "text": "\n".join(summary_lines),
        "generated_at_ms": payload.get("generated_at_ms"),
        "failed_steps": failed_steps,
        "release_gate_alerts": release_gate_alerts,
        "cancel_authority_alerts": cancel_authority_alert_list,
        "role_contracts_alerts": role_contracts_alert_list,
        "artifacts": dict(payload.get("artifacts", {})),
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Hermes Nightly AO2 Advancement",
        "",
        f"- status: `{payload['status']}`",
        f"- generated_at_ms: `{payload['generated_at_ms']}`",
        "",
        "## Steps",
        "",
    ]
    for step in payload["steps"]:
        command = " ".join(step["command"])
        lines.extend(
            [
                f"### {step['id']}",
                "",
                f"- title: {step['title']}",
                f"- status: `{step['status']}`",
                f"- cwd: `{step['cwd']}`",
                f"- command: `{command}`",
            ]
        )
        if "log" in step:
            lines.append(f"- log: `{step['log']}`")
        lines.append("")
    if "repeat_failure_guard" in payload:
        guard = payload["repeat_failure_guard"]
        lines.extend(
            [
                "## Repeat Failure Guard",
                "",
                f"- status: `{guard.get('status', 'unknown')}`",
                f"- failed_step: `{guard.get('failed_step', '')}`",
                f"- consecutive_count: `{guard.get('consecutive_count', 0)}`",
                f"- threshold: `{guard.get('threshold', 0)}`",
            ]
        )
        repair_handoff = payload.get("artifacts", {}).get("repair_handoff")
        if repair_handoff:
            lines.append(f"- repair_handoff: `{repair_handoff}`")
            lines.append("")
    control_plane_release_smoke_path = Path(
        payload.get("artifacts", {}).get("control_plane_release_smoke", "")
    )
    if control_plane_release_smoke_path:
        control_plane_release_smoke: dict[str, Any] = {}
        if control_plane_release_smoke_path.is_file():
            try:
                control_plane_release_smoke = json.loads(
                    control_plane_release_smoke_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                control_plane_release_smoke = {"status": "unreadable"}
        lines.extend(
            [
                "## Control Plane Release Smoke",
                "",
                f"- artifact: `{control_plane_release_smoke_path}`",
                f"- status: `{control_plane_release_smoke.get('status', 'missing')}`",
            ]
        )
        if control_plane_release_smoke.get("archive"):
            lines.append(f"- archive: `{control_plane_release_smoke['archive']}`")
        source_counts = control_plane_release_smoke.get("dashboard_source_counts", {})
        if isinstance(source_counts, dict):
            if source_counts.get("fixture") is not None:
                lines.append(f"- fixture_count: `{source_counts['fixture']}`")
            if source_counts.get("live") is not None:
                lines.append(f"- live_count: `{source_counts['live']}`")
        lines.append("")
    provider_registry_publish_path = Path(payload.get("artifacts", {}).get("provider_registry_publish", ""))
    if provider_registry_publish_path:
        provider_registry_publish: dict[str, Any] = {}
        if provider_registry_publish_path.is_file():
            try:
                provider_registry_publish = json.loads(
                    provider_registry_publish_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                provider_registry_publish = {"status": "unreadable"}
        lines.extend(
            [
                "## Provider Registry Observer",
                "",
                f"- artifact: `{provider_registry_publish_path}`",
                f"- status: `{provider_registry_publish.get('status', 'missing')}`",
            ]
        )
        observer_links = provider_registry_publish.get("observer_links", {})
        if isinstance(observer_links, dict):
            if observer_links.get("dashboard"):
                lines.append(f"- provider_registry_dashboard: `{observer_links['dashboard']}`")
            if observer_links.get("dashboard_json"):
                lines.append(
                    f"- provider_registry_dashboard_json: `{observer_links['dashboard_json']}`"
                )
            if observer_links.get("phase1_operator_panel"):
                lines.append(
                    f"- phase1_operator_panel: `{observer_links['phase1_operator_panel']}`"
                )
        lines.append("")
    provider_acceptance_preservation_path = Path(
        payload.get("artifacts", {}).get("provider_acceptance_preservation", "")
    )
    if provider_acceptance_preservation_path:
        provider_acceptance_preservation: dict[str, Any] = {}
        if provider_acceptance_preservation_path.is_file():
            try:
                provider_acceptance_preservation = json.loads(
                    provider_acceptance_preservation_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                provider_acceptance_preservation = {"status": "unreadable"}
        lines.extend(
            [
                "## Provider Acceptance Preservation",
                "",
                f"- artifact: `{provider_acceptance_preservation_path}`",
                f"- status: `{provider_acceptance_preservation.get('status', 'missing')}`",
            ]
        )
        if provider_acceptance_preservation.get("tag"):
            lines.append(f"- tag: `{provider_acceptance_preservation['tag']}`")
        providers = provider_acceptance_preservation.get("providers", {})
        if isinstance(providers, dict):
            for provider in ("codex", "claude"):
                provider_summary = providers.get(provider, {})
                if isinstance(provider_summary, dict):
                    lines.append(
                        f"- {provider}: `score={provider_summary.get('smoke_score', 'unknown')} "
                        f"replay={provider_summary.get('replay_status', 'unknown')} "
                        f"source={provider_summary.get('source_class', 'unknown')}`"
                    )
        lines.append("")
    provider_phase1_path = Path(payload.get("artifacts", {}).get("provider_phase1_readiness", ""))
    if provider_phase1_path:
        provider_phase1: dict[str, Any] = {}
        provider_publish: dict[str, Any] = {}
        if provider_phase1_path.is_file():
            try:
                provider_phase1 = json.loads(provider_phase1_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                provider_phase1 = {"status": "unreadable"}
        provider_publish_path = Path(payload.get("artifacts", {}).get("provider_phase1_readiness_publish", ""))
        if provider_publish_path and provider_publish_path.is_file():
            try:
                provider_publish = json.loads(provider_publish_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                provider_publish = {"status": "unreadable"}
        provider_acceptance_publish_path = Path(payload.get("artifacts", {}).get("provider_acceptance_publish", ""))
        provider_acceptance_publish: dict[str, Any] = {}
        if provider_acceptance_publish_path and provider_acceptance_publish_path.is_file():
            try:
                provider_acceptance_publish = json.loads(
                    provider_acceptance_publish_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                provider_acceptance_publish = {"status": "unreadable"}
        lines.extend(
            [
                "## Provider Phase 1 Readiness",
                "",
                f"- artifact: `{provider_phase1_path}`",
                f"- status: `{provider_phase1.get('status', 'missing')}`",
                f"- live_provider_policy: `{provider_phase1.get('live_provider_policy', 'missing')}`",
            ]
        )
        if provider_publish_path:
            lines.append(f"- readiness_publish_artifact: `{provider_publish_path}`")
            lines.append(f"- readiness_publish: `{provider_publish.get('status', 'missing')}`")
            if provider_publish.get("observer_dashboard_status"):
                lines.append(f"- readiness_observer: `{provider_publish['observer_dashboard_status']}`")
            observer_snapshot = provider_publish.get("observer_dashboard_snapshot", {})
            phase1_status = (
                observer_snapshot.get("phase1_status", {}) if isinstance(observer_snapshot, dict) else {}
            )
            if isinstance(phase1_status, dict):
                if phase1_status.get("state"):
                    lines.append(f"- phase1_state: `{phase1_status['state']}`")
                if phase1_status.get("next_action"):
                    lines.append(f"- phase1_next_action: `{phase1_status['next_action']}`")
            observer_links = provider_publish.get("observer_links", {})
            if isinstance(observer_links, dict):
                if observer_links.get("dashboard"):
                    lines.append(f"- readiness_dashboard: `{observer_links['dashboard']}`")
                if observer_links.get("dashboard_json"):
                    lines.append(f"- readiness_dashboard_json: `{observer_links['dashboard_json']}`")
        if provider_acceptance_publish_path:
            lines.append(f"- acceptance_publish_artifact: `{provider_acceptance_publish_path}`")
            lines.append(f"- acceptance_publish: `{provider_acceptance_publish.get('status', 'missing')}`")
            if provider_acceptance_publish.get("observer_dashboard_status"):
                lines.append(
                    f"- acceptance_observer: `{provider_acceptance_publish['observer_dashboard_status']}`"
                )
            observer_links = provider_acceptance_publish.get("observer_links", {})
            if isinstance(observer_links, dict) and observer_links.get("dashboard"):
                lines.append(f"- acceptance_dashboard: `{observer_links['dashboard']}`")
            observer_snapshot = provider_acceptance_publish.get("observer_dashboard_snapshot", {})
            if isinstance(observer_snapshot, dict):
                phase1_acceptance = observer_snapshot.get("phase1_acceptance", {})
                if isinstance(phase1_acceptance, dict):
                    if phase1_acceptance.get("state"):
                        lines.append(
                            f"- acceptance_phase1_state: `{phase1_acceptance['state']}`"
                        )
                    if phase1_acceptance.get("next_action"):
                        lines.append(
                            "- acceptance_phase1_next_action: "
                            f"`{phase1_acceptance['next_action']}`"
                        )
                if observer_snapshot.get("total_count") is not None:
                    lines.append(f"- acceptance_total_count: `{observer_snapshot['total_count']}`")
                if observer_snapshot.get("passed_count") is not None:
                    lines.append(f"- acceptance_passed_count: `{observer_snapshot['passed_count']}`")
        contracts = provider_phase1.get("contracts", {})
        if isinstance(contracts, dict):
            for provider in ("codex", "claude"):
                contract = contracts.get(provider, {})
                if isinstance(contract, dict):
                    lines.append(f"- {provider}_contract: `{contract.get('status', 'unknown')}`")
        for name in ("scripted_gate", "codex_gate", "codex_pilot"):
            item = provider_phase1.get(name, {})
            if isinstance(item, dict):
                lines.append(f"- {name}: `{item.get('status', 'unknown')}`")
        lines.append("")
    gate_artifact_path = Path(payload.get("artifacts", {}).get("release_gate_dry_run", ""))
    if gate_artifact_path:
        gate_artifact: dict[str, Any] = {}
        if gate_artifact_path.is_file():
            try:
                gate_artifact = json.loads(gate_artifact_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                gate_artifact = {"status": "unreadable"}
        lines.extend(
            [
                "## Release Gate Dry Run",
                "",
                f"- artifact: `{gate_artifact_path}`",
                f"- status: `{gate_artifact.get('status', 'missing')}`",
            ]
        )
        if "enriched" in gate_artifact:
            lines.append(f"- enriched: `{gate_artifact['enriched'].get('status', 'unknown')}`")
        if "malformed" in gate_artifact:
            lines.append(f"- malformed: `{gate_artifact['malformed'].get('status', 'unknown')}`")
        if "enriched_summary" in gate_artifact:
            lines.append(f"- enriched_summary: `{gate_artifact['enriched_summary']}`")
        if "malformed_summary" in gate_artifact:
            lines.append(f"- malformed_summary: `{gate_artifact['malformed_summary']}`")
        lines.append("")
        failed_checks = release_gate_failed_checks(payload)
        if failed_checks:
            lines.extend(["## Release Gate Alerts", ""])
            for check in failed_checks:
                lines.append(f"- `{check['name']}`: {check['message']}")
            lines.append("")
    cancel_authority_path_raw = payload.get("artifacts", {}).get(
        "cancel_authority_dry_run", ""
    )
    if cancel_authority_path_raw:
        cancel_authority_path = Path(cancel_authority_path_raw)
        cancel_authority_artifact: dict[str, Any] = {}
        if cancel_authority_path.is_file():
            try:
                cancel_authority_artifact = json.loads(
                    cancel_authority_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                cancel_authority_artifact = {"status": "unreadable"}
        if not isinstance(cancel_authority_artifact, dict):
            cancel_authority_artifact = {"status": "malformed"}
        lines.extend(
            [
                "## Cancel-Authority Dry-Run",
                "",
                f"- artifact: `{cancel_authority_path}`",
                f"- status: `{cancel_authority_artifact.get('status', 'missing')}`",
            ]
        )
        for field in ("mode", "weekday_configured", "weekday_observed"):
            value = cancel_authority_artifact.get(field)
            if value is not None:
                lines.append(f"- {field}: `{value}`")
        status_value = cancel_authority_artifact.get("status")
        if status_value == "executed":
            outcome = cancel_authority_artifact.get("outcome")
            if outcome is not None:
                lines.append(f"- outcome: `{outcome}`")
            accepted = cancel_authority_artifact.get("accepted")
            if accepted is not None:
                lines.append(f"- accepted: `{accepted}`")
        elif status_value in {"skipped", "binary_missing", "capture_failed"}:
            skip_reason = cancel_authority_artifact.get("skip_reason")
            if skip_reason:
                lines.append(f"- skip_reason: `{skip_reason}`")
        lines.append("")
        cancel_alerts = cancel_authority_alerts(payload)
        if cancel_alerts:
            lines.extend(["## Cancel-Authority Alerts", ""])
            for alert in cancel_alerts:
                lines.append(f"- `{alert['name']}`: {alert['message']}")
            lines.append("")
    bridge_evidence_path_raw = payload.get("artifacts", {}).get(
        "factory_compat_bridge_evidence", ""
    )
    if bridge_evidence_path_raw:
        bridge_evidence_path = Path(bridge_evidence_path_raw)
        bridge_evidence_artifact: dict[str, Any] = {}
        if bridge_evidence_path.is_file():
            try:
                bridge_evidence_artifact = json.loads(
                    bridge_evidence_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                bridge_evidence_artifact = {"status": "unreadable"}
        if not isinstance(bridge_evidence_artifact, dict):
            bridge_evidence_artifact = {"status": "malformed"}
        role_contracts_block = bridge_evidence_artifact.get("role_contracts")
        if not isinstance(role_contracts_block, dict):
            role_contracts_block = {}
        missing_roles = role_contracts_block.get("missing_roles")
        missing_role_count = (
            len(missing_roles) if isinstance(missing_roles, list) else None
        )
        if not bridge_evidence_path.is_file():
            role_contracts_status = "missing"
        elif bridge_evidence_artifact.get("status") in {"unreadable", "malformed"}:
            role_contracts_status = bridge_evidence_artifact["status"]
        elif role_contracts_block:
            role_contracts_status = "observed"
        else:
            role_contracts_status = "absent"
        lines.extend(
            [
                "## Role Contracts",
                "",
                f"- artifact: `{bridge_evidence_path}`",
                f"- status: `{role_contracts_status}`",
            ]
        )
        for field in (
            "owner",
            "loaded_count",
            "factory_v3_required_to_load",
            "path",
        ):
            value = role_contracts_block.get(field)
            if value is not None:
                lines.append(f"- {field}: `{value}`")
        if missing_role_count is not None:
            lines.append(f"- missing_role_count: `{missing_role_count}`")
            if missing_role_count > 0 and isinstance(missing_roles, list):
                preview = ", ".join(str(role) for role in missing_roles[:5])
                lines.append(f"- missing_roles_preview: `{preview}`")
        lines.append("")
        # Per-contract table. AO2 emits one role_contract_ref per task in
        # governed_run_plan.tasks; numbered fan-outs collapse to the same
        # canonical contract, so we deduplicate by sha256+name to render
        # one row per *distinct* contract actually loaded. Sorted by
        # contract name for stable diffs across runs.
        distinct_contracts: dict[tuple[str, str], dict[str, Any]] = {}
        if bridge_evidence_path.is_file() and isinstance(
            bridge_evidence_artifact, dict
        ):
            tasks = (
                bridge_evidence_artifact.get("governed_run_plan", {}).get("tasks")
                or []
            )
            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    ref = task.get("role_contract_ref")
                    if not isinstance(ref, dict):
                        continue
                    name = str(ref.get("name") or "")
                    sha = str(ref.get("sha256") or "")
                    if not name or not sha:
                        continue
                    distinct_contracts.setdefault((name, sha), ref)
        if distinct_contracts:
            lines.extend(
                [
                    "### Loaded contracts",
                    "",
                    "| contract | status | sha256 | path |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for (name, sha), ref in sorted(distinct_contracts.items()):
                status = str(ref.get("contract_status") or "unknown")
                # Show first 12 + ellipsis for human-scannable comparison
                # across runs; full sha is in the JSON for tooling.
                sha_short = f"{sha[:12]}…" if len(sha) > 12 else sha
                path_value = ref.get("path") or ""
                path_basename = (
                    Path(str(path_value)).name if path_value else ""
                )
                lines.append(
                    f"| `{name}` | `{status}` | `{sha_short}` | `{path_basename}` |"
                )
            lines.append("")
        role_contracts_alert_list = role_contracts_alerts(payload)
        if role_contracts_alert_list:
            lines.extend(["## Role Contracts Alerts", ""])
            for alert in role_contracts_alert_list:
                lines.append(f"- `{alert['name']}`: {alert['message']}")
            lines.append("")
    checklist_path = Path(payload.get("artifacts", {}).get("phase1_promotion_checklist", ""))
    if checklist_path:
        checklist: dict[str, Any] = {}
        checklist_publish: dict[str, Any] = {}
        decision_publish: dict[str, Any] = {}
        if checklist_path.is_file():
            try:
                checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                checklist = {"status": "unreadable"}
        checklist_publish_path = Path(
            payload.get("artifacts", {}).get("phase1_promotion_checklist_publish", "")
        )
        if checklist_publish_path and checklist_publish_path.is_file():
            try:
                checklist_publish = json.loads(checklist_publish_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                checklist_publish = {"status": "unreadable"}
        decision_publish_path = Path(
            payload.get("artifacts", {}).get("phase1_promotion_decision_publish", "")
        )
        if decision_publish_path and decision_publish_path.is_file():
            try:
                decision_publish = json.loads(decision_publish_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                decision_publish = {"status": "unreadable"}
        lines.extend(
            [
                "## Phase 1 Promotion Checklist",
                "",
                f"- artifact: `{checklist_path}`",
                f"- status: `{checklist.get('status', 'missing')}`",
                f"- phase1_state: `{checklist.get('phase1_state', 'missing')}`",
            ]
        )
        if checklist.get("next_action"):
            lines.append(f"- next_action: `{checklist['next_action']}`")
        if checklist_publish_path:
            lines.append(f"- publish_artifact: `{checklist_publish_path}`")
            lines.append(f"- publish_status: `{checklist_publish.get('status', 'missing')}`")
            if checklist_publish.get("observer_dashboard_status"):
                lines.append(
                    f"- publish_observer: `{checklist_publish['observer_dashboard_status']}`"
                )
            observer_snapshot = checklist_publish.get("observer_dashboard_snapshot", {})
            if isinstance(observer_snapshot, dict):
                if observer_snapshot.get("state"):
                    lines.append(f"- observer_state: `{observer_snapshot['state']}`")
                checklist_artifact = observer_snapshot.get("checklist_artifact", {})
                if isinstance(checklist_artifact, dict) and checklist_artifact.get("sha256"):
                    lines.append(f"- observer_checklist_sha256: `{checklist_artifact['sha256']}`")
            observer_links = checklist_publish.get("observer_links", {})
            if isinstance(observer_links, dict):
                if observer_links.get("dashboard"):
                    lines.append(f"- promotion_dashboard: `{observer_links['dashboard']}`")
                if observer_links.get("dashboard_json"):
                    lines.append(f"- promotion_dashboard_json: `{observer_links['dashboard_json']}`")
                if observer_links.get("operator_panel"):
                    lines.append(f"- promotion_operator_panel: `{observer_links['operator_panel']}`")
                if observer_links.get("operator_panel_json"):
                    lines.append(
                        f"- promotion_operator_panel_json: `{observer_links['operator_panel_json']}`"
                    )
        if decision_publish_path:
            lines.append(f"- decision_publish_artifact: `{decision_publish_path}`")
            lines.append(f"- decision_publish_status: `{decision_publish.get('status', 'missing')}`")
            if decision_publish.get("signed") is not None:
                lines.append(f"- decision_signed: `{decision_publish.get('signed')}`")
            if decision_publish.get("endpoint"):
                lines.append(f"- decision_endpoint: `{decision_publish['endpoint']}`")
            if decision_publish.get("dashboard_url"):
                lines.append(f"- decision_dashboard: `{decision_publish['dashboard_url']}`")
            receipt = decision_publish.get("receipt", {})
            if isinstance(receipt, dict) and receipt.get("sha256"):
                lines.append(f"- decision_sha256: `{receipt['sha256']}`")
        panel_path = Path(payload.get("artifacts", {}).get("phase1_promotion_panel", ""))
        if panel_path:
            panel: dict[str, Any] = {}
            if panel_path.is_file():
                try:
                    panel = json.loads(panel_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    panel = {"status": "unreadable"}
            lines.append(f"- panel_artifact: `{panel_path}`")
            lines.append(f"- panel_status: `{panel.get('status', 'missing')}`")
            badges = panel.get("badges", {})
            if isinstance(badges, dict):
                lines.append(f"- panel_signature: `{badges.get('signature', 'missing')}`")
                lines.append(f"- panel_three_os: `{badges.get('three_os', 'missing')}`")
        release_publication_publish_path = Path(
            payload.get("artifacts", {}).get("release_publication_publish", "")
        )
        if release_publication_publish_path:
            release_publication_publish: dict[str, Any] = {}
            if release_publication_publish_path.is_file():
                try:
                    release_publication_publish = json.loads(
                        release_publication_publish_path.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    release_publication_publish = {"status": "unreadable"}
            lines.append(f"- release_publication_publish_artifact: `{release_publication_publish_path}`")
            lines.append(
                "- release_publication_publish_status: "
                f"`{release_publication_publish.get('status', 'missing')}`"
            )
            if release_publication_publish.get("release_publication_artifact"):
                lines.append(
                    "- release_publication_artifact: "
                    f"`{release_publication_publish['release_publication_artifact']}`"
                )
            if release_publication_publish.get("release_tag"):
                lines.append(f"- release_publication_tag: `{release_publication_publish['release_tag']}`")
            if release_publication_publish.get("observer_dashboard_status"):
                lines.append(
                    "- release_publication_observer: "
                    f"`{release_publication_publish['observer_dashboard_status']}`"
                )
            observer_links = release_publication_publish.get("observer_links", {})
            if isinstance(observer_links, dict) and observer_links.get("dashboard"):
                lines.append(f"- release_publication_dashboard: `{observer_links['dashboard']}`")
            release_cockpit_status_path = Path(
                payload.get("artifacts", {}).get("release_cockpit_status", "")
            )
            if release_cockpit_status_path:
                release_cockpit_status: dict[str, Any] = {}
                if release_cockpit_status_path.is_file():
                    try:
                        release_cockpit_status = json.loads(
                            release_cockpit_status_path.read_text(encoding="utf-8")
                        )
                    except json.JSONDecodeError:
                        release_cockpit_status = {"status": "unreadable"}
                frontend_status = release_cockpit_status.get("frontend_status", {})
                if not isinstance(frontend_status, dict):
                    frontend_status = {}
                lines.append(f"- release_cockpit_status_artifact: `{release_cockpit_status_path}`")
                lines.append(
                    "- release_cockpit_status: "
                    f"`{release_cockpit_status.get('status') or frontend_status.get('status', 'missing')}`"
                )
                if frontend_status.get("phase1_promotion"):
                    lines.append(f"- release_cockpit_phase1: `{frontend_status['phase1_promotion']}`")
                if frontend_status.get("provider_acceptance_total") is not None:
                    lines.append(
                        "- release_cockpit_provider_acceptance_total: "
                        f"`{frontend_status['provider_acceptance_total']}`"
                    )
                latest_acceptance = frontend_status.get("latest_provider_acceptance", {})
                if isinstance(latest_acceptance, dict):
                    for provider in ("codex", "claude"):
                        provider_summary = latest_acceptance.get(provider, {})
                        if not isinstance(provider_summary, dict):
                            continue
                        status = provider_summary.get("status", "missing")
                        source_class = provider_summary.get("source_class", "missing")
                        lines.append(
                            f"- release_cockpit_{provider}_acceptance: "
                            f"`{status}/{source_class}`"
                        )
                        if provider_summary.get("run_id"):
                            lines.append(
                                f"- release_cockpit_{provider}_run: "
                                f"`{provider_summary['run_id']}`"
                            )
            if isinstance(observer_links, dict) and observer_links.get("cockpit"):
                lines.append(f"- release_cockpit: `{observer_links['cockpit']}`")
            if isinstance(observer_links, dict) and observer_links.get("cockpit_json"):
                lines.append(f"- release_cockpit_json: `{observer_links['cockpit_json']}`")
            release_handoff_status_path = Path(
                payload.get("artifacts", {}).get("release_handoff_status", "")
            )
            if release_handoff_status_path:
                release_handoff_status: dict[str, Any] = {}
                if release_handoff_status_path.is_file():
                    try:
                        release_handoff_status = json.loads(
                            release_handoff_status_path.read_text(encoding="utf-8")
                        )
                    except json.JSONDecodeError:
                        release_handoff_status = {"status": "unreadable"}
                handoff_frontend = release_handoff_status.get("frontend_status", {})
                if not isinstance(handoff_frontend, dict):
                    handoff_frontend = {}
                handoff_links = release_handoff_status.get("links", {})
                if not isinstance(handoff_links, dict):
                    handoff_links = {}
                lines.append(f"- release_handoff_status_artifact: `{release_handoff_status_path}`")
                lines.append(
                    "- release_handoff_status: "
                    f"`{release_handoff_status.get('status') or handoff_frontend.get('status', 'missing')}`"
                )
                if handoff_frontend.get("provider_acceptance"):
                    lines.append(
                        "- release_handoff_provider_acceptance: "
                        f"`{handoff_frontend['provider_acceptance']}`"
                    )
                if handoff_links.get("release_candidate_handoff_json"):
                    if handoff_links.get("release_candidate_handoff"):
                        lines.append(
                            "- release_handoff: "
                            f"`{handoff_links['release_candidate_handoff']}`"
                        )
                    lines.append(
                        "- release_handoff_json: "
                        f"`{handoff_links['release_candidate_handoff_json']}`"
                    )
                release_readiness_status_path = Path(
                    payload.get("artifacts", {}).get("release_readiness_status", "")
                )
                if release_readiness_status_path:
                    release_readiness_status: dict[str, Any] = {}
                    if release_readiness_status_path.is_file():
                        try:
                            release_readiness_status = json.loads(
                                release_readiness_status_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_readiness_status = {"status": "unreadable"}
                    readiness_frontend = release_readiness_status.get("frontend_status", {})
                    if not isinstance(readiness_frontend, dict):
                        readiness_frontend = {}
                    readiness_links = release_readiness_status.get("links", {})
                    if not isinstance(readiness_links, dict):
                        readiness_links = {}
                    lines.append(
                        f"- release_readiness_status_artifact: `{release_readiness_status_path}`"
                    )
                    lines.append(
                        "- release_readiness_status: "
                        f"`{release_readiness_status.get('status') or readiness_frontend.get('status', 'missing')}`"
                    )
                    if readiness_links.get("release_readiness_json"):
                        if readiness_links.get("release_readiness"):
                            lines.append(
                                "- release_readiness: "
                                f"`{readiness_links['release_readiness']}`"
                            )
                        lines.append(
                            "- release_readiness_json: "
                            f"`{readiness_links['release_readiness_json']}`"
                        )
                release_support_bundle_status_path = Path(
                    payload.get("artifacts", {}).get("release_support_bundle_status", "")
                )
                if release_support_bundle_status_path:
                    release_support_bundle_status: dict[str, Any] = {}
                    if release_support_bundle_status_path.is_file():
                        try:
                            release_support_bundle_status = json.loads(
                                release_support_bundle_status_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_support_bundle_status = {"status": "unreadable"}
                    support_frontend = release_support_bundle_status.get("frontend_status", {})
                    if not isinstance(support_frontend, dict):
                        support_frontend = {}
                    support_links = release_support_bundle_status.get("links", {})
                    if not isinstance(support_links, dict):
                        support_links = {}
                    lines.append(
                        "- release_support_bundle_status_artifact: "
                        f"`{release_support_bundle_status_path}`"
                    )
                    lines.append(
                        "- release_support_bundle_status: "
                        f"`{release_support_bundle_status.get('status') or support_frontend.get('status', 'missing')}`"
                    )
                    if support_frontend.get("release_candidate_version"):
                        lines.append(
                            "- release_support_bundle_candidate: "
                            f"`{support_frontend['release_candidate_version']}`"
                        )
                    if support_frontend.get("candidate_correlation"):
                        lines.append(
                            "- release_support_bundle_candidate_correlation: "
                            f"`{support_frontend['candidate_correlation']}`"
                        )
                    if support_links.get("release_support_bundle_json"):
                        lines.append(
                            "- release_support_bundle_json: "
                            f"`{support_links['release_support_bundle_json']}`"
                        )
                release_handoff_checklist_path = Path(
                    payload.get("artifacts", {}).get("release_handoff_checklist", "")
                )
                if release_handoff_checklist_path:
                    release_handoff_checklist: dict[str, Any] = {}
                    if release_handoff_checklist_path.is_file():
                        try:
                            release_handoff_checklist = json.loads(
                                release_handoff_checklist_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_handoff_checklist = {"status": "unreadable"}
                    lines.append(
                        f"- release_handoff_checklist_artifact: `{release_handoff_checklist_path}`"
                    )
                    if payload.get("artifacts", {}).get("release_handoff_checklist_markdown"):
                        lines.append(
                            "- release_handoff_checklist_markdown: "
                            f"`{payload['artifacts']['release_handoff_checklist_markdown']}`"
                        )
                    lines.append(
                        "- release_handoff_checklist_status: "
                        f"`{release_handoff_checklist.get('status', 'missing')}`"
                    )
                release_evaluator_decision_path = Path(
                    payload.get("artifacts", {}).get("release_evaluator_decision", "")
                )
                if release_evaluator_decision_path:
                    release_evaluator_decision: dict[str, Any] = {}
                    if release_evaluator_decision_path.is_file():
                        try:
                            release_evaluator_decision = json.loads(
                                release_evaluator_decision_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_evaluator_decision = {"status": "unreadable"}
                    lines.append(
                        f"- release_evaluator_decision_artifact: `{release_evaluator_decision_path}`"
                    )
                    if payload.get("artifacts", {}).get("release_evaluator_decision_markdown"):
                        lines.append(
                            "- release_evaluator_decision_markdown: "
                            f"`{payload['artifacts']['release_evaluator_decision_markdown']}`"
                        )
                    lines.append(
                        "- release_evaluator_decision: "
                        f"`{release_evaluator_decision.get('decision', release_evaluator_decision.get('status', 'missing'))}`"
                    )
                release_evaluator_decision_publish_path = Path(
                    payload.get("artifacts", {}).get("release_evaluator_decision_publish", "")
                )
                if release_evaluator_decision_publish_path:
                    release_evaluator_decision_publish: dict[str, Any] = {}
                    if release_evaluator_decision_publish_path.is_file():
                        try:
                            release_evaluator_decision_publish = json.loads(
                                release_evaluator_decision_publish_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_evaluator_decision_publish = {"status": "unreadable"}
                    lines.append(
                        "- release_evaluator_decision_publish_artifact: "
                        f"`{release_evaluator_decision_publish_path}`"
                    )
                    lines.append(
                        "- release_evaluator_decision_publish_status: "
                        f"`{release_evaluator_decision_publish.get('status', 'missing')}`"
                    )
                    if release_evaluator_decision_publish.get("observer_dashboard_status"):
                        lines.append(
                            "- release_evaluator_decision_observer: "
                            f"`{release_evaluator_decision_publish['observer_dashboard_status']}`"
                        )
                    evaluator_links = release_evaluator_decision_publish.get("observer_links", {})
                    if isinstance(evaluator_links, dict) and evaluator_links.get(
                        "evaluator_decision_dashboard"
                    ):
                        lines.append(
                            "- release_evaluator_decision_dashboard: "
                            f"`{evaluator_links['evaluator_decision_dashboard']}`"
                        )
                release_evaluator_decision_status_path = Path(
                    payload.get("artifacts", {}).get("release_evaluator_decision_status", "")
                )
                if release_evaluator_decision_status_path:
                    release_evaluator_decision_status: dict[str, Any] = {}
                    if release_evaluator_decision_status_path.is_file():
                        try:
                            release_evaluator_decision_status = json.loads(
                                release_evaluator_decision_status_path.read_text(
                                    encoding="utf-8"
                                )
                            )
                        except json.JSONDecodeError:
                            release_evaluator_decision_status = {"status": "unreadable"}
                    evaluator_status_frontend = release_evaluator_decision_status.get(
                        "frontend_status",
                        {},
                    )
                    if not isinstance(evaluator_status_frontend, dict):
                        evaluator_status_frontend = {}
                    evaluator_status_links = release_evaluator_decision_status.get("links", {})
                    if not isinstance(evaluator_status_links, dict):
                        evaluator_status_links = {}
                    lines.append(
                        "- release_evaluator_decision_status_artifact: "
                        f"`{release_evaluator_decision_status_path}`"
                    )
                    lines.append(
                        "- release_evaluator_decision_status: "
                        f"`{release_evaluator_decision_status.get('status') or evaluator_status_frontend.get('status', 'missing')}`"
                    )
                    if evaluator_status_links.get("release_evaluator_decision_dashboard_json"):
                        lines.append(
                            "- release_evaluator_decision_dashboard_json: "
                            f"`{evaluator_status_links['release_evaluator_decision_dashboard_json']}`"
                        )
                release_support_bundle_post_decision_status_path = Path(
                    payload.get("artifacts", {}).get(
                        "release_support_bundle_post_decision_status",
                        "",
                    )
                )
                if release_support_bundle_post_decision_status_path:
                    release_support_bundle_post_decision_status: dict[str, Any] = {}
                    if release_support_bundle_post_decision_status_path.is_file():
                        try:
                            release_support_bundle_post_decision_status = json.loads(
                                release_support_bundle_post_decision_status_path.read_text(
                                    encoding="utf-8"
                                )
                            )
                        except json.JSONDecodeError:
                            release_support_bundle_post_decision_status = {"status": "unreadable"}
                    support_post_frontend = release_support_bundle_post_decision_status.get(
                        "frontend_status",
                        {},
                    )
                    if not isinstance(support_post_frontend, dict):
                        support_post_frontend = {}
                    lines.append(
                        "- release_support_bundle_post_decision_status_artifact: "
                        f"`{release_support_bundle_post_decision_status_path}`"
                    )
                    lines.append(
                        "- release_support_bundle_post_decision_status: "
                        f"`{release_support_bundle_post_decision_status.get('status') or support_post_frontend.get('status', 'missing')}`"
                    )
                release_support_verifier_handoff_path = Path(
                    payload.get("artifacts", {}).get("release_support_verifier_handoff", "")
                )
                if release_support_verifier_handoff_path:
                    release_support_verifier_handoff: dict[str, Any] = {}
                    if release_support_verifier_handoff_path.is_file():
                        try:
                            release_support_verifier_handoff = json.loads(
                                release_support_verifier_handoff_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            release_support_verifier_handoff = {"status": "unreadable"}
                    verifier_decision = release_support_verifier_handoff.get("operator_decision", {})
                    if not isinstance(verifier_decision, dict):
                        verifier_decision = {}
                    verifier_trust_boundary = release_support_verifier_handoff.get("trust_boundary", {})
                    if not isinstance(verifier_trust_boundary, dict):
                        verifier_trust_boundary = {}
                    lines.append(
                        "- release_support_verifier_handoff_artifact: "
                        f"`{release_support_verifier_handoff_path}`"
                    )
                    lines.append(
                        "- release_support_verifier_handoff_status: "
                        f"`{release_support_verifier_handoff.get('status', 'missing')}`"
                    )
                    lines.append(
                        "- release_support_verifier_handoff_owner: "
                        f"`{verifier_trust_boundary.get('release_acceptance_owner', 'ao-operator evaluator-closer')}`"
                    )
                    lines.append(
                        "- release_support_verifier_control_plane_approves_release: "
                        f"`{str(verifier_decision.get('control_plane_approves_release', False)).lower()}`"
                    )
            receipt = release_publication_publish.get("receipt", {})
            if isinstance(receipt, dict) and receipt.get("sha256"):
                lines.append(f"- release_publication_sha256: `{receipt['sha256']}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "nightly-ao2-advancement.json"
    markdown_path = out_dir / "nightly-ao2-advancement.md"
    notification_path = out_dir / "nightly-notification.json"
    artifacts = dict(payload.get("artifacts", {}))
    artifacts.update(
        {
            "json": str(json_path),
            "markdown": str(markdown_path),
            "notification": str(notification_path),
        }
    )
    payload["artifacts"] = artifacts
    payload["notification"] = build_notification_payload(payload)
    notification_path.write_text(
        json.dumps(payload["notification"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(payload, markdown_path)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload["artifacts"]


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Bounded Hermes cron job for AO2 advancement")
    parser.add_argument("--factory-root", type=Path, default=root)
    parser.add_argument("--ao2-root", type=Path, default=(root / ".." / "ao2").resolve())
    parser.add_argument(
        "--ao2-control-plane",
        type=Path,
        default=(root / ".." / "ao2-control-plane").resolve(),
    )
    parser.add_argument("--ao-runtime", type=Path, default=(root / ".." / "ao-runtime").resolve())
    parser.add_argument("--out-dir", type=Path, default=root / "run-artifacts" / "hermes-nightly-ao2")
    parser.add_argument("--ubuntu-target", default="ao2-ubuntu-nucx")
    parser.add_argument("--windows-target", default="win-hp255-via-ubuntu")
    parser.add_argument(
        "--provider-registry-control-plane-url",
        default=os.environ.get("AO2_CP_URL", "http://127.0.0.1:8744"),
    )
    parser.add_argument(
        "--provider-registry-signing-key",
        type=Path,
        default=Path(os.environ.get("AO2_PROVIDER_REGISTRY_SIGNING_KEY", root / "keys" / "ao2-provider-registry.pem")),
    )
    parser.add_argument(
        "--provider-registry-signer-id",
        default=os.environ.get("AO2_PROVIDER_REGISTRY_SIGNER_ID", "ao2-provider-registry"),
    )
    parser.add_argument(
        "--phase1-decision-signing-key",
        type=Path,
        default=Path(
            os.environ.get(
                "AO2_PHASE1_DECISION_SIGNING_KEY",
                root / ".." / "ao2" / ".release-signing" / "ao2-release-signing-key.pem",
            )
        ),
    )
    parser.add_argument(
        "--phase1-decision-signer-id",
        default=os.environ.get("AO2_PHASE1_DECISION_SIGNER_ID", "ao2-phase1-release"),
    )
    parser.add_argument(
        "--pack-evidence-signing-key",
        type=Path,
        default=(
            Path(os.environ["AO2_PACK_EVIDENCE_SIGNING_KEY"])
            if os.environ.get("AO2_PACK_EVIDENCE_SIGNING_KEY")
            else None
        ),
        help=(
            "Optional override for the AO2-owned signing key used by the "
            "release-ao2-native-evidence-pack-producer step. When omitted, "
            "the step falls back to --phase1-decision-signing-key, then "
            "--provider-registry-signing-key, then the standard repo-local "
            "locations. Factory-v3 only forwards the path; AO2 owns the key."
        ),
    )
    parser.add_argument(
        "--pack-evidence-signer-id",
        default=os.environ.get(
            "AO2_PACK_EVIDENCE_SIGNER_ID", "ao2-factory-pack-evidence-signer"
        ),
        help=(
            "Signer id passed to `ao2 factory pack-evidence --signer-id` "
            "when a signing key is discovered."
        ),
    )
    parser.add_argument(
        "--pack-evidence-disable-signing",
        action="store_true",
        help=(
            "Disable signing-key discovery for the "
            "release-ao2-native-evidence-pack-producer step entirely; the "
            "step runs unsigned even if a key file exists. Used by tests."
        ),
    )
    parser.add_argument(
        "--obligation-gate-signing-key",
        type=Path,
        default=(
            Path(os.environ["AO2_OBLIGATION_GATE_SIGNING_KEY"])
            if os.environ.get("AO2_OBLIGATION_GATE_SIGNING_KEY")
            else None
        ),
        help=(
            "Optional override for the AO2-owned signing key used by the "
            "midpoint/closure obligation-gate steps. Threaded through to "
            "`ao2 contract gate --support-signing-key` via "
            "`hermes_ao_bridge.py contract-gate`, which emits an "
            "`ao2.workbench-evidence-export.v1` wrapper + .json.sig + "
            "`workbench-evidence-signing-public.pem` next to each raw gate "
            "so downstream release-gate verifiers (and "
            "`ao2 contract obligation-gate-signing-survey --summary`) report "
            "`signed-and-verified`. When omitted, the step falls back to "
            "--pack-evidence-signing-key, --phase1-decision-signing-key, "
            "--provider-registry-signing-key, then standard repo-local "
            "locations. Factory-v3 only forwards the path; AO2 owns the key. "
            "Default-off when no key is discoverable preserves the legacy "
            "unsigned path."
        ),
    )
    parser.add_argument(
        "--obligation-gate-signer-id",
        default=os.environ.get(
            "AO2_OBLIGATION_GATE_SIGNER_ID",
            "ao2-nightly-obligation-gate-signer",
        ),
        help=(
            "Signer id passed to `ao2 contract gate --support-signer-id` "
            "when an obligation-gate signing key is discovered."
        ),
    )
    parser.add_argument(
        "--obligation-gate-operator-role",
        default=os.environ.get(
            "AO2_OBLIGATION_GATE_OPERATOR_ROLE", "operator"
        ),
        help=(
            "Operator role passed to "
            "`ao2 contract gate --support-operator-role` when an "
            "obligation-gate signing key is discovered. Must be non-empty "
            "for the verifier's `ao2_owned` check."
        ),
    )
    parser.add_argument(
        "--obligation-gate-signer-run-id",
        default=os.environ.get(
            "AO2_OBLIGATION_GATE_SIGNER_RUN_ID",
            "ao2-nightly-advancement",
        ),
        help=(
            "Run id passed to `ao2 contract gate --support-run-id` when an "
            "obligation-gate signing key is discovered. Recorded in the "
            "signed wrapper's audit_event for observability parity with "
            "workbench-emitted wrappers."
        ),
    )
    parser.add_argument(
        "--obligation-gate-disable-signing",
        action="store_true",
        help=(
            "Disable signing-key discovery for the midpoint/closure "
            "obligation-gate steps entirely; both gates emit unsigned even "
            "if a key file exists. Used by tests."
        ),
    )
    parser.add_argument(
        "--evaluator-decision-signing-key",
        type=Path,
        default=(
            Path(os.environ["AO2_EVALUATOR_DECISION_SIGNING_KEY"])
            if os.environ.get("AO2_EVALUATOR_DECISION_SIGNING_KEY")
            else None
        ),
        help=(
            "Optional override for the AO2-owned signing key used by the "
            "release-ao2-native-evaluator-producer step. Threaded through "
            "to `ao2 factory evaluate --signing-key` so the AO2 native "
            "evaluator decision is signed natively (parity-checklist: "
            "ao2_can_sign_native_evaluator_decision=true). When omitted, "
            "the step falls back to --obligation-gate-signing-key, "
            "--pack-evidence-signing-key, --phase1-decision-signing-key, "
            "--provider-registry-signing-key, then standard repo-local "
            "locations. Factory-v3 only forwards the path; AO2 owns the key."
        ),
    )
    parser.add_argument(
        "--evaluator-decision-signer-id",
        default=os.environ.get(
            "AO2_EVALUATOR_DECISION_SIGNER_ID",
            "ao2-native-evaluator-closer",
        ),
        help=(
            "Signer id passed to `ao2 factory evaluate --signer-id` when an "
            "evaluator-decision signing key is discovered."
        ),
    )
    parser.add_argument(
        "--evaluator-decision-disable-signing",
        action="store_true",
        help=(
            "Disable signing-key discovery for the "
            "release-ao2-native-evaluator-producer step entirely; the step "
            "runs unsigned even if a key file exists. Used by tests."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-signing-key",
        type=Path,
        default=(
            Path(os.environ["AO2_BRIDGE_EVIDENCE_SIGNING_KEY"])
            if os.environ.get("AO2_BRIDGE_EVIDENCE_SIGNING_KEY")
            else None
        ),
        help=(
            "Optional override for the AO2-owned signing key used by the "
            "factory-compat-nightly-run bridge canonicalization step. "
            "Threaded through to `ao2 factory bridge --signing-key` so the "
            "nightly emits AO2-native `ao2.factory-bridge.v1` schema "
            "evidence + signed sidecars instead of the legacy ao-operator "
            "compat schema. When omitted, the step falls back to "
            "--evaluator-decision-signing-key, --obligation-gate-signing-key, "
            "--pack-evidence-signing-key, --phase1-decision-signing-key, "
            "--provider-registry-signing-key, then standard repo-local "
            "locations. Factory-v3 only forwards the path; AO2 owns the key."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-signer-id",
        default=os.environ.get(
            "AO2_BRIDGE_EVIDENCE_SIGNER_ID",
            "ao2-factory-bridge",
        ),
        help=(
            "Signer id passed to `ao2 factory bridge --signer-id` when a "
            "bridge-evidence signing key is discovered."
        ),
    )
    parser.add_argument(
        "--bridge-evidence-disable-signing",
        action="store_true",
        help=(
            "Disable signing-key discovery for the factory-compat-nightly-run "
            "bridge canonicalization step entirely; the orchestrator stays on "
            "the Python-local helper and emits the legacy compat schema "
            "(no signing, no sidecars) even if a key file exists. Used by tests."
        ),
    )
    parser.add_argument(
        "--factory-compat-ao-operator-runspec",
        type=Path,
        default=None,
        help=(
            "Override path to the AO Operator RunSpec the nightly bridge "
            "canonicalises before AO2 plans the run. Defaults to "
            "ao-operator/ao/runspecs/ao-operator-smoke.yaml when present. "
            "Wires Phase 2 exit-gate items #1, #2, #3 into the nightly chain."
        ),
    )
    parser.add_argument(
        "--factory-compat-disable-ao-operator-bridge",
        action="store_true",
        help=(
            "Skip the AO Operator -> AO2 bridge + Hermes AO2-refs context "
            "emission for the factory-compat nightly step. Falls back to "
            "the synthetic-runspec path. Used by tests that exercise the "
            "legacy code path or environments where the canonical RunSpec "
            "is absent."
        ),
    )
    parser.add_argument(
        "--factory-compat-control-plane-receipt",
        type=Path,
        default=None,
        help=(
            "Override path to an ao2-control-plane ingest receipt JSON "
            "(schema_version: ao2.cp-ingest-receipt.v1) the nightly step "
            "pins into the Hermes AO2-refs payload. When omitted, the "
            "step auto-discovers a receipt at "
            "<out-dir>/factory-compat-cp-ingest-receipt.json when present."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-record-out",
        type=Path,
        default=None,
        help=(
            "Override path the nightly step writes the AO2 memory record "
            "JSON (schema_version: ao2.memory-record.v1) to. The "
            "orchestrator invokes `ao2 memory write --json` after "
            "pack-evidence and pins the returned record id + sha256 "
            "into the Hermes AO2-refs payload. Defaults to "
            "<out-dir>/factory-compat-memory-record.json. Closes the "
            "memory record identifier half of Phase 2 exit-gate item #3."
        ),
    )
    parser.add_argument(
        "--factory-compat-disable-ao-operator-memory-record",
        action="store_true",
        help=(
            "Skip the `ao2 memory write` step in the factory-compat "
            "nightly orchestrator. The Hermes AO2-refs payload still "
            "carries mapping digest + evidence-pack sha + AO2 run id, "
            "but no memory record id. Used by tests."
        ),
    )
    parser.add_argument(
        "--factory-compat-require-all-ao2-ref-categories",
        action="store_true",
        help=(
            "Strict-mode: forward --require-all-ao2-ref-categories to the "
            "factory-compat orchestrator so it refuses to emit the Hermes "
            "context payload unless all four Phase 2 #3 AO2 ref "
            "categories (bridge_evidence, evidence_pack, memory_record, "
            "cp_receipt) are present. Disabled by default; opt in once "
            "the memory-publish CP-receipt producer is configured "
            "(--factory-compat-memory-publish-control-plane-url + "
            "AO2_CP_API_TOKEN). Closes Phase 2 exit-gate item #3's "
            "machine-checkable invariant."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-control-plane-url",
        default=None,
        help=(
            "ao2-control-plane base URL the factory-compat memory-publish "
            "step posts the signed memory export to. When omitted or blank "
            "the step skips with status=skipped — Hermes auto-discovery "
            "then finds no receipt and the payload omits the "
            "control_plane_* fields. Closes the producer half of Phase 2 "
            "exit-gate item #3, ao2-control-plane observer slice."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-api-token-env",
        default="AO2_CP_API_TOKEN",
        help=(
            "Environment variable that holds the bearer token forwarded to "
            "ao2 memory publish via --api-token. Default AO2_CP_API_TOKEN; "
            "step skips when unset. Never echoed in any logged output."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-target",
        type=Path,
        default=None,
        help=(
            "Override the factory-compat target directory passed to "
            "ao2 memory export --target. Defaults to the same target the "
            "factory-compat nightly run populates so the published export "
            "covers the memory record the chain just wrote."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-export-out",
        type=Path,
        default=None,
        help=(
            "Override the ao2.memory-export.v1 path written by "
            "ao2 memory export. Defaults to "
            "<out-dir>/factory-compat-memory-export.json."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-signing-key",
        type=Path,
        default=None,
        help=(
            "Override the ed25519 key passed to ao2 memory export "
            "--signing-key. When omitted the same discovery chain the "
            "pack-evidence step uses applies so operators do not have to "
            "provision a separate key."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-signer-id",
        default="ao2-memory",
        help=(
            "signer-id forwarded to ao2 memory export. Default ao2-memory."
        ),
    )
    parser.add_argument(
        "--factory-compat-memory-publish-allow-unsigned",
        action="store_true",
        help=(
            "Opt out of slice-19 default-on signed publish (forwards "
            "--allow-unsigned-memory-export to ao2 memory publish). Hidden "
            "from operator-facing flows because the principled path is to "
            "supply a signing key; intended for tests."
        ),
    )
    parser.add_argument(
        "--require-pack-evidence-signed",
        action="store_true",
        help=(
            "When a signing key is discovered, also pass "
            "--require-signed-evidence so the bridge refuses to accept the "
            "produced summary unless AO2 reports signature_verified=true "
            "and deterministic_replay.verified=true."
        ),
    )
    parser.add_argument("--require-remotes", action="store_true")
    parser.add_argument(
        "--require-provider-readiness-publish",
        action="store_true",
        help="Fail the release-gate dry-run unless provider readiness was published to the control plane.",
    )
    parser.add_argument(
        "--provider-acceptance-bundle",
        type=Path,
        action="append",
        default=[],
        help="Already-created AO2 Codex/Claude provider-pilot acceptance bundle to publish as observer evidence.",
    )
    parser.add_argument(
        "--provider-acceptance-root",
        type=Path,
        default=None,
        help="Root scanned recursively for provider-pilot-acceptance.json when no explicit bundle is supplied.",
    )
    parser.add_argument(
        "--require-provider-acceptance-publish",
        action="store_true",
        help="Fail the release-gate dry-run unless provider-pilot acceptance evidence was published.",
    )
    parser.add_argument(
        "--require-provider-acceptance-source",
        choices=("any", "live"),
        default="any",
        help=(
            "Fail the release-gate dry-run unless published provider-pilot acceptance "
            "evidence comes from the required source class. Use live for final Phase 1 promotion."
        ),
    )
    parser.add_argument(
        "--require-live-provider-pilot",
        choices=("codex", "claude"),
        action="append",
        default=[],
        help="Require an already-recorded live provider gate/pilot to be ready; does not start live provider execution.",
    )
    parser.add_argument(
        "--release-publication-artifact",
        type=Path,
        help=(
            "Optional ao2.release-publication-summary.v1 artifact to publish to the control plane; "
            "defaults to the latest published v*-phase1-release.json under the AO2 release-candidates directory."
        ),
    )
    parser.add_argument("--repeat-failure-threshold", type=int, default=2)
    parser.add_argument("--force-repeat-failure-run", action="store_true")
    parser.add_argument(
        "--cancel-authority-dry-run-mode",
        choices=("auto", "force", "off"),
        default="auto",
        help=(
            "Cadence mode for the AO2 watchdog cancel-authority dry-run step. "
            "auto: run only on --cancel-authority-dry-run-weekday; "
            "force: always run when ao2 binary is present; "
            "off: never run."
        ),
    )
    parser.add_argument(
        "--cancel-authority-dry-run-weekday",
        type=int,
        default=1,
        help=(
            "ISO weekday (1=Mon..7=Sun) on which to run the cancel-authority "
            "dry-run when --cancel-authority-dry-run-mode=auto. Defaults to 1 (Mon)."
        ),
    )
    parser.add_argument(
        "--cancel-authority-dry-run-active-pid",
        type=int,
        default=4242,
        help=(
            "Synthetic active PID passed through to the dry-run script. "
            "No real process with this PID is signalled or inspected; the "
            "value is used only inside build_ownership to assert the "
            "no-active attestation covers the recorded terminated_pid."
        ),
    )
    parser.add_argument(
        "--cancel-authority-dry-run-reason",
        default="",
        help=(
            "Operator reason recorded on the dry-run attestation. Empty "
            "string falls back to the wrapper script's nightly default."
        ),
    )
    parser.add_argument(
        "--cancel-authority-dry-run-strict",
        action="store_true",
        help=(
            "Exit the cancel-authority dry-run step with status=failed "
            "if status is capture_failed/binary_missing or executed-but-"
            "not-accepted. The skipped status never trips --strict."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def normalize_args_paths(args: argparse.Namespace) -> None:
    path_attrs = [
        "factory_root",
        "ao2_root",
        "ao2_control_plane",
        "ao_runtime",
        "out_dir",
        "provider_registry_signing_key",
        "phase1_decision_signing_key",
        "pack_evidence_signing_key",
        "obligation_gate_signing_key",
        "evaluator_decision_signing_key",
        "bridge_evidence_signing_key",
        "provider_acceptance_root",
        "release_publication_artifact",
    ]
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if value is not None:
            setattr(args, attr, Path(value).expanduser().resolve())
    args.provider_acceptance_bundle = [
        Path(value).expanduser().resolve()
        for value in (getattr(args, "provider_acceptance_bundle", []) or [])
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    normalize_args_paths(args)
    obligation_artifacts = write_nightly_obligation_ledger(args)
    write_planned_control_plane_release_smoke_artifact(args)
    write_planned_release_gate_dry_run_artifact(args)
    write_planned_three_os_smoke_observer_artifact(args)
    write_planned_three_os_smoke_publish_artifact(args)
    write_planned_phase1_promotion_checklist_artifact(args)
    write_planned_phase1_promotion_checklist_publish_artifact(args)
    write_planned_phase1_promotion_decision_publish_artifact(args)
    write_planned_phase1_promotion_history_artifact(args)
    write_planned_phase1_promotion_status_artifact(args)
    write_planned_phase1_promotion_panel_artifact(args)
    write_planned_release_publication_publish_artifact(args)
    write_planned_release_cockpit_status_artifact(args)
    write_planned_release_handoff_status_artifact(args)
    write_planned_release_readiness_status_artifact(args)
    write_planned_release_support_bundle_status_artifact(args)
    write_planned_release_handoff_checklist_artifact(args)
    write_planned_release_evaluator_decision_artifact(args)
    write_planned_release_evaluator_decision_publish_artifact(args)
    write_planned_release_evaluator_decision_status_artifact(args)
    write_planned_factory_compat_nightly_run_summary_artifact(args)
    write_planned_release_ao2_native_evidence_pack_producer_summary_artifact(args)
    write_planned_release_ao2_native_evaluator_producer_summary_artifact(args)
    write_planned_release_ao2_native_evaluator_verification_artifact(args)
    write_planned_release_evaluator_closure_with_ao2_verification_artifact(args)
    write_planned_release_support_bundle_status_artifact(
        args,
        output_path=nightly_release_support_bundle_post_decision_status_path(args),
        phase="post_evaluator_decision_publish",
    )
    write_planned_release_support_verifier_handoff_artifact(args)
    write_planned_provider_phase1_readiness_artifact(args)
    write_planned_provider_phase1_readiness_publish_artifact(args)
    write_planned_provider_acceptance_publish_artifact(args)
    write_planned_provider_acceptance_preservation_artifact(args)
    write_planned_cancel_authority_dry_run_artifact(args)
    steps = build_steps(args)
    guard_payload = None if args.dry_run else repeat_failure_guard_payload(args, steps)
    if guard_payload is not None:
        write_outputs(guard_payload, args.out_dir)
        print(
            json.dumps(guard_payload, indent=2, sort_keys=True)
            if args.json
            else guard_payload["artifacts"]["markdown"]
        )
        return 1
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "status": "planned" if args.dry_run else "running",
        "steps": steps,
        "remotes_required": args.require_remotes,
    }
    gap_backlog_path = write_gap_backlog(payload, args.out_dir, args)
    payload["artifacts"] = {
        "gap_backlog": str(gap_backlog_path),
        "provider_registry": str(nightly_provider_registry_path(args)),
        "provider_registry_publish": str(nightly_provider_registry_publish_path(args)),
        "control_plane_release_smoke": str(nightly_control_plane_release_smoke_path(args)),
        "provider_phase1_readiness": str(nightly_provider_phase1_readiness_path(args)),
        "provider_phase1_readiness_publish": str(nightly_provider_phase1_readiness_publish_path(args)),
        "provider_acceptance_publish": str(nightly_provider_acceptance_publish_path(args)),
        "provider_acceptance_preservation": str(nightly_provider_acceptance_preservation_path(args)),
        "cancel_authority_dry_run": str(nightly_cancel_authority_dry_run_path(args)),
        "three_os_smoke_observer": str(nightly_three_os_smoke_observer_path(args)),
        "three_os_smoke_publish": str(nightly_three_os_smoke_publish_path(args)),
        "phase1_promotion_checklist": str(nightly_phase1_promotion_checklist_path(args)),
        "phase1_promotion_checklist_publish": str(nightly_phase1_promotion_checklist_publish_path(args)),
        "phase1_promotion_decision": str(nightly_phase1_promotion_decision_path(args)),
        "phase1_promotion_decision_publish": str(nightly_phase1_promotion_decision_publish_path(args)),
        "phase1_promotion_history": str(nightly_phase1_promotion_history_path(args)),
        "phase1_promotion_status": str(nightly_phase1_promotion_status_path(args)),
        "phase1_promotion_panel": str(nightly_phase1_promotion_panel_path(args)),
        "phase1_promotion_panel_markdown": str(nightly_phase1_promotion_panel_markdown_path(args)),
        "release_publication_publish": str(nightly_release_publication_publish_path(args)),
        "release_cockpit_status": str(nightly_release_cockpit_status_path(args)),
        "release_handoff_status": str(nightly_release_handoff_status_path(args)),
        "release_readiness_status": str(nightly_release_readiness_status_path(args)),
        "release_support_bundle_status": str(nightly_release_support_bundle_status_path(args)),
        "release_handoff_checklist": str(nightly_release_handoff_checklist_path(args)),
        "release_handoff_checklist_markdown": str(nightly_release_handoff_checklist_markdown_path(args)),
        "release_evaluator_decision": str(nightly_release_evaluator_decision_path(args)),
        "release_evaluator_decision_markdown": str(nightly_release_evaluator_decision_markdown_path(args)),
        "release_evaluator_decision_publish": str(nightly_release_evaluator_decision_publish_path(args)),
        "release_evaluator_decision_status": str(nightly_release_evaluator_decision_status_path(args)),
        "factory_compat_nightly_run_summary": str(
            nightly_factory_compat_nightly_run_summary_path(args)
        ),
        "factory_compat_nightly_run_evidence_pack": str(
            nightly_factory_compat_evidence_pack_path(args)
        ),
        "factory_compat_bridge_evidence": str(
            nightly_factory_compat_bridge_evidence_path(args)
        ),
        "release_ao2_native_evidence_pack_producer_summary": str(
            nightly_release_ao2_native_evidence_pack_producer_summary_path(args)
        ),
        "release_ao2_native_evidence_pack": str(
            nightly_release_ao2_native_evidence_pack_path(args)
        ),
        "release_ao2_native_evaluator_producer_summary": str(
            nightly_release_ao2_native_evaluator_producer_summary_path(args)
        ),
        "release_ao2_native_evaluator_producer_decision": str(
            nightly_release_ao2_native_evaluator_producer_decision_path(args)
        ),
        "release_ao2_native_evaluator_verification": str(
            nightly_release_ao2_native_evaluator_verification_path(args)
        ),
        "release_evaluator_closure_with_ao2_verification": str(
            nightly_release_evaluator_closure_with_ao2_verification_path(args)
        ),
        "release_evaluator_closure_with_ao2_verification_markdown": str(
            nightly_release_evaluator_closure_with_ao2_verification_markdown_path(args)
        ),
        "release_support_bundle_post_decision_status": str(
            nightly_release_support_bundle_post_decision_status_path(args)
        ),
        "release_support_verifier_handoff": str(
            nightly_release_support_verifier_handoff_path(args)
        ),
        "release_support_verifier_handoff_markdown": str(
            nightly_release_support_verifier_handoff_markdown_path(args)
        ),
        **obligation_artifacts,
    }
    if not args.dry_run:
        with managed_provider_readiness_control_plane(args) as control_plane:
            if control_plane.get("status") != "not_required":
                payload["provider_readiness_control_plane"] = control_plane
            log_dir = args.out_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            failures: list[str] = []
            for step in payload["steps"]:
                if step["id"] == "gap-miner":
                    gap_log = log_dir / "gap-miner.log"
                    gap_summary = payload["gap_backlog"]
                    gap_log.write_text(
                        json.dumps(gap_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = "passed"
                    step["exit_code"] = 0
                    step["duration_seconds"] = 0.0
                    step["log"] = str(gap_log)
                elif step["id"] == "provider-phase1-readiness":
                    started = time.time()
                    provider_log = log_dir / "provider-phase1-readiness.log"
                    provider_summary = write_provider_phase1_readiness_artifact(args)
                    provider_log.write_text(
                        json.dumps(provider_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = "passed" if provider_summary.get("status") == "passed" else "failed"
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(provider_log)
                elif step["id"] == "provider-phase1-readiness-publish":
                    started = time.time()
                    publish_log = log_dir / "provider-phase1-readiness-publish.log"
                    publish_summary = write_provider_phase1_readiness_publish_artifact(args)
                    publish_log.write_text(
                        json.dumps(publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(publish_log)
                elif step["id"] == "provider-acceptance-publish":
                    started = time.time()
                    publish_log = log_dir / "provider-acceptance-publish.log"
                    publish_summary = write_provider_acceptance_publish_artifact(args)
                    publish_log.write_text(
                        json.dumps(publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(publish_log)
                elif step["id"] == "ao2-release-gate-dry-run":
                    started = time.time()
                    gate_log = log_dir / "ao2-release-gate-dry-run.log"
                    gate_summary = write_release_gate_dry_run_artifact(args)
                    gate_log.write_text(
                        json.dumps(gate_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = "passed" if gate_summary.get("status") == "passed" else "failed"
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(gate_log)
                elif step["id"] == "phase1-promotion-checklist":
                    started = time.time()
                    checklist_log = log_dir / "phase1-promotion-checklist.log"
                    checklist_summary = write_phase1_promotion_checklist_artifact(args)
                    checklist_log.write_text(
                        json.dumps(checklist_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if checklist_summary.get("status") in {"passed", "blocked"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(checklist_log)
                elif step["id"] == "three-os-smoke-observer":
                    started = time.time()
                    smoke_log = log_dir / "three-os-smoke-observer.log"
                    smoke_summary = write_three_os_smoke_observer_artifact(args)
                    smoke_log.write_text(
                        json.dumps(smoke_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = "passed" if smoke_summary.get("status") == "passed" else "failed"
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(smoke_log)
                elif step["id"] == "three-os-smoke-publish":
                    started = time.time()
                    smoke_publish_log = log_dir / "three-os-smoke-publish.log"
                    smoke_publish_summary = write_three_os_smoke_publish_artifact(args)
                    smoke_publish_log.write_text(
                        json.dumps(smoke_publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if smoke_publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(smoke_publish_log)
                elif step["id"] == "phase1-promotion-checklist-publish":
                    started = time.time()
                    checklist_publish_log = log_dir / "phase1-promotion-checklist-publish.log"
                    checklist_publish_summary = write_phase1_promotion_checklist_publish_artifact(args)
                    checklist_publish_log.write_text(
                        json.dumps(checklist_publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if checklist_publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(checklist_publish_log)
                elif step["id"] == "phase1-promotion-decision-publish":
                    started = time.time()
                    decision_publish_log = log_dir / "phase1-promotion-decision-publish.log"
                    decision_publish_summary = write_phase1_promotion_decision_publish_artifact(args)
                    decision_publish_log.write_text(
                        json.dumps(decision_publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if decision_publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(decision_publish_log)
                elif step["id"] == "release-publication-publish":
                    started = time.time()
                    publication_publish_log = log_dir / "release-publication-publish.log"
                    publication_publish_summary = write_release_publication_publish_artifact(args)
                    publication_publish_log.write_text(
                        json.dumps(publication_publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if publication_publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(publication_publish_log)
                elif step["id"] == "release-evaluator-decision-publish":
                    started = time.time()
                    decision_publish_log = log_dir / "release-evaluator-decision-publish.log"
                    decision_publish_summary = write_release_evaluator_decision_publish_artifact(args)
                    decision_publish_log.write_text(
                        json.dumps(decision_publish_summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    step["status"] = (
                        "passed"
                        if decision_publish_summary.get("status") in {"passed", "skipped"}
                        else "failed"
                    )
                    step["exit_code"] = 0 if step["status"] == "passed" else 1
                    step["duration_seconds"] = round(time.time() - started, 3)
                    step["log"] = str(decision_publish_log)
                else:
                    if step["id"] == "ao2-release-summary-enrich":
                        write_release_summary_from_bridge_log(args, log_dir)
                    run_step(step, log_dir)
                if step["status"] != "passed":
                    failures.append(step["id"])
                    break
            payload["failures"] = failures
            payload["status"] = "failed" if failures else "passed"
            payload["artifacts"].update(update_failure_history_from_payload(args, payload))
    write_outputs(payload, args.out_dir)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload["artifacts"]["markdown"])
    return 0 if payload["status"] in {"planned", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
