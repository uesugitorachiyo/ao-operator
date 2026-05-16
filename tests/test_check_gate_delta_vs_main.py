"""Tests for the gate-delta-vs-main pre-PR check."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import check_gate_delta_vs_main as gate


def test_gate_pass_with_six_cases_and_two_mutations() -> None:
    payload = gate.evaluate()
    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
    assert payload["mutation_case_count"] == 2
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    assert payload["case_ids"] == list(gate.CASE_IDS)
    observed = {case["id"]: case["observed_verdict"] for case in payload["cases"]}
    assert observed == gate.EXPECTED_VERDICTS
    assert payload["errors"] == []


def test_each_case_carries_delta_and_matches_expectation() -> None:
    payload = gate.evaluate()
    for case in payload["cases"]:
        assert "delta" in case
        for kind in ("regressions", "improvements", "pre_existing", "unchanged_passing", "removed"):
            assert kind in case["delta"]
        assert case["matches_expectation"] is True, case["id"]


def test_clean_branch_case_passes() -> None:
    case = gate.run_clean_branch_matches_main_passes()
    assert case["observed_verdict"] == "PASS"
    assert case["delta"]["regressions"] == []
    assert case["matches_expectation"] is True


def test_branch_introduces_new_failure_case_fails() -> None:
    case = gate.run_branch_introduces_new_failure_rejected()
    assert case["observed_verdict"] == "FAIL"
    assert case["delta"]["regressions"] == ["check_b.py"]
    assert case["matches_expectation"] is True


def test_branch_fixes_pre_existing_failure_case_passes() -> None:
    case = gate.run_branch_fixes_pre_existing_failure_passes()
    assert case["observed_verdict"] == "PASS"
    assert case["delta"]["improvements"] == ["check_b.py"]
    assert case["delta"]["regressions"] == []


def test_pre_existing_failure_unchanged_case_passes() -> None:
    case = gate.run_pre_existing_failure_unchanged_is_informational()
    assert case["observed_verdict"] == "PASS"
    assert case["delta"]["pre_existing"] == ["check_b.py"]
    assert case["delta"]["regressions"] == []


def test_gate_added_only_on_branch_failing_case_fails() -> None:
    case = gate.run_gate_added_only_on_branch_failing_is_regression()
    assert case["observed_verdict"] == "FAIL"
    assert case["delta"]["regressions"] == ["check_b_new.py"]


def test_gate_removed_on_branch_case_passes() -> None:
    case = gate.run_gate_removed_on_branch_is_neutral()
    assert case["observed_verdict"] == "PASS"
    assert case["delta"]["removed"] == ["check_b.py"]
    assert case["delta"]["regressions"] == []


def test_compute_delta_classifies_all_four_transitions() -> None:
    base = {"a.py": 0, "b.py": 0, "c.py": 1, "d.py": 1}
    branch = {"a.py": 0, "b.py": 1, "c.py": 0, "d.py": 1}
    delta = gate.compute_delta(base, branch)
    assert delta["regressions"] == ["b.py"]
    assert delta["improvements"] == ["c.py"]
    assert delta["pre_existing"] == ["d.py"]
    assert delta["unchanged_passing"] == ["a.py"]
    assert delta["removed"] == []


def test_compute_delta_new_passing_gate_counted_as_unchanged_passing() -> None:
    base = {"a.py": 0}
    branch = {"a.py": 0, "b_new.py": 0}
    delta = gate.compute_delta(base, branch)
    assert delta["regressions"] == []
    assert delta["unchanged_passing"] == ["a.py", "b_new.py"]


def test_derive_verdict_returns_fail_when_regressions_present() -> None:
    assert gate.derive_verdict({"regressions": ["x"], "improvements": [], "pre_existing": [], "unchanged_passing": [], "removed": []}) == "FAIL"
    assert gate.derive_verdict({"regressions": [], "improvements": ["x"], "pre_existing": ["y"], "unchanged_passing": [], "removed": ["z"]}) == "PASS"


def test_parse_security_md_extracts_python3_scripts_commands() -> None:
    text = textwrap.dedent(
        """
        ## Required Gates

        Before public release, run:

        ```bash
        python3 scripts/check_a.py --json
        python3 scripts/check_b.py --scan-repo --json
        ```

        Some prose after.
        """
    )
    commands = gate.parse_security_md(text)
    assert commands == [
        "python3 scripts/check_a.py --json",
        "python3 scripts/check_b.py --scan-repo --json",
    ]


def test_parse_security_md_picks_first_code_block_with_python3_scripts() -> None:
    text = textwrap.dedent(
        """
        ## Setup

        ```bash
        echo unrelated
        ```

        ## Required Gates

        ```bash
        python3 scripts/check_only.py --json
        ```
        """
    )
    commands = gate.parse_security_md(text)
    assert commands == ["python3 scripts/check_only.py --json"]


def test_parse_security_md_returns_empty_when_no_block_matches() -> None:
    assert gate.parse_security_md("# Just prose, no fence") == []
    assert gate.parse_security_md("```\necho hi\n```") == []


def test_strip_write_output_flag_removes_space_form() -> None:
    cmd = "python3 scripts/check_a.py --write-output run-artifacts/out.json --json"
    assert (
        gate.strip_write_output_flag(cmd)
        == "python3 scripts/check_a.py --json"
    )


def test_strip_write_output_flag_removes_equals_form() -> None:
    cmd = "python3 scripts/check_a.py --write-output=run-artifacts/out.json --json"
    assert (
        gate.strip_write_output_flag(cmd)
        == "python3 scripts/check_a.py --json"
    )


def test_strip_write_output_flag_removes_bare_form() -> None:
    # Bare --write-output (const default), followed by another flag
    cmd = "python3 scripts/check_a.py --write-output --json"
    assert (
        gate.strip_write_output_flag(cmd)
        == "python3 scripts/check_a.py --json"
    )


def test_strip_write_output_flag_leaves_unrelated_commands_intact() -> None:
    cmd = "python3 scripts/check_a.py --scan-repo --json"
    assert gate.strip_write_output_flag(cmd) == cmd


def test_gate_status_helper() -> None:
    assert gate.gate_status(0) == "PASS"
    assert gate.gate_status(1) == "FAIL"
    assert gate.gate_status(124) == "FAIL"


def test_run_gate_subprocess_returns_exit_code(tmp_path: Path) -> None:
    # Tiny script that exits with whatever code we ask for.
    script = tmp_path / "fake_gate.py"
    script.write_text("import sys; sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)\n", encoding="utf-8")
    pass_result = gate.run_gate(f"python3 {script} 0", cwd=tmp_path)
    fail_result = gate.run_gate(f"python3 {script} 7", cwd=tmp_path)
    assert pass_result["exit_code"] == 0
    assert fail_result["exit_code"] == 7
    assert "duration_seconds" in pass_result


def test_run_gate_chain_on_ref_without_worktree_runs_locally(tmp_path: Path) -> None:
    script = tmp_path / "fake_gate.py"
    script.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    commands = [f"python3 {script}"]
    records, exit_map = gate.run_gate_chain_on_ref(tmp_path, commands, base_ref=None)
    assert len(records) == 1
    assert exit_map[commands[0]] == 0


def test_repo_scan_report_against_synthetic_tree(tmp_path: Path) -> None:
    # Build a tiny git repo with a synthetic SECURITY.md and a gate script.
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=False)
    (tmp_path / "scripts").mkdir()
    fake_gate = tmp_path / "scripts" / "fake_gate_pass.py"
    fake_gate.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text(
        textwrap.dedent(
            """
            # Security Policy

            ## Required Gates

            ```bash
            python3 scripts/fake_gate_pass.py
            ```
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "init",
            "--no-gpg-sign",
        ],
        cwd=tmp_path,
        check=True,
    )

    report = gate.repo_scan_report(
        root=tmp_path,
        base_ref="main",
        security_md=tmp_path / "SECURITY.md",
    )
    assert report["verdict"] == "PASS"
    assert report["command_count"] == 1
    assert report["delta"]["regressions"] == []
    assert report["delta"]["unchanged_passing"] == ["python3 scripts/fake_gate_pass.py"]


def test_repo_scan_report_fails_when_no_gates_parsed(tmp_path: Path) -> None:
    (tmp_path / "SECURITY.md").write_text("# nothing here\n", encoding="utf-8")
    report = gate.repo_scan_report(
        root=tmp_path,
        base_ref="HEAD",
        security_md=tmp_path / "SECURITY.md",
    )
    assert report["verdict"] == "FAIL"
    assert any("No gate commands" in err for err in report["errors"])


def test_summarize_returns_evaluate_output() -> None:
    payload = gate.summarize()
    assert payload["verdict"] == "PASS"
    assert payload["case_count"] == 6
