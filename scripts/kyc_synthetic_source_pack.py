#!/usr/bin/env python3
"""Build a deterministic synthetic KYC source pack for financial demos.

This fixture contains no real customer PII. It is intentionally narrow so the
financial-services KYC profile can exercise classification, redaction, rules
evaluation, risk scoring, and supervisory review without paid connectors or
private data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "ao-operator/kyc-synthetic-source-pack/v1"

SUPPORTED_CASES: dict[str, dict[str, Any]] = {
    "synthetic-kyc-001": {
        "customer_type": "individual",
        "jurisdiction": "US-CA",
        "documents": [
            {
                "id": "doc-identity",
                "type": "government_id",
                "text": "Synthetic government ID for Demo Person, DOB 1990-01-01, document number DEMO-1234.",
                "pii_fields": ["name", "date_of_birth", "document_number"],
            },
            {
                "id": "doc-address",
                "type": "proof_of_address",
                "text": "Synthetic utility statement for Demo Person at 1 Demo Way, San Francisco, CA 94105.",
                "pii_fields": ["name", "address"],
            },
        ],
        "rules": [
            {
                "id": "identity-document-present",
                "description": "Government identity document must be present.",
                "severity": "hard-stop",
            },
            {
                "id": "address-document-present",
                "description": "Proof of address must be present.",
                "severity": "review",
            },
            {
                "id": "pii-redaction-required",
                "description": "PII must be redacted before non-PII reviewers consume the case.",
                "severity": "hard-stop",
            },
        ],
    }
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, body: object) -> str:
    encoded = json.dumps(body, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(encoded)
    return _sha256_bytes(encoded)


def _write_text(path: Path, body: str) -> str:
    encoded = body.encode("utf-8")
    path.write_bytes(encoded)
    return _sha256_bytes(encoded)


def build_source_pack(case_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    normalized = case_id.strip().lower()
    try:
        fixture = SUPPORTED_CASES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(SUPPORTED_CASES))
        raise ValueError(
            f"unsupported synthetic KYC case {case_id!r}; supported cases: {supported}"
        ) from exc

    documents = "\n".join(
        [
            "# Synthetic KYC Documents",
            "",
            f"Case: `{normalized}`",
            "Synthetic data only: `true`",
            "Real customer PII: `false`",
            "",
            "## Documents",
            "",
            *[
                "\n".join(
                    [
                        f"### {document['id']}",
                        "",
                        f"Type: `{document['type']}`",
                        f"PII fields: `{', '.join(document['pii_fields'])}`",
                        "",
                        document["text"],
                        "",
                    ]
                )
                for document in fixture["documents"]
            ],
            "## Boundary",
            "",
            "- All identities, addresses, dates, and identifiers are synthetic.",
            "- Do not use this fixture for real customer onboarding.",
            "- Do not approve, deny, or score a real account from this fixture.",
            "",
        ]
    )
    rules_grid = {
        "schema": "ao-operator/kyc-rules-grid/v1",
        "case_id": normalized,
        "customer_type": fixture["customer_type"],
        "jurisdiction": fixture["jurisdiction"],
        "rules": fixture["rules"],
    }
    redaction_map = {
        "schema": "ao-operator/kyc-redaction-map-placeholder/v1",
        "case_id": normalized,
        "encrypted": False,
        "placeholder_only": True,
        "redactions": [
            {"field": "name", "replacement": "[REDACTED_NAME]"},
            {"field": "date_of_birth", "replacement": "[REDACTED_DOB]"},
            {"field": "document_number", "replacement": "[REDACTED_DOCUMENT_NUMBER]"},
            {"field": "address", "replacement": "[REDACTED_ADDRESS]"},
        ],
    }
    artifacts = {
        "customer-documents.md": documents,
        "rules-grid.json": json.dumps(rules_grid, indent=2, sort_keys=True) + "\n",
        "redaction-map-placeholder.json": json.dumps(redaction_map, indent=2, sort_keys=True) + "\n",
    }
    manifest = {
        "schema": SCHEMA,
        "case_id": normalized,
        "synthetic_data_only": True,
        "real_customer_pii": False,
        "paid_connectors": [],
        "artifacts": [],
    }
    for name, body in artifacts.items():
        manifest["artifacts"].append(
            {
                "name": name,
                "sha256": _sha256_bytes(body.encode("utf-8")),
                "bytes": len(body.encode("utf-8")),
            }
        )
    return manifest, artifacts


def write_source_pack(case_id: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, artifacts = build_source_pack(case_id)
    for name, body in artifacts.items():
        artifact_path = output_dir / name
        if name.endswith(".json"):
            digest = _write_json(artifact_path, json.loads(body))
        else:
            digest = _write_text(artifact_path, body)
        expected = next(item["sha256"] for item in manifest["artifacts"] if item["name"] == name)
        if digest != expected:  # pragma: no cover - defensive invariant
            raise RuntimeError(f"digest mismatch while writing {name}")
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    manifest = write_source_pack(args.case_id, args.output_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
