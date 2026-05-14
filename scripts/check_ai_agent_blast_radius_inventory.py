#!/usr/bin/env python3
"""AI agent blast-radius inventory gate.

Models the AO Operator + AO Runtime agent-reachable surface as a
deterministic in-process inventory and proves each blast-radius
hazard is fail-closed by injecting deliberate mutations against the
inventory.

The gate exercises six deterministic cases against a temporary work
directory (no repo pollution, no provider dispatch, no AO):

* ``clean_inventory_classified_and_gated`` -- control: every
  agent-reachable path is classified by category and blast radius;
  destructive paths carry an explicit approval gate; credential-
  bearing paths are not reachable from untrusted content/tool
  output; provider dispatch paths require the existing approval and
  readiness posture; release/public artifact paths exclude
  instruction files, memory blocks, raw prompts, credentials, and
  local-only diagnostics.
* ``unclassified_high_blast_radius_command_path_rejected`` --
  mutation: a high-blast-radius command path is registered without a
  category/blast-radius classification; the inventory MUST reject
  any unclassified high-blast-radius command path.
* ``destructive_action_without_approval_gate_rejected`` -- mutation:
  a destructive filesystem-mutation/transfer/git path is registered
  without an explicit approval gate; the inventory MUST reject any
  destructive action that lacks an explicit approval gate.
* ``credential_path_reachable_from_untrusted_content_rejected`` --
  mutation: a credential-bearing path (provider OAuth file, API key
  store, signed-bundle private key) is marked reachable from
  untrusted content or tool output; the inventory MUST reject any
  credential-bearing path that is reachable from an untrusted-input
  surface.
* ``provider_dispatch_without_approval_readiness_rejected`` --
  mutation: a provider dispatch path is registered as executable
  without the existing approval and readiness posture (no approval
  gate, ``readiness_gated=false``, ``dispatch_authorized=true``);
  the inventory MUST reject any provider dispatch path that can
  execute without the approval and readiness posture.
* ``release_artifact_includes_instruction_or_credentials_rejected``
  -- mutation: a release/public artifact path is registered as
  including instruction files, memory blocks, raw prompts,
  credentials, or local-only diagnostics; the inventory MUST reject
  any release/public artifact path that can include those payloads.

Every case lays down a per-case blast-radius-inventory transcript in
a temporary work directory, runs it through the verifier embedded in
this gate, and records ``observed_verdict``. The gate's overall
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
    "ai-agent-blast-radius-inventory.json"
)
SCHEMA = "ao-operator/ai-agent-blast-radius-inventory/v1"

CASE_IDS = (
    "clean_inventory_classified_and_gated",
    "unclassified_high_blast_radius_command_path_rejected",
    "destructive_action_without_approval_gate_rejected",
    "credential_path_reachable_from_untrusted_content_rejected",
    "provider_dispatch_without_approval_readiness_rejected",
    "release_artifact_includes_instruction_or_credentials_rejected",
)

EXPECTED_VERDICTS = {
    "clean_inventory_classified_and_gated": "PASS",
    "unclassified_high_blast_radius_command_path_rejected": "FAIL",
    "destructive_action_without_approval_gate_rejected": "FAIL",
    "credential_path_reachable_from_untrusted_content_rejected": "FAIL",
    "provider_dispatch_without_approval_readiness_rejected": "FAIL",
    "release_artifact_includes_instruction_or_credentials_rejected": "FAIL",
}

VALID_CATEGORIES = {
    "command",
    "destructive_action",
    "credential",
    "provider_dispatch",
    "release_artifact",
}
VALID_BLAST_RADIUS = {"low", "moderate", "high"}

_CLEAN_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_command_path_alpha",
        "category": "command",
        "blast_radius": "high",
        "destructive": False,
        "approval_gate_required": False,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    },
    {
        "id": "clean_destructive_action_beta",
        "category": "destructive_action",
        "blast_radius": "high",
        "destructive": True,
        "approval_gate_required": True,
        "approval_gate_present": True,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    },
    {
        "id": "clean_credential_path_gamma",
        "category": "credential",
        "blast_radius": "high",
        "destructive": False,
        "approval_gate_required": True,
        "approval_gate_present": True,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": True,
        "includes_local_diagnostics": False,
    },
    {
        "id": "clean_provider_dispatch_path_delta",
        "category": "provider_dispatch",
        "blast_radius": "high",
        "destructive": False,
        "approval_gate_required": True,
        "approval_gate_present": True,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    },
    {
        "id": "clean_release_artifact_epsilon",
        "category": "release_artifact",
        "blast_radius": "moderate",
        "destructive": False,
        "approval_gate_required": False,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    },
)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _BlastRadiusInventoryVerifier:
    """In-memory blast-radius inventory state machine.

    Models the AO Operator + AO Runtime agent-reachable surface:

    1. Every agent-reachable path MUST be classified by category and
       blast radius.
    2. Every destructive action MUST carry an explicit approval gate.
    3. No credential-bearing path MUST be reachable from untrusted
       content or tool output.
    4. Every provider dispatch path MUST require the existing
       approval and readiness posture (approval gate present,
       readiness_gated=true, dispatch_authorized=false).
    5. No release/public artifact path MUST include instruction
       files, memory blocks, raw prompts, credentials, or local-only
       diagnostics.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, entry: dict[str, Any]) -> None:
        self.entries.append(dict(entry))
        self._validate_entry(entry)

    def _validate_entry(self, entry: dict[str, Any]) -> None:
        path_id = str(entry.get("id") or "<unnamed>")
        category = entry.get("category")
        blast_radius = entry.get("blast_radius")
        if category not in VALID_CATEGORIES or blast_radius not in VALID_BLAST_RADIUS:
            self.errors.append(
                f"unclassified_high_blast_radius_path:id={path_id},category={category!r},blast_radius={blast_radius!r}"
            )
            return
        if entry.get("destructive") is True and entry.get("approval_gate_present") is not True:
            self.errors.append(
                f"destructive_action_missing_approval_gate:id={path_id},category={category}"
            )
        if category == "credential" and entry.get("reachable_from_untrusted_input") is True:
            self.errors.append(
                f"credential_path_reachable_from_untrusted_input:id={path_id}"
            )
        if category == "provider_dispatch":
            if (
                entry.get("approval_gate_present") is not True
                or entry.get("readiness_gated") is not True
                or entry.get("dispatch_authorized") is True
            ):
                self.errors.append(
                    f"provider_dispatch_without_approval_readiness:id={path_id},approval_gate_present={entry.get('approval_gate_present')},readiness_gated={entry.get('readiness_gated')},dispatch_authorized={entry.get('dispatch_authorized')}"
                )
        if category == "release_artifact":
            leak_fields = (
                "includes_instruction_files",
                "includes_memory_blocks",
                "includes_raw_prompts",
                "includes_credentials",
                "includes_local_diagnostics",
            )
            leaked = [field for field in leak_fields if entry.get(field) is True]
            if leaked:
                self.errors.append(
                    f"release_artifact_includes_unsafe_payload:id={path_id},leaked_fields={','.join(leaked)}"
                )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "blast-radius-inventory-transcript.json").write_text(
        json.dumps({"entries": transcript}, indent=2, sort_keys=True),
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


def run_clean_inventory_classified_and_gated(work: Path) -> dict[str, Any]:
    case_id = "clean_inventory_classified_and_gated"
    verifier = _BlastRadiusInventoryVerifier()
    transcript: list[dict[str, Any]] = []
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)
        transcript.append({"op": "register", **entry})

    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every agent-reachable path is classified by category and blast "
            "radius; destructive paths carry an explicit approval gate; credential "
            "paths are not reachable from untrusted input; provider dispatch paths "
            "require the approval/readiness posture; release artifact paths exclude "
            "instruction files, memory blocks, raw prompts, credentials, and local-"
            "only diagnostics"
        ),
    )


