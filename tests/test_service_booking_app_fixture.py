from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_service_booking_recovery_fixture_verifies() -> None:
    proc = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=ROOT / "examples" / "service-booking-recovery-app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "verdict=PASS" in proc.stdout
    assert "request_count=7" in proc.stdout
    assert "statuses=follow-up,lost,new,scheduled" in proc.stdout
    assert "saveable_revenue=13400" in proc.stdout


def test_service_booking_sdd_and_fixture_are_linked() -> None:
    sdd = (ROOT / "examples" / "ingestible-specs" / "service-booking-recovery-sdd.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "examples" / "service-booking-recovery-app" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "Build a first-screen web app" in sdd
    assert "service-booking-recovery-sdd.md" in readme
    assert "describe the outcome" in readme


def test_service_booking_prompt_remains_available_as_secondary_app_sample() -> None:
    prompt = (ROOT / "docs" / "guides" / "codex-claude-service-booking-prompt.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for body in (prompt, readme):
        assert "service-booking-recovery-sdd.md" in body
        assert "examples/service-booking-recovery-app" in body
        assert "saveable_revenue=13400" in body

    assert "Paste This Into Codex Or Claude Code" in prompt
    assert "Do not set OPENAI_API_KEY or ANTHROPIC_API_KEY" in prompt


def test_financial_services_sdd_is_first_run_ready() -> None:
    prompt = (
        ROOT / "docs" / "guides" / "codex-claude-financial-services-profile-prompt.md"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "guides" / "try-ao-operator-in-5-minutes.md").read_text(
        encoding="utf-8"
    )

    for body in (prompt, readme, guide):
        assert "financial-citation-audit-sdd.md" in body
        assert "smoke-test" in body
        assert "citation and compliance review with signed paper trail" in body
        assert "public-proof" in body
        assert "public-proof.json" in body
        assert "public-proof.md" in body
