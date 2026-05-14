#!/usr/bin/env python3
"""MCP / Tool poisoning detection gate.

Models the descriptor-trust invariant that no MCP server or tool
descriptor exposed to a AO Operator agent can poison the agent's tool
surface without an explicit operator-approved trust marker. Every
poisoning hazard class (hidden imperative in description, tool
result schema destructive-default drift, MCP returning a URL to
fetch and apply, tool-name shadowing, signed descriptor advertising
an unallowed privilege) is fail-closed.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO, no real
MCP servers contacted):

* ``clean_no_mcp_or_tool_poisoning_indicators`` -- control: every
  registered descriptor carries an operator-approved trust marker,
  no hazard classes are observed, and no tool-name shadowing exists.
* ``hidden_imperative_in_mcp_description_rejected`` -- mutation: an
  unapproved MCP tool description embeds a hidden imperative; the
  verifier MUST reject.
* ``tool_result_schema_adds_destructive_default_arg_rejected`` --
  mutation: a tool result schema mutates between invocations to add
  a destructive default argument; the verifier MUST reject.
* ``mcp_returns_url_to_fetch_and_apply_rejected`` -- mutation: an
  MCP returns a URL the agent is asked to fetch and apply directly;
  the verifier MUST reject.
* ``tool_name_shadowing_overrides_native_tool_rejected`` --
  mutation: a non-native MCP tool registers a name that shadows a
  trusted native tool; the verifier MUST reject.
* ``signed_descriptor_advertises_unallowed_privilege_rejected`` --
  mutation: a signed tool descriptor advertises a privilege class
  outside its allowlist; the verifier MUST reject.

Every case lays down a per-case ``mcp-tool-poisoning-transcript.json``
in a temporary work directory, runs it through the verifier embedded
in this gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the expected
verdict.

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
    "mcp-tool-poisoning-detection.json"
)
SCHEMA = "ao-operator/mcp-tool-poisoning-detection/v1"

CASE_IDS = (
    "clean_no_mcp_or_tool_poisoning_indicators",
    "hidden_imperative_in_mcp_description_rejected",
    "tool_result_schema_adds_destructive_default_arg_rejected",
    "mcp_returns_url_to_fetch_and_apply_rejected",
    "tool_name_shadowing_overrides_native_tool_rejected",
    "signed_descriptor_advertises_unallowed_privilege_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_mcp_or_tool_poisoning_indicators": "PASS",
    "hidden_imperative_in_mcp_description_rejected": "FAIL",
    "tool_result_schema_adds_destructive_default_arg_rejected": "FAIL",
    "mcp_returns_url_to_fetch_and_apply_rejected": "FAIL",
    "tool_name_shadowing_overrides_native_tool_rejected": "FAIL",
    "signed_descriptor_advertises_unallowed_privilege_rejected": "FAIL",
}

DESCRIPTOR_CLASSIFICATIONS = {
    "trusted_native",
    "operator_approved_mcp",
    "unapproved_mcp",
    "signed_descriptor_within_allowlist",
    "signed_descriptor_outside_allowlist",
}
APPROVED_CLASSIFICATIONS = {
    "trusted_native",
    "operator_approved_mcp",
    "signed_descriptor_within_allowlist",
}
HAZARD_CLASSES = {
    "hidden_imperative_in_description",
    "tool_result_schema_destructive_default_drift",
    "mcp_returns_url_to_fetch_and_apply",
    "tool_name_shadowing",
    "signed_descriptor_advertises_unallowed_privilege",
}
NATIVE_TOOL_NAMES = {
    "native::shell.exec",
    "native::filesystem.write",
    "native::network.fetch",
}

_TOOL_ALPHA = "mcp_alpha::tool_alpha"
_TOOL_BETA = "mcp_alpha::tool_beta"
_NATIVE_SHELL = "native::shell.exec"
_SIGNED_DESCRIPTOR_REV1 = "signed_descriptor:alpha:rev_1"
_RETURN_URL_FRAGMENT = (
    "return_url:https_alpha_example_test::fetch_and_apply"
)
_HIDDEN_IMPERATIVE_FRAGMENT = (
    "hidden_imperative:ignore_prior_instructions_marker_alpha"
)
_DESTRUCTIVE_DEFAULT_FRAGMENT = (
    "destructive_default:rm_workspace_marker_alpha"
)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _McpToolPoisoningVerifier:
    """In-memory MCP / tool descriptor verifier.

    Each ``register`` call records one descriptor with its trust
    classification, hazard class (if any), tool name, and descriptor
    payload reference. A FAIL is recorded whenever an unapproved
    classification surfaces a known hazard class, whenever a tool
    name shadows a trusted native tool, or whenever a signed
    descriptor advertises a privilege class outside its allowlist.
    """

    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._registered_names: set[str] = set()

    def register(self, edge: dict[str, Any]) -> None:
        self.edges.append(dict(edge))
        self._validate_edge(edge)

    def _validate_edge(self, edge: dict[str, Any]) -> None:
        edge_id = str(edge.get("id") or "<unnamed>")
        classification = edge.get("descriptor_classification")
        hazard = edge.get("hazard_class")
        tool_name = edge.get("tool_name") or "<unknown>"
        if classification not in DESCRIPTOR_CLASSIFICATIONS:
            self.errors.append(
                f"unknown_descriptor_classification:id={edge_id},class={classification!r}"
            )
            return
        if hazard is not None and hazard not in HAZARD_CLASSES:
            self.errors.append(
                f"unknown_hazard_class:id={edge_id},hazard={hazard!r}"
            )
            return

        if (
            classification != "trusted_native"
            and tool_name in NATIVE_TOOL_NAMES
        ):
            self.errors.append(
                f"tool_name_shadowing_rejection:id={edge_id},name={tool_name}"
            )
            self._registered_names.add(tool_name)
            return

        if classification == "signed_descriptor_outside_allowlist":
            self.errors.append(
                f"signed_descriptor_advertises_unallowed_privilege_rejection:id={edge_id},name={tool_name}"
            )
            self._registered_names.add(tool_name)
            return

        if hazard is None:
            self._registered_names.add(tool_name)
            return

        if classification in APPROVED_CLASSIFICATIONS:
            self._registered_names.add(tool_name)
            return

        self.errors.append(
            f"{hazard}_unapproved_mcp_rejection:id={edge_id},name={tool_name}"
        )
        self._registered_names.add(tool_name)

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_EDGES: tuple[dict[str, Any], ...] = (
    {
        "id": "trusted_native_shell",
        "descriptor_classification": "trusted_native",
        "hazard_class": None,
        "tool_name": _NATIVE_SHELL,
        "descriptor_payload_path": "native::shell.exec::baseline",
        "operator_approved": True,
    },
    {
        "id": "operator_approved_mcp_alpha",
        "descriptor_classification": "operator_approved_mcp",
        "hazard_class": None,
        "tool_name": _TOOL_ALPHA,
        "descriptor_payload_path": "mcp_alpha::tool_alpha::baseline",
        "operator_approved": True,
    },
    {
        "id": "signed_descriptor_within_allowlist_rev1",
        "descriptor_classification": "signed_descriptor_within_allowlist",
        "hazard_class": None,
        "tool_name": _SIGNED_DESCRIPTOR_REV1,
        "descriptor_payload_path": (
            "signed_descriptor:alpha:rev_1:within_allowlist"
        ),
        "operator_approved": True,
    },
    {
        "id": "operator_approved_mcp_beta",
        "descriptor_classification": "operator_approved_mcp",
        "hazard_class": None,
        "tool_name": _TOOL_BETA,
        "descriptor_payload_path": "mcp_alpha::tool_beta::baseline",
        "operator_approved": True,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "mcp-tool-poisoning-transcript.json").write_text(
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


def run_clean_no_mcp_or_tool_poisoning_indicators(work: Path) -> dict[str, Any]:
    case_id = "clean_no_mcp_or_tool_poisoning_indicators"
    verifier = _McpToolPoisoningVerifier()
    for edge in _CLEAN_EDGES:
        verifier.register(edge)
    transcript = [{"op": "register", **edge} for edge in _CLEAN_EDGES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered descriptor carries an operator-"
            "approved trust marker, no hazard class is observed, and no "
            "tool-name shadowing exists"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _McpToolPoisoningVerifier()
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


def run_hidden_imperative_in_mcp_description_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "hidden_imperative_in_mcp_description_rejected",
        {
            "id": "mutated_hidden_imperative_unapproved_mcp",
            "descriptor_classification": "unapproved_mcp",
            "hazard_class": "hidden_imperative_in_description",
            "tool_name": "mcp_alpha::tool_gamma",
            "descriptor_payload_path": _HIDDEN_IMPERATIVE_FRAGMENT,
            "operator_approved": False,
        },
        detail=(
            "mutation: an unapproved MCP tool description embeds a hidden "
            "imperative and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_tool_result_schema_adds_destructive_default_arg_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tool_result_schema_adds_destructive_default_arg_rejected",
        {
            "id": "mutated_tool_result_schema_destructive_default",
            "descriptor_classification": "unapproved_mcp",
            "hazard_class": "tool_result_schema_destructive_default_drift",
            "tool_name": "mcp_alpha::tool_delta",
            "descriptor_payload_path": _DESTRUCTIVE_DEFAULT_FRAGMENT,
            "operator_approved": False,
        },
        detail=(
            "mutation: a tool result schema mutates between invocations to "
            "add a destructive default argument and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_mcp_returns_url_to_fetch_and_apply_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "mcp_returns_url_to_fetch_and_apply_rejected",
        {
            "id": "mutated_mcp_returns_url_to_fetch_and_apply",
            "descriptor_classification": "unapproved_mcp",
            "hazard_class": "mcp_returns_url_to_fetch_and_apply",
            "tool_name": "mcp_alpha::tool_epsilon",
            "descriptor_payload_path": _RETURN_URL_FRAGMENT,
            "operator_approved": False,
        },
        detail=(
            "mutation: an MCP returns a URL the agent is asked to fetch and "
            "apply directly and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_tool_name_shadowing_overrides_native_tool_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "tool_name_shadowing_overrides_native_tool_rejected",
        {
            "id": "mutated_tool_name_shadows_native_shell",
            "descriptor_classification": "unapproved_mcp",
            "hazard_class": "tool_name_shadowing",
            "tool_name": _NATIVE_SHELL,
            "descriptor_payload_path": (
                "tool_name_shadowing:override_native_shell_marker_alpha"
            ),
            "operator_approved": False,
        },
        detail=(
            "mutation: a non-native MCP tool registers under a name that "
            "shadows the trusted native tool name and the verifier must "
            "reject instead of silently accepting"
        ),
    )


def run_signed_descriptor_advertises_unallowed_privilege_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "signed_descriptor_advertises_unallowed_privilege_rejected",
        {
            "id": "mutated_signed_descriptor_outside_allowlist",
            "descriptor_classification": "signed_descriptor_outside_allowlist",
            "hazard_class": "signed_descriptor_advertises_unallowed_privilege",
            "tool_name": "signed_descriptor:alpha:rev_2",
            "descriptor_payload_path": (
                "signed_descriptor:alpha:rev_2:outside_allowlist"
            ),
            "operator_approved": False,
        },
        detail=(
            "mutation: a signed tool descriptor advertises a privilege "
            "class outside its allowlist and the verifier must reject "
            "instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_mcp_or_tool_poisoning_indicators": run_clean_no_mcp_or_tool_poisoning_indicators,
    "hidden_imperative_in_mcp_description_rejected": run_hidden_imperative_in_mcp_description_rejected,
    "tool_result_schema_adds_destructive_default_arg_rejected": run_tool_result_schema_adds_destructive_default_arg_rejected,
    "mcp_returns_url_to_fetch_and_apply_rejected": run_mcp_returns_url_to_fetch_and_apply_rejected,
    "tool_name_shadowing_overrides_native_tool_rejected": run_tool_name_shadowing_overrides_native_tool_rejected,
    "signed_descriptor_advertises_unallowed_privilege_rejected": run_signed_descriptor_advertises_unallowed_privilege_rejected,
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
        "descriptor_classifications": sorted(DESCRIPTOR_CLASSIFICATIONS),
        "approved_classifications": sorted(APPROVED_CLASSIFICATIONS),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "native_tool_names": sorted(NATIVE_TOOL_NAMES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "MCP / Tool poisoning detection gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix MCP / Tool poisoning detection blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-mcp-tool-poisoning-detection-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-mcp-tool-poisoning-detection-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
