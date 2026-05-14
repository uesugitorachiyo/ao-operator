#!/usr/bin/env python3
"""Validate the AO Operator security threat model and data-flow gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/security-threat-model/v1"
DEFAULT_DOC = "docs/sdd/39-security-threat-model-data-flow.md"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/security-threat-model.json"

REQUIRED_TERMS = {
    "stride": ["STRIDE"],
    "data_flow": ["data-flow", "operator", "AO Operator", "AO Runtime", "remote worker", "provider CLI"],
    "trust_boundary": ["trust boundary", "operator approval", "SSH transport", "OAuth credential boundary"],
    "assets": ["assets", "provider OAuth", "workspace bundle", "role artifacts", "AO events"],
    "threats": ["spoofing", "tampering", "repudiation", "information disclosure", "denial of service", "elevation of privilege"],
    "mitigations": ["host-key pinning", "safe archive extraction", "redaction", "no-provider DAST", "manual pen test"],
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def summarize(root: Path = ROOT, doc: str = DEFAULT_DOC) -> dict[str, Any]:
    root = root.resolve()
    doc_path = root / doc
    body = read_text(doc_path)
    lower_body = body.lower()
    blockers: list[str] = []
    sections: dict[str, dict[str, Any]] = {}

    for section, terms in REQUIRED_TERMS.items():
        missing = [term for term in terms if term.lower() not in lower_body]
        if missing:
            blockers.append(f"{section}: missing " + ", ".join(missing))
        sections[section] = {
            "documented": not missing,
            "required_terms": terms,
            "missing_terms": missing,
        }

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": str(root),
        "document": doc,
        "verdict": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "sections": sections,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Resolve threat-model blockers before public release."
            if blockers
            else "Threat model is recorded; keep manual pen testing gated separately."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"verdict={payload['verdict']}",
        f"dispatch_authorized={str(payload['dispatch_authorized']).lower()}",
        f"live_providers_run={str(payload['live_providers_run']).lower()}",
    ]
    lines.extend(f"blocker={blocker}" for blocker in payload["blockers"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AO Operator security threat model")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--doc", default=DEFAULT_DOC)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(args.root, args.doc)
    if args.write_output is not None:
        output = Path(args.write_output)
        if not output.is_absolute():
            output = args.root / output
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
