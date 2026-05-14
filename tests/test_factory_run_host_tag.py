"""Tests for v0.2 D2: per-role host_tag → RunSpec hostTags surfacing.

D1 + D3 shipped in ao-runtime: Task.host_tags + tag-aware coordinator
dispatch + worker-advertised tags via env or ~/.config/ao-worker.toml.

D2's job (this file): ao-operator profile JSONs declare host_tag per role,
factory_run.py validates the new optional schema field, _tasks_from_profile
projects it through, and runspec_body emits per-task hostTags lines ONLY
when --remote is passed. Default-mode output stays byte-for-byte identical
to v0.1.1 for any legacy profile (parity guarantee).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import factory_run


def _write_profile(tmp_path: Path, name: str, payload: dict) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    target = profiles_dir / f"{name}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _profile_with_host_tag(name: str, host_tag: object) -> dict:
    """Build a synthetic two-role profile where role `alpha` declares
    host_tag and role `beta` does not. Mirrors the loader test fixtures
    in tests/test_factory_run_profile_loader.py."""
    return {
        "profile": name,
        "schema": factory_run.PROFILE_SCHEMA_ID,
        "version": factory_run.PROFILE_VERSION,
        "description": "synthetic D2 host_tag fixture",
        "common_instructions": ["c1"],
        "roles": [
            {
                "id": "alpha",
                "role": "Alpha",
                "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
                "deps": [],
                "reads": ["task brief"],
                "writes": ["docs/<slug>/alpha.md"],
                "skills": [],
                "instructions": ["a1"],
                "host_tag": host_tag,
            },
            {
                "id": "beta",
                "role": "Beta",
                "provider_key": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
                "deps": ["alpha"],
                "reads": ["docs/<slug>/alpha.md"],
                "writes": ["docs/<slug>/beta.md"],
                "skills": [],
                "instructions": ["b1"],
            },
        ],
    }


def test_profile_loader_accepts_host_tag(tmp_path):
    payload = _profile_with_host_tag("synthetic", ["mac", "live"])
    _write_profile(tmp_path, "synthetic", payload)
    profile = factory_run._load_profile("synthetic", repo_root=tmp_path)
    alpha = profile["roles_by_id"]["alpha"]
    assert alpha["host_tag"] == ["mac", "live"]
    # Beta declared no host_tag; it must remain absent on the role dict.
    assert "host_tag" not in profile["roles_by_id"]["beta"]
    # Projection through _tasks_from_profile carries host_tag onto the task
    # dict that materialize()/runspec_body see.
    tasks = factory_run._tasks_from_profile(profile)
    by_id = {t["id"]: t for t in tasks}
    assert by_id["alpha"]["host_tag"] == ["mac", "live"]
    assert "host_tag" not in by_id["beta"]


def test_profile_loader_rejects_host_tag_non_list(tmp_path):
    # String, not list — must trip the validator with the exact message
    # specified in the D2 spec.
    payload = _profile_with_host_tag("synthetic", "mac")
    _write_profile(tmp_path, "synthetic", payload)
    with pytest.raises(
        factory_run.ProfileError,
        match=r"host_tag must be list\[str\] when present",
    ):
        factory_run._load_profile("synthetic", repo_root=tmp_path)


def _intake_for_runspec(slug: str = "synthetic-d2") -> factory_run.Intake:
    """Minimal Intake stub for runspec_body — only fields read by
    runspec_body are exercised (slug, plus dataclass invariants)."""
    return factory_run.Intake(
        slug=slug,
        brief_path=Path("/tmp/synthetic-brief.md"),
        brief="D2 host_tag synthetic fixture",
        classification="Code-Mod",
        shape="Single-File",
        blocked=False,
        blocker="none",
        acceptance=[],
        scoped_reads=[],
        scoped_writes=[],
    )


def _tasks_for_runspec() -> list[dict[str, object]]:
    return [
        {
            "id": "alpha",
            "role": "Alpha",
            "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
            "deps": [],
            "reads": [],
            "writes": [],
            "host_tag": ["mac"],
        },
        {
            "id": "beta",
            "role": "Beta",
            "provider_key": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
            "deps": ["alpha"],
            "reads": [],
            "writes": [],
            # No host_tag — must NOT receive a hostTags line even with
            # remote=True.
        },
    ]


def _providers_for_runspec() -> dict[str, str]:
    return {"alpha": "claude", "beta": "claude"}


def test_runspec_emits_host_tags_when_remote_true(tmp_path):
    intake = _intake_for_runspec()
    tasks = _tasks_for_runspec()
    providers = _providers_for_runspec()
    body = factory_run.runspec_body(
        intake, providers, tmp_path, tasks, remote=True
    )
    # Alpha declared host_tag=["mac"] → hostTags line appears under its task.
    assert 'hostTags: ["mac"]' in body
    # Beta declared no host_tag → no hostTags line for it. Stronger check:
    # only one hostTags line exists in the whole RunSpec.
    assert body.count("hostTags:") == 1
    # The hostTags line must appear in alpha's task block, before beta.
    alpha_idx = body.index("- id: alpha")
    beta_idx = body.index("- id: beta")
    host_tags_idx = body.index("hostTags:")
    assert alpha_idx < host_tags_idx < beta_idx


def test_runspec_omits_host_tags_when_remote_false(tmp_path):
    """Byte-for-byte parity guard: with --remote off, no hostTags line
    appears anywhere in the RunSpec, even for tasks whose role declared
    host_tag. This pins the v0.1.1 default-mode output contract.

    Uses an isolated workspace path under tmp_path that does NOT contain
    the substring 'hostTags' — pytest's tmp_path interpolates the test
    function name into the directory, so we route around it deliberately
    to keep this assertion strict.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    intake = _intake_for_runspec()
    tasks = _tasks_for_runspec()
    providers = _providers_for_runspec()
    body = factory_run.runspec_body(
        intake, providers, workspace, tasks, remote=False
    )
    assert "hostTags" not in body
    # Also assert byte-for-byte equivalence with the legacy code path
    # (remote=None falling through when the module flag is False, which
    # is the default after import). This is the v0.1.1 parity guard.
    factory_run._set_active_remote(False)
    try:
        legacy_body = factory_run.runspec_body(
            intake, providers, workspace, tasks
        )
    finally:
        # Reset module flag so test ordering doesn't leak state.
        factory_run._set_active_remote(False)
    assert body == legacy_body


