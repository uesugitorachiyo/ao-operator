from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_router_default_state_version


def write_readiness(path: Path, *, ready: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    return path


def write_brief(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Refactor router internals.\n\nPinning suite: pytest tests/test_agent_os_router.py\n",
        encoding="utf-8",
    )
    return path


def stage_router_repo(tmp_path: Path, *, default_state_version: str = "v2") -> Path:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    real_router = (
        Path(__file__).resolve().parents[1] / "scripts" / "agent_os_router.py"
    ).read_text(encoding="utf-8")
    if default_state_version != "v2":
        real_router = real_router.replace(
            'parser.add_argument("--state-version", choices=["v1", "v2"], default="v2")',
            f'parser.add_argument("--state-version", choices=["v1", "v2"], default="{default_state_version}")',
        )
    (scripts_dir / "agent_os_router.py").write_text(real_router, encoding="utf-8")
    return repo


def test_default_state_version_gate_passes_when_default_is_v2(tmp_path):
    brief = write_brief(tmp_path / "brief.md")
    readiness = write_readiness(tmp_path / "readiness.json")

    payload = check_agent_os_router_default_state_version.summarize(
        root=Path(__file__).resolve().parents[1],
        brief=brief,
        readiness=readiness,
        work_dir=tmp_path / "work",
    )

    assert payload["schema"] == "ao-operator/agent-os-router-default-state-version/v1"
    assert payload["verdict"] == "PASS"
    assert payload["argparse_default"] == "v2"
    assert payload["case_count"] == 3
    assert {c["id"] for c in payload["cases"]} == {
        "default_emits_state_v2",
        "explicit_v1_remains_supported",
        "explicit_v2_matches_default",
    }
    for case in payload["cases"]:
        assert case["observed_verdict"] == "PASS"
    assert payload["errors"] == []
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_default_state_version_gate_fails_when_argparse_default_is_v1(tmp_path):
    repo = stage_router_repo(tmp_path, default_state_version="v1")
    brief = write_brief(tmp_path / "brief.md")
    readiness = write_readiness(tmp_path / "readiness.json")

    payload = check_agent_os_router_default_state_version.summarize(
        root=repo,
        brief=brief,
        readiness=readiness,
        work_dir=tmp_path / "work",
    )

    assert payload["argparse_default"] == "v1"
    assert payload["verdict"] == "FAIL"
    assert any("must be 'v2'" in e for e in payload["errors"])


def test_default_state_version_gate_cli_writes_report(tmp_path, capsys):
    brief = write_brief(tmp_path / "brief.md")
    readiness = write_readiness(tmp_path / "readiness.json")
    output = tmp_path / "out.json"

    code = check_agent_os_router_default_state_version.main(
        [
            "--root",
            str(Path(__file__).resolve().parents[1]),
            "--brief",
            str(brief),
            "--architecture-readiness",
            str(readiness),
            "--work-dir",
            str(tmp_path / "work"),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "ao-operator/agent-os-router-default-state-version/v1"
    assert saved["verdict"] == "PASS"
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
