#!/usr/bin/env python3
"""Check dependency and supply-chain release posture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/supply-chain-gate/v1"
DEFAULT_DOC = "docs/sdd/43-supply-chain-audit-gate.md"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/supply-chain-gate.json"

DEPENDENCY_MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
)
LOCKFILES = (
    "requirements.lock",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "Cargo.lock",
)
DOC_TERMS = ("dependency review", "vulnerability advisory", "license", "pinning")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def summarize(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifests = [path for path in DEPENDENCY_MANIFESTS if (root / path).is_file()]
    lockfiles = [path for path in LOCKFILES if (root / path).is_file()]
    doc_body = read_text(root / DEFAULT_DOC).lower()
    missing_doc_terms = [term for term in DOC_TERMS if term not in doc_body]
    blockers: list[str] = []

    if manifests and not lockfiles:
        blockers.append("lockfile required when dependency manifests are present")
    if manifests and missing_doc_terms:
        blockers.append("supply-chain SDD missing " + ", ".join(missing_doc_terms))

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": "${FACTORY_V3_ROOT}",
        "document": DEFAULT_DOC,
        "dependency_manifests": manifests,
        "lockfiles": lockfiles,
        "audit_plan_documented": not missing_doc_terms if manifests else True,
        "missing_doc_terms": missing_doc_terms if manifests else [],
        "verdict": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "No dependency manifests detected; rerun this gate whenever dependencies are introduced."
            if not manifests
            else "Dependency manifests have lockfile and audit-plan coverage."
            if not blockers
            else "Add lockfile and supply-chain audit documentation before release."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check supply-chain posture")
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
        payload["output"] = output.relative_to(args.root).as_posix() if output.is_relative_to(args.root) else str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
