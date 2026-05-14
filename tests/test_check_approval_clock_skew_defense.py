"""Tests for the approval clock-skew defense gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_approval_clock_skew_defense as gate  # noqa: E402


def test_gate_pass_with_six_cases_and_five_mutations(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path)
    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["mutation_case_count"] == 5
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == list(gate.CASE_IDS)
    observed = {case["id"]: case["observed_verdict"] for case in payload["cases"]}
    assert observed == gate.EXPECTED_VERDICTS
    assert payload["errors"] == []


def test_each_case_persists_a_per_case_transcript(tmp_path: Path) -> None:
    gate.evaluate(work_dir=tmp_path)
    for case_id in gate.CASE_IDS:
        transcript_path = tmp_path / case_id / "approval-clock-skew-defense-transcript.json"
        assert transcript_path.exists(), case_id
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        edges = data["edges"]
        assert isinstance(edges, list) and edges, case_id
        for edge in edges:
            assert edge["op"] == "register"
            assert "approval_class" in edge
            assert "approval_id" in edge


def test_clean_case_has_no_observed_errors(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path)
    clean_case = next(
        case
        for case in payload["cases"]
        if case["id"] == "clean_no_clock_skew_or_replay_or_stale_freshness_edges"
    )
    assert clean_case["observed_verdict"] == "PASS"
    assert clean_case["observed_errors"] == []


def test_each_mutation_case_records_observed_errors(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path)
    mutation_ids = {
        case_id
        for case_id, expected in gate.EXPECTED_VERDICTS.items()
        if expected == "FAIL"
    }
    for case in payload["cases"]:
        if case["id"] in mutation_ids:
            assert case["observed_verdict"] == "FAIL", case["id"]
            assert case["observed_errors"], case["id"]


def test_summarize_writes_via_temporary_work_dir() -> None:
    payload = gate.summarize()
    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"


def test_write_output_persists_payload(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path / "work")
    out = tmp_path / "approval-clock-skew-defense.json"
    gate.write_output(out, payload)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema"] == gate.SCHEMA
    assert written["verdict"] == "PASS"
