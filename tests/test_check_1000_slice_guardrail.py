from __future__ import annotations

import json
from pathlib import Path

import check_1000_slice_guardrail
import factory_run


def write_dry_run_evidence(root: Path, slug: str = "remote-transfer-v2-stress", *, task_count: int = 2007) -> None:
    status_dir = root / "run-artifacts" / slug
    status_dir.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "evaluations").mkdir(parents=True, exist_ok=True)
    (status_dir / f"{slug}-status.md").write_text(
        "Mode: dry-run\nAO Run: none\n",
        encoding="utf-8",
    )
    (root / "docs" / "evaluations" / f"{slug}-evaluation.md").write_text(
        "Verdict: ACCEPTED\nAO Run: none\nThis evaluation does not claim a live AO provider run.\n",
        encoding="utf-8",
    )
    lines = ["runspec:\n", "  tasks:\n"]
    lines.extend(f"    - id: task-{idx}\n" for idx in range(task_count))
    (status_dir / f"{slug}.runspec.yaml").write_text("".join(lines), encoding="utf-8")


def test_dry_run_evidence_checks_pass_for_committed_shape(tmp_path):
    write_dry_run_evidence(tmp_path)

    checks, errors = check_1000_slice_guardrail.dry_run_evidence_checks(
        root=tmp_path,
        slug="remote-transfer-v2-stress",
    )

    assert errors == []
    assert {check["status"] for check in checks} == {"PASS"}


def test_dry_run_evidence_checks_fail_when_status_claims_run(tmp_path):
    write_dry_run_evidence(tmp_path)
    status = tmp_path / "run-artifacts/remote-transfer-v2-stress/remote-transfer-v2-stress-status.md"
    status.write_text("Mode: run\nAO Run: r-live\n", encoding="utf-8")

    _, errors = check_1000_slice_guardrail.dry_run_evidence_checks(
        root=tmp_path,
        slug="remote-transfer-v2-stress",
    )

    assert "status.mode_dry_run failed" in errors
    assert "status.ao_run_none failed" in errors


def test_guarded_live_blockers_ignore_large_run_override(monkeypatch):
    monkeypatch.setenv(factory_run.ALLOW_LARGE_LIVE_RUN_ENV, "1")
    tasks = [{"id": f"task-{idx}"} for idx in range(2007)]

    blockers = check_1000_slice_guardrail.guarded_live_blockers(tasks)

    assert len(blockers) == 1
    assert "2007 exceeds" in blockers[0]
    assert factory_run.ALLOW_LARGE_LIVE_RUN_ENV in blockers[0]


def test_main_writes_non_dispatching_guardrail_report(tmp_path, monkeypatch, capsys):
    write_dry_run_evidence(tmp_path)
    topology = tmp_path / "topology.yaml"
    contract = tmp_path / "contract.json"
    topology.write_text("tasks: []\n", encoding="utf-8")
    contract.write_text(json.dumps({"slices": [{} for _ in range(1000)]}), encoding="utf-8")
    monkeypatch.setattr(
        check_1000_slice_guardrail.factory_run,
        "parse_topology",
        lambda path, slug, contract: [{"id": f"task-{idx}"} for idx in range(2007)],
    )
    output = tmp_path / check_1000_slice_guardrail.DEFAULT_OUTPUT

    code = check_1000_slice_guardrail.main(
        [
            "--root",
            str(tmp_path),
            "--topology",
            str(topology),
            "--contract",
            str(contract),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["dry_run_only"] is True
    assert payload["dispatch_authorized"] is False
    assert payload["live_guardrail_blocked"] is True
    assert json.loads(capsys.readouterr().out)["output"] == str(output)
