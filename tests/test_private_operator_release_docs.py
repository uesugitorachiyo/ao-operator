from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_private_operator_release_runbook_covers_release_gate_topics() -> None:
    doc = ROOT / "docs" / "private-operator-release.md"

    assert doc.is_file()
    body = doc.read_text(encoding="utf-8")

    for required in [
        "## Private Install",
        "## Verification",
        "## Troubleshooting",
        "## Security Posture",
        "## What This Does Not Claim",
        "ao-runtime v0.2.0-ga",
        "ao-operator v0.7.0-ga",
        "Provider API-key environment variables are forbidden",
        "No public launch assets published from this private train",
    ]:
        assert required in body


def test_private_operator_release_runbook_is_linked_from_top_level_docs() -> None:
    for relative in ("README.md", "SETUP.md"):
        body = (ROOT / relative).read_text(encoding="utf-8")
        assert "docs/private-operator-release.md" in body