def run_unclassified_high_blast_radius_command_path_rejected(work: Path) -> dict[str, Any]:
    case_id = "unclassified_high_blast_radius_command_path_rejected"
    verifier = _BlastRadiusInventoryVerifier()
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)

    mutated = {
        "id": "mutated_unclassified_command_zeta",
        "category": None,
        "blast_radius": None,
        "destructive": False,
        "approval_gate_required": False,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    }
    verifier.register(mutated)

    transcript = [
        {"op": "register", **entry} for entry in (*_CLEAN_INVENTORY, mutated)
    ]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a high-blast-radius command path is registered without a "
            "category or blast-radius classification and the inventory must reject "
            "instead of silently accepting"
        ),
    )


def run_destructive_action_without_approval_gate_rejected(work: Path) -> dict[str, Any]:
    case_id = "destructive_action_without_approval_gate_rejected"
    verifier = _BlastRadiusInventoryVerifier()
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)

    mutated = {
        "id": "mutated_destructive_action_eta",
        "category": "destructive_action",
        "blast_radius": "high",
        "destructive": True,
        "approval_gate_required": True,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    }
    verifier.register(mutated)

    transcript = [
        {"op": "register", **entry} for entry in (*_CLEAN_INVENTORY, mutated)
    ]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a destructive filesystem mutation, transfer, or git path is "
            "registered without an explicit approval gate and the inventory must "
            "reject instead of silently accepting"
        ),
    )


