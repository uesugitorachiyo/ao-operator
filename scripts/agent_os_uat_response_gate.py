#!/usr/bin/env python3
"""Evaluate Agent OS human UAT responses before closure authorization."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UAT_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json"
DEFAULT_RESPONSES = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-responses.json"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json"
INCOMPLETE_BLOCKER = "human UAT responses are incomplete"
REJECTED_BLOCKER = "human UAT responses contain rejection"


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


def uat_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("uat_items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def response_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("responses")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def response_template(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "ao-operator/agent-os-uat-responses/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "responses": [
            {
                "id": str(item.get("id") or ""),
                "role": str(item.get("role") or ""),
                "question": str(item.get("question") or ""),
                "accepted": None,
                "response": "",
                "responder": "",
                "responded_at": "",
            }
            for item in items
        ],
    }


def validate_source(data: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "ao-operator/agent-os-uat-state/v1":
        errors.append("UAT report schema must be ao-operator/agent-os-uat-state/v1")
    if data.get("verdict") != "PASS":
        errors.append("UAT report verdict must be PASS")
    if data.get("dispatch_authorized") is not False:
        errors.append("dispatch_authorized must remain false for UAT response gate")
    if data.get("live_providers_run") is not False:
        errors.append("live_providers_run must remain false for UAT response gate")
    if data.get("closure_authorized") is not False:
        errors.append("source closure_authorized must remain false before response gate")
    if not items:
        errors.append("UAT items must be non-empty")
    return errors


def response_summary(items: list[dict[str, Any]], responses: list[dict[str, Any]]) -> dict[str, int]:
    by_id = {str(item.get("id")): item for item in responses if item.get("id")}
    accepted = 0
    rejected = 0
    pending = 0
    for item in items:
        response = by_id.get(str(item.get("id")))
        if not response or response.get("accepted") is None:
            pending += 1
        elif response.get("accepted") is True:
            accepted += 1
        else:
            rejected += 1
    return {
        "accepted": accepted,
        "pending": pending,
        "rejected": rejected,
        "required": len(items),
    }


def complete_accepted_response(response: dict[str, Any]) -> bool:
    return (
        response.get("accepted") is True
        and bool(str(response.get("response") or "").strip())
        and bool(str(response.get("responder") or "").strip())
        and bool(str(response.get("responded_at") or "").strip())
    )


def closure_allowed(items: list[dict[str, Any]], responses: list[dict[str, Any]]) -> bool:
    by_id = {str(item.get("id")): item for item in responses if item.get("id")}
    return all(complete_accepted_response(by_id.get(str(item.get("id"))) or {}) for item in items)


def gate_blockers(summary: dict[str, int], *, malformed: bool) -> list[str]:
    blockers: list[str] = []
    if malformed:
        blockers.append(INCOMPLETE_BLOCKER)
    if summary["rejected"]:
        blockers.append(REJECTED_BLOCKER)
    if summary["pending"] or summary["accepted"] < summary["required"]:
        if INCOMPLETE_BLOCKER not in blockers:
            blockers.append(INCOMPLETE_BLOCKER)
    return blockers


def evaluate_gate(
    *,
    root: Path = ROOT,
    uat_report: str | Path = DEFAULT_UAT_REPORT,
    responses_path: str | Path = DEFAULT_RESPONSES,
    write_template: bool = False,
) -> dict[str, Any]:
    uat_path = resolve_path(root, uat_report)
    response_path = resolve_path(root, responses_path)
    data = load_json(uat_path)
    items = uat_items(data)
    errors = validate_source(data, items)
    if write_template and not response_path.exists():
        write_output(response_path, response_template(items))
    response_data = load_json(response_path)
    malformed = bool(response_data) and response_data.get("schema") != "ao-operator/agent-os-uat-responses/v1"
    responses = response_items(response_data)
    summary = response_summary(items, responses)
    allowed = not errors and not malformed and closure_allowed(items, responses)
    blockers = [] if allowed else gate_blockers(summary, malformed=malformed)
    return {
        "schema": "ao-operator/agent-os-uat-response-gate/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors and not malformed else "FAIL",
        "uat_report": relpath(root, uat_path),
        "responses": relpath(root, response_path),
        "response_summary": summary,
        "blockers": blockers,
        "closure_authorized": allowed,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors + (["response schema must be ao-operator/agent-os-uat-responses/v1"] if malformed else []),
        "next_safe_command": (
            "Run Agent OS closure gate."
            if allowed
            else "Collect complete accepted human UAT responses before closure authorization."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate AO Operator Agent OS UAT responses")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--uat-report", default=DEFAULT_UAT_REPORT)
    parser.add_argument("--responses", default=DEFAULT_RESPONSES)
    parser.add_argument("--write-template", action="store_true")
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = evaluate_gate(
        root=args.root,
        uat_report=args.uat_report,
        responses_path=args.responses,
        write_template=args.write_template,
    )
    if args.write_output is not None:
        output_arg = Path(args.write_output)
        output_path = output_arg if output_arg.is_absolute() else args.root / output_arg
        write_output(output_path, payload)
        payload["output"] = str(output_path)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"closure_authorized={str(payload['closure_authorized']).lower()}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
