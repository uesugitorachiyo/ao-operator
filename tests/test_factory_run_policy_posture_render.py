"""F-A: tests for `_render_policy_yaml` and the materialize() integration that
wires a profile's policy_posture block into a per-slug AO policy YAML.

Coverage:

- Renderer shape: rule order, decision tokens, all three shell prefix lists,
  network egress deny, secrets forbidden_env per-key denies, secrets ask
  catch-all, agent.run allow rules.
- Renderer output parses as valid YAML.
- `_profile_has_policy_posture` correctly detects presence/absence.
- materialize() integration is covered by the e2e dry-run test
  (tests/e2e/test_profile_secure_agent_e2e.py) which confirms the
  RunSpec `policyProfile:` field points at the slug-local YAML; the
  in-process tests here keep narrow scope.
"""
from __future__ import annotations

import pytest
import yaml

import factory_run


@pytest.fixture(autouse=True)
def _reset_active_profile():
    factory_run._set_active_profile(None)
    yield
    factory_run._set_active_profile(None)


def _decisions_by_prefix(rules: list[dict], decision: str) -> list[str]:
    out = []
    for rule in rules:
        if rule.get("decision") != decision:
            continue
        match = rule.get("match", {})
        if match.get("action.type") != "shell.run":
            continue
        prefix = match.get("action.commandPrefix")
        if prefix:
            out.append(prefix)
    return out


def _profile_with_policy_posture() -> dict:
    return factory_run._validate_profile(
        "policy",
        {
            "profile": "policy",
            "schema": factory_run.PROFILE_SCHEMA_ID,
            "version": factory_run.PROFILE_VERSION,
            "description": "synthetic policy posture profile",
            "common_instructions": [],
            "policy_posture": {
                "shell": {
                    "deny_prefixes": ["docker", "kubectl", "aws"],
                    "require_approval_for": ["rm", "mv", "curl", "wget", "ssh", "sudo"],
                    "allow_prefixes": ["git", "python3", "pytest", "ls", "cat", "grep", "rg"],
                },
                "network": {"egress_default": "deny", "allow_hosts": []},
                "secrets": {
                    "forbidden_env": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
                    "require_approval_for_read": True,
                },
            },
            "roles": [
                {
                    "id": "intake",
                    "role": "Intake",
                    "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                    "deps": [],
                    "reads": ["task brief"],
                    "writes": ["run-artifacts/<slug>/roles/intake.md"],
                    "skills": [],
                    "instructions": [],
                }
            ],
        },
    )


def test_render_policy_yaml_profile_parses_as_yaml():
    profile = _profile_with_policy_posture()
    body = factory_run._render_policy_yaml(profile, "demo-slug")
    doc = yaml.safe_load(body)
    assert doc["id"] == "ao-operator-policy-demo-slug"
    assert doc["default_decision"] == "allow"
    assert isinstance(doc["rules"], list)
    assert len(doc["rules"]) >= 20  # 2 universal + 16 prefixes + 1 net + 2 secret + 1 ask + 2 agent.run = 24


def test_render_policy_yaml_emits_all_three_shell_prefix_lists():
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    assert _decisions_by_prefix(doc["rules"], "deny") == ["docker", "kubectl", "aws"]
    assert _decisions_by_prefix(doc["rules"], "ask") == [
        "rm", "mv", "curl", "wget", "ssh", "sudo",
    ]
    assert _decisions_by_prefix(doc["rules"], "allow") == [
        "git", "python3", "pytest", "ls", "cat", "grep", "rg",
    ]


def test_render_policy_yaml_orders_deny_before_ask_before_allow():
    """First-match-wins: profile shell.deny_prefixes must precede
    require_approval_for which must precede allow_prefixes, otherwise
    overlapping prefixes (none today, but defensive) would resolve wrong."""
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    rules = doc["rules"]

    def first_index_with(decision: str) -> int:
        for i, rule in enumerate(rules):
            m = rule.get("match", {})
            if rule.get("decision") == decision and m.get("action.type") == "shell.run" and "action.commandPrefix" in m:
                return i
        return -1

    assert -1 < first_index_with("deny") < first_index_with("ask") < first_index_with("allow")


def test_render_policy_yaml_emits_network_egress_deny_when_allow_hosts_empty():
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    egress = [r for r in doc["rules"] if r["match"].get("action.type") == "network.egress"]
    assert len(egress) == 1
    assert egress[0]["decision"] == "deny"


def test_render_policy_yaml_emits_per_key_secret_denies_then_ask_catchall():
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    secret_reads = [r for r in doc["rules"] if r["match"].get("action.type") == "secrets.read"]
    # Two per-key denies (OPENAI_API_KEY, ANTHROPIC_API_KEY) + one ask catch-all.
    assert len(secret_reads) == 3
    assert [r["decision"] for r in secret_reads] == ["deny", "deny", "ask"]
    assert {r["match"].get("action.command") for r in secret_reads if r["decision"] == "deny"} == {
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    }


def test_render_policy_yaml_includes_agent_run_allow_rules():
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    runners = {r["match"].get("action.type"): r["decision"]
               for r in doc["rules"]
               if r["match"].get("action.type", "").startswith("agent.run.")}
    assert runners == {"agent.run.codex": "allow", "agent.run.claude": "allow"}


def test_render_policy_yaml_universal_safety_rules_first():
    """force-push and the universal destructive shell rule must precede
    any profile-specific rule so the universal safety rails always win."""
    profile = _profile_with_policy_posture()
    doc = yaml.safe_load(factory_run._render_policy_yaml(profile, "demo"))
    first_two = doc["rules"][:2]
    types = [r["match"].get("action.type") for r in first_two]
    assert types == ["git.force_push", "shell.run"]
    assert first_two[0]["decision"] == "deny"
    assert first_two[1]["decision"] == "deny"


def test_profile_has_policy_posture_detects_policy_profile():
    profile = _profile_with_policy_posture()
    assert factory_run._profile_has_policy_posture(profile) is True


def test_profile_has_policy_posture_returns_false_for_evidence():
    """evidence profile carries no policy_posture block — runner must keep
    pointing at the static ao/policy/local-dev.yaml."""
    evidence = factory_run._load_profile("evidence")
    assert factory_run._profile_has_policy_posture(evidence) is False


def test_profile_has_policy_posture_returns_false_for_none():
    assert factory_run._profile_has_policy_posture(None) is False
