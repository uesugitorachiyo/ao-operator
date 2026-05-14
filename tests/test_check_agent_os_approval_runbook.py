from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_agent_os_approval_runbook


def test_runbook_checker_requires_materialization_cleanup_and_no_dispatch(tmp_path):
    runbook = tmp_path / "docs/runbooks/agent-os-approval-materialization.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text(
        """# Agent OS Approval Materialization Runbook

## Commands

python3 scripts/materialize_agent_os_approval.py --write-approval-file --approved --operator OPERATOR --accepted-risk RISK
python3 scripts/validate_agent_os_runspec_execution_approval.py --json
python3 scripts/check_agent_os_approval_lifecycle.py --json
python3 scripts/run_agent_os_runspec_execution.py --json
python3 scripts/cleanup_agent_os_approval.py --apply --force --json

## Negative Constraints

- Do not run AO from this runbook.
- Do not dispatch provider CLIs from this runbook.
- Do not commit approval files.
- Keep approval files time-boxed.
""",
        encoding="utf-8",
    )

    payload = check_agent_os_approval_runbook.check_runbook(root=tmp_path, runbook=runbook)

    assert payload["verdict"] == "PASS"
    assert payload["required_item_count"] == 9
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_runbook_checker_fails_when_cleanup_command_missing(tmp_path):
    runbook = tmp_path / "docs/runbooks/agent-os-approval-materialization.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("materialize_agent_os_approval.py --write-approval-file\nDo not run AO\n", encoding="utf-8")

    payload = check_agent_os_approval_runbook.check_runbook(root=tmp_path, runbook=runbook)

    assert payload["verdict"] == "FAIL"
    assert any("cleanup_agent_os_approval.py" in error for error in payload["errors"])


def test_runbook_checker_cli_writes_report(tmp_path, capsys):
    runbook = tmp_path / "docs/runbooks/agent-os-approval-materialization.md"
    output = tmp_path / "run-artifacts/runbook.json"
    runbook.parent.mkdir(parents=True)
    runbook.write_text(check_agent_os_approval_runbook.REQUIRED_TEXT_FOR_TESTS, encoding="utf-8")

    code = check_agent_os_approval_runbook.main(
        ["--root", str(tmp_path), "--runbook", str(runbook), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-approval-runbook/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
