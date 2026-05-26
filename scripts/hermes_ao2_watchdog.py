#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import signal
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ao2_watchdog_cancel_ownership as _cancel_ownership  # noqa: E402


SCHEMA = "ao-operator/hermes-ao2-watchdog/v1"
PANEL_SCHEMA = "ao-operator/hermes-ao2-watchdog-panel/v1"
LEGACY_AUTHORITY_WARNING = (
    "ao-operator retained cancel authority; supply --ao2-cancel-transition "
    "or --no-active-ao2-runs-attestation to record AO2-owned authority inline"
)
_AO2_OWNERSHIP_DEFAULT = {
    "cancel_owner": _cancel_ownership.EXPECTED_AO2_DECISION_OWNER,
    "retry_owner": _cancel_ownership.EXPECTED_AO2_DECISION_OWNER,
    "factory_v3_role": _cancel_ownership.EXPECTED_FACTORY_V3_ROLE,
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_pid(lock_dir: Path) -> int | None:
    try:
        text = (lock_dir / "pid").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def release_lock(lock_dir: Path) -> None:
    shutil.rmtree(lock_dir, ignore_errors=True)


def terminate_process(pid: int, *, grace_seconds: float) -> None:
    if pid <= 0:
        return
    use_process_group = False
    try:
        use_process_group = os.getpgid(pid) == pid
    except OSError:
        return
    try:
        if use_process_group:
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        return
    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        if use_process_group:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        return


def lock_age_seconds(lock_dir: Path) -> float | None:
    try:
        return time.time() - lock_dir.stat().st_mtime
    except OSError:
        return None


def acquire_lock(
    lock_dir: Path, *, max_lock_age_seconds: int
) -> tuple[bool, int | None, bool, float | None, bool]:
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
    except FileExistsError:
        pid = read_pid(lock_dir)
        age = lock_age_seconds(lock_dir)
        if pid is not None and pid_alive(pid):
            overdue = age is not None and age > max_lock_age_seconds
            return False, pid, False, age, overdue
        stale = True
        if age is None:
            age = max_lock_age_seconds + 1
        if age <= max_lock_age_seconds and pid is None:
            return False, pid, False, age, False
        release_lock(lock_dir)
        lock_dir.mkdir()
        return True, None, stale, age, False
    return True, None, False, 0.0, False


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sanitized_for_status(value: Any, *, secret: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            if str(key).lower() in {"authorization", "api_token", "bearer_token", "token"}:
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = sanitized_for_status(nested, secret=secret)
        return sanitized
    if isinstance(value, list):
        return [sanitized_for_status(item, secret=secret) for item in value]
    if isinstance(value, str):
        sanitized = value
        if secret:
            sanitized = sanitized.replace(secret, "<redacted>")
        return sanitized
    return value


def json_request(
    url: str,
    *,
    api_token: str,
    method: str,
    body: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_token}",
    }
    if body is not None:
        headers["content-type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        status_code = int(response.status)
        response_body = response.read().decode("utf-8")
    if not response_body.strip():
        return status_code, {}
    payload = json.loads(response_body)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return status_code, payload


def shell_join(command: list[Any]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def load_base_prompt(args: argparse.Namespace) -> str:
    return args.prompt_file.read_text(encoding="utf-8")


def latest_nonaccepted_evidence_pack(ao2_root: Path) -> dict[str, Any] | None:
    runs_root = ao2_root / ".ao2" / "runs"
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
        return None
    candidates.sort(key=lambda item: (int(item["mtime_ns"]), item["path"]), reverse=True)
    return candidates[0]


def ao2_release_bin(args: argparse.Namespace) -> Path:
    return args.ao2_root / "target" / "release" / ("ao2.exe" if os.name == "nt" else "ao2")


def normal_advancement_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(args.factory_root / "scripts" / "hermes_nightly_ao2_advancement.py"),
        "--factory-root",
        str(args.factory_root),
        "--ao2-root",
        str(args.ao2_root),
        "--ao2-control-plane",
        str(args.ao2_control_plane),
        "--ao-runtime",
        str(args.ao_runtime),
        "--out-dir",
        str(args.status_dir / "nightly-ao2"),
        "--require-remotes",
        "--json",
    ]


def repair_resume_latest_command(args: argparse.Namespace) -> list[str]:
    run_id = f"hermes-watchdog-repair-{int(time.time())}"
    command = [
        sys.executable,
        str(args.factory_root / "scripts" / "hermes_ao_bridge.py"),
        "repair-resume-latest",
        "--template",
        args.repair_template,
        "--ao2-target",
        str(args.ao2_root),
        "--ao2-bin",
        str(ao2_release_bin(args)),
        "--run-id",
        run_id,
        "--provider",
        args.repair_provider,
        "--provider-prompt-file",
        str(args.prompt_file),
        "--json",
    ]
    if getattr(args, "ao2_queue_submit", None) is not None:
        command.extend(["--ao2-queue-submit", str(args.ao2_queue_submit)])
    for transition in getattr(args, "ao2_queue_transitions", None) or []:
        command.extend(["--ao2-queue-transition", str(transition)])
    if getattr(args, "ao2_queue_ownership_out", None) is not None:
        command.extend(["--ao2-queue-ownership-out", str(args.ao2_queue_ownership_out)])
    if getattr(args, "require_ao2_queue_ownership", False):
        command.append("--require-ao2-queue-ownership")
    return command


def backend_decision(args: argparse.Namespace) -> dict[str, Any]:
    selected = latest_nonaccepted_evidence_pack(args.ao2_root)
    if selected is not None and args.decision_mode in {"auto", "repair-latest"}:
        return {
            "mode": "repair_resume_latest",
            "reason": "latest non-accepted AO2 evidence pack exists",
            "selected": selected,
            "command": repair_resume_latest_command(args),
            "trust_boundary": {
                "frontend": "Hermes",
                "trusted_execution": "ao2 repair resume",
                "governed_backend": "ao-operator / AO Operator evaluator-closer",
                "control_plane": "ao2-control-plane read-only observer",
            },
        }
    return {
        "mode": "normal_advancement",
        "reason": "no non-accepted AO2 evidence pack found" if selected is None else "decision mode forced normal advancement",
        "selected": selected,
        "command": normal_advancement_command(args),
        "trust_boundary": {
            "frontend": "Hermes",
            "trusted_execution": "ao2 signed evidence boundary",
            "governed_backend": "ao-operator / AO Operator evaluator-closer",
            "control_plane": "ao2-control-plane read-only observer",
        },
    }


def render_prompt(args: argparse.Namespace, decision: dict[str, Any]) -> str:
    base_prompt = load_base_prompt(args)
    command = shell_join(decision["command"])
    selected = decision.get("selected") or {}
    selected_lines = []
    if selected:
        selected_lines = [
            f"- selected_evidence_pack: {selected.get('path', '')}",
            f"- selected_run_id: {selected.get('run_id', '')}",
            f"- selected_verdict: {selected.get('verdict', '')}",
        ]
    return "\n".join(
        [
            base_prompt.rstrip(),
            "",
            "Hermes watchdog backend decision:",
            f"- Backend route selected: {decision['mode']}",
            f"- Reason: {decision['reason']}",
            *selected_lines,
            "",
            "Execute this backend command first unless a newer blocker is discovered:",
            "",
            "```sh",
            command,
            "```",
            "",
            "After it finishes, verify artifacts and preserve the same trust boundary.",
            "",
        ]
    )


def command_for(args: argparse.Namespace, prompt_text: str) -> list[str]:
    return [args.hermes_bin, "-z", prompt_text]


def prompt_metadata(args: argparse.Namespace, prompt: str) -> dict[str, str]:
    snapshot_path = args.status_dir / "ao2-watchdog-prompt.md"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(prompt, encoding="utf-8")
    return {
        "path": str(args.prompt_file),
        "sha256": sha256_text(prompt),
        "snapshot_path": str(snapshot_path),
    }


def create_guard_bin(args: argparse.Namespace) -> Path:
    guard_bin = args.status_dir / "guard-bin"
    guard_bin.mkdir(parents=True, exist_ok=True)
    gate_path = args.status_dir / "three-os-completion-gate.json"
    gate_script = Path(__file__).resolve().with_name("check_hermes_three_os_completion_gate.py")
    real_git = shutil.which("git") or "git"
    git_wrapper = guard_bin / "git"
    git_wrapper.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"REAL_GIT={real_git!r}",
                f"GATE_SCRIPT={str(gate_script)!r}",
                "GATE_PATH=\"${HERMES_AO2_COMPLETION_GATE_PATH:-}\"",
                "subcommand=\"${1:-}\"",
                "case \"$subcommand\" in",
                "  commit|push|merge|tag)",
                "    if [[ -z \"$GATE_PATH\" ]]; then",
                "      echo \"Hermes AO2 completion gate path is not set\" >&2",
                "      exit 1",
                "    fi",
                "    python3 \"$GATE_SCRIPT\" --gate \"$GATE_PATH\" >/dev/null",
                "    ;;",
                "esac",
                "exec \"$REAL_GIT\" \"$@\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    git_wrapper.chmod(0o755)
    if not gate_path.exists():
        write_json(
            gate_path,
            {
                "schema": "ao-operator/hermes-three-os-completion-gate/v1",
                "verdict": "pending",
                "platforms": {},
            },
        )
    return guard_bin


def start_hermes(args: argparse.Namespace, lock_dir: Path) -> tuple[subprocess.Popen[str], dict[str, str]]:
    logs_dir = args.status_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    guard_bin = create_guard_bin(args)
    gate_path = args.status_dir / "three-os-completion-gate.json"
    child_env = dict(os.environ)
    child_env["HERMES_AO2_COMPLETION_GATE_PATH"] = str(gate_path)
    child_env["PATH"] = str(guard_bin) + os.pathsep + child_env.get("PATH", "")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stdout_path = logs_dir / f"hermes-ao2-{stamp}.out.log"
    stderr_path = logs_dir / f"hermes-ao2-{stamp}.err.log"
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    try:
        child = subprocess.Popen(
            command_for(args, args.watchdog_prompt_text),
            cwd=args.factory_root,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
            env=child_env,
        )
    except Exception:
        stdout.close()
        stderr.close()
        release_lock(lock_dir)
        raise
    stdout.close()
    stderr.close()
    (lock_dir / "pid").write_text(str(child.pid) + "\n", encoding="utf-8")
    (lock_dir / "started_at_ms").write_text(str(int(time.time() * 1000)) + "\n", encoding="utf-8")
    return child, {"stdout": str(stdout_path), "stderr": str(stderr_path)}


def base_payload(args: argparse.Namespace, status: str, prompt: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_at_ms": int(time.time() * 1000),
        "status": status,
        "next_check_seconds": args.interval_seconds,
        "factory_root": str(args.factory_root),
        "ao2_root": str(args.ao2_root),
        "ao2_control_plane": str(args.ao2_control_plane),
        "ao_runtime": str(args.ao_runtime),
        "prompt": prompt,
        "backend_decision": args.backend_decision,
    }


def watchdog_panel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("backend_decision") or {}
    selected = decision.get("selected") or {}
    prompt = payload.get("prompt") or {}
    artifacts = payload.get("artifacts") or {}
    lock = {
        "active_pid": payload.get("active_pid"),
        "lock_age_seconds": payload.get("lock_age_seconds"),
        "lock_dir": payload.get("lock_dir"),
        "max_lock_age_seconds": payload.get("max_lock_age_seconds"),
        "stale_lock_removed": payload.get("stale_lock_removed"),
    }
    panel: dict[str, Any] = {
        "schema": PANEL_SCHEMA,
        "generated_at_ms": payload.get("generated_at_ms"),
        "watchdog_status": payload.get("status"),
        "watchdog_action": payload.get("action"),
        "next_check_seconds": payload.get("next_check_seconds"),
        "backend_route": decision.get("mode"),
        "reason": decision.get("reason"),
        "selected_evidence": selected,
        "backend_command": decision.get("command") or [],
        "backend_command_text": shell_join(decision.get("command") or []),
        "prompt_snapshot": prompt.get("snapshot_path"),
        "lock": {key: value for key, value in lock.items() if value is not None},
        "logs": payload.get("logs") or {},
        "trust_boundary": decision.get("trust_boundary") or {},
        "operator_links": {
            "selected_evidence": selected.get("path", ""),
            "prompt_snapshot": prompt.get("snapshot_path", ""),
            "watchdog_status": artifacts.get("watchdog_status", ""),
        },
    }
    authority = payload.get("ao2_cancel_authority")
    if authority is not None:
        panel["ao2_cancel_authority"] = authority
    return panel


def watchdog_panel_markdown(panel: dict[str, Any]) -> str:
    selected = panel.get("selected_evidence") or {}
    trust_boundary = panel.get("trust_boundary") or {}
    logs = panel.get("logs") or {}
    lines = [
        "# Hermes AO2 Watchdog Operator Panel",
        "",
        f"- Status: {panel.get('watchdog_status') or ''}",
        f"- Action: {panel.get('watchdog_action') or ''}",
        f"- Backend route: {panel.get('backend_route') or ''}",
        f"- Reason: {panel.get('reason') or ''}",
        f"- Next check seconds: {panel.get('next_check_seconds') or ''}",
        "",
        "## Selected Evidence",
        "",
        f"- Run ID: {selected.get('run_id', '')}",
        f"- Verdict: {selected.get('verdict', '')}",
        f"- Path: {selected.get('path', '')}",
        "",
        "## Backend Command",
        "",
        "```sh",
        str(panel.get("backend_command_text") or ""),
        "```",
        "",
        "## Trust Boundary",
        "",
    ]
    for key in ("frontend", "trusted_execution", "governed_backend", "control_plane"):
        lines.append(f"- {key}: {trust_boundary.get(key, '')}")
    lines.extend(
        [
            "",
            "## Operator Links",
            "",
            f"- Prompt snapshot: {panel.get('prompt_snapshot') or ''}",
            f"- Selected evidence: {selected.get('path', '')}",
            f"- Stdout log: {logs.get('stdout', '')}",
            f"- Stderr log: {logs.get('stderr', '')}",
            "",
        ]
    )
    authority = panel.get("ao2_cancel_authority")
    if authority:
        sources = authority.get("sources") or {}
        claim = authority.get("claim") or {}
        lines.extend(
            [
                "## AO2 Cancel Authority",
                "",
                f"- Mode: {authority.get('mode', '')}",
                f"- Decision: {authority.get('decision', '')}",
            ]
        )
        if authority.get("warning"):
            lines.append(f"- Warning: {authority['warning']}")
        if authority.get("error"):
            lines.append(f"- Error: {authority['error']}")
        if claim:
            lines.append(f"- Claim status: {claim.get('status', '')}")
        transitions = sources.get("transitions") or []
        if transitions:
            for path in transitions:
                lines.append(f"- Transition source: {path}")
        attestation = sources.get("no_active_ao2_runs_attestation")
        if attestation:
            lines.append(f"- No-active-runs attestation: {attestation}")
        lines.append("")
    return "\n".join(lines)


def publish_watchdog_panel_to_control_plane(
    args: argparse.Namespace, panel_json_path: Path
) -> dict[str, Any]:
    base_url = str(args.publish_control_plane_url or "").rstrip("/")
    token_env = str(args.publish_api_token_env)
    result: dict[str, Any] = {
        "status": "failed",
        "control_plane_url": base_url,
        "api_token_env": token_env,
    }
    api_token = os.environ.get(token_env)
    if not base_url:
        result["reason"] = "publish_control_plane_url_not_configured"
        return result
    if not api_token:
        result["reason"] = "publish_api_token_env_not_set"
        return result
    try:
        body = panel_json_path.read_bytes()
        post_url = f"{base_url}/api/v1/hermes/watchdog/panel"
        latest_url = f"{base_url}/api/v1/hermes/watchdog/panel/latest.json"
        post_status, receipt = json_request(
            post_url,
            api_token=api_token,
            method="POST",
            body=body,
        )
        latest_status, latest_snapshot = json_request(
            latest_url,
            api_token=api_token,
            method="GET",
        )
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        result["error"] = sanitized_for_status(str(exc), secret=api_token)
        return result
    return {
        "status": "published",
        "control_plane_url": base_url,
        "api_token_env": token_env,
        "receipt_status_code": post_status,
        "latest_status_code": latest_status,
        "receipt": sanitized_for_status(receipt, secret=api_token),
        "latest_snapshot": sanitized_for_status(latest_snapshot, secret=api_token),
        "observer_links": {
            "panel_html": f"{base_url}/api/v1/hermes/watchdog/panel",
            "latest_json": latest_url,
            "history_json": f"{base_url}/api/v1/hermes/watchdog/history.json",
        },
    }


def write_watchdog_outputs(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    status_path = args.status_dir / "watchdog-status.json"
    panel_json_path = args.status_dir / "watchdog-panel.json"
    panel_markdown_path = args.status_dir / "watchdog-panel.md"
    history_stem = str(payload.get("generated_at_ms") or int(time.time() * 1000))
    panel_history_json_path = args.status_dir / "panel-history" / f"{history_stem}.json"
    panel_history_markdown_path = args.status_dir / "panel-history" / f"{history_stem}.md"
    payload.setdefault("artifacts", {})
    payload["artifacts"].update(
        {
            "watchdog_status": str(status_path),
            "watchdog_panel_json": str(panel_json_path),
            "watchdog_panel_markdown": str(panel_markdown_path),
            "watchdog_panel_history_json": str(panel_history_json_path),
            "watchdog_panel_history_markdown": str(panel_history_markdown_path),
        }
    )
    panel = watchdog_panel_payload(payload)
    write_json(panel_json_path, panel)
    write_json(panel_history_json_path, panel)
    panel_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    panel_history_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    panel_markdown = watchdog_panel_markdown(panel)
    panel_markdown_path.write_text(panel_markdown, encoding="utf-8")
    panel_history_markdown_path.write_text(panel_markdown, encoding="utf-8")
    if args.publish_control_plane_url:
        payload["control_plane_publish"] = publish_watchdog_panel_to_control_plane(
            args, panel_json_path
        )
    write_json(status_path, payload)


def _load_validated_transition(path: Path) -> dict[str, Any]:
    payload = _cancel_ownership._load_json(path)
    _cancel_ownership._validate_transition(payload, path)
    return payload


def _load_validated_attestation(path: Path) -> dict[str, Any]:
    payload = _cancel_ownership._load_json(path)
    _cancel_ownership._validate_attestation(payload, path)
    return payload


def evaluate_ao2_cancel_authority(
    args: argparse.Namespace, *, active_pid: int
) -> dict[str, Any]:
    """Decide whether the live watchdog may proceed to terminate ``active_pid``.

    Returns a dict with at least:

    - ``decision``: ``allow_unilateral_legacy`` / ``accept_ao2_owns_watchdog_cancel``
      / ``refuse_pending_ao2_authority_source`` /
      ``refuse_invalid_ao2_authority_source``
    - ``mode``: ``factory_v3_unilateral_legacy_pending_source_wiring`` /
      ``ao2_owned`` / ``refused_no_source`` / ``refused_invalid_source``
    - ``ao2_cancel_authority`` payload to attach to the watchdog status JSON.
    - ``refused_action`` (only when decision starts with ``refuse``): the
      ``action`` to surface in the refused payload.
    """

    transition_paths: list[Path] = list(getattr(args, "ao2_cancel_transitions", []) or [])
    attestation_path: Path | None = getattr(args, "no_active_ao2_runs_attestation", None)
    require = bool(getattr(args, "require_ao2_cancel_authority", False))

    has_source = bool(transition_paths) or attestation_path is not None

    if not has_source:
        if require:
            return {
                "decision": "refuse_pending_ao2_authority_source",
                "mode": "refused_no_source",
                "refused_action": "refused_overdue_termination_pending_ao2_authority",
                "authority": {
                    "mode": "refused_no_source",
                    "decision": "refuse_pending_ao2_authority_source",
                    "error": (
                        "--require-ao2-cancel-authority was set but neither "
                        "--ao2-cancel-transition nor --no-active-ao2-runs-attestation "
                        "was supplied; ao-operator cannot terminate without AO2 "
                        "cancel authority"
                    ),
                    "ao2_ownership": dict(_AO2_OWNERSHIP_DEFAULT),
                    "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
                    "sources": {
                        "transitions": [],
                        "no_active_ao2_runs_attestation": None,
                    },
                },
            }
        return {
            "decision": "allow_unilateral_legacy",
            "mode": "factory_v3_unilateral_legacy_pending_source_wiring",
            "authority": {
                "mode": "factory_v3_unilateral_legacy_pending_source_wiring",
                "decision": "allow_unilateral_legacy",
                "warning": LEGACY_AUTHORITY_WARNING,
                "ao2_ownership": dict(_AO2_OWNERSHIP_DEFAULT),
                "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
                "sources": {
                    "transitions": [],
                    "no_active_ao2_runs_attestation": None,
                },
            },
        }

    try:
        transitions = [_load_validated_transition(path) for path in transition_paths]
        attestation = (
            _load_validated_attestation(attestation_path)
            if attestation_path is not None
            else None
        )
    except _cancel_ownership.InvalidCancelOwnershipInputError as exc:
        return {
            "decision": "refuse_invalid_ao2_authority_source",
            "mode": "refused_invalid_source",
            "refused_action": "refused_overdue_termination_invalid_ao2_authority",
            "authority": {
                "mode": "refused_invalid_source",
                "decision": "refuse_invalid_ao2_authority_source",
                "error": str(exc),
                "ao2_ownership": dict(_AO2_OWNERSHIP_DEFAULT),
                "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
                "sources": {
                    "transitions": [str(p) for p in transition_paths],
                    "no_active_ao2_runs_attestation": (
                        str(attestation_path) if attestation_path is not None else None
                    ),
                },
            },
        }

    synthetic_watchdog = {
        "schema": SCHEMA,
        "action": _cancel_ownership.TERMINATING_WATCHDOG_ACTION,
        "terminated_pid": active_pid,
    }
    claim = _cancel_ownership.build_ownership(
        watchdog=synthetic_watchdog,
        transitions=transitions,
        attestation=attestation,
    )
    if claim.get("status") != "accepted":
        return {
            "decision": "refuse_invalid_ao2_authority_source",
            "mode": "refused_invalid_source",
            "refused_action": "refused_overdue_termination_invalid_ao2_authority",
            "authority": {
                "mode": "refused_invalid_source",
                "decision": "refuse_invalid_ao2_authority_source",
                "error": "; ".join(claim.get("blockers") or ["claim was not accepted"]),
                "claim": claim,
                "ao2_ownership": dict(_AO2_OWNERSHIP_DEFAULT),
                "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
                "sources": {
                    "transitions": [str(p) for p in transition_paths],
                    "no_active_ao2_runs_attestation": (
                        str(attestation_path) if attestation_path is not None else None
                    ),
                },
            },
        }
    return {
        "decision": "accept_ao2_owns_watchdog_cancel",
        "mode": "ao2_owned",
        "authority": {
            "mode": "ao2_owned",
            "decision": "accept_ao2_owns_watchdog_cancel",
            "claim": claim,
            "ao2_ownership": dict(_AO2_OWNERSHIP_DEFAULT),
            "trust_boundary": dict(_cancel_ownership.TRUST_BOUNDARY),
            "sources": {
                "transitions": [str(p) for p in transition_paths],
                "no_active_ao2_runs_attestation": (
                    str(attestation_path) if attestation_path is not None else None
                ),
            },
        },
    }


def run_watchdog(args: argparse.Namespace) -> dict[str, Any]:
    args.status_dir.mkdir(parents=True, exist_ok=True)
    args.backend_decision = backend_decision(args)
    args.watchdog_prompt_text = render_prompt(args, args.backend_decision)
    prompt = prompt_metadata(args, args.watchdog_prompt_text)
    lock_dir = args.status_dir / "ao2-watchdog.lock"
    max_lock_age_seconds = args.max_lock_age_minutes * 60
    acquired, active_pid, stale_removed, lock_age, overdue = acquire_lock(
        lock_dir,
        max_lock_age_seconds=max_lock_age_seconds,
    )
    if not acquired and overdue and args.recover_overdue and active_pid is not None:
        authority = evaluate_ao2_cancel_authority(args, active_pid=active_pid)
        if authority["decision"].startswith("refuse"):
            payload = {
                **base_payload(args, "refused", prompt),
                "action": authority["refused_action"],
                "active_pid": active_pid,
                "lock_age_seconds": lock_age,
                "lock_dir": str(lock_dir),
                "max_lock_age_seconds": max_lock_age_seconds,
                "ao2_cancel_authority": authority["authority"],
            }
            write_watchdog_outputs(args, payload)
            return payload
        terminate_process(active_pid, grace_seconds=args.terminate_grace_seconds)
        release_lock(lock_dir)
        lock_dir.mkdir()
        child, logs = start_hermes(args, lock_dir)
        payload = {
            **base_payload(args, "started", prompt),
            "action": "recovered_overdue_hermes_oneshot",
            "active_pid": child.pid,
            "terminated_pid": active_pid,
            "stale_lock_removed": True,
            "lock_age_seconds": lock_age,
            "lock_dir": str(lock_dir),
            "max_lock_age_seconds": max_lock_age_seconds,
            "logs": logs,
            "ao2_cancel_authority": authority["authority"],
        }
        write_watchdog_outputs(args, payload)
        return payload

    if not acquired:
        status = "overdue" if overdue else "running"
        payload = {
            **base_payload(args, status, prompt),
            "action": "running_past_max_lock_age" if overdue else "check_back_later",
            "active_pid": active_pid,
            "lock_age_seconds": lock_age,
            "lock_dir": str(lock_dir),
            "max_lock_age_seconds": max_lock_age_seconds,
        }
        write_watchdog_outputs(args, payload)
        return payload

    if args.dry_run:
        release_lock(lock_dir)
        payload = {
            **base_payload(args, "would_start", prompt),
            "action": "dry_run",
            "command": command_for(args, args.watchdog_prompt_text),
            "stale_lock_removed": stale_removed,
            "lock_dir": str(lock_dir),
        }
        write_watchdog_outputs(args, payload)
        return payload

    child, logs = start_hermes(args, lock_dir)
    payload = {
        **base_payload(args, "started", prompt),
        "action": "started_hermes_oneshot",
        "active_pid": child.pid,
        "stale_lock_removed": stale_removed,
        "lock_dir": str(lock_dir),
        "logs": logs,
    }
    write_watchdog_outputs(args, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Hermes cron watchdog for AO2 advancement")
    parser.add_argument("--factory-root", type=Path, default=root)
    parser.add_argument("--ao2-root", type=Path, default=(root / ".." / "ao2").resolve())
    parser.add_argument(
        "--ao2-control-plane",
        type=Path,
        default=(root / ".." / "ao2-control-plane").resolve(),
    )
    parser.add_argument("--ao-runtime", type=Path, default=(root / ".." / "ao-runtime").resolve())
    parser.add_argument(
        "--status-dir",
        type=Path,
        default=root / "run-artifacts" / "hermes-ao2-watchdog",
    )
    parser.add_argument("--hermes-bin", default="hermes")
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=root / "run-artifacts" / "hermes-governed-backend-control-plane" / "prompt.txt",
    )
    parser.add_argument("--interval-seconds", type=int, default=600)
    parser.add_argument("--max-lock-age-minutes", type=int, default=720)
    parser.add_argument("--recover-overdue", action="store_true")
    parser.add_argument("--terminate-grace-seconds", type=float, default=5.0)
    parser.add_argument(
        "--decision-mode",
        choices=("auto", "normal", "repair-latest"),
        default="auto",
    )
    parser.add_argument("--repair-provider", default="codex")
    parser.add_argument("--repair-template", default="bug-fix")
    parser.add_argument(
        "--publish-control-plane-url",
        help="Explicit ao2-control-plane base URL for publishing watchdog panels.",
    )
    parser.add_argument(
        "--publish-api-token-env",
        default="AO2_CP_API_TOKEN",
        help="Environment variable containing the control-plane bearer token.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--ao2-queue-submit",
        dest="ao2_queue_submit",
        type=Path,
        default=None,
        help=(
            "Forward an AO2 queue-submit JSON to repair-resume-latest so the "
            "bridge can attach a ao-operator/ao2-queue-failure-recovery-ownership "
            "claim."
        ),
    )
    parser.add_argument(
        "--ao2-queue-transition",
        dest="ao2_queue_transitions",
        type=Path,
        action="append",
        default=[],
        help="Forward AO2 queue-transition JSONs to repair-resume-latest (repeatable).",
    )
    parser.add_argument(
        "--ao2-queue-ownership-out",
        dest="ao2_queue_ownership_out",
        type=Path,
        default=None,
        help="Forward an ownership-claim output path to repair-resume-latest.",
    )
    parser.add_argument(
        "--require-ao2-queue-ownership",
        dest="require_ao2_queue_ownership",
        action="store_true",
        help=(
            "Forward --require-ao2-queue-ownership to repair-resume-latest so the "
            "watchdog cannot drain a non-accepted pack without AO2 queue evidence."
        ),
    )
    parser.add_argument(
        "--ao2-cancel-transition",
        dest="ao2_cancel_transitions",
        type=Path,
        action="append",
        default=[],
        help=(
            "AO2 queue-transition JSON authorising the recover-overdue "
            "termination (schema "
            "ao2.ao-operator-compat-workbench-queue-transition.v1, status "
            "cancelled). Repeatable. When provided, the watchdog records an "
            "inline ao2_cancel_authority claim in the status payload."
        ),
    )
    parser.add_argument(
        "--no-active-ao2-runs-attestation",
        dest="no_active_ao2_runs_attestation",
        type=Path,
        default=None,
        help=(
            "Parity-oracle attestation (schema "
            "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1) "
            "certifying no AO2 run is in flight, used when the stuck Hermes "
            "one-shot has no AO2 cancel transition to cite."
        ),
    )
    parser.add_argument(
        "--require-ao2-cancel-authority",
        dest="require_ao2_cancel_authority",
        action="store_true",
        help=(
            "Refuse to terminate an overdue Hermes one-shot unless an AO2 "
            "cancel transition or no-active-ao2-runs attestation is supplied. "
            "Phase 2 exit-gate item #5: cancel decisions are owned by AO2."
        ),
    )
    return parser


def normalize_paths(args: argparse.Namespace) -> None:
    for attr in ("factory_root", "ao2_root", "ao2_control_plane", "ao_runtime", "status_dir", "prompt_file"):
        setattr(args, attr, Path(getattr(args, attr)).expanduser().resolve())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    normalize_paths(args)
    payload = run_watchdog(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])
    if payload.get("status") == "refused":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
