from __future__ import annotations

import json
from pathlib import Path

import check_security_sdlc_roadmap as roadmap
import pr_ready


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_security_sdlc_roadmap_requires_pentest_and_cert_lanes(tmp_path):
    write(
        tmp_path / "docs" / "sdd" / "37-public-release-security-and-dast.md",
        "AST public-release security gate DAST no-provider\n",
    )
    write(
        tmp_path / "docs" / "sdd" / "38-security-sdlc-roadmap.md",
        "Penetration testing, manual pen test, manual pentest report, report template, SEI CERT secure coding standards, threat model, data-flow, strict-public artifact hygiene, evidence integrity, host-key evidence, known_hosts, supply-chain, and dependency review are gated roadmap lanes.\n",
    )
    write(tmp_path / "docs" / "sdd" / "39-security-threat-model-data-flow.md", "threat model data-flow\n")
    write(tmp_path / "docs" / "sdd" / "40-manual-penetration-test-gate.md", "manual pen test\n")
    write(tmp_path / "SECURITY.md", "Report security issues privately.\n")
    write(tmp_path / "scripts" / "check_public_release_security.py", "# scanner\n")
    write(tmp_path / "scripts" / "redact_strict_public_artifacts.py", "# redactor\n")
    write(tmp_path / "scripts" / "check_status_json_integrity.py", "# integrity\n")
    write(tmp_path / "scripts" / "check_host_key_evidence.py", "# host key\n")
    write(tmp_path / "scripts" / "classify_pentest_report.py", "# classifier\n")
    write(tmp_path / "scripts" / "check_supply_chain_gate.py", "# supply chain\n")
    write(tmp_path / "scripts" / "check_dast_readiness.py", "# dast\n")
    write(tmp_path / "docs" / "templates" / "manual-pentest-report-template.md", "# template\n")
    write(
        tmp_path / "examples" / "remote-transfer-v2-stress" / "operator-slices.json",
        json.dumps(
            {
                "schema": "ao-operator/operator-slices/v1",
                "slices": [
                        {"id": "63-public-release-security-dast"},
                        {"id": "64-security-sdlc-roadmap-cert-pentest"},
                        {"id": "65-record-security-threat-model"},
                        {"id": "66-record-manual-pentest-gate"},
                        {"id": "67-record-host-key-evidence-gate"},
                        {"id": "68-classify-manual-pentest-report-template"},
                        {"id": "69-record-supply-chain-gate"},
                    ],
                }
            ),
    )

    payload = roadmap.summarize(tmp_path)

    assert payload["schema"] == "ao-operator/security-sdlc-roadmap/v1"
    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["controls"]["sei_cert"]["status"] == "PLANNED"
    assert payload["controls"]["penetration_testing"]["status"] == "PLANNED"
    assert payload["controls"]["strict_public_artifact_hygiene"]["status"] == "ACTIVE"
    assert payload["controls"]["status_json_integrity"]["status"] == "ACTIVE"
    assert payload["controls"]["host_key_evidence"]["status"] == "ACTIVE"
    assert payload["controls"]["manual_pentest_report_classifier"]["status"] == "ACTIVE"
    assert payload["controls"]["supply_chain_gate"]["status"] == "ACTIVE"


def test_security_sdlc_roadmap_fails_when_pentest_is_missing(tmp_path):
    write(tmp_path / "docs" / "sdd" / "37-public-release-security-and-dast.md", "AST DAST\n")
    write(tmp_path / "docs" / "sdd" / "38-security-sdlc-roadmap.md", "SEI CERT only.\n")
    write(tmp_path / "SECURITY.md", "Security policy.\n")
    write(
        tmp_path / "examples" / "remote-transfer-v2-stress" / "operator-slices.json",
        json.dumps({"schema": "ao-operator/operator-slices/v1", "slices": []}),
    )

    payload = roadmap.summarize(tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("penetration_testing" in blocker for blocker in payload["blockers"])


def test_pr_ready_ci_includes_security_sdlc_gates():
    commands = [" ".join(command) for command in pr_ready.command_plan(ci=True)]

    assert any("scripts/check_public_release_security.py --fail-on HIGH" in command for command in commands)
    assert any("scripts/check_public_release_security.py --strict-public --fail-on HIGH" in command for command in commands)
    assert any("scripts/check_public_release_security.py --strict-public --fail-on HIGH --summary-only" in command for command in commands)
    assert any("scripts/check_dast_readiness.py" in command for command in commands)
    assert any("scripts/check_security_sdlc_roadmap.py" in command for command in commands)
