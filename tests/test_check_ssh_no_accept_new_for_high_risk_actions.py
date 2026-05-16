"""Tests for the SSH no-accept-new for HIGH-risk actions gate."""

from __future__ import annotations

import json
from pathlib import Path

import check_ssh_no_accept_new_for_high_risk_actions as gate


def test_gate_pass_with_four_cases_and_two_mutations(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path)
    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 4
    assert payload["mutation_case_count"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == list(gate.CASE_IDS)
    observed = {case["id"]: case["observed_verdict"] for case in payload["cases"]}
    assert observed == gate.EXPECTED_VERDICTS
    assert payload["errors"] == []


def test_each_case_persists_a_per_case_transcript(tmp_path: Path) -> None:
    gate.evaluate(work_dir=tmp_path)
    for case_id in gate.CASE_IDS:
        transcript_path = (
            tmp_path / case_id / "ssh-no-accept-new-transcript.json"
        )
        assert transcript_path.exists(), case_id
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        assert "fixture_files" in data
        assert "findings" in data


def test_clean_case_passes_with_zero_findings(tmp_path: Path) -> None:
    case = gate.run_clean_repo_has_no_accept_new_in_high_risk_paths(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_remote_dast_script_mutation_fails(tmp_path: Path) -> None:
    case = gate.run_accept_new_in_remote_dast_script_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    assert len(case["findings"]) == 1
    assert case["findings"][0]["path"] == "remote_dast/launch.sh"
    assert "accept-new" in case["findings"][0]["snippet"]
    assert case["matches_expectation"] is True


def test_pentest_yaml_mutation_fails_with_space_form(tmp_path: Path) -> None:
    case = gate.run_accept_new_in_pentest_yaml_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    assert len(case["findings"]) == 1
    assert case["findings"][0]["path"] == "pentest/ssh-options.yaml"
    assert case["matches_expectation"] is True


def test_low_risk_path_negative_control_passes(tmp_path: Path) -> None:
    case = gate.run_accept_new_in_low_risk_path_allowed(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_is_high_risk_path_recognises_all_tokens() -> None:
    for token in gate.HIGH_RISK_PATH_TOKENS:
        assert gate.is_high_risk_path(f"{token}/script.sh") is True
        assert gate.is_high_risk_path(f"some/{token}/nested.yaml") is True


def test_is_high_risk_path_rejects_low_risk_paths() -> None:
    assert gate.is_high_risk_path("docs/notes.md") is False
    assert gate.is_high_risk_path("README.md") is False
    assert gate.is_high_risk_path("src/main.py") is False


def test_self_exempt_files_are_not_flagged() -> None:
    assert gate.is_exempt("scripts/check_ssh_no_accept_new_for_high_risk_actions.py")
    assert gate.is_exempt("tests/test_check_ssh_no_accept_new_for_high_risk_actions.py")


def test_pattern_matches_both_equals_and_space_forms() -> None:
    assert gate.ACCEPT_NEW_PATTERN.search("StrictHostKeyChecking=accept-new")
    assert gate.ACCEPT_NEW_PATTERN.search("StrictHostKeyChecking accept-new")
    assert gate.ACCEPT_NEW_PATTERN.search("stricthostkeychecking=ACCEPT-NEW")  # case insensitive


def test_pattern_does_not_match_yes_or_no() -> None:
    assert gate.ACCEPT_NEW_PATTERN.search("StrictHostKeyChecking=yes") is None
    assert gate.ACCEPT_NEW_PATTERN.search("StrictHostKeyChecking=no") is None
    assert gate.ACCEPT_NEW_PATTERN.search("StrictHostKeyChecking=ask") is None


def test_repo_scan_report_returns_pass_on_clean_fixture(tmp_path: Path) -> None:
    (tmp_path / "remote_dast").mkdir()
    (tmp_path / "remote_dast" / "safe.sh").write_text(
        "ssh -o StrictHostKeyChecking=yes target true\n",
        encoding="utf-8",
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_repo_scan_report_returns_fail_on_dirty_fixture(tmp_path: Path) -> None:
    (tmp_path / "remote_dast").mkdir()
    (tmp_path / "remote_dast" / "danger.sh").write_text(
        "ssh -o StrictHostKeyChecking=accept-new target true\n",
        encoding="utf-8",
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "FAIL"
    assert len(report["findings"]) == 1


def test_summarize_creates_tmpdir_when_none_provided() -> None:
    payload = gate.summarize()
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 4
