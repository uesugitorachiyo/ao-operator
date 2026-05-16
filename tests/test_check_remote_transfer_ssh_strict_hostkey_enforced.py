"""Tests for the remote-transfer SSH StrictHostKeyChecking enforcement gate."""

from __future__ import annotations

import json
from pathlib import Path

import check_remote_transfer_ssh_strict_hostkey_enforced as gate


def test_gate_pass_with_five_cases_and_two_mutations(tmp_path: Path) -> None:
    payload = gate.evaluate(work_dir=tmp_path)
    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
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
            tmp_path / case_id / "remote-transfer-strict-hostkey-transcript.json"
        )
        assert transcript_path.exists(), case_id
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        assert "fixture_files" in data
        assert "findings" in data


def test_clean_case_passes_with_zero_findings(tmp_path: Path) -> None:
    case = gate.run_clean_repo_passes(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_missing_strict_flag_mutation_fails(tmp_path: Path) -> None:
    case = gate.run_ssh_invocation_missing_strict_flag_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    issues = {f["issue"] for f in case["findings"]}
    assert "missing_StrictHostKeyChecking_yes" in issues
    assert case["matches_expectation"] is True


def test_missing_known_hosts_flag_mutation_fails(tmp_path: Path) -> None:
    case = gate.run_ssh_invocation_missing_known_hosts_flag_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    issues = {f["issue"] for f in case["findings"]}
    assert "missing_UserKnownHostsFile" in issues
    assert case["matches_expectation"] is True


def test_scp_with_both_flags_passes(tmp_path: Path) -> None:
    case = gate.run_scp_invocation_with_both_flags_passes(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_rsync_e_ssh_with_both_flags_passes(tmp_path: Path) -> None:
    case = gate.run_rsync_e_ssh_invocation_with_both_flags_passes(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_is_remote_transfer_path_recognises_all_tokens() -> None:
    for token in gate.REMOTE_TRANSFER_PATH_TOKENS:
        assert gate.is_remote_transfer_path(f"{token}/launch.sh") is True
        assert gate.is_remote_transfer_path(f"nested/{token}/inner.yaml") is True


def test_is_remote_transfer_path_rejects_non_remote_paths() -> None:
    assert gate.is_remote_transfer_path("docs/notes.md") is False
    assert gate.is_remote_transfer_path("src/main.py") is False
    assert gate.is_remote_transfer_path("README.md") is False


def test_self_exempt_files_are_not_flagged() -> None:
    assert gate.is_exempt(
        "scripts/check_remote_transfer_ssh_strict_hostkey_enforced.py"
    )
    assert gate.is_exempt(
        "tests/test_check_remote_transfer_ssh_strict_hostkey_enforced.py"
    )


def test_invocation_pattern_recognises_ssh_scp_sftp_rsync() -> None:
    for binary in ("ssh", "scp", "sftp", "rsync"):
        assert gate.INVOCATION_PATTERN.search(f" {binary} target")
        assert gate.INVOCATION_PATTERN.search(f"/usr/bin/{binary} target")


def test_invocation_pattern_does_not_match_substrings() -> None:
    # "unsshable" or "scpa" or random word boundaries must not match.
    assert gate.INVOCATION_PATTERN.search("unsshable command") is None
    assert gate.INVOCATION_PATTERN.search("sshd_config") is None
    assert gate.INVOCATION_PATTERN.search("scpath") is None


def test_strict_yes_pattern_matches_equals_and_space_forms() -> None:
    assert gate.STRICT_YES_PATTERN.search("StrictHostKeyChecking=yes")
    assert gate.STRICT_YES_PATTERN.search("StrictHostKeyChecking yes")
    assert gate.STRICT_YES_PATTERN.search("stricthostkeychecking=YES")


def test_strict_yes_pattern_does_not_match_no_or_ask_or_accept_new() -> None:
    assert gate.STRICT_YES_PATTERN.search("StrictHostKeyChecking=no") is None
    assert gate.STRICT_YES_PATTERN.search("StrictHostKeyChecking=ask") is None
    assert gate.STRICT_YES_PATTERN.search("StrictHostKeyChecking=accept-new") is None


def test_repo_scan_report_returns_pass_on_clean_fixture(tmp_path: Path) -> None:
    (tmp_path / "remote_transfer").mkdir()
    (tmp_path / "remote_transfer" / "ok.sh").write_text(
        "ssh -o StrictHostKeyChecking=yes "
        "-o UserKnownHostsFile=evidence/known_hosts target true\n",
        encoding="utf-8",
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_repo_scan_report_returns_fail_on_dirty_fixture(tmp_path: Path) -> None:
    (tmp_path / "remote_transfer").mkdir()
    (tmp_path / "remote_transfer" / "bad.sh").write_text(
        "ssh target true\n",  # missing both flags
        encoding="utf-8",
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "FAIL"
    issues = {f["issue"] for f in report["findings"]}
    assert "missing_StrictHostKeyChecking_yes" in issues
    assert "missing_UserKnownHostsFile" in issues


def test_summarize_creates_tmpdir_when_none_provided() -> None:
    payload = gate.summarize()
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 5
