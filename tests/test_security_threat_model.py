from __future__ import annotations

from pathlib import Path

import check_security_threat_model as threat_model


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_security_threat_model_requires_data_flow_and_stride(tmp_path):
    write(
        tmp_path / "docs" / "sdd" / "39-security-threat-model-data-flow.md",
        "\n".join(
            [
                "STRIDE threat model",
                "Data-flow: operator -> AO Operator -> AO Runtime -> remote worker -> provider CLI.",
                "Trust boundary: operator approval, SSH transport, AO event artifacts, OAuth credential boundary.",
                "Assets: provider OAuth, workspace bundle, role artifacts, AO events, operator approval.",
                "Threats: spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege.",
                "Mitigations: host-key pinning, safe archive extraction, redaction, no-provider DAST, manual pen test gate.",
            ]
        )
        + "\n",
    )

    payload = threat_model.summarize(tmp_path)

    assert payload["schema"] == "ao-operator/security-threat-model/v1"
    assert payload["verdict"] == "PASS"
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_security_threat_model_fails_without_trust_boundaries(tmp_path):
    write(tmp_path / "docs" / "sdd" / "39-security-threat-model-data-flow.md", "STRIDE only\n")

    payload = threat_model.summarize(tmp_path)

    assert payload["verdict"] == "FAIL"
    assert any("trust boundary" in blocker for blocker in payload["blockers"])