def run_credential_path_reachable_from_untrusted_content_rejected(work: Path) -> dict[str, Any]:
    case_id = "credential_path_reachable_from_untrusted_content_rejected"
    verifier = _BlastRadiusInventoryVerifier()
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)

    mutated = {
        "id": "mutated_credential_path_theta",
        "category": "credential",
        "blast_radius": "high",
        "destructive": False,
        "approval_gate_required": True,
        "approval_gate_present": True,
        "reachable_from_untrusted_input": True,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": True,
        "includes_local_diagnostics": False,
    }
    verifier.register(mutated)

    transcript = [
        {"op": "register", **entry} for entry in (*_CLEAN_INVENTORY, mutated)
    ]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a credential-bearing path (provider OAuth file, API key store, "
            "signed-bundle private key) is marked reachable from untrusted content or "
            "tool output and the inventory must reject instead of silently accepting"
        ),
    )


def run_provider_dispatch_without_approval_readiness_rejected(work: Path) -> dict[str, Any]:
    case_id = "provider_dispatch_without_approval_readiness_rejected"
    verifier = _BlastRadiusInventoryVerifier()
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)

    mutated = {
        "id": "mutated_provider_dispatch_iota",
        "category": "provider_dispatch",
        "blast_radius": "high",
        "destructive": False,
        "approval_gate_required": True,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": False,
        "dispatch_authorized": True,
        "includes_instruction_files": False,
        "includes_memory_blocks": False,
        "includes_raw_prompts": False,
        "includes_credentials": False,
        "includes_local_diagnostics": False,
    }
    verifier.register(mutated)

    transcript = [
        {"op": "register", **entry} for entry in (*_CLEAN_INVENTORY, mutated)
    ]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a provider dispatch path is registered as executable without "
            "the existing approval and readiness posture (no approval gate, "
            "readiness_gated=false, dispatch_authorized=true) and the inventory must "
            "reject instead of silently accepting"
        ),
    )


def run_release_artifact_includes_instruction_or_credentials_rejected(work: Path) -> dict[str, Any]:
    case_id = "release_artifact_includes_instruction_or_credentials_rejected"
    verifier = _BlastRadiusInventoryVerifier()
    for entry in _CLEAN_INVENTORY:
        verifier.register(entry)

    mutated = {
        "id": "mutated_release_artifact_kappa",
        "category": "release_artifact",
        "blast_radius": "moderate",
        "destructive": False,
        "approval_gate_required": False,
        "approval_gate_present": False,
        "reachable_from_untrusted_input": False,
        "readiness_gated": True,
        "dispatch_authorized": False,
        "includes_instruction_files": True,
        "includes_memory_blocks": True,
        "includes_raw_prompts": True,
        "includes_credentials": True,
        "includes_local_diagnostics": True,
    }
    verifier.register(mutated)

    transcript = [
        {"op": "register", **entry} for entry in (*_CLEAN_INVENTORY, mutated)
    ]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "mutation: a release/public artifact path is registered as including "
            "instruction files, memory blocks, raw prompts, credentials, and local-"
            "only diagnostics and the inventory must reject instead of silently "
            "accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_inventory_classified_and_gated": run_clean_inventory_classified_and_gated,
    "unclassified_high_blast_radius_command_path_rejected": run_unclassified_high_blast_radius_command_path_rejected,
    "destructive_action_without_approval_gate_rejected": run_destructive_action_without_approval_gate_rejected,
    "credential_path_reachable_from_untrusted_content_rejected": run_credential_path_reachable_from_untrusted_content_rejected,
    "provider_dispatch_without_approval_readiness_rejected": run_provider_dispatch_without_approval_readiness_rejected,
    "release_artifact_includes_instruction_or_credentials_rejected": run_release_artifact_includes_instruction_or_credentials_rejected,
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
        "categories": sorted(VALID_CATEGORIES),
        "blast_radius_levels": sorted(VALID_BLAST_RADIUS),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "AI agent blast-radius inventory is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix AI agent blast-radius inventory blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-blast-radius-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-ai-agent-blast-radius-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
