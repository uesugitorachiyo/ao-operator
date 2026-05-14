from __future__ import annotations

import json
from pathlib import Path

import agent_os_router


def test_route_brief_classifies_bug_fix_and_requires_reproducer_gate():
    brief = """
Fix the remote transfer cancellation bug.

Failing reproducer evidence:
- pytest tests/test_cancel.py::test_cancel_kills_provider fails before the fix.
"""

    payload = agent_os_router.route_brief(brief, labels=["remote-worker"])

    assert payload["classification"] == "MODERATE"
    assert payload["shape"] == "bug-fix"
    assert payload["routes"] == ["quick", "remote-worker"]
    assert payload["dispatch_authorized"] is True
    assert payload["required_verification"]


def test_route_brief_blocks_live_provider_without_approval():
    brief = "Run the 75-slice live provider proof. Shape: greenfield."

    payload = agent_os_router.route_brief(brief, labels=["live-provider"])

    assert payload["routes"] == ["live-provider"]
    assert payload["dispatch_authorized"] is False
    assert "live-provider route requires explicit approval" in payload["blockers"]
    assert payload["next_safe_command"].startswith("Create explicit approval")


def test_state_snapshot_names_required_project_artifacts():
    route = agent_os_router.route_brief("Build a small docs-only status report.")

    state = agent_os_router.build_state_snapshot(route, lane="agent-os-mission-router-state")

    assert state["schema"] == "ao-operator/agent-os-state/v1"
    assert state["lane"] == "agent-os-mission-router-state"
    assert state["dispatch_authorized"] == route["dispatch_authorized"]
    assert state["project_artifacts"] == [
        "PROJECT.md",
        "REQUIREMENTS.md",
        "ROADMAP.md",
        "STATE.md",
        "DECISIONS.md",
        "LEARNINGS.md",
    ]


def test_cli_writes_state_snapshot_v1_when_pinned(tmp_path, capsys):
    brief = tmp_path / "brief.md"
    state = tmp_path / "STATE.json"
    brief.write_text("Refactor parser internals.\n\nPinning suite: pytest tests/test_parser.py\n", encoding="utf-8")

    code = agent_os_router.main(
        [
            "--brief",
            str(brief),
            "--label",
            "release",
            "--state-version",
            "v1",
            "--write-state",
            str(state),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["schema"] == "ao-operator/agent-os-state/v1"
    assert payload["route"]["shape"] == "refactor"
    assert payload["route"]["routes"] == ["quick", "release"]
    assert json.loads(capsys.readouterr().out)["output"] == str(state)


def test_cli_default_state_version_is_v2(tmp_path, capsys):
    brief = tmp_path / "brief.md"
    readiness = tmp_path / "readiness.json"
    state = tmp_path / "STATE.json"
    brief.write_text("Refactor parser internals.\n\nPinning suite: pytest tests/test_parser.py\n", encoding="utf-8")
    write_readiness(readiness)

    code = agent_os_router.main(
        [
            "--brief",
            str(brief),
            "--label",
            "release",
            "--architecture-readiness",
            str(readiness),
            "--write-state",
            str(state),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["schema"] == "ao-operator/agent-os-state/v2"
    assert payload["architecture_ready"] is True
    assert payload["route"]["shape"] == "refactor"
    assert json.loads(capsys.readouterr().out)["output"] == str(state)


def write_readiness(path: Path, *, ready: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "ao-operator/agent-os-architecture-readiness/v1",
                "verdict": "PASS" if ready else "FAIL",
                "architecture_ready": ready,
                "dispatch_authorized": False,
                "live_providers_run": False,
                "baseline_count": 5,
                "blockers": [] if ready else ["baseline missing"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_state_v2_snapshot_requires_architecture_readiness(tmp_path):
    readiness = tmp_path / "readiness.json"
    write_readiness(readiness)
    route = agent_os_router.route_brief("Build a small docs-only status report.", labels=["release"])

    state = agent_os_router.build_state_snapshot_v2(
        route,
        architecture_readiness=agent_os_router.load_json(readiness),
        architecture_readiness_path=readiness,
        root=tmp_path,
    )

    assert state["schema"] == "ao-operator/agent-os-state/v2"
    assert state["previous_schema"] == "ao-operator/agent-os-state/v1"
    assert state["role_graph_schema"] == "ao-operator/agent-os-role-graph/v1"
    assert state["architecture_ready"] is True
    assert state["dispatch_authorized"] is False
    assert state["live_providers_run"] is False
    assert state["route"]["routes"] == ["quick", "release"]


def test_state_v2_snapshot_fails_closed_without_architecture_readiness(tmp_path):
    readiness = tmp_path / "readiness.json"
    write_readiness(readiness, ready=False)
    route = agent_os_router.route_brief("Build a small docs-only status report.", labels=["release"])

    state = agent_os_router.build_state_snapshot_v2(
        route,
        architecture_readiness=agent_os_router.load_json(readiness),
        architecture_readiness_path=readiness,
        root=tmp_path,
    )

    assert state["schema"] == "ao-operator/agent-os-state/v2"
    assert state["verdict"] == "FAIL"
    assert state["dispatch_authorized"] is False
    assert "architecture readiness must be PASS" in state["blockers"]


def test_cli_writes_state_v2_when_requested(tmp_path, capsys):
    brief = tmp_path / "brief.md"
    readiness = tmp_path / "readiness.json"
    state = tmp_path / "STATE-v2.json"
    brief.write_text("Refactor parser internals.\n\nPinning suite: pytest tests/test_parser.py\n", encoding="utf-8")
    write_readiness(readiness)

    code = agent_os_router.main(
        [
            "--brief",
            str(brief),
            "--label",
            "release",
            "--state-version",
            "v2",
            "--architecture-readiness",
            str(readiness),
            "--write-state",
            str(state),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["schema"] == "ao-operator/agent-os-state/v2"
    assert payload["architecture_ready"] is True
    assert payload["route"]["shape"] == "refactor"
    assert json.loads(capsys.readouterr().out)["output"] == str(state)
