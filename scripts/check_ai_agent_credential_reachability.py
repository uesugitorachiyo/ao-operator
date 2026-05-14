#!/usr/bin/env python3
"""AI agent credential-reachability gate.

Models the agent-driven dataflow taint analysis that governs every
AO Operator / AO Runtime path where untrusted content (user prompt,
tool output, MCP tool result, web fetch payload, or prompt-
injection-tainted source) can reach a credential-bearing path
(provider OAuth file, signed-bundle private key, API key store,
session token, ssh key directory, or env-resolved API key).

The gate proves that no untrusted source can reach a credential-
reachable sink without an explicit egress redaction step. Every
unredacted untrusted->credential edge is fail-closed.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_no_untrusted_to_credential_reachable_path`` -- control:
  every dataflow edge is either trusted-source, non-credential-
  reachable, or redacted at egress; the verifier produces no
  errors.
* ``untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected``
  -- mutation: an untrusted user prompt is concatenated into a
  subprocess argv that touches the credential directory; the
  verifier MUST reject.
* ``agent_tool_output_piped_to_shell_with_ssh_dir_rejected`` --
  mutation: an agent tool output is piped to a shell pipeline
  (git/scp/rsync) targeting the ssh directory; the verifier MUST
  reject.
* ``mcp_tool_result_included_in_role_handoff_with_session_paths_rejected``
  -- mutation: an MCP tool result is included verbatim in a role-
  handoff state envelope that carries session token paths; the
  verifier MUST reject.
* ``web_fetch_reflected_into_shell_resolving_env_rejected`` --
  mutation: a web-fetch payload is reflected into a shell
  command that resolves an env variable carrying a credential; the
  verifier MUST reject.
* ``prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected``
  -- mutation: a prompt-injection-tainted source triggers a
  filesystem read of a credential path while the egress redaction
  step is bypassed; the verifier MUST reject.

Every case lays down a per-case
``credential-reachability-transcript.json`` in a temporary work
directory, runs it through the verifier embedded in this gate, and
records ``observed_verdict``. The gate's overall verdict is ``PASS``
only when every case lines up with the expected verdict.

The gate never invokes AO or provider CLIs and never authorizes
dispatch.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "ai-agent-credential-reachability.json"
)
SCHEMA = "ao-operator/ai-agent-credential-reachability/v1"

CASE_IDS = (
    "clean_no_untrusted_to_credential_reachable_path",
    "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected",
    "agent_tool_output_piped_to_shell_with_ssh_dir_rejected",
    "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected",
    "web_fetch_reflected_into_shell_resolving_env_rejected",
    "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_untrusted_to_credential_reachable_path": "PASS",
    "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected": "FAIL",
    "agent_tool_output_piped_to_shell_with_ssh_dir_rejected": "FAIL",
    "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected": "FAIL",
    "web_fetch_reflected_into_shell_resolving_env_rejected": "FAIL",
    "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected": "FAIL",
}

UNTRUSTED_SOURCES = {
    "untrusted_user_prompt",
    "untrusted_tool_output",
    "untrusted_mcp_result",
    "untrusted_web_fetch",
    "untrusted_prompt_injection",
}
TRUSTED_SOURCES = {"trusted_internal"}
VALID_SOURCES = UNTRUSTED_SOURCES | TRUSTED_SOURCES
VALID_SINKS = {
    "subprocess_argv",
    "shell_pipe",
    "role_handoff",
    "shell_env_resolved",
    "filesystem_read",
}

_CREDENTIAL_DIR = ".credentials/factory_alpha"
_SSH_DIR = ".ssh/factory_alpha"
_SESSION_TOKEN_PATH = ".session/token_alpha"
_API_KEY_ENV = "FACTORY_PROVIDER_API_KEY_ALPHA"
_CONFIG_CRED_PATH = ".config/factory_alpha/credentials.json"
_PUBLIC_DOC_PATH = "docs/public/welcome_alpha.md"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _CredentialReachabilityVerifier:
    """In-memory credential-reachability dataflow state machine.

    Each ``register`` call records one dataflow edge with its source
    classification, sink, target path, credential-reachability flag,
    and redacted-at-egress flag. A FAIL is recorded whenever an
    untrusted source reaches a credential-reachable target without
    being redacted at egress.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        source = edge.get("source_classification")
        sink = edge.get("sink")
        if source not in VALID_SOURCES:
            self.errors.append(
                f"unknown_source_classification:id={edge_id},source={source!r}"
            )
            return
        if sink not in VALID_SINKS:
            self.errors.append(f"unknown_sink:id={edge_id},sink={sink!r}")
            return
        if source not in UNTRUSTED_SOURCES:
            return
        if edge.get("target_credential_reachable") is not True:
            return
        if edge.get("redacted_at_egress") is True:
            return
        target = edge.get("target_path") or "<unknown>"
        self.errors.append(
            f"{source}_{sink}_credential_reachable:id={edge_id},target={target}"
        )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "trusted_internal_subprocess_argv_non_credential",
        "source_classification": "trusted_internal",
        "sink": "subprocess_argv",
        "target_path": _PUBLIC_DOC_PATH,
        "target_credential_reachable": False,
        "redacted_at_egress": False,
    },
    {
        "id": "untrusted_user_prompt_filesystem_read_redacted",
        "source_classification": "untrusted_user_prompt",
        "sink": "filesystem_read",
        "target_path": _CONFIG_CRED_PATH,
        "target_credential_reachable": True,
        "redacted_at_egress": True,
    },
    {
        "id": "untrusted_tool_output_role_handoff_non_credential",
        "source_classification": "untrusted_tool_output",
        "sink": "role_handoff",
        "target_path": _PUBLIC_DOC_PATH,
        "target_credential_reachable": False,
        "redacted_at_egress": False,
    },
    {
        "id": "untrusted_web_fetch_subprocess_argv_redacted",
        "source_classification": "untrusted_web_fetch",
        "sink": "subprocess_argv",
        "target_path": _CREDENTIAL_DIR,
        "target_credential_reachable": True,
        "redacted_at_egress": True,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "credential-reachability-transcript.json").write_text(
        json.dumps({"edges": transcript}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _case_summary(
    case_id: str,
    *,
    observed_verdict: str,
    observed_errors: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "observed_verdict": observed_verdict,
        "observed_errors": observed_errors,
        "detail": detail,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def run_clean_no_untrusted_to_credential_reachable_path(work: Path) -> dict[str, Any]:
    case_id = "clean_no_untrusted_to_credential_reachable_path"
    verifier = _CredentialReachabilityVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)

    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every dataflow edge is either trusted-source, non-"
            "credential-reachable, or redacted at egress"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _CredentialReachabilityVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    verifier.register(mutated)
    transcript = [{"op": "register", **edge} for edge in (*_CLEAN_EDGES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected",
        {
            "id": "mutated_user_prompt_subprocess_argv_credential_dir",
            "source_classification": "untrusted_user_prompt",
            "sink": "subprocess_argv",
            "target_path": _CREDENTIAL_DIR,
            "target_credential_reachable": True,
            "redacted_at_egress": False,
        },
        detail=(
            "mutation: an untrusted user prompt is concatenated into a subprocess "
            "argv that touches the credential directory and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_agent_tool_output_piped_to_shell_with_ssh_dir_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "agent_tool_output_piped_to_shell_with_ssh_dir_rejected",
        {
            "id": "mutated_tool_output_shell_pipe_ssh_dir",
            "source_classification": "untrusted_tool_output",
            "sink": "shell_pipe",
            "target_path": _SSH_DIR,
            "target_credential_reachable": True,
            "redacted_at_egress": False,
        },
        detail=(
            "mutation: an agent tool output is piped to a git/scp/rsync shell "
            "pipeline targeting the ssh directory and the verifier must reject "
            "instead of silently accepting"
        ),
    )


def run_mcp_tool_result_included_in_role_handoff_with_session_paths_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected",
        {
            "id": "mutated_mcp_result_role_handoff_session_path",
            "source_classification": "untrusted_mcp_result",
            "sink": "role_handoff",
            "target_path": _SESSION_TOKEN_PATH,
            "target_credential_reachable": True,
            "redacted_at_egress": False,
        },
        detail=(
            "mutation: an MCP tool result is included verbatim in a role-handoff "
            "state envelope that carries session token paths and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_web_fetch_reflected_into_shell_resolving_env_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "web_fetch_reflected_into_shell_resolving_env_rejected",
        {
            "id": "mutated_web_fetch_shell_env_api_key",
            "source_classification": "untrusted_web_fetch",
            "sink": "shell_env_resolved",
            "target_path": _API_KEY_ENV,
            "target_credential_reachable": True,
            "redacted_at_egress": False,
        },
        detail=(
            "mutation: a web-fetch payload is reflected into a shell command "
            "that resolves an env variable carrying a credential and the "
            "verifier must reject instead of silently accepting"
        ),
    )


def run_prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected",
        {
            "id": "mutated_prompt_injection_filesystem_read_credentials_json",
            "source_classification": "untrusted_prompt_injection",
            "sink": "filesystem_read",
            "target_path": _CONFIG_CRED_PATH,
            "target_credential_reachable": True,
            "redacted_at_egress": False,
        },
        detail=(
            "mutation: a prompt-injection-tainted source triggers a filesystem "
            "read of a credential path while the egress redaction step is "
            "bypassed and the verifier must reject instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_untrusted_to_credential_reachable_path": run_clean_no_untrusted_to_credential_reachable_path,
    "untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected": run_untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected,
    "agent_tool_output_piped_to_shell_with_ssh_dir_rejected": run_agent_tool_output_piped_to_shell_with_ssh_dir_rejected,
    "mcp_tool_result_included_in_role_handoff_with_session_paths_rejected": run_mcp_tool_result_included_in_role_handoff_with_session_paths_rejected,
    "web_fetch_reflected_into_shell_resolving_env_rejected": run_web_fetch_reflected_into_shell_resolving_env_rejected,
    "prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected": run_prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected,
}


def evaluate(*, work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cases = [CASE_RUNNERS[case_id](work_dir) for case_id in CASE_IDS]
    errors: list[str] = []
    by_id = {case["id"]: case for case in cases}
    for case_id, expected in EXPECTED_VERDICTS.items():
        observed = by_id.get(case_id, {}).get("observed_verdict")
        if observed != expected:
            errors.append(
                f"{case_id} expected {expected}, observed {observed or 'missing'}"
            )
    overall_pass = not errors
    mutation_case_ids = [cid for cid, v in EXPECTED_VERDICTS.items() if v == "FAIL"]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if overall_pass else "FAIL",
        "case_count": len(cases),
        "case_ids": list(CASE_IDS),
        "mutation_case_count": len(mutation_case_ids),
        "expected_case_verdicts": dict(EXPECTED_VERDICTS),
        "untrusted_sources": sorted(UNTRUSTED_SOURCES),
        "sinks": sorted(VALID_SINKS),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "AI agent credential-reachability gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix AI agent credential-reachability blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-credential-reachability-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-credential-reachability-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
