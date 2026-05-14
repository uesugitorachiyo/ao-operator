from __future__ import annotations

from pathlib import Path

import check_host_key_evidence as hostkey


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_host_key_evidence_gate_records_non_dispatching_requirements(tmp_path):
    write(
        tmp_path / "docs" / "sdd" / "41-host-key-evidence-gate.md",
        "\n".join(
            [
                "Host-key pinning requires known_hosts evidence.",
                "Use ssh-keygen -F and ssh-keyscan output only as reviewed evidence.",
                "Remote transfer commands must use StrictHostKeyChecking=yes and UserKnownHostsFile.",
                "Do not use accept-new for remote DAST.",
                "Record fingerprint evidence before approval.",
            ]
        )
        + "\n",
    )

    payload = hostkey.summarize(tmp_path)

    assert payload["schema"] == "ao-operator/host-key-evidence/v1"
    assert payload["verdict"] == "PASS"
    assert payload["remote_dast_authorized"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["checks"]["known_hosts"]["documented"] is True


def test_host_key_evidence_gate_fails_when_known_hosts_terms_are_missing(tmp_path):
    write(tmp_path / "docs" / "sdd" / "41-host-key-evidence-gate.md", "Host-key pinning only.\n")

    payload = hostkey.summarize(tmp_path)

    assert payload["verdict"] == "FAIL"
    assert payload["blockers"]
