from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import factory_run


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_factory(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/factory_run.py", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_specify_alias_rewrites_to_greenfield_dry_run():
    rewritten = factory_run._handle_spec_kit_alias(
        ["factory_run.py", "specify", "examples/starters/greenfield-example.md"]
    )
    assert rewritten == [
        "factory_run.py",
        "--brief",
        "examples/starters/greenfield-example.md",
        "--profile",
        "greenfield",
        "--dry-run",
        "--slug",
        "greenfield-example",
    ]


def test_tasks_alias_lists_profile_tasks_json():
    proc = run_factory("tasks", "demo-slug", "--profile", "bug-fix", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["alias"] == "tasks"
    assert [task["id"] for task in payload["tasks"]] == [
        "intake",
        "planner",
        "implementer",
        "reviewer",
        "evaluator-closer",
    ]


def test_tasks_alias_reports_standalone_handoff_for_financial_services():
    proc = run_factory(
        "tasks",
        "financial-services-earnings-note",
        "--profile",
        "financial-services:earnings-note",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    handoff = payload["standalone_handoff"]
    assert handoff["repo"] == "../financial-services-profile"
    assert handoff["command"] == "fsp run earnings-note --engine ao"
    assert handoff["status"] == "run-artifacts/financial-services-profile-v0.3-standalone.md"


def test_plan_alias_reports_planner_role():
    proc = run_factory("plan", "demo-slug", "--profile", "greenfield", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["alias"] == "plan"
    assert payload["role"] == "planner"
    assert payload["writes"] == ["docs/plans/<slug>-plan.md"]


def test_analyze_alias_reports_gate_route():
    proc = run_factory("analyze", "demo-slug", "--profile", "smoke-test", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["alias"] == "analyze"
    assert payload["gates"] == {"gate_b": True, "gate_r": True}

