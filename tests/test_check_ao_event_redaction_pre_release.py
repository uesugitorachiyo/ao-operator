"""Tests for the AO event-log redaction pre-release gate."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import check_ao_event_redaction_pre_release as gate


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
        transcript_path = (
            tmp_path / case_id / "ao-event-redaction-transcript.json"
        )
        assert transcript_path.exists(), case_id
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        assert "findings" in data
        assert "expected_finding_ids" in data
        assert "matches_expectation" in data
        assert "event_count" in data


def test_clean_events_log_case_passes_with_zero_findings(tmp_path: Path) -> None:
    case = gate.run_clean_events_log_passes(tmp_path)
    assert case["observed_verdict"] == "PASS"
    assert case["findings"] == []
    assert case["matches_expectation"] is True


def test_personal_path_in_stdout_case_fails(tmp_path: Path) -> None:
    case = gate.run_personal_path_in_stdout_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in case["findings"]}
    assert "personal_path" in finding_ids
    assert case["matches_expectation"] is True


def test_anthropic_api_key_pattern_in_stderr_case_fails(tmp_path: Path) -> None:
    case = gate.run_anthropic_api_key_pattern_in_stderr_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in case["findings"]}
    assert "anthropic_api_key" in finding_ids
    assert "anthropic_sk_prefix_token" in finding_ids
    assert case["matches_expectation"] is True


def test_bearer_token_in_artifact_case_fails(tmp_path: Path) -> None:
    case = gate.run_bearer_token_in_artifact_payload_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in case["findings"]}
    assert "bearer_token" in finding_ids
    assert case["matches_expectation"] is True


def test_private_ipv4_in_task_metadata_case_fails(tmp_path: Path) -> None:
    case = gate.run_private_ipv4_in_task_metadata_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in case["findings"]}
    assert "private_network_target" in finding_ids
    assert case["matches_expectation"] is True


def test_base64_round_trip_secret_case_fails(tmp_path: Path) -> None:
    case = gate.run_base64_round_trip_secret_in_payload_rejected(tmp_path)
    assert case["observed_verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in case["findings"]}
    assert "base64::anthropic_api_key" in finding_ids
    assert "base64::anthropic_sk_prefix_token" in finding_ids
    assert case["matches_expectation"] is True


def test_iter_strings_yields_nested_string_values() -> None:
    tree = {
        "a": "alpha",
        "b": {"c": "charlie", "d": [1, "delta", {"e": "echo"}]},
    }
    pairs = list(gate._iter_strings(tree))
    paths = [p for p, _ in pairs]
    values = [v for _, v in pairs]
    assert "/a" in paths
    assert "alpha" in values
    assert "charlie" in values
    assert "delta" in values
    assert "echo" in values


def test_iter_strings_skips_non_string_scalars() -> None:
    tree = {"a": 1, "b": 2.5, "c": True, "d": None, "e": "keep"}
    values = [v for _, v in gate._iter_strings(tree)]
    assert values == ["keep"]


def test_scan_string_for_patterns_detects_high_and_medium() -> None:
    high_hits = gate._scan_string_for_patterns(
        "stderr: ANTHROPIC_API_KEY=sk-ant-placeholder-redaction-target trailing"
    )
    finding_ids = {fid for _, fid in high_hits}
    assert "anthropic_api_key" in finding_ids
    assert "anthropic_sk_prefix_token" in finding_ids
    medium_hits = gate._scan_string_for_patterns(
        "leaked path /home/operator-alpha/out.tar"
    )
    medium_ids = {fid for _, fid in medium_hits}
    assert "personal_path" in medium_ids


def test_scan_string_for_patterns_returns_empty_on_benign_text() -> None:
    assert gate._scan_string_for_patterns("hello world") == []
    assert gate._scan_string_for_patterns("status: succeeded") == []


def test_attempt_base64_decode_returns_text_for_valid_input() -> None:
    encoded = base64.b64encode(b"ANTHROPIC_API_KEY=sk-ant-test-value").decode("ascii")
    decoded = gate._attempt_base64_decode(encoded)
    assert decoded == "ANTHROPIC_API_KEY=sk-ant-test-value"


def test_attempt_base64_decode_returns_none_for_non_base64() -> None:
    assert gate._attempt_base64_decode("hello") is None
    assert gate._attempt_base64_decode("ANTHROPIC_API_KEY=plain") is None
    assert gate._attempt_base64_decode("abc") is None  # too short


def test_parse_events_log_handles_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"id": "ev-1", "kind": "run.started"})
        + "\n"
        + json.dumps({"id": "ev-2", "kind": "run.completed"})
        + "\n",
        encoding="utf-8",
    )
    events = gate.parse_events_log(log)
    assert len(events) == 2
    assert events[0]["id"] == "ev-1"
    assert events[1]["id"] == "ev-2"


def test_parse_events_log_handles_aggregated_json_array(tmp_path: Path) -> None:
    log = tmp_path / "events.json"
    log.write_text(
        json.dumps([{"id": "ev-a"}, {"id": "ev-b"}]),
        encoding="utf-8",
    )
    events = gate.parse_events_log(log)
    assert len(events) == 2


def test_parse_events_log_handles_aggregated_object(tmp_path: Path) -> None:
    log = tmp_path / "events.json"
    log.write_text(
        json.dumps({"events": [{"id": "ev-x"}]}),
        encoding="utf-8",
    )
    events = gate.parse_events_log(log)
    assert len(events) == 1
    assert events[0]["id"] == "ev-x"


def test_parse_events_log_tolerates_malformed_jsonl_line(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"id": "ev-good"}) + "\nnot-json-\n",
        encoding="utf-8",
    )
    events = gate.parse_events_log(log)
    assert len(events) == 2
    assert events[0]["id"] == "ev-good"
    assert events[1]["id"].startswith("<malformed-line-")


def test_is_debug_capture_path_matches_failure_snapshot_segments() -> None:
    assert gate.is_debug_capture_path(
        "run-artifacts/x/failure-snapshots/runs/y/events.jsonl"
    )
    assert gate.is_debug_capture_path(
        "run-artifacts/x/failure_snapshots/runs/y/events.jsonl"
    )
    assert not gate.is_debug_capture_path("run-artifacts/x/runs/y/events.jsonl")
    assert not gate.is_debug_capture_path(
        "run-artifacts/release-candidate/failuresnapshots-readme.md"
    )


def test_iter_event_logs_skips_failure_snapshot_trees(tmp_path: Path) -> None:
    rb = tmp_path / "run-artifacts" / "rb"
    fs = tmp_path / "run-artifacts" / "rb" / "failure-snapshots" / "case-1" / "runs"
    rb.mkdir(parents=True)
    fs.mkdir(parents=True)
    (rb / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (fs / "events.jsonl").write_text("{}\n", encoding="utf-8")
    paths = {gate.relpath(tmp_path, p) for p in gate.iter_event_logs(tmp_path)}
    assert "run-artifacts/rb/events.jsonl" in paths
    assert all("failure-snapshots" not in p for p in paths)


def test_iter_event_logs_skips_self_exempt_paths(tmp_path: Path) -> None:
    (tmp_path / "run-artifacts" / "x").mkdir(parents=True)
    (tmp_path / "run-artifacts" / "x" / "events.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "evaluations" / "y").mkdir(parents=True)
    (tmp_path / "docs" / "evaluations" / "y" / "notes.md").write_text(
        "no events here", encoding="utf-8"
    )
    paths = list(gate.iter_event_logs(tmp_path))
    rel = {gate.relpath(tmp_path, p) for p in paths}
    assert rel == {"run-artifacts/x/events.jsonl"}


def test_repo_scan_report_returns_pass_on_clean_fixture(tmp_path: Path) -> None:
    (tmp_path / "run-artifacts" / "clean").mkdir(parents=True)
    (tmp_path / "run-artifacts" / "clean" / "events.jsonl").write_text(
        json.dumps({"id": "ev-1", "payload": {"stdout": "hello"}}) + "\n",
        encoding="utf-8",
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_repo_scan_report_returns_fail_on_dirty_fixture(tmp_path: Path) -> None:
    (tmp_path / "run-artifacts" / "dirty").mkdir(parents=True)
    leaky_event = {
        "id": "ev-leak",
        "payload": {
            "stdout": "writing to /home/operator-alpha/out.tar via 10.42.7.1"
        },
    }
    (tmp_path / "run-artifacts" / "dirty" / "events.jsonl").write_text(
        json.dumps(leaky_event) + "\n", encoding="utf-8"
    )
    report = gate.repo_scan_report(root=tmp_path)
    assert report["verdict"] == "FAIL"
    finding_ids = {f["finding_id"] for f in report["findings"]}
    assert "personal_path" in finding_ids
    assert "private_network_target" in finding_ids


def test_scan_events_log_records_source_path(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps(
            {
                "id": "ev-leak",
                "payload": {"stderr": "Bearer abcdef0123456789placeholder"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    findings = gate.scan_events_log(log)
    assert findings
    assert all(f["source_path"] == "events.jsonl" for f in findings)


def test_summarize_creates_tmpdir_when_none_provided() -> None:
    payload = gate.summarize()
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
