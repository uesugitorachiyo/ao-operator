from __future__ import annotations

import json
from pathlib import Path

import verify_closure


def test_obligation_ledger_evidence_fails_rejected_ledger(tmp_path: Path):
    ledger_dir = tmp_path / "run-artifacts" / "demo"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "obligation-ledger.json").write_text(
        json.dumps(
            {
                "schema_version": "ao2.obligation-ledger.v1",
                "summary": {"pass": 0, "fail": 1, "unverified": 0, "waived": 0},
                "verdict": "rejected",
            }
        ),
        encoding="utf-8",
    )

    result = verify_closure.obligation_ledger_evidence(tmp_path, require=False)

    assert result["verdict"] == "FAIL"
    assert result["ledger_count"] == 1
    assert any("verdict must be accepted" in detail for detail in result["details"])


def test_obligation_ledger_evidence_accepts_clean_ledger(tmp_path: Path):
    ledger_dir = tmp_path / "run-artifacts" / "demo"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "obligation-ledger.json").write_text(
        json.dumps(
            {
                "schema_version": "ao2.obligation-ledger.v1",
                "summary": {"pass": 3, "fail": 0, "unverified": 0, "waived": 0},
                "verdict": "accepted",
            }
        ),
        encoding="utf-8",
    )

    result = verify_closure.obligation_ledger_evidence(tmp_path, require=False)

    assert result["verdict"] == "PASS"
    assert result["ledger_count"] == 1
    assert result["details"] == []


def test_obligation_ledger_evidence_can_require_a_ledger(tmp_path: Path):
    result = verify_closure.obligation_ledger_evidence(tmp_path, require=True)

    assert result["verdict"] == "FAIL"
    assert result["ledger_count"] == 0
    assert result["details"] == ["required obligation ledger was not found"]


def test_obligation_ledger_evidence_rechecks_ledger_against_repo(tmp_path: Path):
    spec = tmp_path / "docs" / "specs" / "demo-spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "- MUST preserve `net = gross - fees` exactly in the implementation note.\n",
        encoding="utf-8",
    )
    ledger_dir = tmp_path / "run-artifacts" / "demo"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "obligation-ledger.json").write_text(
        json.dumps(
            {
                "schema_version": "ao2.obligation-ledger.v1",
                "source_contracts": [
                    {
                        "path": "docs/specs/demo-spec.md",
                        "sha256": "sha256:placeholder",
                    }
                ],
                "obligations": [
                    {
                        "id": "OBL-001",
                        "kind": "content_preservation",
                        "statement": "MUST preserve `net = gross - fees` exactly in the implementation note.",
                        "source_path": "docs/specs/demo-spec.md",
                        "source_line": 1,
                        "source_excerpt_hash": "sha256:placeholder",
                        "expected_fragments": ["net = gross - fees"],
                        "status": "pass",
                        "evidence": [],
                        "waiver": None,
                    }
                ],
                "summary": {"pass": 1, "fail": 0, "unverified": 0, "waived": 0},
                "verdict": "accepted",
            }
        ),
        encoding="utf-8",
    )

    result = verify_closure.obligation_ledger_evidence(tmp_path, require=True)

    assert result["verdict"] == "FAIL"
    assert any("fail count must be 0, got 1" in detail for detail in result["details"])
