from __future__ import annotations

import json
from pathlib import Path

import check_agent_os_runspec_ao_preflight_compatibility as gate


SYNTHETIC_API_VERSION = '''//! apiVersion module.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ApiVersion {
    /// ao.dev/v1
    #[serde(rename = "ao.dev/v1")]
    AoDevV1,
}
'''

SYNTHETIC_RUN_SPEC = '''//! RunSpec module.
use serde::{Deserialize, Serialize};

pub struct RunSpec {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RunSpecKind {
    /// kind: Run
    Run,
}

pub struct RunSpecBody {}
'''

SYNTHETIC_TASK = '''//! Task module.
use serde::{Deserialize, Serialize};

pub struct Task {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TaskKind {
    /// shell
    Shell,
    /// agent
    Agent,
    /// review
    Review,
    /// test
    Test,
}
'''

SYNTHETIC_RUNSPEC_YAML = '''apiVersion: ao.dev/v1
kind: Run
metadata:
  name: synthetic-runspec
  description: synthetic two-task spec for tests.
spec:
  tasks:
    - id: task-alpha
      kind: agent
      deps: []
      spec:
        provider: codex
        agent: codex-default
        promptFile: ao/prompts/test/01.md
        workspace: .
        policyProfile: ao/policy/local-dev.yaml
        dispatchAuthorized: false
    - id: task-beta
      kind: agent
      deps: ["task-alpha"]
      spec:
        provider: codex
        agent: codex-default
        promptFile: ao/prompts/test/02.md
        workspace: .
        policyProfile: ao/policy/local-dev.yaml
        dispatchAuthorized: false
'''


def seed_ao_source(ao_root: Path) -> Path:
    src = ao_root / "crates" / "ao-core" / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "api_version.rs").write_text(SYNTHETIC_API_VERSION, encoding="utf-8")
    (src / "run_spec.rs").write_text(SYNTHETIC_RUN_SPEC, encoding="utf-8")
    (src / "task.rs").write_text(SYNTHETIC_TASK, encoding="utf-8")
    return src


def seed_runspec(root: Path) -> Path:
    runspec = root / "ao" / "runspecs" / "agent-os-phase-draft.yaml"
    runspec.parent.mkdir(parents=True, exist_ok=True)
    runspec.write_text(SYNTHETIC_RUNSPEC_YAML, encoding="utf-8")
    return runspec


def test_extract_ao_contract_reads_serde_renames(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")

    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")

    assert contract["api_versions"] == ("ao.dev/v1",)
    assert contract["runspec_kinds"] == ("Run",)
    assert contract["task_kinds"] == ("shell", "agent", "review", "test")


def test_baseline_runspec_passes_against_synthetic_contract(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    seed_runspec(tmp_path)

    payload = gate.build_report(
        root=tmp_path,
        runspec=Path("ao/runspecs/agent-os-phase-draft.yaml"),
        ao_runtime=(tmp_path / "ao-runtime"),
    )

    assert payload["schema"] == "ao-operator/agent-os-runspec-ao-preflight-compatibility/v1"
    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 2
    assert payload["task_ids"] == ["task-alpha", "task-beta"]
    assert payload["mutation_case_count"] == 5
    assert payload["baseline_errors"] == []
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False
    for case in payload["mutation_cases"]:
        assert case["observed_verdict"] == "FAIL"


def test_wrong_api_version_is_rejected(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    mutated = gate.mutate_yaml_body(SYNTHETIC_RUNSPEC_YAML, "wrong_api_version_refused")

    result = gate.evaluate(mutated, contract)

    assert result["verdict"] == "FAIL"
    assert any("apiVersion" in err and "ao.dev/v2" in err for err in result["errors"])


def test_wrong_runspec_kind_is_rejected(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    mutated = gate.mutate_yaml_body(SYNTHETIC_RUNSPEC_YAML, "wrong_runspec_kind_refused")

    result = gate.evaluate(mutated, contract)

    assert result["verdict"] == "FAIL"
    assert any("RunSpec kind" in err and "Job" in err for err in result["errors"])


def test_unknown_task_kind_is_rejected(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    mutated = gate.mutate_yaml_body(SYNTHETIC_RUNSPEC_YAML, "unknown_task_kind_refused")

    result = gate.evaluate(mutated, contract)

    assert result["verdict"] == "FAIL"
    assert any("shellscript" in err for err in result["errors"])


def test_unknown_dependency_is_rejected(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    mutated = gate.mutate_yaml_body(SYNTHETIC_RUNSPEC_YAML, "unknown_dependency_refused")

    result = gate.evaluate(mutated, contract)

    assert result["verdict"] == "FAIL"
    assert any("agent-os-ghost-task" in err for err in result["errors"])


def test_dag_cycle_is_detected(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    cycle_yaml = SYNTHETIC_RUNSPEC_YAML.replace(
        '    - id: task-alpha\n      kind: agent\n      deps: []',
        '    - id: task-alpha\n      kind: agent\n      deps: ["task-beta"]',
    )

    result = gate.evaluate(cycle_yaml, contract)

    assert result["verdict"] == "FAIL"
    assert any("cycle" in err.lower() for err in result["errors"])


def test_metadata_name_required(tmp_path):
    seed_ao_source(tmp_path / "ao-runtime")
    contract = gate.extract_ao_contract(tmp_path / "ao-runtime")
    no_meta_yaml = SYNTHETIC_RUNSPEC_YAML.replace(
        "  name: synthetic-runspec\n", "  name: \n"
    )

    result = gate.evaluate(no_meta_yaml, contract)

    assert result["verdict"] == "FAIL"
    assert any("metadata.name" in err for err in result["errors"])


def test_main_writes_artifact(tmp_path, capsys):
    seed_ao_source(tmp_path / "ao-runtime")
    seed_runspec(tmp_path)
    output = tmp_path / "run-artifacts/preflight.json"

    code = gate.main(
        [
            "--root",
            str(tmp_path),
            "--ao-runtime",
            str(tmp_path / "ao-runtime"),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["verdict"] == "PASS"
    assert written["dispatch_authorized"] is False
    assert written["live_providers_run"] is False
    assert written["mutation_case_count"] == 5
    printed = json.loads(capsys.readouterr().out)
    assert printed["mutation_case_count"] == 5
