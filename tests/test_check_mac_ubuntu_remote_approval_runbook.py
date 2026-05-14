from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_mac_ubuntu_remote_approval_runbook


def test_remote_approval_runbook_requires_transfer_revoke_cleanup_and_no_dispatch(tmp_path):
    runbook = tmp_path / "docs/runbooks/mac-ubuntu-remote-approval-operations.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text(check_mac_ubuntu_remote_approval_runbook.REQUIRED_TEXT_FOR_TESTS, encoding="utf-8")

    payload = check_mac_ubuntu_remote_approval_runbook.check_runbook(root=tmp_path, runbook=runbook)

    assert payload["verdict"] == "PASS"
    assert payload["required_item_count"] == len(check_mac_ubuntu_remote_approval_runbook.REQUIRED_ITEMS)
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_remote_approval_runbook_fails_when_revocation_rollback_is_missing(tmp_path):
    runbook = tmp_path / "docs/runbooks/mac-ubuntu-remote-approval-operations.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text(
        """# Remote approval operations

FACTORY_V3_REMOTE_HOST="${FACTORY_V3_REMOTE_HOST}"
python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_signed_approval_bundle_transfer.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
Do not run AO.
Do not dispatch provider CLIs.
""",
        encoding="utf-8",
    )

    payload = check_mac_ubuntu_remote_approval_runbook.check_runbook(root=tmp_path, runbook=runbook)

    assert payload["verdict"] == "FAIL"
    assert any("check_mac_ubuntu_remote_approval_revocation_rollback.py" in error for error in payload["errors"])


def test_remote_approval_runbook_cli_writes_report(tmp_path, capsys):
    runbook = tmp_path / "docs/runbooks/mac-ubuntu-remote-approval-operations.md"
    output = tmp_path / "run-artifacts/remote-runbook.json"
    runbook.parent.mkdir(parents=True)
    runbook.write_text(check_mac_ubuntu_remote_approval_runbook.REQUIRED_TEXT_FOR_TESTS, encoding="utf-8")

    code = check_mac_ubuntu_remote_approval_runbook.main(
        ["--root", str(tmp_path), "--runbook", str(runbook), "--write-output", str(output), "--json"]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/mac-ubuntu-remote-approval-runbook/v1"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
