from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "run-artifacts/release-v0.2/windows-outbound-bootstrap/windows-live-validation-progress.md"


def test_windows_live_progress_records_outbound_success_and_registration() -> None:
    body = PROGRESS.read_text(encoding="utf-8")

    required = [
        "Status: PASS",
        "Windows outbound SSH tunnel and AO worker registration are proven",
        "Coordinator reachability through tunnel",
        "Crane key auth",
        "Windows worker registration",
        "ao-worker: registered; heartbeat interval=10s",
        "W4 dispatch proof",
        "Windows Codex PATH",
        "Provider-backed Windows Codex smoke",
        "No current network blocker",
        "windows-live-worker",
    ]
    for text in required:
        assert text in body


def test_windows_live_progress_keeps_provider_api_keys_out_of_path() -> None:
    body = PROGRESS.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" in body
    assert "ANTHROPIC_API_KEY" in body
    assert "were absent from the Windows process environment" in body
    assert "provider API-key paths out of the run" in body
