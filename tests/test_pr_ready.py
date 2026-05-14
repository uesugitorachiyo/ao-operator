from __future__ import annotations

import pr_ready


def test_pr_ready_plan_includes_expected_local_gates():
    commands = pr_ready.command_plan()
    compile_command = commands[0]

    assert compile_command[:3] == [pr_ready.sys.executable, "-m", "py_compile"]
    assert "scripts/agent_os_role_graph.py" in compile_command
    assert "scripts/check_agent_os_accepted_execution_commit_guard.py" in compile_command
    assert "scripts/check_release_readiness.py" not in compile_command
    assert [pr_ready.sys.executable, "scripts/validate_scaffold.py"] in commands
    assert [pr_ready.sys.executable, "scripts/artifact_hygiene.py", "--strict"] in commands
    assert [pr_ready.sys.executable, "scripts/check_evidence_pack_readiness.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_live_evidence_pack_replay.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_evidence_pack_replay_proof_status.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_three_os_pre_public_gate.py", "--json"] not in commands
    assert [pr_ready.sys.executable, "-m", "pytest", "-q"] in commands
    assert [pr_ready.sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] in commands


def test_pr_ready_plan_can_skip_expensive_gates():
    commands = pr_ready.command_plan(include_pytest=False, include_closure=False)

    assert [pr_ready.sys.executable, "-m", "pytest", "-q"] not in commands
    assert [pr_ready.sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] not in commands


def test_pr_ready_pre_public_plan_requires_three_os_gate():
    commands = pr_ready.command_plan(
        include_three_os_pre_public=True,
        include_pytest=False,
        include_closure=False,
    )

    assert [pr_ready.sys.executable, "scripts/check_three_os_pre_public_gate.py", "--json"] in commands
    assert [pr_ready.sys.executable, "-m", "pytest", "-q"] not in commands
    assert [pr_ready.sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] not in commands


def test_pr_ready_ci_plan_keeps_deterministic_gates_without_closure():
    commands = pr_ready.command_plan(ci=True)

    assert [pr_ready.sys.executable, "scripts/validate_scaffold.py"] in commands
    assert [pr_ready.sys.executable, "scripts/artifact_hygiene.py", "--strict"] in commands
    assert [pr_ready.sys.executable, "scripts/redact_strict_public_artifacts.py", "--fail-on-changes", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_status_json_integrity.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_host_key_evidence.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/classify_pentest_report.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_supply_chain_gate.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_evidence_pack_readiness.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_live_evidence_pack_replay.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_evidence_pack_replay_proof_status.py", "--json"] in commands
    assert [pr_ready.sys.executable, "scripts/check_agent_os_approval_lifecycle.py", "--json"] not in commands
    assert [pr_ready.sys.executable, "scripts/check_mac_ubuntu_approval_artifact_parity.py", "--json"] not in commands
    assert [
        pr_ready.sys.executable,
        "scripts/check_public_release_security.py",
        "--strict-public",
        "--fail-on",
        "HIGH",
        "--json",
    ] in commands
    assert [
        pr_ready.sys.executable,
        "scripts/check_public_release_security.py",
        "--strict-public",
        "--fail-on",
        "HIGH",
        "--summary-only",
        "--json",
    ] in commands
    assert [pr_ready.sys.executable, "-m", "pytest", "-q"] in commands
    assert [pr_ready.sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] not in commands


def test_pr_ready_dry_run_returns_plan_without_results():
    result = pr_ready.run(dry_run=True, include_pytest=False, include_closure=False)

    assert result["verdict"] == "PASS"
    assert result["mode"] == "local"
    assert result["commands"]
    assert result["results"] == []
    assert result["errors"] == []


def test_pr_ready_ci_dry_run_reports_ci_mode():
    result = pr_ready.run(dry_run=True, ci=True)

    assert result["verdict"] == "PASS"
    assert result["mode"] == "ci"
    assert [pr_ready.sys.executable, "scripts/verify_closure.py", "--repo", ".", "--with-pytest", "--json"] not in result["commands"]