def test_remote_node_mapping_uses_explicit_env_then_live_defaults():
    env = {"FACTORY_V3_REMOTE_NODE_FOR_TAGS_MAC_LIVE": "macbook-worker"}
    assert factory_run._remote_node_for_host_tags(["mac", "live"], env) == "macbook-worker"
    assert factory_run._remote_node_for_host_tags(["ubuntu"], {}) == "ubuntu-live-worker"
    assert factory_run._remote_node_for_host_tags([], {}) == "ubuntu-live-worker"
    assert factory_run._remote_node_for_host_tags(["windows", "live"], {}) == ""


def test_codex_manifest_sandbox_rewrite_changes_only_value():
    body = """apiVersion: ao.dev/v1
kind: AgentManifest
spec:
  command:
    - codex
    - exec
    - --sandbox
    - workspace-write
"""

    rewritten = factory_run._codex_manifest_with_sandbox(body, "danger-full-access")

    assert "    - --sandbox\n    - danger-full-access\n" in rewritten
    assert "workspace-write" not in rewritten


def test_remote_shell_evidence_instruction_is_windows_specific():
    windows = factory_run._remote_shell_evidence_instruction(["windows", "live"])
    ubuntu = factory_run._remote_shell_evidence_instruction(["ubuntu"])

    assert "PowerShell" in windows
    assert "Do not run `uname`" in windows
    assert "PowerShell" not in ubuntu


def test_runtime_capture_workspace_label_redacts_absolute_paths():
    assert (
        factory_run._runtime_capture_workspace_label(
            {"workspace": "/Users/example/private/ao-operator"}
        )
        == "${FACTORY_V3_ROOT}"
    )
    assert (
        factory_run._runtime_capture_workspace_label(
            {"workspace": "C:/Users/example/private/ao-operator"}
        )
        == "${FACTORY_V3_ROOT}"
    )
    assert (
        factory_run._runtime_capture_workspace_label({"workspace": "../ao-operator"})
        == "<redacted-workspace>"
    )
    assert factory_run._runtime_capture_workspace_label({"workspace": "workspace"}) == "workspace"


def test_three_os_live_dispatch_windows_role_uses_codex_sandbox_override():
    profile = factory_run._load_profile("three-os-live-dispatch")
    tasks = factory_run._tasks_from_profile(profile)
    by_id = {task["id"]: task for task in tasks}

    assert by_id["windows-live"]["codex_sandbox"] == "danger-full-access"
    assert "codex_sandbox" not in by_id["mac-live"]


def test_parse_topology_preserves_deterministic_replay_spec(tmp_path):
    topology = tmp_path / "topology.yaml"
    topology.write_text(
        """
spec:
  tasks:
    - id: deterministic-check
      deps: []
      spec:
        provider: codex
        deterministic: true
        replay_command: ["python3", "scripts/check_evidence_pack_readiness.py", "--json"]
        replay_outputs: ["deterministic-check.json"]
""",
        encoding="utf-8",
    )

    task = factory_run.parse_topology(topology, "demo", None)[0]

    assert task["deterministic"] is True
    assert task["replay_command"] == ["python3", "scripts/check_evidence_pack_readiness.py", "--json"]
    assert task["replay_outputs"] == ["deterministic-check.json"]
