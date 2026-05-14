#!/usr/bin/env python3
"""Guard success-evidence commits for bounded live runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_ROUTING = "run-artifacts/remote-transfer-v2-stress-live/dispatch/live-postrun-routing.json"


def default_output_path(root: Path, slug: str) -> Path:
    return root / "run-artifacts" / slug / "dispatch" / "live-success-commit-guard.json"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def check_guard(
    *,
    root: Path = ROOT,
    slug: str = DEFAULT_SLUG,
    routing_path: str | Path = DEFAULT_ROUTING,
) -> dict[str, Any]:
    resolved_routing = resolve_path(root, routing_path)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        routing = load_json(resolved_routing)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        routing = {}
        errors.append(f"postrun routing unavailable: {exc}")

    acceptance = check_live_acceptance.check_slug(slug, root=root)
    route = str(routing.get("route") or "")
    classification = str(routing.get("classification") or "")
    acceptance_pass = acceptance.get("verdict") == "PASS"
    route_allows_success = route == "RUN_ACCEPTANCE"
    routing_allows_success = routing.get("commit_success_evidence_allowed") is True
    commit_allowed = route_allows_success and routing_allows_success and acceptance_pass

    if routing and routing.get("schema") != "ao-operator/live-postrun-routing/v1":
        errors.append("postrun routing schema is invalid")
    if routing and routing.get("live_providers_run") is not False:
        errors.append("postrun routing must have live_providers_run=false")
    if routing and routing.get("raw_snapshot_commit_allowed") is not False:
        errors.append("postrun routing must keep raw_snapshot_commit_allowed=false")
    if route_allows_success and not acceptance_pass:
        errors.append("route RUN_ACCEPTANCE requires live acceptance PASS before success commit")
    if routing_allows_success and not acceptance_pass:
        errors.append("routing commit_success_evidence_allowed=true conflicts with live acceptance FAIL")
    if acceptance_pass and not route_allows_success:
        errors.append("live acceptance PASS requires postrun route RUN_ACCEPTANCE before success commit")
    if not commit_allowed:
        warnings.append("success live evidence commit is not allowed in the current state")

    next_actions: list[str]
    if commit_allowed:
        next_actions = [
            "Commit accepted bounded-live evidence only.",
            "Do not include raw AO homes or failed-live diagnostic snapshots.",
        ]
    elif classification == "DIAGNOSTIC_REQUIRED":
        next_actions = [
            "Preserve sanitized diagnostics before any rerun.",
            "Do not commit the failed live run as successful evidence.",
        ]
    elif classification == "PENDING_LIVE_RUN":
        next_actions = [
            "Wait for explicit operator approval before running the bounded live slice.",
            "Do not commit pre-live artifacts as accepted live evidence.",
        ]
    else:
        next_actions = ["Regenerate postrun routing before deciding commit eligibility."]

    return {
        "schema": "ao-operator/live-success-commit-guard/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "slug": slug,
        "classification": classification,
        "route": route,
        "routing": relpath(root, resolved_routing),
        "acceptance_verdict": acceptance.get("verdict"),
        "commit_success_evidence_allowed": commit_allowed,
        "raw_snapshot_commit_allowed": False,
        "live_providers_run": False,
        "acceptance": {
            "verdict": acceptance.get("verdict"),
            "checks": acceptance.get("checks", []),
        },
        "next_actions": next_actions,
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"classification={payload['classification']}",
        f"route={payload['route']}",
        f"commit_success_evidence_allowed={str(payload['commit_success_evidence_allowed']).lower()}",
    ]
    lines.extend(f"error={error}" for error in payload.get("errors", []))
    lines.extend(f"warning={warning}" for warning in payload.get("warnings", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard bounded-live success evidence commits")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--routing", default=DEFAULT_ROUTING)
    parser.add_argument(
        "--write-output",
        nargs="?",
        const="",
        help="Write guard JSON; optionally provide an explicit path",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check_guard(root=args.root, slug=args.slug, routing_path=args.routing)
    if args.write_output is not None:
        output_path = Path(args.write_output) if args.write_output else default_output_path(args.root, args.slug)
        if not output_path.is_absolute():
            output_path = args.root / output_path
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
