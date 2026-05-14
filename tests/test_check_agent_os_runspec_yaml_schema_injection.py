from __future__ import annotations

import json

import check_agent_os_runspec_yaml_schema_injection as gate


CANONICAL_YAML = (
    "apiVersion: ao.dev/v1\n"
    "kind: Run\n"
    "metadata:\n"
    "  name: agent-os-phase-draft\n"
    "  description: Non-dispatching draft.\n"
    "spec:\n"
    "  tasks:\n"
    "    - id: agent-os-planner\n"
    "      kind: agent\n"
    "      deps: []\n"
    "      spec:\n"
    "        provider: codex\n"
    "        agent: codex-default\n"
    "        promptFile: ao/prompts/agent-os-phase/01-planner.md\n"
    "        workspace: .\n"
    "        policyProfile: ao/policy/local-dev.yaml\n"
    "        dispatchAuthorized: false\n"
    "    - id: agent-os-implementer\n"
    "      kind: agent\n"
    "      deps: [\"agent-os-planner\"]\n"
    "      spec:\n"
    "        provider: codex\n"
    "        agent: codex-default\n"
    "        promptFile: ao/prompts/agent-os-phase/04-implementer.md\n"
    "        workspace: .\n"
    "        policyProfile: ao/policy/local-dev.yaml\n"
    "        dispatchAuthorized: false\n"
)


def test_baseline_canonical_yaml_passes():
    evaluation = gate.evaluate_runspec_yaml(CANONICAL_YAML)

    assert evaluation["verdict"] == "PASS", evaluation["errors"]
    assert evaluation["task_count"] == 2
    assert evaluation["task_ids"] == ["agent-os-planner", "agent-os-implementer"]
    assert evaluation["errors"] == []


def test_malformed_yaml_is_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "malformed_yaml_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert evaluation["parse_error_count"] >= 1
    assert any("unbalanced" in e for e in evaluation["errors"])


def test_duplicate_task_ids_are_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "duplicate_task_ids_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert any("duplicate task id" in e for e in evaluation["errors"])


def test_missing_spec_block_is_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "missing_spec_block_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert any("missing" in e and "spec" in e for e in evaluation["errors"])


def test_bad_deps_type_is_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "bad_deps_type_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert any("deps must be a list" in e for e in evaluation["errors"])


def test_unknown_task_field_is_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "unknown_task_field_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert any("unknown key" in e and "mysteryField" in e for e in evaluation["errors"])


def test_unsafe_dispatch_authorized_is_refused():
    mutated = gate.mutate_yaml_body(CANONICAL_YAML, "unsafe_dispatch_authorized_refused")
    evaluation = gate.evaluate_runspec_yaml(mutated)

    assert evaluation["verdict"] == "FAIL"
    assert any("dispatchAuthorized must be false" in e for e in evaluation["errors"])


def test_tab_character_is_refused():
    body = CANONICAL_YAML.replace("  description:", "\tdescription:")
    evaluation = gate.evaluate_runspec_yaml(body)

    assert evaluation["verdict"] == "FAIL"
    assert any("tab" in e for e in evaluation["errors"])


def test_unknown_top_level_key_is_refused():
    body = CANONICAL_YAML + "extras:\n  surprise: true\n"
    evaluation = gate.evaluate_runspec_yaml(body)

    assert evaluation["verdict"] == "FAIL"
    assert any("unknown key" in e and "extras" in e for e in evaluation["errors"])


def test_build_report_against_canonical_yaml_passes(tmp_path):
    runspec_path = tmp_path / "runspec.yaml"
    runspec_path.write_text(CANONICAL_YAML, encoding="utf-8")

    payload = gate.build_report(root=tmp_path, runspec=runspec_path)

    assert payload["schema"] == gate.SCHEMA
    assert payload["verdict"] == "PASS"
    assert payload["task_count"] == 2
    assert payload["mutation_case_count"] == 6
    assert payload["mutation_case_ids"] == list(gate.MUTATION_CASE_IDS)
    assert all(case["observed_verdict"] == "FAIL" for case in payload["mutation_cases"])
    assert payload["dispatch_authorized"] is False
    assert payload["live_providers_run"] is False


def test_build_report_fails_when_a_mutation_does_not_refuse(monkeypatch, tmp_path):
    runspec_path = tmp_path / "runspec.yaml"
    runspec_path.write_text(CANONICAL_YAML, encoding="utf-8")

    def fake_mutate(body: str, case_id: str) -> str:
        return body

    monkeypatch.setattr(gate, "mutate_yaml_body", fake_mutate)

    payload = gate.build_report(root=tmp_path, runspec=runspec_path)

    assert payload["verdict"] == "FAIL"
    assert any("must fail closed" in e for e in payload["errors"])


def test_main_writes_artifact_with_dispatch_flag_false(tmp_path):
    runspec_path = tmp_path / "runspec.yaml"
    runspec_path.write_text(CANONICAL_YAML, encoding="utf-8")
    output = tmp_path / "schema-injection.json"

    code = gate.main(
        [
            "--root",
            str(tmp_path),
            "--runspec",
            str(runspec_path),
            "--write-output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["verdict"] == "PASS"
    assert saved["dispatch_authorized"] is False
    assert saved["live_providers_run"] is False
    assert saved["mutation_case_count"] == 6
