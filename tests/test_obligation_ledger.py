from __future__ import annotations

import json
from pathlib import Path

import factory_run
import obligation_ledger


def test_obligation_ledger_extracts_and_checks_preserved_fragment(tmp_path: Path):
    spec = tmp_path / "SPEC.md"
    spec.write_text(
        "- MUST preserve `net = gross - fees` exactly in the implementation note.\n",
        encoding="utf-8",
    )
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("No equation here.\n", encoding="utf-8")

    ledger = obligation_ledger.extract_ledger(spec, "SPEC.md")
    assert ledger["schema_version"] == "ao2.obligation-ledger.v1"
    assert ledger["summary"]["unverified"] == 1
    assert ledger["obligations"][0]["expected_fragments"] == ["net = gross - fees"]

    missing = obligation_ledger.check_ledger(ledger, target)
    assert missing["verdict"] == "rejected"
    assert missing["summary"]["fail"] == 1

    (target / "README.md").write_text(
        "The implementation note preserves: net = gross - fees\n",
        encoding="utf-8",
    )
    present = obligation_ledger.check_ledger(ledger, target)
    assert present["verdict"] == "accepted"
    assert present["summary"]["pass"] == 1
    assert present["obligations"][0]["evidence"][0]["path"] == "README.md"


def test_exact_fragment_ledger_drops_generic_generated_obligations(tmp_path: Path):
    spec = tmp_path / "SPEC.md"
    spec.write_text(
        "\n".join(
            [
                "- Greenfield scope includes explicit acceptance criteria and scoped write boundaries before dispatch.",
                "- MUST preserve `net = gross - fees` exactly.",
            ]
        ),
        encoding="utf-8",
    )

    ledger = obligation_ledger.exact_fragment_ledger(
        obligation_ledger.extract_ledger(spec, "SPEC.md")
    )

    assert len(ledger["obligations"]) == 1
    assert ledger["obligations"][0]["expected_fragments"] == ["net = gross - fees"]


def test_materialize_writes_obligation_ledger(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(factory_run, "ROOT", tmp_path)
    monkeypatch.setattr(factory_run, "PROFILES_DIR", tmp_path / "profiles")
    intake = factory_run.Intake(
        slug="ledger-demo",
        brief_path=tmp_path / "brief.md",
        brief="MUST preserve `net = gross - fees` exactly.",
        classification="small",
        shape="bug-fix",
        blocked=False,
        blocker="none",
        acceptance=["MUST preserve `net = gross - fees` exactly."],
        scoped_reads=["README.md"],
        scoped_writes=["README.md"],
    )
    tasks = [dict(task) for task in factory_run.BASELINE_TASKS]
    providers = {str(task["id"]): "codex" for task in tasks}

    paths = factory_run.materialize(
        intake,
        providers,
        tmp_path,
        tasks,
        topology=None,
        contract=None,
        mode="materialized",
    )

    ledger_path = paths["obligation_ledger"]
    assert ledger_path == tmp_path / "run-artifacts" / "ledger-demo" / "obligation-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["source_contracts"][0]["path"] == "docs/specs/ledger-demo-spec.md"
    assert ledger["summary"]["unverified"] >= 1
    assert all(item["expected_fragments"] for item in ledger["obligations"])
    assert "Obligation ledger: run-artifacts/ledger-demo/obligation-ledger.json" in paths[
        "status"
    ].read_text(encoding="utf-8")
