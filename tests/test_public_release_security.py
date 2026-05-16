from __future__ import annotations

import json
from pathlib import Path

import check_public_release_security as security


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def finding_ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["findings"]}


def test_text_scan_flags_public_release_leaks(tmp_path):
    private_target = "Ubuntu host: " + "dev@" + ".".join(["10", "0", "0", "138"])
    path = write(
        tmp_path / "docs" / "release.md",
        "\n".join(
            [
                "Mac path: /Users/example/Documents/ao-operator",
                private_target,
                "<claude-mem-context> stale context",
                "Authorization: Bearer live-token-123456",
            ]
        )
        + "\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "FAIL"
    assert {
        "text.personal_path",
        "text.private_network_target",
        "text.stale_context",
        "text.token_shape",
    }.issubset(finding_ids(payload))


def test_text_scan_allows_negative_api_key_policy_without_secret_value(tmp_path):
    path = write(
        tmp_path / "docs" / "policy.md",
        "Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "PASS"
    assert payload["findings"] == []


def test_ast_scan_flags_shell_true_subprocess(tmp_path):
    path = write(
        tmp_path / "scripts" / "unsafe_shell.py",
        "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "FAIL"
    assert "ast.subprocess_shell_true" in finding_ids(payload)


def test_ast_scan_flags_unpinned_ssh_host_key_policy(tmp_path):
    path = write(
        tmp_path / "scripts" / "ssh_accept_new.py",
        "SSH_OPTS = ['ssh', '-o', 'StrictHostKeyChecking=accept-new', 'host']\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "FAIL"
    assert "ast.ssh_accept_new" in finding_ids(payload)


def test_ast_scan_allows_no_accept_new_gate_self_detection_literals(tmp_path):
    path = write(
        tmp_path / "scripts" / "check_ssh_no_accept_new_for_high_risk_actions.py",
        "MUTATION = 'ssh -o StrictHostKeyChecking=accept-new target.example true'\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "PASS"
    assert "ast.ssh_accept_new" not in finding_ids(payload)


def test_ast_scan_flags_shell_tar_extraction(tmp_path):
    path = write(
        tmp_path / "scripts" / "tar_extract.py",
        "REMOTE_SCRIPT = '''tar -xzf \"$BUNDLE\" -C \"$EXTRACT\"'''\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "FAIL"
    assert "ast.shell_tar_extract" in finding_ids(payload)


def test_json_report_is_machine_readable(tmp_path):
    path = write(tmp_path / "README.md", "AO Operator public release surface.\n")

    payload = security.scan_paths(tmp_path, [path])

    encoded = json.dumps(payload, sort_keys=True)
    assert "ao-operator/public-release-security/v1" in encoded
    assert payload["verdict"] == "PASS"


def test_report_groups_findings_with_cert_aligned_remediation(tmp_path):
    path = write(
        tmp_path / "scripts" / "unsafe.py",
        "\n".join(
            [
                "import subprocess",
                "subprocess.run('echo unsafe', shell=True)",
                "LOCAL='/Users/example/Documents/ao-operator'",
            ]
        )
        + "\n",
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "FAIL"
    assert payload["finding_groups"]["ast.subprocess_shell_true"]["count"] == 1
    assert payload["finding_groups"]["text.personal_path"]["count"] == 1
    assert payload["finding_groups"]["ast.subprocess_shell_true"]["cert_alignment"]
    assert payload["remediation_plan"][0]["finding_id"] == "ast.subprocess_shell_true"
    assert payload["remediation_plan"][0]["next_action"]


def test_summary_only_payload_keeps_groups_without_full_finding_list(tmp_path):
    private_target = "Ubuntu host: " + "dev@" + ".".join(["10", "0", "0", "138"])
    path = write(
        tmp_path / "run-artifacts" / "historical.md",
        "\n".join(
            [
                "Mac path: /Users/example/Documents/ao-operator",
                private_target,
            ]
        )
        + "\n",
    )

    payload = security.scan_paths(tmp_path, [path])
    compact = security.summary_only_payload(payload)

    assert compact["summary"] == payload["summary"]
    assert compact["finding_groups"] == payload["finding_groups"]
    assert compact["remediation_plan"] == payload["remediation_plan"]
    assert compact["findings_sample"] == payload["findings"][:20]
    assert compact["findings_omitted"] == len(payload["findings"])
    assert "findings" not in compact


def test_text_report_accepts_summary_only_payload(tmp_path):
    private_target = "Ubuntu host: " + "dev@" + ".".join(["10", "0", "0", "138"])
    path = write(tmp_path / "run-artifacts" / "historical.md", private_target + "\n")
    payload = security.scan_paths(tmp_path, [path])
    compact = security.summary_only_payload(payload)

    report = security.text_report(compact)

    assert "verdict=FAIL" in report
    assert "findings=1 high=0 medium=1 low=0" in report
    assert "text.private_network_target" in report


def test_scanner_does_not_report_its_own_detection_literals():
    payload = security.scan_paths(security.ROOT, [security.ROOT / "scripts/check_public_release_security.py"])

    assert payload["verdict"] == "PASS"
    assert payload["findings"] == []


def test_scanner_does_not_report_redaction_regex_literals():
    payload = security.scan_paths(security.ROOT, [security.ROOT / "scripts/run_operator_slice.py"])

    assert "text.personal_path" not in finding_ids(payload)


def test_scanner_allows_stale_context_marker_literals_in_python_hygiene_code(tmp_path):
    path = write(
        tmp_path / "scripts" / "hygiene.py",
        'STALE_CONTEXT_MARKERS = ["<claude-mem-context>", "FACTORY_V3_LLM_WIKI_PATH", "path:llm_wiki"]\n',
    )

    payload = security.scan_paths(tmp_path, [path])

    assert payload["verdict"] == "PASS"
