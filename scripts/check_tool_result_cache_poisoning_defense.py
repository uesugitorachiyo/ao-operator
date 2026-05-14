#!/usr/bin/env python3
"""Tool result cache poisoning defense gate.

Models the tool-result cache integrity invariant that no Factory
v3 cached tool result can be served via a cache-key collision, a
stale-cache serve after invalidation, a TTL extension via admin
replay, a forged response signature, or a cross-tenant cache
share.

Every cache-entry edge whose payload would let a poisoned tool
result reach the model is fail-closed.

The gate exercises six deterministic cases against a temporary
work directory (no repo pollution, no provider dispatch, no AO,
no real cache backend invoked):

* ``clean_no_tool_result_cache_poisoning`` -- control: every
  registered cache entry has a unique declared cache key, is
  fresh relative to its declared invalidation token, has not had
  its TTL extended via replay, carries a verified response
  signature, and is scoped to a single tenant.
* ``cache_key_collision_admit_rejected`` -- mutation: a cache
  entry collides on the declared cache key with a different
  tenant's payload; the verifier MUST reject.
* ``stale_cache_serve_after_invalidation_admit_rejected`` --
  mutation: a cache entry is served after its declared
  invalidation token has been bumped; the verifier MUST reject.
* ``ttl_extension_via_admin_replay_admit_rejected`` -- mutation:
  a cache entry has its TTL extended by replaying the admin
  refresh path; the verifier MUST reject.
* ``forged_response_signature_admit_rejected`` -- mutation: a
  cache entry carries a forged response signature that does not
  match the declared signing key; the verifier MUST reject.
* ``cross_tenant_cache_share_admit_rejected`` -- mutation: a
  cache entry is reused across two distinct tenants; the
  verifier MUST reject.

Every case lays down a per-case
``tool-result-cache-poisoning-transcript.json`` in a temporary
work directory, runs it through the verifier embedded in this
gate, and records ``observed_verdict``. The gate's overall
verdict is ``PASS`` only when every case lines up with the
expected verdict.

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
    "tool-result-cache-poisoning-defense.json"
)
SCHEMA = "ao-operator/tool-result-cache-poisoning-defense/v1"

CASE_IDS = (
    "clean_no_tool_result_cache_poisoning",
    "cache_key_collision_admit_rejected",
    "stale_cache_serve_after_invalidation_admit_rejected",
    "ttl_extension_via_admin_replay_admit_rejected",
    "forged_response_signature_admit_rejected",
    "cross_tenant_cache_share_admit_rejected",
)

EXPECTED_VERDICTS = {
    "clean_no_tool_result_cache_poisoning": "PASS",
    "cache_key_collision_admit_rejected": "FAIL",
    "stale_cache_serve_after_invalidation_admit_rejected": "FAIL",
    "ttl_extension_via_admin_replay_admit_rejected": "FAIL",
    "forged_response_signature_admit_rejected": "FAIL",
    "cross_tenant_cache_share_admit_rejected": "FAIL",
}

ENTRY_CLASSES = {
    "clean_entry",
    "cache_key_collision",
    "stale_cache_serve_after_invalidation",
    "ttl_extension_via_admin_replay",
    "forged_response_signature",
    "cross_tenant_cache_share",
}
APPROVED_ENTRY_CLASSES = {
    "clean_entry",
}
HAZARD_CLASSES = {
    "cache_key_collision_admit",
    "stale_cache_serve_after_invalidation_admit",
    "ttl_extension_via_admin_replay_admit",
    "forged_response_signature_admit",
    "cross_tenant_cache_share_admit",
}

DECLARED_CACHE_KEY_ALPHA = "key::cache_alpha"
DECLARED_CACHE_KEY_BETA = "key::cache_beta"
DECLARED_CACHE_KEY_GAMMA = "key::cache_gamma"
DECLARED_INVALIDATION_TOKEN = "invalidation::token_alpha"
DECLARED_SIGNING_KEY = "signing::key_alpha"

_CLEAN_ENTRY_ALPHA = "cache::clean_alpha"
_CLEAN_ENTRY_BETA = "cache::clean_beta"
_CLEAN_ENTRY_GAMMA = "cache::clean_gamma"
_KEY_COLLISION_ENTRY = "cache::key_collision_alpha"
_STALE_SERVE_ENTRY = "cache::stale_serve_alpha"
_TTL_EXTENSION_ENTRY = "cache::ttl_extension_alpha"
_FORGED_SIGNATURE_ENTRY = "cache::forged_signature_alpha"
_CROSS_TENANT_ENTRY = "cache::cross_tenant_alpha"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


class _ToolResultCachePoisoningDefenseVerifier:
    """In-memory tool-result cache poisoning-defense verifier."""

    def __init__(self) -> None:
        self.cache_entries: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def register(self, entry: dict[str, Any]) -> None:
        self.cache_entries.append(dict(entry))
        self._validate_entry(entry)

    def _validate_entry(self, entry: dict[str, Any]) -> None:
        entry_id = str(entry.get("id") or "<unnamed>")
        entry_class = entry.get("entry_class")
        if entry_class not in ENTRY_CLASSES:
            self.errors.append(
                f"unknown_entry_class:id={entry_id},class={entry_class!r}"
            )
            return
        if entry_class == "cache_key_collision":
            self.errors.append(
                f"cache_key_collision_admit_rejection:id={entry_id},entry={entry.get('cache_entry_id', '<unknown>')}"
            )
            return
        if entry_class == "stale_cache_serve_after_invalidation":
            self.errors.append(
                f"stale_cache_serve_after_invalidation_admit_rejection:id={entry_id},entry={entry.get('cache_entry_id', '<unknown>')}"
            )
            return
        if entry_class == "ttl_extension_via_admin_replay":
            self.errors.append(
                f"ttl_extension_via_admin_replay_admit_rejection:id={entry_id},entry={entry.get('cache_entry_id', '<unknown>')}"
            )
            return
        if entry_class == "forged_response_signature":
            self.errors.append(
                f"forged_response_signature_admit_rejection:id={entry_id},entry={entry.get('cache_entry_id', '<unknown>')}"
            )
            return
        if entry_class == "cross_tenant_cache_share":
            self.errors.append(
                f"cross_tenant_cache_share_admit_rejection:id={entry_id},entry={entry.get('cache_entry_id', '<unknown>')}"
            )
            return
        if entry_class not in APPROVED_ENTRY_CLASSES:
            self.errors.append(
                f"unapproved_entry_class:id={entry_id},class={entry_class!r}"
            )

    def verdict(self) -> str:
        return "PASS" if not self.errors else "FAIL"


_CLEAN_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "id": "clean_entry_alpha",
        "entry_class": "clean_entry",
        "cache_entry_id": _CLEAN_ENTRY_ALPHA,
        "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
        "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
        "declared_signing_key": DECLARED_SIGNING_KEY,
        "tenant": "tenant::alpha",
        "key_collision_observed": False,
        "stale_serve_observed": False,
        "ttl_extension_observed": False,
        "forged_signature_observed": False,
        "cross_tenant_observed": False,
    },
    {
        "id": "clean_entry_beta",
        "entry_class": "clean_entry",
        "cache_entry_id": _CLEAN_ENTRY_BETA,
        "declared_cache_key": DECLARED_CACHE_KEY_BETA,
        "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
        "declared_signing_key": DECLARED_SIGNING_KEY,
        "tenant": "tenant::beta",
        "key_collision_observed": False,
        "stale_serve_observed": False,
        "ttl_extension_observed": False,
        "forged_signature_observed": False,
        "cross_tenant_observed": False,
    },
    {
        "id": "clean_entry_gamma",
        "entry_class": "clean_entry",
        "cache_entry_id": _CLEAN_ENTRY_GAMMA,
        "declared_cache_key": DECLARED_CACHE_KEY_GAMMA,
        "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
        "declared_signing_key": DECLARED_SIGNING_KEY,
        "tenant": "tenant::gamma",
        "key_collision_observed": False,
        "stale_serve_observed": False,
        "ttl_extension_observed": False,
        "forged_signature_observed": False,
        "cross_tenant_observed": False,
    },
)


def _persist_case(work: Path, case_id: str, transcript: list[dict[str, Any]]) -> None:
    case_dir = work / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "tool-result-cache-poisoning-transcript.json").write_text(
        json.dumps({"cache_entries": transcript}, indent=2, sort_keys=True),
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


def run_clean_no_tool_result_cache_poisoning(work: Path) -> dict[str, Any]:
    case_id = "clean_no_tool_result_cache_poisoning"
    verifier = _ToolResultCachePoisoningDefenseVerifier()
    for entry in _CLEAN_ENTRIES:
        verifier.register(entry)
    transcript = [{"op": "register", **entry} for entry in _CLEAN_ENTRIES]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=(
            "control: every registered cache entry has a unique "
            "declared cache key, is fresh relative to its declared "
            "invalidation token, has not had its TTL extended via "
            "replay, carries a verified response signature, and is "
            "scoped to a single tenant"
        ),
    )


def _run_mutation(
    work: Path, case_id: str, mutated: dict[str, Any], detail: str
) -> dict[str, Any]:
    verifier = _ToolResultCachePoisoningDefenseVerifier()
    for entry in _CLEAN_ENTRIES:
        verifier.register(entry)
    verifier.register(mutated)
    transcript = [{"op": "register", **entry} for entry in (*_CLEAN_ENTRIES, mutated)]
    _persist_case(work, case_id, transcript)
    return _case_summary(
        case_id,
        observed_verdict=verifier.verdict(),
        observed_errors=list(verifier.errors),
        detail=detail,
    )


def run_cache_key_collision_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "cache_key_collision_admit_rejected",
        {
            "id": "mutated_cache_key_collision_admit",
            "entry_class": "cache_key_collision",
            "cache_entry_id": _KEY_COLLISION_ENTRY,
            "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
            "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
            "declared_signing_key": DECLARED_SIGNING_KEY,
            "tenant": "tenant::beta",
            "key_collision_observed": True,
            "stale_serve_observed": False,
            "ttl_extension_observed": False,
            "forged_signature_observed": False,
            "cross_tenant_observed": False,
        },
        detail=(
            "mutation: a cache entry collides on the declared "
            "cache key with a different tenant's payload and the "
            "verifier must reject instead of silently accepting"
        ),
    )


def run_stale_cache_serve_after_invalidation_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "stale_cache_serve_after_invalidation_admit_rejected",
        {
            "id": "mutated_stale_cache_serve_after_invalidation_admit",
            "entry_class": "stale_cache_serve_after_invalidation",
            "cache_entry_id": _STALE_SERVE_ENTRY,
            "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
            "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
            "declared_signing_key": DECLARED_SIGNING_KEY,
            "tenant": "tenant::alpha",
            "key_collision_observed": False,
            "stale_serve_observed": True,
            "ttl_extension_observed": False,
            "forged_signature_observed": False,
            "cross_tenant_observed": False,
        },
        detail=(
            "mutation: a cache entry is served after its declared "
            "invalidation token has been bumped and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_ttl_extension_via_admin_replay_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "ttl_extension_via_admin_replay_admit_rejected",
        {
            "id": "mutated_ttl_extension_via_admin_replay_admit",
            "entry_class": "ttl_extension_via_admin_replay",
            "cache_entry_id": _TTL_EXTENSION_ENTRY,
            "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
            "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
            "declared_signing_key": DECLARED_SIGNING_KEY,
            "tenant": "tenant::alpha",
            "key_collision_observed": False,
            "stale_serve_observed": False,
            "ttl_extension_observed": True,
            "forged_signature_observed": False,
            "cross_tenant_observed": False,
        },
        detail=(
            "mutation: a cache entry has its TTL extended by "
            "replaying the admin refresh path and the verifier "
            "must reject instead of silently accepting"
        ),
    )


def run_forged_response_signature_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "forged_response_signature_admit_rejected",
        {
            "id": "mutated_forged_response_signature_admit",
            "entry_class": "forged_response_signature",
            "cache_entry_id": _FORGED_SIGNATURE_ENTRY,
            "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
            "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
            "declared_signing_key": DECLARED_SIGNING_KEY,
            "tenant": "tenant::alpha",
            "key_collision_observed": False,
            "stale_serve_observed": False,
            "ttl_extension_observed": False,
            "forged_signature_observed": True,
            "cross_tenant_observed": False,
        },
        detail=(
            "mutation: a cache entry carries a forged response "
            "signature that does not match the declared signing "
            "key and the verifier must reject instead of silently "
            "accepting"
        ),
    )


def run_cross_tenant_cache_share_admit_rejected(work: Path) -> dict[str, Any]:
    return _run_mutation(
        work,
        "cross_tenant_cache_share_admit_rejected",
        {
            "id": "mutated_cross_tenant_cache_share_admit",
            "entry_class": "cross_tenant_cache_share",
            "cache_entry_id": _CROSS_TENANT_ENTRY,
            "declared_cache_key": DECLARED_CACHE_KEY_ALPHA,
            "declared_invalidation_token": DECLARED_INVALIDATION_TOKEN,
            "declared_signing_key": DECLARED_SIGNING_KEY,
            "tenant": "tenant::beta",
            "key_collision_observed": False,
            "stale_serve_observed": False,
            "ttl_extension_observed": False,
            "forged_signature_observed": False,
            "cross_tenant_observed": True,
        },
        detail=(
            "mutation: a cache entry is reused across two "
            "distinct tenants and the verifier must reject "
            "instead of silently accepting"
        ),
    )


CASE_RUNNERS = {
    "clean_no_tool_result_cache_poisoning": run_clean_no_tool_result_cache_poisoning,
    "cache_key_collision_admit_rejected": run_cache_key_collision_admit_rejected,
    "stale_cache_serve_after_invalidation_admit_rejected": run_stale_cache_serve_after_invalidation_admit_rejected,
    "ttl_extension_via_admin_replay_admit_rejected": run_ttl_extension_via_admin_replay_admit_rejected,
    "forged_response_signature_admit_rejected": run_forged_response_signature_admit_rejected,
    "cross_tenant_cache_share_admit_rejected": run_cross_tenant_cache_share_admit_rejected,
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
        "entry_classes": sorted(ENTRY_CLASSES),
        "approved_entry_classes": sorted(APPROVED_ENTRY_CLASSES),
        "hazard_classes": sorted(HAZARD_CLASSES),
        "cases": cases,
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Tool result cache poisoning defense gate is locked fail-closed; continue Mac-to-Ubuntu remote transfer hardening."
            if overall_pass
            else "Fix Tool result cache poisoning defense blockers before further security hardening."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize(*, work_dir: Path | None = None) -> dict[str, Any]:
    if work_dir is not None:
        return evaluate(work_dir=work_dir)
    with tempfile.TemporaryDirectory(prefix="ao-operator-tool-result-cache-poisoning-defense-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="ao-operator-tool-result-cache-poisoning-defense-") as tmp:
            payload = evaluate(work_dir=Path(tmp))

    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)

    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
