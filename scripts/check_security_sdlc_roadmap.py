#!/usr/bin/env python3
"""Validate the AO Operator security SDLC roadmap gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/security-sdlc-roadmap/v1"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/security-sdlc-roadmap.json"


CONTROL_DEFINITIONS = {
    "ast_sast": {
        "status": "ACTIVE",
        "required_terms": ["AST", "public-release security gate"],
        "required_files": ["scripts/check_public_release_security.py"],
        "description": "Static source and artifact scanning for high-risk release patterns.",
    },
    "dast_no_provider": {
        "status": "ACTIVE",
        "required_terms": ["DAST", "no-provider"],
        "required_files": ["scripts/check_dast_readiness.py"],
        "description": "Dynamic tests for transfer/operator surfaces without live provider dispatch.",
    },
    "strict_public_artifact_hygiene": {
        "status": "ACTIVE",
        "required_terms": ["strict-public artifact hygiene"],
        "required_files": ["scripts/redact_strict_public_artifacts.py"],
        "description": "Redaction gate for committed historical status and evaluation artifacts.",
    },
    "status_json_integrity": {
        "status": "ACTIVE",
        "required_terms": ["evidence integrity"],
        "required_files": ["scripts/check_status_json_integrity.py"],
        "description": "JSON parseability gate for committed status and evaluation artifacts.",
    },
    "sei_cert": {
        "status": "PLANNED",
        "required_terms": ["SEI CERT", "secure coding standards"],
        "required_files": [],
        "description": "CERT-aligned secure coding controls and manual review checklist.",
    },
    "penetration_testing": {
        "status": "PLANNED",
        "required_terms": ["penetration testing", "manual pen test"],
        "required_files": [],
        "description": "Human-approved remote and adversarial testing before public exposure.",
    },
    "host_key_evidence": {
        "status": "ACTIVE",
        "required_terms": ["host-key evidence", "known_hosts"],
        "required_files": ["scripts/check_host_key_evidence.py"],
        "description": "Host-key pinning evidence gate before remote DAST approval.",
    },
    "manual_pentest_report_classifier": {
        "status": "ACTIVE",
        "required_terms": ["manual pentest report", "report template"],
        "required_files": ["scripts/classify_pentest_report.py", "docs/templates/manual-pentest-report-template.md"],
        "description": "Manual pentest report template and classifier.",
    },
    "supply_chain_gate": {
        "status": "ACTIVE",
        "required_terms": ["supply-chain", "dependency review"],
        "required_files": ["scripts/check_supply_chain_gate.py"],
        "description": "Dependency manifest, lockfile, advisory, and license release gate.",
    },
    "threat_model_data_flow": {
        "status": "PLANNED",
        "required_terms": ["threat model", "data-flow"],
        "required_files": [],
        "description": "STRIDE-style data-flow analysis for remote worker and provider boundaries.",
    },
}

ROADMAP_DOCS = [
    "docs/sdd/37-public-release-security-and-dast.md",
    "docs/sdd/38-security-sdlc-roadmap.md",
    "docs/sdd/39-security-threat-model-data-flow.md",
    "docs/sdd/40-manual-penetration-test-gate.md",
    "docs/sdd/41-host-key-evidence-gate.md",
    "docs/sdd/42-manual-pentest-report-classifier.md",
    "docs/sdd/43-supply-chain-audit-gate.md",
    "SECURITY.md",
]
OPERATOR_MANIFEST = "examples/remote-transfer-v2-stress/operator-slices.json"
REQUIRED_OPERATOR_SLICES = [
    "63-public-release-security-dast",
    "64-security-sdlc-roadmap-cert-pentest",
    "65-record-security-threat-model",
    "66-record-manual-pentest-gate",
    "67-record-host-key-evidence-gate",
    "68-classify-manual-pentest-report-template",
    "69-record-supply-chain-gate",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_operator_slice_ids(root: Path) -> set[str]:
    path = root / OPERATOR_MANIFEST
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return set()
    return {str(item.get("id")) for item in slices if isinstance(item, dict)}


def summarize(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    corpus = "\n".join(read_text(root / path) for path in ROADMAP_DOCS)
    lower_corpus = corpus.lower()
    blockers: list[str] = []
    controls: dict[str, dict[str, Any]] = {}

    for control_id, definition in CONTROL_DEFINITIONS.items():
        missing_terms = [
            term
            for term in definition["required_terms"]
            if term.lower() not in lower_corpus
        ]
        missing_files = [
            path
            for path in definition["required_files"]
            if not (root / path).is_file()
        ]
        ok = not missing_terms and not missing_files
        if not ok:
            blockers.append(
                f"{control_id}: missing "
                + ", ".join([*missing_terms, *missing_files])
            )
        controls[control_id] = {
            "status": definition["status"],
            "description": definition["description"],
            "documented": ok,
            "missing_terms": missing_terms,
            "missing_files": missing_files,
        }

    slice_ids = load_operator_slice_ids(root)
    missing_slices = [slice_id for slice_id in REQUIRED_OPERATOR_SLICES if slice_id not in slice_ids]
    if missing_slices:
        blockers.append("operator_slices: missing " + ", ".join(missing_slices))

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": str(root),
        "verdict": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "controls": controls,
        "operator_manifest": OPERATOR_MANIFEST,
        "required_operator_slices": REQUIRED_OPERATOR_SLICES,
        "missing_operator_slices": missing_slices,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "Resolve missing security SDLC roadmap items before public release."
            if blockers
            else "Security SDLC roadmap is recorded; keep host-key evidence and manual pen testing gated."
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
    for control_id, control in payload["controls"].items():
        lines.append(f"control={control_id} status={control['status']} documented={str(control['documented']).lower()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AO Operator security SDLC roadmap")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = summarize(args.root)
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
