"""F-B: tests for the AO approval responder CLI.

Unit tests cover the AllowRule parser, ticket matcher, and decision logic.
The end-to-end integration test queues real tickets via `ao-policy evaluate`
into a temp SQLite DB, runs the responder, and asserts the right
approve/deny verbs landed in the queue. Auto-skips when the ao-policy
binary is not present (e.g. CI without ao-runtime built).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RESPONDER = REPO_ROOT / "scripts" / "ao_approval_responder.py"
SECURE_AGENT_POLICY_PROFILE = REPO_ROOT / "run-artifacts" / "factoryv3-smoke-fa-secagent" / "policy.yaml"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import ao_approval_responder as ar  # noqa: E402


def _ao_policy_binary() -> Path | None:
    # FU2 cross-platform: honor AO_POLICY_BINARY env var first so Mac /
    # Windows hosts (with different absolute ao-runtime checkout paths)
    # don't need a symlink to /opt/ai-workstation/projects/ao-runtime
    # to satisfy these tests. Mirrors the F2 FACTORY_V3_PYTHON pattern.
    override = os.environ.get("AO_POLICY_BINARY")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
        # Explicit override that points at a missing file is operator
        # error, not a silent skip — but since these tests already
        # skip-when-None, returning None here keeps the behavior
        # consistent (skip with the env var unhelpfully set).
        return None
    candidate = Path("/opt/ai-workstation/projects/ao-runtime/target/debug/ao-policy")
    if candidate.is_file():
        return candidate
    found = shutil.which("ao-policy")
    return Path(found) if found else None


def test_allow_rule_parse_with_prefix():
    rule = ar.AllowRule.parse("shell.run:mv")
    assert rule.action_type == "shell.run"
    assert rule.command_prefix == "mv"


def test_allow_rule_parse_without_prefix():
    rule = ar.AllowRule.parse("agent.run.codex")
    assert rule.action_type == "agent.run.codex"
    assert rule.command_prefix is None


def test_allow_rule_parse_strips_whitespace():
    rule = ar.AllowRule.parse("  shell.run : mv  ")
    assert rule.action_type == "shell.run"
    assert rule.command_prefix == "mv"


def test_matches_action_type_only_when_no_prefix_specified():
    rule = ar.AllowRule("agent.run.codex", None)
    assert ar._matches(rule, {"action_type": "agent.run.codex", "action_command": None})
    assert not ar._matches(rule, {"action_type": "shell.run", "action_command": None})


def test_matches_command_prefix_exact_or_with_space():
    rule = ar.AllowRule("shell.run", "mv")
    assert ar._matches(rule, {"action_type": "shell.run", "action_command": "mv"})
    assert ar._matches(rule, {"action_type": "shell.run", "action_command": "mv /tmp/a /tmp/b"})
    # Substring of a longer command name must NOT match.
    assert not ar._matches(rule, {"action_type": "shell.run", "action_command": "mvn install"})
    assert not ar._matches(rule, {"action_type": "shell.run", "action_command": "rm /tmp/a"})


def test_decide_approve_when_rule_matches():
    rule = ar.AllowRule("shell.run", "mv")
    verb, reason = ar._decide(
        {"action_type": "shell.run", "action_command": "mv /tmp/a /tmp/b"},
        [rule],
    )
    assert verb == "approve"
    assert "shell.run:mv" in reason


def test_decide_deny_when_no_rule_matches():
    rule = ar.AllowRule("shell.run", "mv")
    verb, reason = ar._decide(
        {"action_type": "shell.run", "action_command": "rm /tmp/a"},
        [rule],
    )
    assert verb == "deny"
    assert "default-deny" in reason


def test_decide_deny_when_allows_empty():
    verb, _ = ar._decide(
        {"action_type": "shell.run", "action_command": "ls"},
        [],
    )
    assert verb == "deny"


@pytest.mark.skipif(_ao_policy_binary() is None, reason="ao-policy binary not present")
@pytest.mark.skipif(not SECURE_AGENT_POLICY_PROFILE.is_file(),
                    reason="rendered secure-agent policy.yaml not present (run dry-run smoke first)")
def test_responder_drains_queue_with_one_approve_and_one_deny():
    """End-to-end: queue 2 tickets via real ao-policy evaluate, run responder
    with shell.run:mv allowed, confirm one approve + one deny, queue empty."""
    binary = _ao_policy_binary()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "approvals.db"

        def queue(action_type: str, command: str) -> None:
            subprocess.run(
                [str(binary), "--db", str(db), "--profile", str(SECURE_AGENT_POLICY_PROFILE),
                 "evaluate", "--task-id", "t", "--action-type", action_type,
                 "--command", command, "--source-trust", "local-user", "--json"],
                check=True, capture_output=True,
            )

        queue("shell.run", "mv /tmp/a /tmp/b")
        queue("secrets.read", "OTHER_SECRET")

        pending = subprocess.run(
            [str(binary), "--db", str(db), "pending", "--json"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert len(json.loads(pending)) == 2

        proc = subprocess.run(
            [sys.executable, str(RESPONDER),
             "--db", str(db), "--ao-policy", str(binary),
             "--allow", "shell.run:mv",
             "--max-idle-polls", "2", "--poll-interval", "0.1", "--json"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr

        decisions = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        summary = decisions[-1]
        events = decisions[:-1]
        assert summary.get("summary") is True
        assert summary["approved"] == 1
        assert summary["denied"] == 1
        assert summary["tickets_seen"] == 2

        approved = [e for e in events if e["decision"] == "approve"]
        denied = [e for e in events if e["decision"] == "deny"]
        assert len(approved) == 1 and approved[0]["action_command"] == "mv /tmp/a /tmp/b"
        assert len(denied) == 1 and denied[0]["action_command"] == "OTHER_SECRET"

        pending_after = subprocess.run(
            [str(binary), "--db", str(db), "pending", "--json"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert len(json.loads(pending_after)) == 0


@pytest.mark.skipif(_ao_policy_binary() is None, reason="ao-policy binary not present")
def test_responder_idle_quota_reached_when_queue_starts_empty():
    """An empty queue across max_idle_polls iterations should exit cleanly
    with zero approved / zero denied."""
    binary = _ao_policy_binary()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "approvals.db"
        subprocess.run(
            [str(binary), "--db", str(db), "pending", "--json"],
            capture_output=True, text=True, check=True,
        )
        proc = subprocess.run(
            [sys.executable, str(RESPONDER),
             "--db", str(db), "--ao-policy", str(binary),
             "--max-idle-polls", "2", "--poll-interval", "0.05", "--json"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        summary_line = proc.stdout.strip().splitlines()[-1]
        summary = json.loads(summary_line)
        assert summary["approved"] == 0
        assert summary["denied"] == 0
        assert summary["tickets_seen"] == 0
        assert summary["polls"] >= 2


def _ao_policy_supports_from_stdin(binary: Path | None) -> bool:
    """Probe whether the local ao-policy binary carries the F-D
    --from-stdin flag (lane head 71de80b in ao-runtime). Skip the
    integration test if the binary predates F-D."""
    if binary is None:
        return False
    try:
        out = subprocess.run(
            [str(binary), "evaluate", "--help"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "--from-stdin" in (out.stdout or "")


@pytest.mark.skipif(_ao_policy_binary() is None, reason="ao-policy binary not present")
@pytest.mark.skipif(
    not _ao_policy_supports_from_stdin(_ao_policy_binary()),
    reason="local ao-policy binary predates F-D (--from-stdin). "
           "Rebuild against ao-runtime v0.1.1 (tag d0e6713) or later.",
)
@pytest.mark.skipif(not SECURE_AGENT_POLICY_PROFILE.is_file(),
                    reason="rendered secure-agent policy.yaml not present (run dry-run smoke first)")
def test_full_v3_chain_claude_stdin_hook_files_ticket_responder_approves():
    """V3 closure path end-to-end: pipe a synthetic Claude PreToolUse JSON
    payload for `mv` through `ao-policy evaluate --from-stdin claude` (F-D),
    confirm a ticket lands in the queue with the expected `task_id` and
    `action_command` synthesised from the payload, then drive the F-B
    responder with `--allow shell.run:mv` and confirm a single approve
    fires + queue drains.

    This is the integrator-side proof that the V3 chain works once F-D
    merges into ao-runtime/main: a real Claude Code session would send the
    same shape of PreToolUse JSON through its hook command, ao-policy
    would queue the ticket, and `ao_approval_responder.py` would fire
    deterministically — yielding the >=1 policy-gated approval cycle V3
    requires."""
    binary = _ao_policy_binary()
    payload = json.dumps({
        "session_id": "sess-v3-end-to-end-1",
        "transcript_path": "/tmp/transcript",
        "cwd": "/repo",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "mv /tmp/x /tmp/y",
            "description": "rename temp file",
        },
    })
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "approvals.db"

        # Step 1: Claude PreToolUse JSON -> ao-policy (F-D path).
        evaluate = subprocess.run(
            [str(binary), "--json", "--db", str(db),
             "--profile", str(SECURE_AGENT_POLICY_PROFILE),
             "evaluate", "--from-stdin", "claude", "--action-type", "shell.run"],
            input=payload, capture_output=True, text=True, check=True, timeout=10,
        )
        outcome = json.loads(evaluate.stdout)
        assert outcome["outcome"] == "pending", outcome
        assert outcome["decision"]["taskId"] == "sess-v3-end-to-end-1"
        assert outcome["ticket"]["action_command"] == "mv /tmp/x /tmp/y"
        assert outcome["ticket"]["action_type"] == "shell.run"

        # Step 2: confirm responder approves shell.run:mv and drains.
        proc = subprocess.run(
            [sys.executable, str(RESPONDER),
             "--db", str(db), "--ao-policy", str(binary),
             "--allow", "shell.run:mv",
             "--max-idle-polls", "2", "--poll-interval", "0.1", "--json"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr

        decisions = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        summary = decisions[-1]
        events = decisions[:-1]
        assert summary.get("summary") is True
        assert summary["approved"] == 1, decisions
        assert summary["denied"] == 0, decisions
        assert summary["tickets_seen"] == 1, decisions
        assert len(events) == 1
        assert events[0]["decision"] == "approve"
        assert events[0]["action_command"] == "mv /tmp/x /tmp/y"

        # Step 3: queue is empty; the V3 approval cycle is closed.
        pending_after = json.loads(subprocess.run(
            [str(binary), "--db", str(db), "pending", "--json"],
            capture_output=True, text=True, check=True,
        ).stdout)
        assert pending_after == []


def test_ao_policy_binary_honors_env_override(monkeypatch, tmp_path):
    """FU2: AO_POLICY_BINARY env var should be the first discovery
    mechanism so Mac/Windows hosts don't need a symlink to the
    Linux-checkout path."""
    fake = tmp_path / "ao-policy-fake"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")  # contents don't matter; only is_file()
    monkeypatch.setenv("AO_POLICY_BINARY", str(fake))
    assert _ao_policy_binary() == fake


def test_ao_policy_binary_env_pointing_at_missing_file_returns_none(monkeypatch, tmp_path):
    """If the operator sets AO_POLICY_BINARY but the path doesn't exist,
    return None rather than silently falling through to the default
    path — that way the skipif guards behave as if the env wasn't set
    AND the operator gets the test-skip message reminding them to fix
    their override."""
    monkeypatch.setenv("AO_POLICY_BINARY", str(tmp_path / "does-not-exist"))
    assert _ao_policy_binary() is None


def test_ao_policy_binary_falls_back_to_shutil_which_when_env_unset(monkeypatch):
    """When AO_POLICY_BINARY is unset and the hardcoded Linux path
    doesn't exist, the helper still finds an ao-policy on PATH if
    one is there. We simulate this by stubbing shutil.which and
    pretending the Linux fallback path is missing."""
    monkeypatch.delenv("AO_POLICY_BINARY", raising=False)
    fake_on_path = "/some/nonexistent/path/ao-policy"
    monkeypatch.setattr("shutil.which",
                        lambda name: fake_on_path if name == "ao-policy" else None)
    # Stub is_file to False for the Linux candidate so we exercise the
    # shutil.which fallback branch.
    real_is_file = Path.is_file

    def stub_is_file(self):
        if str(self) == "/opt/ai-workstation/projects/ao-runtime/target/debug/ao-policy":
            return False
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", stub_is_file)
    result = _ao_policy_binary()
    assert result == Path(fake_on_path)


def test_responder_missing_binary_returns_exit_1(tmp_path: Path):
    """Sanity: pointing --ao-policy at a non-existent file must fail fast
    with exit code 1, not hang or crash deeper in the polling loop."""
    proc = subprocess.run(
        [sys.executable, str(RESPONDER),
         "--db", str(tmp_path / "x.db"),
         "--ao-policy", str(tmp_path / "no-such-binary"),
         "--max-idle-polls", "1", "--poll-interval", "0.05"],
        capture_output=True, text=True, check=False, timeout=5,
    )
    assert proc.returncode == 1
    assert "ao-policy binary not found" in proc.stderr
