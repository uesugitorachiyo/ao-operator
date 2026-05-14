from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "run-artifacts/release-v0.5/RELEASE-NOTES.md"


def test_v0_5_release_notes_record_tag_and_scope() -> None:
    body = NOTES.read_text(encoding="utf-8")

    required = [
        "Release Notes v0.5.0",
        "**Tag:** `v0.5.0`",
        "**Tag commit:** `31e5e229`",
        "Plan-hardener role",
        "Queue recovery hardening",
        "Redacted RunSpec validation",
        "Operator cockpit hash visibility",
        "Blocked execution evidence",
        "Parity hygiene",
    ]
    for text in required:
        assert text in body


def test_v0_5_release_notes_preserve_safe_execution_boundary() -> None:
    body = NOTES.read_text(encoding="utf-8")

    required = [
        "`dispatch_authorized=false`",
        "no live provider dispatch",
        "Agent OS execution remains blocked",
        "`would_run_provider=false`",
        "Release readiness",
        "No live provider dispatch",
        "Start a separate gated SDD lane",
    ]
    for text in required:
        assert text in body
