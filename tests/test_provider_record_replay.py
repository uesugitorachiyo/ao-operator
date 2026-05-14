from __future__ import annotations

import json
import sys
from pathlib import Path

import provider_record_replay as prr


def test_record_from_response_file_and_replay_without_command(tmp_path: Path, capsys):
    prompt = tmp_path / "prompt.md"
    response = tmp_path / "response.txt"
    recording = tmp_path / "recording.jsonl"
    prompt.write_text("Do the task.\n", encoding="utf-8")
    response.write_text("Result: DONE\n", encoding="utf-8")

    record_rc = prr.main(
        [
            "record",
            "--recording",
            str(recording),
            "--provider",
            "codex",
            "--task-id",
            "implementer-slice",
            "--prompt-file",
            str(prompt),
            "--response-file",
            str(response),
            "--param",
            "model=gpt-5.4",
        ]
    )
    replay_rc = prr.main(
        [
            "replay",
            "--recording",
            str(recording),
            "--provider",
            "codex",
            "--task-id",
            "implementer-slice",
            "--prompt-file",
            str(prompt),
            "--param",
            "model=gpt-5.4",
        ]
    )

    output = capsys.readouterr().out
    assert record_rc == replay_rc == 0
    assert "Result: DONE" in output
    record = json.loads(recording.read_text(encoding="utf-8").splitlines()[0])
    assert record["prompt"]["sha256"] == prr.sha256_text("Do the task.\n")
    assert record["params"] == {"model": "gpt-5.4"}
    assert record["tool_summary"]["stdout_lines"] == 1
    assert any("task.completed" in line for line in record["ao_events"])


def test_record_command_captures_stdout_stderr_and_replay_json(tmp_path: Path, capsys):
    prompt = tmp_path / "prompt.md"
    recording = tmp_path / "recording.jsonl"
    prompt.write_text("hello\n", encoding="utf-8")

    rc = prr.main(
        [
            "record",
            "--recording",
            str(recording),
            "--provider",
            "claude",
            "--task-id",
            "reviewer-slice",
            "--prompt-file",
            str(prompt),
            "--",
            sys.executable,
            "-c",
            "import sys; print('{\"type\":\"tool_call\",\"name\":\"read\"}'); print('warn', file=sys.stderr)",
        ]
    )
    capsys.readouterr()
    replay_rc = prr.main(
        [
            "replay",
            "--recording",
            str(recording),
            "--provider",
            "claude",
            "--task-id",
            "reviewer-slice",
            "--prompt-file",
            str(prompt),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == replay_rc == 0
    assert payload["live_providers_run"] is False
    assert payload["response"]["stderr"] == "warn\n"
    assert payload["tool_summary"]["json_event_counts"]["tool:read"] == 1


def test_replay_miss_does_not_invoke_or_fabricate_response(tmp_path: Path, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("hello\n", encoding="utf-8")

    rc = prr.main(
        [
            "replay",
            "--recording",
            str(tmp_path / "missing.jsonl"),
            "--provider",
            "codex",
            "--task-id",
            "planner-intake",
            "--prompt-file",
            str(prompt),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "recording not found" in captured.err


def test_verify_rejects_prompt_hash_drift(tmp_path: Path, capsys):
    recording = tmp_path / "recording.jsonl"
    recording.write_text(
        json.dumps(
            {
                "schema": prr.SCHEMA,
                "key": "k",
                "prompt": {"text": "abc", "sha256": "wrong"},
                "response": {"stdout": "", "stderr": "", "returncode": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rc = prr.main(["verify", "--recording", str(recording)])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["verdict"] == "FAIL"
    assert payload["errors"] == ["record 1: prompt sha256 mismatch"]
